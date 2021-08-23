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

from craft_parts.parts import Part

logger = logging.getLogger(__name__)


class LayerHash:
    """The overlay validation hash for a part."""

    def __init__(self, layer_hash: bytes = b""):  # pylint: disable=E0601
        self._hash_bytes = layer_hash

    def __eq__(self, other):
        return self._hash_bytes == other._hash_bytes

    @classmethod
    def for_part(cls, part: Part, *, previous_layer_hash: "LayerHash") -> "LayerHash":
        """Obtain the validation hash for a part.

        :param part: The part being processed.
        :param previous_layer_hash: The validation hash of the previous
            layer in the overlay stack.
        """
        hasher = hashlib.sha1()

        for entry in part.spec.overlay_packages:
            hasher.update(entry.encode())

        if part.spec.overlay_script:
            hasher.update(part.spec.overlay_script.encode())

        hasher.update(previous_layer_hash.bytes())

        return cls(hasher.digest())

    @classmethod
    def load(cls, part: Part) -> "LayerHash":
        """Read the part layer validation hash from persistent state.

        :param part: The part whose layer hash will be loaded.

        :return: The validaton hash of the layer corresponding to the
            given part, or None if there's no previous state.
        """
        hash_file = part.part_state_dir / "layer_hash"
        if not hash_file.exists():
            return cls()

        with open(hash_file) as file:
            hex_string = file.readline()

        return cls(bytes.fromhex(hex_string))

    def save(self, part: Part) -> None:
        """Save the part layer validation hash to persistent storage.

        :param part: The part whose layer hash will be saved.
        """
        hash_file = part.part_state_dir / "layer_hash"
        hash_file.write_text(self.hex())

    def bytes(self) -> bytes:
        """Return the current hash as bytes."""
        return self._hash_bytes

    def hex(self) -> str:
        """Return the current hash as a hexadecimal string."""
        return self._hash_bytes.hex()
