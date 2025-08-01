# -*- Mode:Python; indent-tabs-mode:nil; tab-width:4 -*-
#
# Copyright 2017-2025 Canonical Ltd.
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License version 3 as published by the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""Definitions and helpers for part handlers."""

import logging
import os
import os.path
import shutil
from collections.abc import Callable, Mapping, Sequence
from glob import iglob
from pathlib import Path
from typing import Any, cast

from typing_extensions import Protocol

from craft_parts import callbacks, errors, overlays, packages, plugins, sources
from craft_parts.actions import Action, ActionType
from craft_parts.filesystem_mounts import FilesystemMount
from craft_parts.infos import PartInfo, StepInfo
from craft_parts.overlays import LayerHash, OverlayManager
from craft_parts.packages import errors as packages_errors
from craft_parts.packages.base import read_origin_stage_package
from craft_parts.packages.platform import is_deb_based
from craft_parts.parts import Part, get_parts_with_overlay, has_overlay_visibility
from craft_parts.plugins import Plugin
from craft_parts.state_manager import (
    MigrationContents,
    MigrationState,
    StepState,
    states,
)
from craft_parts.state_manager.stage_state import StageState
from craft_parts.steps import Step
from craft_parts.utils import file_utils, os_utils
from craft_parts.utils.partition_utils import DEFAULT_PARTITION

from . import filesets, migration
from .environment import generate_step_environment
from .errors import EnvironmentChangedError
from .organize import organize_files
from .step_handler import (
    StagePartitionContents,
    StepContents,
    StepHandler,
    StepPartitionContents,
    Stream,
)

logger = logging.getLogger(__name__)


# pylint: disable=too-many-lines


class _RunHandler(Protocol):
    def __call__(
        self,
        step_info: StepInfo,
        *,
        stdout: Stream,
        stderr: Stream,
    ) -> StepState: ...


class _UpdateHandler(Protocol):
    def __call__(
        self,
        step_info: StepInfo,
        *,
        stdout: Stream,
        stderr: Stream,
    ) -> None: ...


# map the source path to the destination path in the partition
_MigratedContents = dict[str, str]


class _Squasher:
    """A helper to squash layers and migrate layered content."""

    def __init__(
        self,
        partition: str | None,
        default_partition: str | None,
        filesystem_mount: FilesystemMount | None = None,
    ) -> None:
        self.migrated_files: dict[str | None, _MigratedContents] = {partition: {}}
        self.migrated_directories: dict[str | None, _MigratedContents] = {partition: {}}
        self._src_partition = partition
        self._default_partition = default_partition
        if filesystem_mount:
            self._filesystem_mount = filesystem_mount

    def migrate(
        self,
        srcdir: Path,
        destdirs: Mapping[str | None, Path],
    ) -> None:
        """Migrate layered content from a partition to destination directories.

        If the source partition is the default one, content can be distributed to other
        partitions using the provided filesystem mounts.
        """
        if (
            self._src_partition is not None
            and self._src_partition == self._default_partition
        ):
            # Distribute content into partitions according to the filesystem mounts
            for entry in reversed(self._filesystem_mount):
                # Only migrate content from the subdirectory indicated by the filesystem mounts
                # entry
                sub_path = entry.mount.lstrip("/")
                dst_partition = entry.device

                # Migrate to the destination partition indicated by the filesystem mounts entry
                self._migrate(
                    srcdir=srcdir,
                    destdir=destdirs[dst_partition],
                    sub_path=sub_path,
                    dst_partition=dst_partition,
                )
        else:
            # Ignore the filesystem mounts and migrate from/to the same partition
            self._migrate(
                srcdir=srcdir,
                destdir=destdirs[self._src_partition],
                sub_path="",
                dst_partition=self._src_partition,
            )

    def _migrate(
        self,
        srcdir: Path,
        destdir: Path,
        sub_path: str,
        dst_partition: str | None,
    ) -> None:
        """Actually migrate content from a source to a destination.

        Associate the lists of migrated content to the partition in a map to
        later store it in the proper state.
        """
        visible_files, visible_dirs = overlays.visible_in_layer(
            srcdir / sub_path,
            destdir,
        )
        logger.debug(f"excluding already migrated files: {self._all_migrated_files}")
        visible_files = visible_files - self._all_migrated_files
        logger.debug(
            f"excluding already migrated dirs: {self._all_migrated_directories}"
        )
        visible_dirs = visible_dirs - self._all_migrated_directories

        layer_files, layer_dirs = migration.migrate_files(
            files=visible_files,
            dirs=visible_dirs,
            srcdir=srcdir / sub_path,
            destdir=destdir,
            oci_translation=True,
        )
        if dst_partition not in self.migrated_files:
            self.migrated_files[dst_partition] = {}

        for f in layer_files:
            src_path = str(Path(sub_path) / f)
            self.migrated_files[dst_partition][src_path] = f

        if dst_partition not in self.migrated_directories:
            self.migrated_directories[dst_partition] = {}

        for f in layer_dirs:
            src_path = str(Path(sub_path) / f)
            self.migrated_directories[dst_partition][src_path] = f

    @property
    def _all_migrated_files(self) -> set[str]:
        """Merge lists of files migrated to every partitions.

        Return a list of paths relative to the source partition.
        """
        migrated_files: set[str] = set()
        for m in self.migrated_files.values():
            migrated_files |= set(m)
        return migrated_files

    @property
    def _all_migrated_directories(self) -> set[str]:
        """Merge lists of directories migrated to every partitions.

        Return a list of paths relative to the source partition.
        """
        migrated_directories: set[str] = set()
        for m in self.migrated_directories.values():
            migrated_directories |= set(m)
        return migrated_directories


class PartHandler:
    """Handle lifecycle steps for a part.

    :param part: The part being processed.
    :param part_info: Information about the part being processed.
    :param part_list: A list containing all parts.
    """

    def __init__(
        self,
        part: Part,
        *,
        part_info: PartInfo,
        part_list: list[Part],
        track_stage_packages: bool = False,
        overlay_manager: OverlayManager,
        ignore_patterns: list[str] | None = None,
        base_layer_hash: LayerHash | None = None,
    ) -> None:
        self._part = part
        self._part_info = part_info
        self._part_list = part_list
        self._track_stage_packages = track_stage_packages
        self._overlay_manager = overlay_manager
        self._base_layer_hash = base_layer_hash
        self._app_environment: dict[str, str] = {}

        self._plugin = plugins.get_plugin(
            part=part,
            properties=part.plugin_properties,
            part_info=part_info,
        )

        self._part_properties = {
            **part.spec.marshal(),
            **part.plugin_properties.marshal(),
        }

        self._source_handler = sources.get_source_handler(
            cache_dir=part_info.cache_dir,
            part=part,
            project_dirs=part_info.dirs,
            ignore_patterns=ignore_patterns,
        )

        self.build_packages = _get_build_packages(part=self._part, plugin=self._plugin)
        self.build_snaps = _get_build_snaps(part=self._part, plugin=self._plugin)

    def run_action(
        self,
        action: Action,
        *,
        stdout: Stream = None,
        stderr: Stream = None,
    ) -> None:
        """Execute the given action for this part using a plugin.

        :param action: The action to execute.
        """
        step_info = StepInfo(self._part_info, action.step)

        if action.action_type == ActionType.UPDATE:
            self._update_action(
                action,
                step_info=step_info,
                stdout=stdout,
                stderr=stderr,
            )
            return

        if action.action_type == ActionType.REAPPLY:
            self._reapply_action(
                action, step_info=step_info, stdout=stdout, stderr=stderr
            )
            return

        if action.action_type == ActionType.RERUN:
            for step in [action.step, *action.step.next_steps()]:
                self.clean_step(step=step)

        handler: _RunHandler

        if action.step == Step.PULL:
            handler = self._run_pull
        elif action.step == Step.OVERLAY:
            handler = self._run_overlay
        elif action.step == Step.BUILD:
            handler = self._run_build
            self._plugin.set_action_properties(action.properties)
        elif action.step == Step.STAGE:
            handler = self._run_stage
        elif action.step == Step.PRIME:
            handler = self._run_prime
        else:
            raise RuntimeError(f"cannot run action for invalid step {action.step!r}")

        callbacks.run_pre_step(step_info)
        state = handler(step_info, stdout=stdout, stderr=stderr)
        state_file = states.get_step_state_path(self._part, action.step)
        state.write(state_file)
        step_info.state = state
        callbacks.run_post_step(step_info)

    def _run_pull(
        self,
        step_info: StepInfo,
        *,
        stdout: Stream,
        stderr: Stream,
    ) -> StepState:
        """Execute the pull step for this part.

        :param step_info: Information about the step to execute.

        :return: The pull step state.
        """
        _remove(self._part.part_src_dir)
        self._make_dirs()

        fetched_packages = self._fetch_stage_packages(step_info=step_info)
        fetched_snaps = self._fetch_stage_snaps()
        self._fetch_overlay_packages()

        self._run_step(
            step_info=step_info,
            scriptlet_name="override-pull",
            work_dir=self._part.part_src_dir,
            stdout=stdout,
            stderr=stderr,
        )

        return states.PullState(
            part_properties=self._part_properties,
            project_options=step_info.project_options,
            assets={
                "stage-packages": fetched_packages,
                "stage-snaps": fetched_snaps,
                "source-details": getattr(self._source_handler, "source_details", None),
            },
        )

    def _run_overlay(
        self,
        step_info: StepInfo,
        *,
        stdout: Stream,
        stderr: Stream,
    ) -> StepState:
        """Execute the overlay step for this part.

        :param step_info: Information about the step to execute.

        :return: The overlay step state.
        """
        self._make_dirs()

        if self._part.has_overlay:
            # install overlay packages
            overlay_packages = self._part.spec.overlay_packages
            if overlay_packages:
                with overlays.LayerMount(
                    self._overlay_manager, top_part=self._part
                ) as ctx:
                    ctx.install_packages(overlay_packages)

            # execute overlay script
            with overlays.LayerMount(self._overlay_manager, top_part=self._part):
                contents = self._run_step(
                    step_info=step_info,
                    scriptlet_name="overlay-script",
                    work_dir=self._part.part_layer_dir,
                    stdout=stdout,
                    stderr=stderr,
                )

            # apply overlay filter
            overlay_fileset = filesets.Fileset(
                self._part.spec.overlay_files, name="overlay"
            )
            destdir = self._part.part_layer_dir
            files, dirs = filesets.migratable_filesets(
                overlay_fileset,
                str(destdir),
                self._part_info.default_partition,
                self._part_info.default_partition,
            )
            _apply_file_filter(filter_files=files, filter_dirs=dirs, destdir=destdir)
        else:
            contents = StepContents()

        partitions_contents: dict[str, MigrationContents] = {
            p: MigrationContents(files=c.files, directories=c.dirs)
            for p, c in contents.partitions_contents.items()
            if not self._part_info.is_default_partition(p)
        }

        layer_hash = self._compute_layer_hash(all_parts=False)
        layer_hash.save(self._part)

        default_contents = contents.partitions_contents.get(
            self._part_info.default_partition, StepPartitionContents()
        )

        return states.OverlayState(
            part_properties=self._part_properties,
            project_options=step_info.project_options,
            partitions_contents=partitions_contents,
            files=default_contents.files,
            directories=default_contents.dirs,
        )

    def _run_build(
        self,
        step_info: StepInfo,
        *,
        stdout: Stream,
        stderr: Stream,
        update: bool = False,
    ) -> StepState:
        """Execute the build step for this part.

        :param step_info: Information about the step to execute.

        :return: The build step state.
        """
        self._make_dirs()
        self._unpack_stage_packages()
        self._unpack_stage_snaps()

        if not update and not self._plugin.get_out_of_source_build():
            _remove(self._part.part_build_dir)

            # Copy source from the part source dir to the part build dir
            shutil.copytree(
                self._part.part_src_dir, self._part.part_build_dir, symlinks=True
            )

        # Perform the build step
        if has_overlay_visibility(self._part, part_list=self._part_list):
            with overlays.LayerMount(self._overlay_manager, top_part=self._part):
                self._run_step(
                    step_info=step_info,
                    scriptlet_name="override-build",
                    work_dir=self._part.part_build_dir,
                    stdout=stdout,
                    stderr=stderr,
                )
        else:
            self._run_step(
                step_info=step_info,
                scriptlet_name="override-build",
                work_dir=self._part.part_build_dir,
                stdout=stdout,
                stderr=stderr,
            )

        # Organize the installed files as requested. We do this in the build step for
        # two reasons:
        #
        #   1. So cleaning and re-running the stage step works even if `organize` is
        #      used
        #   2. So collision detection takes organization into account, i.e. we can use
        #      organization to get around file collisions between parts when staging.
        #
        # If `update` is true, we give permission to overwrite files that already exist.
        # Typically we do NOT want this, so that parts don't accidentally clobber e.g.
        # files brought in from stage-packages, but in the case of updating build, we
        # want the part to have the ability to organize over the files it organized last
        # time around. We can be confident that this won't overwrite anything else,
        # because to do so would require changing the `organize` keyword, which will
        # make the build step dirty and require a clean instead of an update.
        organize_files(
            part_name=self._part.name,
            file_map=self._part.spec.organize_files,
            install_dir_map=self._part.part_install_dirs,
            overwrite=update,
            default_partition=step_info.default_partition,
        )

        assets = {
            "build-packages": self.build_packages,
            "build-snaps": self.build_snaps,
        }
        assets.update(_get_machine_manifest())

        # Overlay integrity is checked based by the hash of its last (topmost) layer,
        # so we compute it for all parts. The overlay hash is added to the build state
        # to ensure proper build step invalidation of parts that can see the overlay
        # filesystem if overlay contents change.
        overlay_hash = self._compute_layer_hash(all_parts=True)

        return states.BuildState(
            part_properties=self._part_properties,
            project_options=step_info.project_options,
            assets=assets,
            overlay_hash=overlay_hash.hex(),
        )

    def _run_stage(
        self,
        step_info: StepInfo,
        *,
        stdout: Stream,
        stderr: Stream,
    ) -> StepState:
        """Execute the stage step for this part.

        :param step_info: Information about the step to execute.

        :return: The stage step state.
        """
        self._make_dirs()

        contents = self._run_step(
            step_info=step_info,
            scriptlet_name="override-stage",
            work_dir=self._part.stage_dir,
            stdout=stdout,
            stderr=stderr,
        )

        self._migrate_overlay_files_to_stage()

        # Overlay integrity is checked based by the hash of its last (topmost) layer,
        # so we compute it for all parts. The overlay hash is added to the stage state
        # to ensure proper stage step invalidation of parts that declare overlay
        # parameters if overlay contents change.
        overlay_hash = self._compute_layer_hash(all_parts=True)

        migration_partitions_contents: dict[str, MigrationContents] = {
            p: MigrationContents(files=c.files, directories=c.dirs)
            for p, c in contents.partitions_contents.items()
            if not self._part_info.is_default_partition(p)
        }

        default_partition = self._part_info.default_partition or DEFAULT_PARTITION
        default_contents = cast(
            StagePartitionContents,
            contents.partitions_contents.get(
                default_partition, StagePartitionContents()
            ),
        )

        return states.StageState(
            partition=default_partition,
            part_properties=self._part_properties,
            project_options=step_info.project_options,
            partitions_contents=migration_partitions_contents,
            files=contents.partitions_contents[default_partition].files,
            directories=contents.partitions_contents[default_partition].dirs,
            overlay_hash=overlay_hash.hex(),
            backstage_files=default_contents.backstage_files,
            backstage_directories=default_contents.backstage_dirs,
        )

    def _run_prime(
        self,
        step_info: StepInfo,
        *,
        stdout: Stream,
        stderr: Stream,
    ) -> StepState:
        """Execute the prime step for this part.

        :param step_info: Information about the step to execute.

        :return: The prime step state.
        """
        self._make_dirs()

        contents = self._run_step(
            step_info=step_info,
            scriptlet_name="override-prime",
            work_dir=self._part.prime_dir,
            stdout=stdout,
            stderr=stderr,
        )

        self._migrate_overlay_files_to_prime()
        default_partition = self._part_info.default_partition or DEFAULT_PARTITION

        if (
            self._part.spec.stage_packages
            and self._track_stage_packages
            and is_deb_based()
        ):
            prime_dirs = list(self._part.prime_dirs.values())
            primed_stage_packages = _get_primed_stage_packages(
                contents.partitions_contents[default_partition].files,
                prime_dirs=prime_dirs,
            )
        else:
            primed_stage_packages = set()

        non_default_partitions_contents: dict[str, MigrationContents] = {
            p: MigrationContents(files=c.files, directories=c.dirs)
            for p, c in contents.partitions_contents.items()
            if not self._part_info.is_default_partition(p)
        }

        return states.PrimeState(
            partition=default_partition,
            part_properties=self._part_properties,
            project_options=step_info.project_options,
            partitions_contents=non_default_partitions_contents,
            files=contents.partitions_contents[default_partition].files,
            directories=contents.partitions_contents[default_partition].dirs,
            primed_stage_packages=primed_stage_packages,
        )

    def _run_step(
        self,
        *,
        step_info: StepInfo,
        scriptlet_name: str,
        work_dir: Path,
        stdout: Stream,
        stderr: Stream,
    ) -> StepContents:
        """Run the scriptlet if overriding, otherwise run the built-in handler.

        :param step_info: Information about the step to execute.
        :param scriptlet_name: The name of this step's scriptlet.
        :param work_dir: The path to run the scriptlet on.

        :return: If step is Stage or Prime, return a tuple of sets containing
            the step's file and directory artifacts.
        """
        step_env = generate_step_environment(
            part=self._part, plugin=self._plugin, step_info=step_info
        )

        if step_info.step == Step.BUILD:
            # Validate build environment. Unlike the pre-validation we did in
            # the execution prologue, we don't assume that a different part
            # can add elements to the build environment. All part dependencies
            # have already ran at this point.
            validator = self._plugin.validator_class(
                part_name=step_info.part_name,
                env=step_env,
                properties=self._part.plugin_properties,
            )
            validator.validate_environment()

        step_handler = StepHandler(
            self._part,
            step_info=step_info,
            plugin=self._plugin,
            source_handler=self._source_handler,
            env=step_env,
            stdout=stdout,
            stderr=stderr,
            partitions=self._part_info.partitions,
        )

        scriptlet = self._part.spec.get_scriptlet(step_info.step)
        if scriptlet is not None:
            step_handler.run_scriptlet(
                scriptlet,
                scriptlet_name=scriptlet_name,
                step=step_info.step,
                work_dir=work_dir,
            )
            return StepContents(stage=step_info.step == Step.STAGE)

        return step_handler.run_builtin()

    def _compute_layer_hash(self, *, all_parts: bool) -> LayerHash:
        """Obtain the layer verification hash.

        The layer verification hash is computed as a digest of layer parameters
        from the first layer up to layer being processed. The integrity of the
        complete overlay stack is verified against the hash of its last (topmost)
        layer.

        :param all_parts: Compute the layer for all parts instead of stopping
            at the current layer. This is used to obtain the verification hash
            for the complete overlay stack.

        :returns: The layer verification hash.
        """
        part_hash = self._base_layer_hash

        for part in self._part_list:
            part_hash = LayerHash.for_part(part, previous_layer_hash=part_hash)
            if not all_parts and part.name == self._part.name:
                break

        if not part_hash:
            raise RuntimeError("could not compute layer hash")

        return part_hash

    def _update_action(
        self,
        action: Action,
        *,
        step_info: StepInfo,
        stdout: Stream,
        stderr: Stream,
    ) -> None:
        """Call the appropriate update handler for the given step."""
        handler: _UpdateHandler

        if action.step == Step.PULL:
            handler = self._update_pull
        elif action.step == Step.OVERLAY:
            handler = self._update_overlay
        elif action.step == Step.BUILD:
            handler = self._update_build
            self._plugin.set_action_properties(action.properties)
        else:
            step_name = action.step.name.lower()
            raise errors.InvalidAction(
                f"cannot update step {step_name!r} of {self._part.name!r}"
            )

        callbacks.run_pre_step(step_info)
        handler(step_info, stdout=stdout, stderr=stderr)

        # update state with updated files and dirs
        state_file = states.get_step_state_path(self._part, action.step)
        if action.step == Step.PULL:
            state = states.load_step_state(self._part, action.step)
            if state:
                new_state = states.PullState(
                    part_properties=state.part_properties,
                    project_options=state.project_options,
                    assets=cast(states.PullState, state).assets,
                    outdated_files=action.properties.changed_files,
                    outdated_dirs=action.properties.changed_dirs,
                )
                new_state.write(state_file)
        else:
            state_file.touch()

        callbacks.run_post_step(step_info)

    def _update_pull(
        self, step_info: StepInfo, *, stdout: Stream, stderr: Stream
    ) -> None:
        """Handle update action for the pull step.

        This handler is called if the pull step is outdated. In this case,
        invoke the source update method.

        :param step_info: The step information.
        """
        self._make_dirs()

        # if there's an override-pull scriptlet, execute it instead
        if self._part.spec.override_pull:
            self._run_step(
                step_info=step_info,
                scriptlet_name="override-pull",
                work_dir=self._part.part_src_dir,
                stdout=stdout,
                stderr=stderr,
            )
            return

        # the sequencer won't generate update actions for parts without
        # source, but they can be created manually
        if not self._source_handler:
            logger.warning(
                "Update requested on part %r without a source handler.",
                self._part.name,
            )
            return

        # the update action is sequenced only if an update is required and the
        # source knows how to update
        state_file = states.get_step_state_path(self._part, step_info.step)
        self._source_handler.check_if_outdated(str(state_file))
        self._source_handler.update()

    def _update_overlay(
        self, step_info: StepInfo, *, stdout: Stream, stderr: Stream
    ) -> None:
        """Handle update action for the overlay step.

        The overlay update handler is empty (out of date overlay must not rerun,
        otherwise its state will be cleaned and build will run again instead of
        just updating).

        :param step_info: The step information.
        """

    def _update_build(
        self, step_info: StepInfo, *, stdout: Stream, stderr: Stream
    ) -> None:
        """Handle update action for the build step.

        This handler is called if the build step is outdated. In this case,
        rebuild without cleaning the current build tree contents.

        :param step_info: The step information.
        """
        if not self._plugin.get_out_of_source_build():
            # Use the local source to update. It's important to use
            # file_utils.copy instead of link_or_copy, as the build process
            # may modify these files
            source = sources.LocalSource(
                self._part.part_src_dir,
                self._part.part_build_dir,
                copy_function=file_utils.copy,
                cache_dir=step_info.cache_dir,
                project_dirs=self._part.dirs,
            )
            state_file = states.get_step_state_path(self._part, step_info.step)
            source.check_if_outdated(str(state_file))  # required by source.update()
            source.update()

        _remove(self._part.part_install_dir)

        self._run_build(step_info, stdout=stdout, stderr=stderr, update=True)

    def _reapply_action(
        self,
        action: Action,
        *,
        step_info: StepInfo,
        stdout: Stream,
        stderr: Stream,
    ) -> None:
        """Call the appropriate reapply handler for the given step."""
        if action.step == Step.OVERLAY:
            self._reapply_overlay(step_info, stdout=stdout, stderr=stderr)
        else:
            step_name = action.step.name.lower()
            raise errors.InvalidAction(
                f"cannot reapply step {step_name!r} of {self._part.name!r}"
            )

    def _reapply_overlay(
        self, step_info: StepInfo, *, stdout: Stream, stderr: Stream
    ) -> None:
        """Clean and repopulate the current part's layer, keeping its state."""
        # delete partition layer dirs, if any
        for partition in self._part_info.partitions or (None,):
            _remove(self._part.part_layer_dirs[partition])

        self._run_overlay(step_info, stdout=stdout, stderr=stderr)

    def _migrate_overlay_files_to_stage(self) -> None:
        """Stage overlay files create state.

        Files and directories are migrated from overlay to stage based on a
        list of visible overlay entries, converting overlayfs whiteout files
        and opaque dirs to OCI.

        Files and directories can be migrated from the default partition to
        any other partition. In the state stored in the workdir files/dirs
        moved between partitions are tracked in the destination, with a path
        relative to the destination.
        """
        parts_with_overlay = get_parts_with_overlay(part_list=self._part_list)
        if self._part not in parts_with_overlay:
            return

        logger.debug("staging overlay files")

        consolidated_states: dict[str | None, MigrationState] = {}

        # process parts in each partition
        for src_partition in self._part_info.partitions or (None,):
            stage_overlay_state_path = states.get_overlay_migration_state_path(
                self._part.overlay_dirs[src_partition], Step.STAGE
            )

            # Overlay data is migrated to stage only when the first part declaring overlay
            # parameters is migrated.
            if stage_overlay_state_path.exists():
                logger.debug(
                    f"stage overlay migration state exists, not migrating overlay data for partition {src_partition}"
                )
                continue

            squasher = _Squasher(
                partition=src_partition,
                default_partition=self._part_info.default_partition,
                filesystem_mount=self._part_info.default_filesystem_mount,
            )
            # Process layers from top to bottom (reversed)
            for part in reversed(parts_with_overlay):
                logger.debug(
                    "migrate %s partition part %r layer to stage",
                    src_partition,
                    part.name,
                )
                squasher.migrate(
                    srcdir=part.part_layer_dirs[src_partition],
                    destdirs=part.stage_dirs,
                )

            _consolidate_states(
                consolidated_states=consolidated_states,
                migrated_files=squasher.migrated_files,
                migrated_directories=squasher.migrated_directories,
            )

        # Write consolidated states once
        self._write_overlay_migration_states(consolidated_states, Step.STAGE)

    def _migrate_overlay_files_to_prime(self) -> None:
        """Prime overlay files and create state.

        Files and directories are migrated from stage to prime, including
        OCI-compatible whiteout files and opaque directories.
        """
        parts_with_overlay = get_parts_with_overlay(part_list=self._part_list)
        if self._part not in parts_with_overlay:
            return

        logger.debug("priming overlay files")

        migration_states: dict[str | None, MigrationState] = {}

        # Process each partition.
        for partition in self._part_info.partitions or (None,):
            prime_overlay_state_path = states.get_overlay_migration_state_path(
                self._part.overlay_dirs[partition], Step.PRIME
            )

            # Overlay data is migrated to prime only when the first part declaring overlay
            # parameters is migrated.
            if prime_overlay_state_path.exists():
                logger.debug(
                    f"prime overlay migration state exists, not migrating overlay data for partition {partition}"
                )
                continue

            # Read the STAGE overlay migration state to know what was migrated from the overlay
            stage_overlay_migration_state = states.load_overlay_migration_state(
                self._part.overlay_dirs[partition], Step.STAGE
            )
            if not stage_overlay_migration_state:
                logger.debug(
                    f"stage overlay migration state does not exist, so no overlay content was migrated to stage for partition {partition}, so no overlay content to prime."
                )
                continue

            migrated_files, migrated_dirs = migration.migrate_files(
                files=stage_overlay_migration_state.files,
                dirs=stage_overlay_migration_state.directories,
                srcdir=self._part.dirs.get_stage_dir(partition),
                destdir=self._part.dirs.get_prime_dir(partition),
                permissions=self._part.spec.permissions,
            )

            if self._part_info.is_default_partition(partition):
                # The default partition is the only one that will be applied on top
                # of the base layer, so clean dangling whiteouts
                self._clean_dangling_whiteouts(
                    self._part_info.prime_dirs[partition],
                    migrated_files,
                    migrated_dirs,
                )
            else:
                # Other partitions are not applied on a base layer, clean all whiteouts
                self._clean_all_whiteouts(
                    self._part_info.prime_dirs[partition],
                    migrated_files,
                )

            migration_states[partition] = MigrationState(
                files=migrated_files, directories=migrated_dirs
            )

        self._write_overlay_migration_states(migration_states, Step.PRIME)

    def _write_overlay_migration_states(
        self, consolidated_states: dict[str | None, MigrationState], step: Step
    ) -> None:
        """Write an overlay migration state for each partition with overlay content.

        Do not overwrite an existing migration state file.
        """
        for partition in self._part_info.partitions or (None,):
            step_overlay_state_path = states.get_overlay_migration_state_path(
                self._part.overlay_dirs[partition],
                step,
            )
            if step_overlay_state_path.exists():
                logger.debug(
                    "%s overlay migration state exists, not overwriting migrated overlay data",
                    step.name,
                )
                continue
            state = consolidated_states.get(partition)
            if state:
                state.write(step_overlay_state_path)

    def _clean_dangling_whiteouts(
        self, prime_dir: Path, migrated_files: set[str], migrated_dirs: set[str]
    ) -> None:
        """Clean up dangling whiteout files with no backing files to white out."""
        dangling_whiteouts = migration.filter_dangling_whiteouts(
            migrated_files, migrated_dirs, base_dir=self._overlay_manager.base_layer_dir
        )
        self._clean_whiteouts(prime_dir, dangling_whiteouts)

    def _clean_all_whiteouts(self, prime_dir: Path, migrated_files: set[str]) -> None:
        """Clean up all whiteout files."""
        all_whiteouts = migration.filter_all_whiteouts(migrated_files)
        self._clean_whiteouts(prime_dir, all_whiteouts)

    def _clean_whiteouts(self, prime_dir: Path, whiteouts: set[str]) -> None:
        """Clean up whiteout files."""
        for whiteout in whiteouts:
            primed_whiteout = prime_dir / whiteout
            try:
                primed_whiteout.unlink()
                logger.debug("unlinked '%s'", str(primed_whiteout))
            except OSError as err:
                # XXX: fuse-overlayfs creates a .wh..opq file in part layer dir?
                logger.debug("error unlinking '%s': %s", str(primed_whiteout), err)

    def clean_step(self, step: Step) -> None:
        """Remove the work files and the state of the given step.

        :param step: The step to clean.
        """
        logger.debug("clean %s:%s", self._part.name, step)

        handler: Callable[[], None]

        if step == Step.PULL:
            handler = self._clean_pull
        elif step == Step.OVERLAY:
            handler = self._clean_overlay
        elif step == Step.BUILD:
            handler = self._clean_build
        elif step == Step.STAGE:
            handler = self._clean_stage
        elif step == Step.PRIME:
            handler = self._clean_prime
        else:
            raise RuntimeError(
                f"Attempt to clean invalid step {step!r} in part {self._part!r}."
            )

        handler()
        states.remove(self._part, step)

    def _clean_pull(self) -> None:
        """Remove the current part's pull step files and state."""
        # remove dirs where stage packages and snaps are fetched
        _remove(self._part.part_packages_dir)
        _remove(self._part.part_snaps_dir)

        # remove the source tree
        _remove(self._part.part_src_dir)

    def _clean_overlay(self) -> None:
        """Remove the current part' s layer data and verification hash."""
        for partition in self._part_info.partitions or (None,):
            _remove(self._part.part_layer_dirs[partition])
        _remove(self._part.part_state_dir / "layer_hash")

    def _clean_build(self) -> None:
        """Remove the current part's build step files and state."""
        _remove(self._part.part_build_dir)
        for install_dir in self._part.part_install_dirs.values():
            _remove(install_dir)

        _remove(self._part.part_export_dir)

    def _clean_stage(self) -> None:
        """Remove the current part's stage step files and state."""
        for (
            partition,
            stage_dir,
        ) in self._part.stage_dirs.items():  # iterate over partitions
            self._clean_shared(Step.STAGE, partition=partition, shared_dir=stage_dir)

        migration.clean_backstage(
            part_name=self._part.name,
            shared_dir=self._part.backstage_dir,
            part_states=cast(
                dict[str, StageState], _load_part_states(Step.STAGE, self._part_list)
            ),
        )

    def _clean_prime(self) -> None:
        """Remove the current part's prime step files and state."""
        for (
            partition,
            prime_dir,
        ) in self._part.prime_dirs.items():  # iterate over partitions
            self._clean_shared(Step.PRIME, partition=partition, shared_dir=prime_dir)

    def _clean_shared(
        self, step: Step, *, partition: str | None, shared_dir: Path
    ) -> None:
        """Remove the current part's shared files from the given directory.

        :param step: The step corresponding to the shared directory.
        :param shared_dir: The shared directory to clean.
        """
        logger.debug(
            f"clean shared dir: {shared_dir} for step: {step} for partition {partition}"
        )
        part_states = _load_part_states(step, self._part_list)
        overlay_migration_state = states.load_overlay_migration_state(
            self._part.overlay_dirs[partition], step
        )

        migration.clean_shared_area(
            part_name=self._part.name,
            shared_dir=shared_dir,
            part_states=part_states,
            overlay_migration_state=overlay_migration_state,
            partition=partition,
        )

        parts_with_overlay_in_step = _parts_with_overlay_in_step(
            step, part_list=self._part_list
        )

        # remove overlay data if this is the last part with overlay
        if self._part.has_overlay and len(parts_with_overlay_in_step) == 1:
            migration.clean_shared_overlay(
                shared_dir=shared_dir,
                part_states=part_states,
                overlay_migration_state=overlay_migration_state,
                partition=partition,
            )
            overlay_migration_state_path = states.get_overlay_migration_state_path(
                self._part.overlay_dirs[partition], step
            )
            logger.info(
                f"remove overlay migration state file for part {self._part.name}, step {step}"
            )
            overlay_migration_state_path.unlink()

    def _symlink_alias_to_default(self) -> None:
        """Create directory and symlinks for the alias of the default partition.

        These symlinks are never consumed by craft-parts. They are created to help
        users debugging a build.
        """
        if not self._part_info.is_default_partition_aliased:
            return
        default_partition = self._part_info.default_partition
        logger.debug("Create symlinks for %s", default_partition)
        self._part_info.alias_partition_dir.mkdir(parents=True, exist_ok=True)

        for src, dst in [
            (self._part_info.parts_dir, self._part_info.parts_alias_symlink),
            (self._part_info.stage_dir, self._part_info.stage_alias_symlink),
            (self._part_info.prime_dir, self._part_info.prime_alias_symlink),
            (self._part_info.overlay_dir, self._part_info.overlay_alias_symlink),
        ]:
            if dst.exists():
                if not dst.is_symlink():
                    # Between two runs of the lifecycle, the default partition alias name
                    # can be changed to a previously concrete partition by the user.
                    raise EnvironmentChangedError(
                        f"cannot create symlinks {dst}, a concrete directory already exists."
                    )
                # The symlink already exists
                continue
            os.symlink(
                src,
                dst,
                target_is_directory=True,
            )

    def _make_dirs(self) -> None:
        dirs = [
            self._part.part_src_dir,
            self._part.part_build_dir,
            self._part.part_export_dir,
            *self._part.part_install_dirs.values(),
            self._part.part_layer_dir,
            *self._part.part_layer_dirs.values(),
            self._part.part_state_dir,
            self._part.part_run_dir,
            *self._part.stage_dirs.values(),
            *self._part.prime_dirs.values(),
            *self._part.overlay_dirs.values(),
        ]
        for dir_name in dirs:
            os.makedirs(dir_name, exist_ok=True)

        self._symlink_alias_to_default()

    def _fetch_stage_packages(self, *, step_info: StepInfo) -> list[str] | None:
        """Download stage packages to the part's package directory.

        :raises StagePackageNotFound: If a package is not available for download.
        """
        stage_packages = self._part.spec.stage_packages
        if not stage_packages:
            return None

        try:
            logger.info("Fetching stage-packages")
            fetched_packages = packages.Repository.fetch_stage_packages(
                cache_dir=step_info.cache_dir,
                package_names=stage_packages,
                arch=step_info.host_arch,
                base=step_info.base,
                stage_packages_path=self._part.part_packages_dir,
            )
        except packages_errors.PackageNotFound as err:
            raise errors.StagePackageNotFound(
                part_name=self._part.name, package_name=err.package_name
            ) from err

        return fetched_packages

    def _fetch_stage_snaps(self) -> Sequence[str] | None:
        """Download snap packages to the part's snap directory."""
        stage_snaps = self._part.spec.stage_snaps
        if not stage_snaps:
            return None

        packages.snaps.download_snaps(
            snaps_list=stage_snaps, directory=str(self._part.part_snaps_dir)
        )

        return stage_snaps

    def _fetch_overlay_packages(self) -> None:
        """Download overlay packages to the local package cache.

        :raises OverlayPackageNotFound: If a package is not available for download.
        """
        overlay_packages = self._part.spec.overlay_packages
        if not overlay_packages:
            return

        try:
            with overlays.PackageCacheMount(self._overlay_manager) as ctx:
                logger.info("Fetching overlay-packages")
                ctx.download_packages(overlay_packages)
        except packages_errors.PackageNotFound as err:
            raise errors.OverlayPackageNotFound(
                part_name=self._part.name, package_name=err.package_name
            ) from err

    def _unpack_stage_packages(self) -> None:
        """Extract stage packages contents to the part's install directory."""
        pulled_packages = None

        pull_state = states.load_step_state(self._part, Step.PULL)
        if pull_state is not None:
            pull_state = cast(states.PullState, pull_state)
            pulled_packages = pull_state.assets.get("stage-packages")

        packages.Repository.unpack_stage_packages(
            stage_packages_path=self._part.part_packages_dir,
            install_path=Path(self._part.part_install_dir),
            stage_packages=pulled_packages,
            track_stage_packages=self._track_stage_packages,
        )

    def _unpack_stage_snaps(self) -> None:
        """Extract stage snap contents to the part's install directory."""
        stage_snaps = self._part.spec.stage_snaps
        if not stage_snaps:
            return

        snaps_dir = self._part.part_snaps_dir
        install_dir = self._part.part_install_dir

        logger.debug("Unpacking stage-snaps to %s", install_dir)

        snap_files = iglob(os.path.join(snaps_dir, "*.snap"))
        snap_sources = (
            sources.SnapSource(
                source=s,
                part_src_dir=snaps_dir,
                cache_dir=self._part_info.cache_dir,
                project_dirs=self._part.dirs,
            )
            for s in snap_files
        )

        for snap_source in snap_sources:
            snap_source.provision(install_dir, keep=True)


