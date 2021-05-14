# -*- Mode:Python; indent-tabs-mode:nil; tab-width:4 -*-
#
# Copyright 2020-2021 Canonical Ltd.
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

import pytest
from pydantic import ValidationError

from craft_parts.infos import PartInfo, ProjectInfo
from craft_parts.parts import Part
from craft_parts.plugins.go_plugin import GoPlugin


def test_get_build_snaps():
    properties = GoPlugin.properties_class.unmarshal(
        {"source": ".", "go-channel": "14/latest"}
    )
    part_info = PartInfo(project_info=ProjectInfo(), part=Part("my-part", {}))
    plugin = GoPlugin(properties=properties, part_info=part_info)

    assert plugin.get_build_snaps() == {"go/14/latest"}


def test_get_build_packages():
    properties = GoPlugin.properties_class.unmarshal({"source": "."})
    part_info = PartInfo(project_info=ProjectInfo(), part=Part("my-part", {}))
    plugin = GoPlugin(properties=properties, part_info=part_info)

    assert plugin.get_build_packages() == {"gcc"}


def test_get_build_environment(new_dir):
    properties = GoPlugin.properties_class.unmarshal({"source": "."})
    part_info = PartInfo(project_info=ProjectInfo(), part=Part("my-part", {}))
    plugin = GoPlugin(properties=properties, part_info=part_info)

    assert plugin.get_build_environment() == {
        "CGO_ENABLED": "1",
        "GOBIN": f"{new_dir}/parts/my-part/install/bin",
        "PARTS_GO_LDFLAGS": "-ldflags -linkmode=external",
    }


def test_get_build_commands():
    properties = GoPlugin.properties_class.unmarshal({"source": "."})
    part_info = PartInfo(project_info=ProjectInfo(), part=Part("my-part", {}))
    plugin = GoPlugin(properties=properties, part_info=part_info)

    assert plugin.get_build_commands() == [
        "go mod download",
        'go install -p "1"  ${PARTS_GO_LDFLAGS} ./...',
    ]


def test_get_build_commands_with_buildtags():
    properties = GoPlugin.properties_class.unmarshal(
        {"source": ".", "go-buildtags": ["dev", "debug"]}
    )
    part_info = PartInfo(project_info=ProjectInfo(), part=Part("my-part", {}))
    plugin = GoPlugin(properties=properties, part_info=part_info)

    assert plugin.get_build_commands() == [
        "go mod download",
        'go install -p "1" -tags=dev,debug ${PARTS_GO_LDFLAGS} ./...',
    ]


def test_invalid_parameters():
    with pytest.raises(ValidationError) as raised:
        GoPlugin.properties_class.unmarshal({"source": ".", "go-invalid": True})
    err = raised.value.errors()
    assert len(err) == 1
    assert err[0]["loc"] == ("go-invalid",)
    assert err[0]["type"] == "value_error.extra"


def test_missing_parameters():
    with pytest.raises(ValidationError) as raised:
        GoPlugin.properties_class.unmarshal({})
    err = raised.value.errors()
    assert len(err) == 1
    assert err[0]["loc"] == ("source",)
    assert err[0]["type"] == "value_error.missing"
