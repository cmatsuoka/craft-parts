# -*- Mode:Python; indent-tabs-mode:nil; tab-width:4 -*-
#
# Copyright 2021 Canonical Ltd.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3 as
# published by the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""Layer management helpers."""

import contextlib
import logging
import os
import shutil
import sys
from pathlib import Path
from typing import List, Optional

import pychroot  # type: ignore

from craft_parts import packages
from craft_parts.infos import ProjectInfo
from craft_parts.parts import Part

from .overlay_fs import OverlayFS

logger = logging.getLogger(__name__)


class OverlayManager:
    """Mount and umount the overlay step layer stack."""

    def __init__(
        self,
        *,
        project_info: ProjectInfo,
        part_list: List[Part],
        base_layer_dir: Optional[Path]
    ):
        self._project_info = project_info
        self._part_list = part_list
        self._layer_dirs = [p.part_layer_dir for p in part_list]
        self._overlay_mount_dir = project_info.overlay_mount_dir
        self._overlay_fs: Optional[OverlayFS] = None
        self._base_layer_dir = base_layer_dir

    def mount_layer(
        self, part: Part, *, pkg_cache: bool = False, empty_base: bool = False
    ) -> None:
        """Mount the overlay step layer stack up to the given part.

        :param part: The part corresponding to the topmost layer to mount.
        :param pkg cache: Whether the package cache layer is enabled.
        """
        if not self._base_layer_dir:
            return

        if empty_base:
            lowers = [self._project_info.overlay_empty_dir]
        else:
            lowers = [self._base_layer_dir]

        if pkg_cache:
            lowers.append(self._project_info.overlay_packages_dir)
        index = self._part_list.index(part)
        lowers.extend(self._layer_dirs[0:index])
        upper = self._layer_dirs[index]

        # lower dirs are stacked right to left
        lowers.reverse()

        self._overlay_fs = OverlayFS(
            lower_dir=lowers,
            upper_dir=upper,
            work_dir=self._project_info.overlay_work_dir,
            mountpoint=self._project_info.overlay_mount_dir,
        )

        self._overlay_fs.mount()

    def mount_pkg_cache(self) -> None:
        """Mount the overlay step package cache layer."""
        if not self._base_layer_dir:
            return

        self._overlay_fs = OverlayFS(
            lower_dir=self._base_layer_dir,
            upper_dir=self._project_info.overlay_packages_dir,
            work_dir=self._project_info.overlay_work_dir,
            mountpoint=self._project_info.overlay_mount_dir,
        )

        self._overlay_fs.mount()

    def unmount(self) -> None:
        """Unmount the overlay step layer stack."""
        if not self._base_layer_dir:
            return

        if not self._overlay_fs:
            logger.warning("overlay filesystem not mounted")
            return

        self._overlay_fs.unmount()
        self._overlay_fs = None

    def refresh_packages_list(self) -> None:
        """Update the list of available packages in the overlay system."""
        if not self._base_layer_dir:
            return

        if not self._overlay_fs:
            logger.warning("overlay filesystem not mounted")
            return

        self._fix_resolv_conf()

        with contextlib.suppress(SystemExit), pychroot.Chroot(self._overlay_mount_dir):
            packages.Repository.refresh_build_packages_list()

    def fetch_packages(self, package_names: List[str]) -> None:
        """Update the list of available packages in the overlay system."""
        if not self._base_layer_dir:
            return

        if not self._overlay_fs:
            logger.warning("overlay filesystem not mounted")
            return

        self._fix_resolv_conf()

        with contextlib.suppress(SystemExit), pychroot.Chroot(self._overlay_mount_dir):
            packages.Repository.fetch_packages(package_names)

    def install_packages(self, package_names: List[str]) -> None:
        """Update the list of available packages in the overlay system."""
        if not self._base_layer_dir:
            return

        if not self._overlay_fs:
            logger.warning("overlay filesystem not mounted")
            return

        self._fix_resolv_conf()

        with contextlib.suppress(SystemExit), pychroot.Chroot(self._overlay_mount_dir):
            packages.Repository.install_build_packages(package_names)
            shutil.rmtree("/var/cache", ignore_errors=True)

    def mkdirs(self) -> None:
        """Create overlay directories and mountpoints."""
        for overlay_dir in [
            self._project_info.overlay_mount_dir,
            self._project_info.overlay_packages_dir,
            self._project_info.overlay_work_dir,
            self._project_info.overlay_empty_dir,
        ]:
            overlay_dir.mkdir(parents=True, exist_ok=True)

    def _fix_resolv_conf(self) -> None:
        """Work around problems with pychroot when resolv.conf a symlink."""
        resolv = self._project_info.overlay_mount_dir / "etc" / "resolv.conf"
        if resolv.is_symlink():
            resolv.unlink()
            resolv.touch()


class PackageCacheMounter:
    """Mount and umount the overlay package cache."""

    def __init__(self, overlay_manager: OverlayManager):
        self._overlay_manager = overlay_manager
        self._overlay_manager.mkdirs()
        self._pid = os.getpid()

    def __enter__(self):
        self._overlay_manager.mount_pkg_cache()
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback):
        if os.getpid() != self._pid:
            sys.exit()
        self._overlay_manager.unmount()
        return False

    def refresh_packages_list(self) -> None:
        """Update the list of available packages in the overlay system."""
        self._overlay_manager.refresh_packages_list()

    def fetch_packages(self, package_names: List[str]) -> None:
        """Download the specified packages to the local system."""
        self._overlay_manager.fetch_packages(package_names)


class LayerMounter:
    """Mount and umount the overlay layer stack."""

    def __init__(
        self,
        overlay_manager: OverlayManager,
        top_part: Part,
        pkg_cache: bool = True,
        empty_base: bool = False,
    ):
        self._overlay_manager = overlay_manager
        self._overlay_manager.mkdirs()
        self._top_part = top_part
        self._pkg_cache = pkg_cache
        self._empty_base = empty_base
        self._pid = os.getpid()

    def __enter__(self):
        self._overlay_manager.mount_layer(
            self._top_part, pkg_cache=self._pkg_cache, empty_base=self._empty_base
        )
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback):
        if os.getpid() != self._pid:
            sys.exit()
        self._overlay_manager.unmount()
        return False

    def install_packages(self, package_names: List[str]) -> None:
        """Install the specified packages on the local system."""
        self._overlay_manager.install_packages(package_names)
