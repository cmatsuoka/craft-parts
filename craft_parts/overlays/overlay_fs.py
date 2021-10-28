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

from typing import Type

from .fs_drivers.base import OverlayFSDriver
from .fs_drivers.overlayfs import OverlayFS as OverlayFS_


def _get_overlay_fs_driver() -> Type[OverlayFSDriver]:
    return OverlayFS_


OverlayFS = _get_overlay_fs_driver()
