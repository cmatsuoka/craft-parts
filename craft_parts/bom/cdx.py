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

"""CycloneDX SBOM model."""

from typing import Any, List, Literal, Optional, constr

import pydantic


class _BaseModel(pydantic.BaseModel):
    """SBOM baseline component information."""

    class Config:  # pylint: disable=too-few-public-methods
        """Pydantic model configuration."""

        validate_assignment = True
        extra = "allow"
        allow_mutation = False
        allow_population_by_field_name = True
        alias_generator = lambda s: s.replace("_", "-")  # noqa: E731


class CycloneDX_SBOM_metadata_tool_externalReference_hash(_BaseModel):
    alg: Literal[
        "MD5",
        "SHA-1",
        "SHA-256",
        "SHA-384",
        "SHA-512",
        "BLAKE2b-256",
        "BLAKE2b-384",
        "BLAKE2b-512",
        "BLAKE3",
    ]
    content: constr(
        regex=r"^([a-fA-F0-9]{32}|[a-fA-F0-9]{40}|[a-fA-F0-9]{64}|[a-fA-F0-9]{96}|[a-fA-F0-9]{128})$"
    )


class CycloneDX_SBOM_metadata_tool_externalReference(_BaseModel):
    url: str
    comment: Optional[str]
    type: Literal[
        "vcs",
        "issue-tracker",
        "website",
        "advisories",
        "bom",
        "mailing-list",
        "social",
        "chat",
        "documentation",
        "support",
        "distribution",
        "license",
        "build-meta",
        "build-system",
        "release-notes",
        "other",
    ]
    hashes: Optional[List[CycloneDX_SBOM_metadata_tool_externalReference_hash]]


class CycloneDX_SBOM_metadata_tool(_BaseModel):
    vendor: Optional[str]
    name: Optional[str]
    version: Optional[str]
    externalReferences: Optional[List[CycloneDX_SBOM_metadata_tool_externalReference]]


class CycloneDX_SBOM_metadata_author(_BaseModel):
    name: Optional[str]
    email: Optional[str]
    phone: Optional[str]


class CycloneDX_SBOM_metadata_component_supplier_contact(_BaseModel):
    name: Optional[str]
    email: Optional[str]
    phone: Optional[str]


class CycloneDX_SBOM_metadata_component_supplier(_BaseModel):
    name: Optional[str]
    url: Optional[str]
    contact: Optional[List[CycloneDX_SBOM_metadata_component_supplier_contact]]


class CycloneDX_SBOM_metadata_component_hash(_BaseModel):
    alg: Literal[
        "MD5",
        "SHA-1",
        "SHA-256",
        "SHA-384",
        "SHA-512",
        "BLAKE2b-256",
        "BLAKE2b-384",
        "BLAKE2b-512",
        "BLAKE3",
    ]
    content: constr(
        regex=r"^([a-fA-F0-9]{32}|[a-fA-F0-9]{40}|[a-fA-F0-9]{64}|[a-fA-F0-9]{96}|[a-fA-F0-9]{128})$"
    )


class CycloneDX_SBOM_metadata_component(_BaseModel):
    type: Literal[
        "application",
        "framework",
        "library",
        "container",
        "operating-system",
        "device",
        "firmware",
        "file",
    ]
    mime_type: Optional[constr(regex=r"^[-+a-z0-9.]+/[-+a-z0-9.]+$")]
    bom_ref: Optional[str]
    supplier: Optional[CycloneDX_SBOM_metadata_component_supplier]
    author: Optional[str]
    publisher: Optional[str]
    group: Optional[str]
    name: str
    version: Optional[str]
    description: Optional[str]
    scope: Optional[Literal["required", "optional", "excluded"]]
    hashes: Optional[CycloneDX_SBOM_metadata_component_hash]
    # license: Optional[Any]
    copyright: Optional[str]
    cpe: Optional[str]
    purl: Optional[str]
    # swid: Optional[Any]
    # pedigree
    # externalReferences
    # components
    # evidence
    # releaseNotes
    # properties
    # signature


class CycloneDX_SBOM_metadata(_BaseModel):

    timestamp: Optional[str]
    tools: Optional[List[CycloneDX_SBOM_metadata_tool]]
    authors: Optional[List[CycloneDX_SBOM_metadata_author]]
    component: Optional[CycloneDX_SBOM_metadata_component]
    # manufacture
    # supplier
    # licenses
    # properties


class CycloneDX_SBOM_component_supplier_contact(_BaseModel):
    name: Optional[str]
    email: Optional[str]
    phone: Optional[str]


class CycloneDX_SBOM_component_supplier(_BaseModel):
    name: Optional[str]
    url: Optional[str]
    contact: Optional[List[CycloneDX_SBOM_component_supplier_contact]]


class CycloneDX_SBOM_component_hash(_BaseModel):
    alg: Literal[
        "MD5",
        "SHA-1",
        "SHA-256",
        "SHA-384",
        "SHA-512",
        "BLAKE2b-256",
        "BLAKE2b-384",
        "BLAKE2b-512",
        "BLAKE3",
    ]
    content: constr(
        regex=r"^([a-fA-F0-9]{32}|[a-fA-F0-9]{40}|[a-fA-F0-9]{64}|[a-fA-F0-9]{96}|[a-fA-F0-9]{128})$"
    )


class CycloneDX_SBOM_component(_BaseModel):
    type: Literal[
        "application",
        "framework",
        "library",
        "container",
        "operating-system",
        "device",
        "firmware",
        "file",
    ]
    mime_type: Optional[constr(regex=r"^[-+a-z0-9.]+/[-+a-z0-9.]+$")]
    bom_ref: Optional[str]
    supplier: Optional[CycloneDX_SBOM_component_supplier]
    author: Optional[str]
    publisher: Optional[str]
    group: Optional[str]
    name: str
    version: Optional[str]
    description: Optional[str]
    scope: Optional[Literal["required", "optional", "excluded"]]
    hashes: Optional[CycloneDX_SBOM_component_hash]
    # license: Optional[Any]
    copyright: Optional[str]
    cpe: Optional[str]
    purl: Optional[str]
    # swid: Optional[Any]
    # pedigree
    # externalReferences
    # components
    # evidence
    # releaseNotes
    # properties
    # signature


class CycloneDX_SBOM_dependency(_BaseModel):
    ref: str
    dependsOn: Optional[List[str]]


class CycloneDX_SBOM(_BaseModel):
    """CycloneDX SBOM nodel."""

    bomFormat: Literal["CycloneDX"]
    specVersion: Literal["1.4"]
    serialNumber: Optional[
        constr(
            regex=r"^urn:uuid:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
        )
    ]
    version: int
    metadata: Optional[CycloneDX_SBOM_metadata]
    components: Optional[List[CycloneDX_SBOM_component]]
    # services
    # externalReferences
    dependencies: Optional[List[CycloneDX_SBOM_dependency]]
    # compositions
    # vulnerabilities
    # signature
