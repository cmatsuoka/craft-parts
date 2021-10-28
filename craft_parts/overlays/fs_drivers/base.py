# -*- Mode:Python; indent-tabs-mode:nil; tab-width:4 -*-
#
# Copyright 2021 Canonical Ltd.
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

"""Low level interface to OS overlayfs."""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Optional


class OverlayFSDriver(ABC):
    """Overlay mounting operation interface."""

    def __init__(self, *, lower_dirs: List[Path], upper_dir: Path, work_dir: Path):
        self._lower_dirs = lower_dirs
        self._upper_dir = upper_dir
        self._work_dir = work_dir
        self._mountpoint: Optional[Path] = None

    @abstractmethod
    def mount(self, mountpoint: Path):
        """Mount a layer stack.

        :param mountpoint: The filesystem mount point.

        :raises OverlayMountError: on mount error.
        """

    def unmount(self) -> None:
        """Umount a layer stack.

        :raises OverlayUnmountError: on unmount error.
        """

    @staticmethod
    def is_whiteout_file(path: Path) -> bool:
        """Verify if the given path corresponds to a whiteout file.

        :param path: The path of the file to verify.

        :returns: Whether the given path is an overlayfs whiteout.
        """

    @staticmethod
    def is_opaque_dir(path: Path) -> bool:
        """Verify if the given path corresponds to an opaque directory.

        :param path: The path of the file to verify.

        :returns: Whether the given path is an overlayfs opaque directory.
        """
