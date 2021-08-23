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

"""The overlay manager and helpers."""

import logging
import os
from pathlib import Path
from typing import Set, Tuple

from . import overlay_fs

logger = logging.getLogger(__name__)


def visible_in_layer(srcdir: Path, destdir: Path) -> Tuple[Set[str], Set[str]]:
    """Determine the files and directories that are visible in a layer."""
    migratable_files: Set[str] = set()
    migratable_dirs: Set[str] = set()

    logger.debug("check layer visibility in %s", srcdir)
    for (root, directories, files) in os.walk(srcdir, topdown=True):
        for file_name in files:
            path = Path(root, file_name)
            relpath = path.relative_to(srcdir)
            destpath = destdir / relpath
            if not destpath.exists():
                migratable_files.add(str(relpath))

        for directory in directories:
            path = Path(root, directory)
            relpath = path.relative_to(srcdir)
            destpath = destdir / relpath
            if not destpath.exists():
                if path.is_symlink():
                    migratable_files.add(str(relpath))
                else:
                    migratable_dirs.add(str(relpath))
            elif overlay_fs.is_oci_opaque_dir(destpath):
                logger.debug("is opaque dir: %s", relpath)
                # Don't descend into this directory, overridden by opaque
                directories.remove(directory)

    logger.debug("files=%r, dirs=%r", migratable_files, migratable_dirs)
    return migratable_files, migratable_dirs
