# -*- Mode:Python; indent-tabs-mode:nil; tab-width:4 -*-
#
# Copyright 2022 Canonical Ltd.
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

"""BOM definition and helpers."""

import dataclasses
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set

import pydantic

from .cdx import (
    CycloneDX_SBOM,
    CycloneDX_SBOM_component,
    CycloneDX_SBOM_component_externalReference,
    CycloneDX_SBOM_component_hash,
    CycloneDX_SBOM_component_supplier,
    CycloneDX_SBOM_dependency,
    CycloneDX_SBOM_metadata,
    CycloneDX_SBOM_metadata_component,
    CycloneDX_SBOM_metadata_tool,
)


class _BaseModel(pydantic.BaseModel):
    """SBOM baseline component information."""

    class Config:  # pylint: disable=too-few-public-methods
        """Pydantic model configuration."""

        validate_assignment = True
        extra = "allow"
        allow_mutation = False
        allow_population_by_field_name = True
        alias_generator = lambda s: s.replace("_", "-")  # noqa: E731


class Component(_BaseModel):
    """BOM component."""

    component_type: str
    component_name: str
    component_hashes: Dict[str, str]
    component_id: str
    version_string: str
    supplier_name: str
    author_name: str
    timestamp: datetime
    download_location: Optional[str] = None
    purl: Optional[str] = None

    @classmethod
    def read(cls, file_path: Path) -> "Component":
        """Read a single component json from file."""
        return pydantic.parse_file_as(path=file_path, type_=cls)

    def write(self, file_path: Path) -> Path:
        """Write bom component to persistent storage."""
        file_path.parent.mkdir(parents=True, exist_ok=True)
        component_file = file_path.parent / (file_path.name + ".component")
        component_file.write_text(self.json(by_alias=True))

        return component_file


_CDX_HASH_ALGORITHM_TRANSLATION = {
    "md5": "MD5",
    "sha1": "SHA-1",
    "sha256": "SHA-256",
    "sha384": "SHA-384",
    "sha512": "SHA-512",
}


@dataclasses.dataclass
class Metadata:
    """Application SBOM metadata."""

    component_name: str
    component_version: str
    component_vendor: str
    component_description: str
    component_id: str
    tool_name: str
    tool_version: str
    tool_vendor: str


class ComponentList(_BaseModel):
    """A list of BOM components."""

    components: List[Component]

    @classmethod
    def read(cls, file_path: Path) -> "ComponentList":
        """Read a component list json from file."""
        return pydantic.parse_file_as(path=file_path, type_=cls)

    def write(self, file_path: Path) -> Path:
        """Write bom component to persistent storage."""
        file_path.parent.mkdir(parents=True, exist_ok=True)
        bom_file = file_path.parent / (file_path.name + ".bom")
        bom_file.write_text(self.json(by_alias=True))

        return bom_file


def consolidate_component_list(part_list: List) -> ComponentList:
    """Merge BOM information from existing sources.

    Gather partial BOM items from different origins, including the part
    source component, part dependencies, and stage packages.
    """
    all_comps: Dict[str, Component] = {}

    for part in part_list:
        # obtain part source BOM

        # obtain part dependencies BOM

        # obtain stage packages BOM
        pkg_bom_path = Path(part.part_state_dir / "stage_packages.bom")
        pkg_bom = ComponentList.read(pkg_bom_path)
        for component in pkg_bom.components:
            all_comps[component.component_id] = component

    return ComponentList(components=list(all_comps.values()))
