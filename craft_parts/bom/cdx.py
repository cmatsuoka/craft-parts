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

from pathlib import Path
from typing import TYPE_CHECKING, List, Literal, Optional

import pydantic
from pydantic import constr


class _BaseModel(pydantic.BaseModel):
    """SBOM baseline component information."""

    class Config:  # pylint: disable=too-few-public-methods
        """Pydantic model configuration."""

        validate_assignment = True
        extra = "allow"
        allow_mutation = False
        allow_population_by_field_name = True
        alias_generator = lambda s: s.replace("_", "-")  # noqa: E731


# We want to use underscores in our CycloneDX class names
# pylint: disable=invalid-name,missing-class-docstring

# We can reorganize this later
# pylint: disable=line-too-long

# also see https://github.com/pydantic/pydantic/issues/2872


# Workaround for mypy
# see https://github.com/samuelcolvin/pydantic/issues/975#issuecomment-551147305
if TYPE_CHECKING:
    UUIDType = str
    MimeType = str
else:
    UUIDType = constr(
        regex=r"^urn:uuid:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"  # noqa: F722
    )
    MimeType = constr(regex=r"^[-+a-z0-9.]+/[-+a-z0-9.]+$")


class CycloneDX_SBOM_metadata_tool_externalReference_hash(_BaseModel):  # noqa: D101
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
    content: constr(  # type: ignore
        regex=r"^([a-fA-F0-9]{32}|[a-fA-F0-9]{40}|[a-fA-F0-9]{64}|[a-fA-F0-9]{96}|[a-fA-F0-9]{128})$"  # noqa: F722
    )


class CycloneDX_SBOM_metadata_tool_externalReference(_BaseModel):  # noqa: D101
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


class CycloneDX_SBOM_metadata_tool(_BaseModel):  # noqa: D101
    vendor: Optional[str] = None
    name: Optional[str] = None
    version: Optional[str] = None
    externalReferences: Optional[
        List[CycloneDX_SBOM_metadata_tool_externalReference]
    ] = None


class CycloneDX_SBOM_metadata_author(_BaseModel):  # noqa: D101
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None


class CycloneDX_SBOM_metadata_component_supplier_contact(_BaseModel):  # noqa: D101
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None


class CycloneDX_SBOM_metadata_component_supplier(_BaseModel):  # noqa: D101
    name: Optional[str]
    url: Optional[str]
    contact: Optional[List[CycloneDX_SBOM_metadata_component_supplier_contact]]


class CycloneDX_SBOM_metadata_component_hash(_BaseModel):  # noqa: D101
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
    content: constr(  # type: ignore
        regex=r"^([a-fA-F0-9]{32}|[a-fA-F0-9]{40}|[a-fA-F0-9]{64}|[a-fA-F0-9]{96}|[a-fA-F0-9]{128})$"  # noqa: F722
    )


class CycloneDX_SBOM_metadata_component(_BaseModel):  # noqa: D101
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
    mime_type: Optional[MimeType] = None
    bom_ref: Optional[str] = None
    supplier: Optional[CycloneDX_SBOM_metadata_component_supplier] = None
    author: Optional[str] = None
    publisher: Optional[str] = None
    group: Optional[str] = None
    name: str
    version: Optional[str] = None
    description: Optional[str] = None
    scope: Optional[Literal["required", "optional", "excluded"]] = None
    hashes: Optional[CycloneDX_SBOM_metadata_component_hash] = None
    # license: Optional[Any]
    copyright: Optional[str] = None
    cpe: Optional[str] = None
    purl: Optional[str] = None
    # swid: Optional[Any]
    # pedigree
    # externalReferences
    # components
    # evidence
    # releaseNotes
    # properties
    # signature


class CycloneDX_SBOM_metadata(_BaseModel):  # noqa: D101
    timestamp: Optional[str] = None
    tools: Optional[List[CycloneDX_SBOM_metadata_tool]] = None
    authors: Optional[List[CycloneDX_SBOM_metadata_author]] = None
    component: Optional[CycloneDX_SBOM_metadata_component] = None
    # manufacture
    # supplier
    # licenses
    # properties


class CycloneDX_SBOM_component_supplier_contact(_BaseModel):  # noqa: D101
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None


class CycloneDX_SBOM_component_supplier(_BaseModel):  # noqa: D101
    name: Optional[str] = None
    url: Optional[str] = None
    contact: Optional[List[CycloneDX_SBOM_component_supplier_contact]] = None


class CycloneDX_SBOM_component_hash(_BaseModel):  # noqa: D101
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
    content: constr(  # type: ignore
        regex=r"^([a-fA-F0-9]{32}|[a-fA-F0-9]{40}|[a-fA-F0-9]{64}|[a-fA-F0-9]{96}|[a-fA-F0-9]{128})$"  # noqa: F722
    )


class CycloneDX_SBOM_component(_BaseModel):  # noqa: D101
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
    mime_type: Optional[MimeType] = None
    bom_ref: Optional[str] = None
    supplier: Optional[CycloneDX_SBOM_component_supplier] = None
    author: Optional[str] = None
    publisher: Optional[str] = None
    group: Optional[str] = None
    name: str
    version: Optional[str] = None
    description: Optional[str] = None
    scope: Optional[Literal["required", "optional", "excluded"]] = None
    hashes: Optional[List[CycloneDX_SBOM_component_hash]] = None
    # license: Optional[Any]
    copyright: Optional[str] = None
    cpe: Optional[str] = None
    purl: Optional[str] = None
    # swid: Optional[Any]
    # pedigree
    # externalReferences
    # components
    # evidence
    # releaseNotes
    # properties
    # signature


class CycloneDX_SBOM_dependency(_BaseModel):  # noqa: D101
    ref: str
    dependsOn: Optional[List[str]] = None


class CycloneDX_SBOM(_BaseModel):
    """CycloneDX SBOM model."""

    bomFormat: Literal["CycloneDX"] = "CycloneDX"
    specVersion: Literal["1.4"] = "1.4"
    serialNumber: Optional[UUIDType] = None
    version: int
    metadata: Optional[CycloneDX_SBOM_metadata] = None
    components: Optional[List[CycloneDX_SBOM_component]] = None
    # services
    # externalReferences
    dependencies: Optional[List[CycloneDX_SBOM_dependency]] = None
    # compositions
    # vulnerabilities
    # signature

    def write(self, file_path: Path) -> None:
        """Write bom component to persistent storage."""
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(self.json(by_alias=True, exclude_none=True))
