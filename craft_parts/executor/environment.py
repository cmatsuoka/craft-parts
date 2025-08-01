# -*- Mode:Python; indent-tabs-mode:nil; tab-width:4 -*-
#
# Copyright 2020-2025 Canonical Ltd.
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

"""Helpers to handle part environment setting."""

from __future__ import annotations

import io
import logging
from typing import TYPE_CHECKING, Any, cast

from craft_parts import errors
from craft_parts.features import Features
from craft_parts.steps import Step
from craft_parts.utils import os_utils
from craft_parts.utils.partition_utils import DEFAULT_PARTITION, is_default_partition

if TYPE_CHECKING:
    from collections.abc import Iterable

    from craft_parts.infos import ProjectInfo, StepInfo
    from craft_parts.parts import Part
    from craft_parts.plugins import Plugin


logger = logging.getLogger(__name__)


def generate_step_environment(
    *, part: Part, plugin: Plugin, step_info: StepInfo
) -> str:
    """Generate an environment to use during step execution.

    :param part: The part being processed.
    :param plugin: The plugin used to build this part.
    :param step_info: Information about the step to be executed.

    :return: The environment to use when executing the step.
    """
    # Craft parts' say.
    parts_environment = _basic_environment_for_part(part=part, step_info=step_info)

    # Plugin's say.
    if step_info.step == Step.BUILD:
        plugin_environment = plugin.get_build_environment()
    else:
        plugin_environment = {}

    # Part's (user) say.
    user_environment = part.spec.build_environment or []

    # Create the script.
    with io.StringIO() as run_environment:
        print("# Environment", file=run_environment)

        print("## Application environment", file=run_environment)
        for key, val in step_info.global_environment.items():
            print(f'export {key}="{val}"', file=run_environment)
        for key, val in step_info.step_environment.items():
            print(f'export {key}="{val}"', file=run_environment)

        print("## Part environment", file=run_environment)
        for key, val in parts_environment.items():
            print(f'export {key}="{val}"', file=run_environment)

        print("## Plugin environment", file=run_environment)
        for key, val in plugin_environment.items():
            print(f'export {key}="{val}"', file=run_environment)

        print("## User environment", file=run_environment)
        for env in user_environment:
            for key, val in env.items():
                print(f'export {key}="{val}"', file=run_environment)

        # Return something suitable for Runner.
        return run_environment.getvalue()


def _basic_environment_for_part(part: Part, *, step_info: StepInfo) -> dict[str, str]:
    """Return the built-in part environment.

    :param part: The part to get environment information from.
    :param step_info: Information for this step.

    :return: A dictionary containing the built-in environment.
    """
    part_environment = _get_step_environment(step_info)
    paths = [part.part_install_dir, part.stage_dir]

    if Features().enable_partitions and Features().enable_overlay:
        part_environment.update(
            _get_step_overlay_environment_for_partitions(part, step_info.partitions)
        )

    bin_paths = []
    for path in paths:
        bin_paths.extend(os_utils.get_bin_paths(root=path, existing_only=True))

    if bin_paths:
        bin_paths.append("$PATH")
        part_environment["PATH"] = _combine_paths(
            paths=bin_paths, prepend="", separator=":"
        )

    include_paths = []
    for path in paths:
        include_paths.extend(
            os_utils.get_include_paths(root=path, arch_triplet=step_info.arch_triplet)
        )

    if include_paths:
        for envvar in ["CPPFLAGS", "CFLAGS", "CXXFLAGS"]:
            part_environment[envvar] = _combine_paths(
                paths=include_paths, prepend="-isystem ", separator=" "
            )

    library_paths = []
    for path in paths:
        library_paths.extend(
            os_utils.get_library_paths(root=path, arch_triplet=step_info.arch_triplet)
        )

    if library_paths:
        part_environment["LDFLAGS"] = _combine_paths(
            paths=library_paths, prepend="-L", separator=" "
        )

    pkg_config_paths = []
    for path in paths:
        pkg_config_paths.extend(
            os_utils.get_pkg_config_paths(
                root=path, arch_triplet=step_info.arch_triplet
            )
        )

    if pkg_config_paths:
        part_environment["PKG_CONFIG_PATH"] = _combine_paths(
            pkg_config_paths, prepend="", separator=":"
        )

    return part_environment


