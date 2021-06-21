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

from craft_parts.parts import Part


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