def _remove(filename: Path) -> None:
    """Remove the given directory entry.

    :param filename: The path to the file or directory to remove.
    """
    if filename.is_symlink() or filename.is_file():
        logger.debug("remove file %s", filename)
        filename.unlink()
    elif filename.is_dir():
        logger.debug("remove directory %s", filename)
        shutil.rmtree(filename)


def _apply_file_filter(
    *, filter_files: set[str], filter_dirs: set[str], destdir: Path
) -> None:
    """Remove files and directories from the filesystem.

    Files and directories that are not part of the given file and directory
    sets will be removed from the filesystem.

    :param filter_files: The set of files to keep.
    :param filter_dirs: The set of directories to keep.
    """
    for root, directories, files in os.walk(destdir, topdown=True):
        for file_name in files:
            path = Path(root, file_name)
            relpath = path.relative_to(destdir)
            if str(relpath) not in filter_files and not overlays.is_whiteout_file(path):
                logger.debug("delete file: %s", relpath)
                path.unlink()

        for directory in directories:
            path = Path(root, directory)
            relpath = path.relative_to(destdir)
            if path.is_symlink():
                if str(relpath) not in filter_files:
                    logger.debug("delete symlink: %s", relpath)
                    path.unlink()
            elif str(relpath) not in filter_dirs:
                logger.debug("delete dir: %s", relpath)
                # Don't descend into this directory-- we'll just delete it
                # entirely.
                directories.remove(directory)
                shutil.rmtree(str(path))