def _get_global_environment(info: ProjectInfo) -> dict[str, str]:
    """Add project and part information variables to the environment.

    :param info: Information about the project.

    :return: A dictionary containing environment variables and values.
    """
    global_environment = {
        # deprecated, use CRAFT_ARCH_TRIPLET_BUILD_{ON|FOR}
        "CRAFT_ARCH_TRIPLET": info.arch_triplet,
        # deprecated, use CRAFT_ARCH_BUILD_FOR
        "CRAFT_TARGET_ARCH": info.target_arch,
        "CRAFT_ARCH_BUILD_ON": info.arch_build_on,
        "CRAFT_ARCH_BUILD_FOR": info.arch_build_for,
        "CRAFT_ARCH_TRIPLET_BUILD_ON": info.arch_triplet_build_on,
        "CRAFT_ARCH_TRIPLET_BUILD_FOR": info.arch_triplet_build_for,
        "CRAFT_PARALLEL_BUILD_COUNT": str(info.parallel_build_count),
        "CRAFT_PROJECT_DIR": str(info.project_dir),
    }

    if Features().enable_overlay:
        global_environment["CRAFT_OVERLAY"] = str(info.overlay_mount_dir)

    if Features().enable_partitions:
        global_environment.update(_get_environment_for_partitions(info))

    global_environment["CRAFT_STAGE"] = str(info.stage_dir)
    global_environment["CRAFT_PRIME"] = str(info.prime_dir)

    if info.project_name is not None:
        global_environment["CRAFT_PROJECT_NAME"] = str(info.project_name)

    return global_environment


def _translate_partition_env(partition: str) -> str:
    """Translate a partition name to a valid env var name chunk.

    :param partition: The partition name

    :returns: The translated name
    """
    return partition.upper().translate({ord("-"): "_", ord("/"): "_"})


def _get_environment_for_partitions(info: ProjectInfo) -> dict[str, str]:
    """Get environment variables related to partitions.

    Assumes the partition feature is enabled.

    :param info: The project information.

    :returns: A dictionary contain environment variables for partitions.

    :raises FeatureError: If the Project does not specify any partitions.
    """
    environment: dict[str, str] = {}

    if not info.partitions:
        raise errors.FeatureError("Partitions enabled but no partitions specified.")

    for partition in info.partitions:
        # CRAFT_DEFAULT_* vars for the default partition
        if info.is_default_partition(partition):
            formatted_default = _translate_partition_env(DEFAULT_PARTITION)
            environment[f"CRAFT_{formatted_default}_STAGE"] = str(
                info.get_stage_dir(partition=partition)
            )
            environment[f"CRAFT_{formatted_default}_PRIME"] = str(
                info.get_prime_dir(partition=partition)
            )
        formatted_partition = _translate_partition_env(partition)

        environment[f"CRAFT_{formatted_partition}_STAGE"] = str(
            info.get_stage_dir(partition=partition)
        )
        environment[f"CRAFT_{formatted_partition}_PRIME"] = str(
            info.get_prime_dir(partition=partition)
        )

    return environment


def _get_step_overlay_environment_for_partitions(
    part: Part, partitions: list[str]
) -> dict[str, str]:
    """Get environment variables related to partitions and overlay for a part.

    Assumes the partition feature is enabled.

    :param step_info: Information about the current step.

    :returns: A dictionary containing step environment variables for partitions.

    :raises FeatureError: If the Project does not specify any partitions.
    """
    environment: dict[str, str] = {}

    if not partitions:
        raise errors.FeatureError("Partitions enabled but no partitions specified.")

    for partition in partitions:
        # CRAFT_DEFAULT_* var for the default partition
        if is_default_partition(partitions, partition):
            environment[
                f"CRAFT_{_translate_partition_env(DEFAULT_PARTITION)}_OVERLAY"
            ] = str(part.part_layer_dirs[partition])

        formatted_partition = _translate_partition_env(partition)

        environment[f"CRAFT_{formatted_partition}_OVERLAY"] = str(
            part.part_layer_dirs[partition]
        )

    return environment


