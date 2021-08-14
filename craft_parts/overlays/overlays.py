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

import hashlib
import logging
import os
from pathlib import Path
from typing import Set, Tuple

from craft_parts.parts import Part

from . import overlay_fs

logger = logging.getLogger(__name__)


def compute_layer_hash(part: Part, previous_layer_hash: bytes) -> bytes:
    """Obtain the validation hash for a part.

    :param part: The part being processed.
    :param previous_layer_hash: The validation hash of the previous
        layer in the overlay stack.

    :return: The validaton hash of the layer corresponding to the
        given part.
    """
    hasher = hashlib.sha1()

    for entry in part.spec.overlay_packages:
        hasher.update(entry.encode())

    if part.spec.overlay_script:
        hasher.update(part.spec.overlay_script.encode())

    hasher.update(previous_layer_hash)

    return hasher.digest()


def load_layer_hash(part: Part) -> bytes:
    """Read the part layer validation hash from persistent state.

    :param part: The part whose layer hash will be loaded.

    :return: The validaton hash of the layer corresponding to the
        given part, or None if there's no previous state.
    """
    hash_file = part.part_state_dir / "layer_hash"
    if not hash_file.exists():
        return b""

    with open(hash_file) as file:
        hex_string = file.readline()

    return bytes.fromhex(hex_string)


def save_layer_hash(part: Part, *, hash_bytes: bytes) -> None:
    """Save the part layer validation hash to persistent storage.

    :param part: The part whose layer hash will be saved.
    """
    hash_file = part.part_state_dir / "layer_hash"
    hash_file.write_text(hash_bytes.hex())


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
            elif overlay_fs.is_opaque_dir(destpath):
                logger.debug("is opaque dir: %s", relpath)
                # Don't descend into this directory, overridden by opaque
                directories.remove(directory)

    logger.debug("files=%r, dirs=%r", migratable_files, migratable_dirs)
    return migratable_files, migratable_dirs
