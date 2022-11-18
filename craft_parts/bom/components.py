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

"""Intemediate metadata components."""

from typing import Dict, List

from craft_parts.bom import Component
from craft_parts.parts import Part


def _get_stage_package_components(part: Part) -> List[Component]:
    component_list: List[Component] = []
    for component_path in part.part_packages_dir.glob("*.component"):
        data = Component.read(component_path)
        component_list.append(data)

    return component_list


def consolidate_component_list(part_list: List[Part]) -> List[Component]:
    """Merge BOM information from existing sources.

    Gather partial BOM items from different origins, including the part
    source component, part dependencies, and stage packages.
    """
    all_comps: Dict[str, Component] = {}

    for part in part_list:
        # obtain part source BOM

        # obtain part dependencies BOM

        # obtain build packages BOM

        # obtain stage packages BOM
        stage_package_components = _get_stage_package_components(part)
        for component in stage_package_components:
            all_comps[component.component_id] = component

    return list(all_comps.values())
