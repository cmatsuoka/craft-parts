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

"""Low level interface to OS overlayfs."""

import logging
from pathlib import Path
from typing import List, Union

from craft_parts.utils import os_utils

logger = logging.getLogger(__name__)


class OverlayFS:
    """Linux overlayfs operations."""

    def __init__(
        self,
        *,
        mountpoint: Path,
        lower_dir: Union[Path, List[Path]],
        upper_dir: Path,
        work_dir: Path
    ):
        if not isinstance(lower_dir, list):
            lower_dir = [lower_dir]

        self._mountpoint = str(mountpoint)
        self._lower_dir = ":".join([str(p) for p in lower_dir])
        self._upper_dir = str(upper_dir)
        self._work_dir = str(work_dir)

    def mount(self) -> None:
        """Mount an overlayfs."""
        logger.debug("mount overlayfs on %s", self._mountpoint)
        os_utils.mount(
            "overlay",
            self._mountpoint,
            "-toverlay",
            "-olowerdir={},upperdir={},workdir={}".format(
                self._lower_dir, self._upper_dir, self._work_dir
            ),
        )

    def unmount(self) -> None:
        """Umount an overlayfs."""
        logger.debug("unmount overlayfs from %s", self._mountpoint)
        os_utils.umount(self._mountpoint)