def _get_build_packages(*, part: Part, plugin: Plugin) -> list[str]:
    """Obtain the consolidated list of required build packages.

    The list of build packages include packages defined directly in
    the parts specification, packages required by the source handler,
    and packages required by the plugin.

    :param part: The part being processed.
    :param plugin: The plugin used in this part.

    :return: The list of build packages.
    """
    all_packages: list[str] = []

    build_packages = part.spec.build_packages
    if build_packages:
        logger.debug("part build packages: %s", build_packages)
        all_packages.extend(build_packages)

    source = part.spec.source
    if source:
        repo = packages.Repository

        source_type = part.spec.source_type
        if not source_type:
            source_type = sources.get_source_type_from_uri(source)

        source_build_packages = repo.get_packages_for_source_type(source_type)
        if source_build_packages:
            logger.debug("source build packages: %s", source_build_packages)
            all_packages.extend(source_build_packages)

    plugin_build_packages = plugin.get_build_packages()
    if plugin_build_packages:
        logger.debug("plugin build packages: %s", plugin_build_packages)
        all_packages.extend(plugin_build_packages)

    return all_packages


def _get_build_snaps(*, part: Part, plugin: Plugin) -> list[str]:
    """Obtain the consolidated list of required build snaps.

    The list of build snaps include snaps defined directly in the parts
    specification and snaps required by the plugin.

    :param part: The part being processed.
    :param plugin: The plugin used in this part.

    :return: The list of build snaps.
    """
    all_snaps: list[str] = []

    build_snaps = part.spec.build_snaps
    if build_snaps:
        logger.debug("part build snaps: %s", build_snaps)
        all_snaps.extend(build_snaps)

    if part.spec.source:
        source_handler = sources.get_source_handler(
            part.part_cache_dir, part, project_dirs=part.dirs
        )

        if source_handler is not None:
            source_build_snaps = source_handler.get_pull_snaps()
            if source_build_snaps:
                logger.debug("source build snaps: %s", source_build_snaps)
                all_snaps.extend(source_build_snaps)

    plugin_build_snaps = plugin.get_build_snaps()
    if plugin_build_snaps:
        logger.debug("plugin build snaps: %s", plugin_build_snaps)
        all_snaps.extend(plugin_build_snaps)

    return all_snaps