def _get_step_environment(step_info: StepInfo) -> dict[str, str]:
    """Add project and part information variables to the environment.

    :param step_info: Information about the current step.

    :return: A dictionary containing environment variables and values.
    """
    global_environment = _get_global_environment(step_info.project_info)

    return {
        **global_environment,
        "CRAFT_PART_NAME": step_info.part_name,
        "CRAFT_STEP_NAME": getattr(step_info.step, "name", ""),
        "CRAFT_PART_SRC": str(step_info.part_src_dir),
        "CRAFT_PART_SRC_WORK": str(step_info.part_src_subdir),
        "CRAFT_PART_BUILD": str(step_info.part_build_dir),
        "CRAFT_PART_BUILD_WORK": str(step_info.part_build_subdir),
        "CRAFT_PART_INSTALL": str(step_info.part_install_dir),
    }


def _combine_paths(paths: Iterable[str], prepend: str, separator: str) -> str:
    """Combine list of paths into a string.

    :param paths: The list of paths to stringify.
    :param prepend: A prefix to prepend to each path in the string.
    :param separator: A string to place between each path in the string.

    :return: A string with the combined paths.
    """
    paths = [f"{prepend}{p}" for p in paths]
    return separator.join(paths)


def expand_environment(
    data: dict[str, Any], *, info: ProjectInfo, skip: list[str] | None = None
) -> None:
    """Replace global variables with their values.

    Global variables are defined by craft-parts and are the subset of the
    ``CRAFT_*`` step execution environment variables that don't depend
    on the part or step being executed. The list of global variables include
    ``CRAFT_ARCH_TRIPLET``, ``CRAFT_PROJECT_DIR``, ``CRAFT_STAGE`` and
    ``CRAFT_PRIME``. Additional global variables can be defined by the
    application using craft-parts.

    :param data: A dictionary whose values will have variable names expanded.
    :param info: The project information.
    :param skip: Keys to skip when performing expansion.
    """
    global_environment = _get_global_environment(info)
    global_environment.update(info.global_environment)

    replacements: dict[str, str] = {}
    for key, value in global_environment.items():
        # Support both $VAR and ${VAR} syntax
        replacements[f"${key}"] = value
        replacements[f"${{{key}}}"] = value

    # order is important - for example, `CRAFT_ARCH_TRIPLET_BUILD_{ON|FOR}` should be
    # evaluated before `CRAFT_ARCH_TRIPLET` to avoid premature variable expansion
    replacements = dict(
        sorted(replacements.items(), key=lambda item: len(item[0]), reverse=True)
    )

    for key, value in data.items():
        if not skip or key not in skip:
            data[key] = _replace_attr(value, replacements)


def _replace_attr(
    attr: list[str] | dict[str, str] | str, replacements: dict[str, str]
) -> list[str] | dict[str, str] | str:
    """Recurse through a complex data structure and replace values.

    The first matching replacement in the replacement map is used. For example,
    _replace_attr(attr="$FOO_BAR", replacements={"$FOO": "hi", "$FOO_BAR": "hello"})
    would evaluate to "hi_BAR".

    :param attr: The data to modify, which may contain nested lists, dicts, and strings.
    :param replacements: A mapping of replacements to make.

    :returns: The data structure with replaced values.
    """
    if isinstance(attr, str):
        for key, value in replacements.items():
            if key in attr:
                _warn_if_deprecated_key(key)
                attr = attr.replace(key, str(value))
        return attr

    if isinstance(attr, list | tuple):
        return [cast(str, _replace_attr(i, replacements)) for i in attr]

    if isinstance(attr, dict):
        result: dict[str, str] = {}
        for _key, _value in attr.items():
            # Run replacements on both the key and value
            key = cast(str, _replace_attr(_key, replacements))
            value = cast(str, _replace_attr(_value, replacements))
            result[key] = value
        return result

    return attr


def _warn_if_deprecated_key(key: str) -> None:
    if key in ("$CRAFT_TARGET_ARCH", "${CRAFT_TARGET_ARCH}"):
        logger.info("CRAFT_TARGET_ARCH is deprecated, use CRAFT_ARCH_BUILD_FOR")
    elif key in ("$CRAFT_ARCH_TRIPLET", "${CRAFT_ARCH_TRIPLET}"):
        logger.info(
            "CRAFT_ARCH_TRIPLET is deprecated, use CRAFT_ARCH_TRIPLET_BUILD_{ON|FOR}"
        )
