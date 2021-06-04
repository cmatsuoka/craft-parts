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
from typing import List

from craft_parts.parts import Part


class OverlayManager:
    """The filesystem layer stack manager.

    :param part_list: The list of parts in the project.
    """

    def __init__(self, part_list: List[Part]):
        self._part_list = part_list


def compute_layer_digest(part: Part, previous_layer_hash: bytes) -> bytes:
    """Obtain the layer identification hash."""
    hasher = hashlib.sha1()

    for entry in part.spec.overlay_packages:
        hasher.update(entry.encode())

    for entry in part.spec.overlay_files:
        hasher.update(entry.encode())

    if part.spec.override_overlay:
        hasher.update(part.spec.override_overlay.encode())

    hasher.update(previous_layer_hash)

    return hasher.digest()