def _get_machine_manifest() -> dict[str, Any]:
    """Obtain information about the system OS and runtime environment."""
    return {
        "uname": os_utils.get_system_info(),
        "installed-packages": sorted(packages.Repository.get_installed_packages()),
        "installed-snaps": sorted(packages.snaps.get_installed_snaps()),
    }


def _load_part_states(step: Step, part_list: list[Part]) -> dict[str, StepState]:
    """Return a dictionary of the state of the given step for all given parts.

    :param step: The step whose states should be loaded.
    :part_list: The list of parts whose states should be loaded.

    :return: A dictionary mapping part names to its state for the given step.
    """
    part_states: dict[str, StepState] = {}
    for part in part_list:
        state = states.load_step_state(part, step)
        if state:
            part_states[part.name] = state
    return part_states


def _parts_with_overlay_in_step(step: Step, *, part_list: list[Part]) -> list[Part]:
    """Obtain a list of parts with overlay that reached the given step.

    :param step: The step to test for parts with overlay.
    :param part_list: A list containing all parts.

    :returns: The list of parts with overlay in step.
    """
    oparts = get_parts_with_overlay(part_list=part_list)
    return [p for p in oparts if states.get_step_state_path(p, step).exists()]


def _get_primed_stage_packages(
    snap_files: set[str], *, prime_dirs: list[Path]
) -> set[str]:
    primed_stage_packages: set[str] = set()
    for _snap_file in snap_files:
        for prime_dir in prime_dirs:
            snap_file = prime_dir / _snap_file
            if not snap_file.exists():
                continue
            stage_package = read_origin_stage_package(str(snap_file))
            if stage_package:
                primed_stage_packages.add(stage_package)
    return primed_stage_packages


def _consolidate_states(
    consolidated_states: dict[str | None, MigrationState],
    migrated_files: dict[str | None, _MigratedContents],
    migrated_directories: dict[str | None, _MigratedContents],
) -> None:
    """Consolidate migrated files into MigrationStates."""
    for partition, files in migrated_files.items():
        dst_files = set(files.values())
        if not consolidated_states.get(partition):
            consolidated_states[partition] = MigrationState(partition=partition)
        consolidated_states[partition].add(files=dst_files)

    for partition, directories in migrated_directories.items():
        dst_dirs = set(directories.values())
        if not consolidated_states.get(partition):
            consolidated_states[partition] = MigrationState(partition=partition)
        consolidated_states[partition].add(directories=dst_dirs)
