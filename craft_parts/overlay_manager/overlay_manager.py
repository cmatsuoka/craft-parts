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
from typing import Dict, List

from craft_parts.parts import Part


class OverlayManager:
    """The filesystem layer stack manager.

    :param part_list: The list of parts in the project.
    """

    def __init__(self, part_list: List[Part], base_layer_hash: bytes):
        self._part_list = part_list
        self._base_layer_hash = base_layer_hash

        self._layer_hash: Dict[str, bytes] = dict()
        for part in part_list:
            self.set_layer_hash(part, load_layer_hash(part))

    def get_layer_hash(self, part: Part) -> bytes:
        """Obtain the layer hash for the given part."""
        return self._layer_hash.get(part.name, b"")

    def set_layer_hash(self, part: Part, hash_bytes: bytes) -> None:
        """Store the value of the layer hash for the given part."""
        self._layer_hash[part.name] = hash_bytes

    def current_layer_hash(self, part: Part) -> bytes:
        """Compute the layer validation hash for the given part.

        :param part: The part being processed.

        :return: The validation hash of the layer corresponding to the
            given part.
        """
        index = self._part_list.index(part)

        if index > 0:
            previous_layer_hash = self.get_layer_hash(self._part_list[index - 1])
        else:
            previous_layer_hash = self._base_layer_hash

        return compute_layer_hash(part, previous_layer_hash)

    def get_overlay_hash(self) -> bytes:
        """Obtain the overlay validation hash."""
        last_part = self._part_list[-1]
        return self.get_layer_hash(last_part)


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

    for entry in part.spec.overlay_files:
        hasher.update(entry.encode())

    if part.spec.override_overlay:
        hasher.update(part.spec.override_overlay.encode())

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
