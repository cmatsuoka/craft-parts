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
import os
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


def is_whiteout_file(path: Path) -> bool:
    """Verify if the given path corresponds to a whiteout file.

    :param path: The path of the file to verify.

    :return: Whether the given path is an overlayfs whiteout.
    """
    if not path.is_char_device() or path.is_symlink():
        return False

    rdev = os.stat(path).st_rdev

    return os.major(rdev) == 0 and os.minor(rdev) == 0


def is_opaque_dir(path: Path) -> bool:
    """Verify if the given path corresponds to an opaque directory.

    :param path: The path of the file to verify.

    :return: Whether the given path is an overlayfs opaque directory.
    """
    if not path.is_dir() or path.is_symlink():
        return False

    try:
        value = os.getxattr(path, "trusted.overlay.opaque")
    except OSError:
        return False

    return value == b"y"


def is_oci_opaque_dir(path: Path) -> bool:
    """Verify if the given path corresponds to an opaque directory.

    :param path: The path of the file to verify.

    :return: Whether the given path is an overlayfs opaque directory.
    """
    if not path.is_dir() or path.is_symlink():
        return False

    opaque_dir_marker = path / ".wh..wh..opq"
    return opaque_dir_marker.exists()


def is_path_visible(root: Path, relpath: Path) -> bool:
    """Verify if the given path is not whited out."""
    logger.debug("check if path is visible: root=%s, relpath=%s", root, relpath)
    levels = len(relpath.parts)
    for level in range(levels):
        path = root / os.path.join(*relpath.parts[: level + 1])
        logger.debug("check %s", path)
        if is_whiteout_file(path) or is_opaque_dir(path):
            logger.debug("is whiteout or opaque: %s", path)
            return False
    return True


def oci_whiteout(path: str) -> str:
    """Convert the given path to an OCI whiteout file name."""
    return os.path.join(os.path.dirname(path), ".wh." + os.path.basename(path))


def oci_opaque_dir(path: str) -> str:
    """Return the OCI opaque directory marker."""
    return os.path.join(path, ".wh..wh..opq")
