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

"""The Go plugin."""

from typing import Any, Dict, List, Set, cast

from .base import Plugin, PluginModel, extract_plugin_properties
from .properties import PluginProperties


class GoPluginProperties(PluginProperties, PluginModel):
    """The part properties used by the Go plugin."""

    go_channel: str = "latest/stable"
    go_buildtags: List[str] = []

    # part properties required by the plugin
    source: str

    @classmethod
    def unmarshal(cls, data: Dict[str, Any]):
        """Populate make properties from the part specification.

        :param data: A dictionary containing part properties.

        :return: The populated plugin properties data object.

        :raise pydantic.ValidationError: If validation fails.
        """
        plugin_data = extract_plugin_properties(
            data, plugin_name="go", required=["source"]
        )
        return cls(**plugin_data)


class GoPlugin(Plugin):
    """The go plugin can be used for go projects using go.mod.

    This plugin uses the common plugin keywords as well as those for "sources".
    For more information check the 'plugins' topic for the former and the
    'sources' topic for the latter.

    Additionally, this plugin uses the following plugin-specific keywords:

    - ``go-channel``
      (string, default: latest/stable)
      The Snap Store channel to install go from.

    - ``go-buildtags``
      (list of strings)
      Tags to use during the go build. Default is not to use any build tags.
    """

    properties_class = GoPluginProperties

    def get_build_snaps(self) -> Set[str]:
        """Return a set of required snaps to install in the build environment."""
        options = cast(GoPluginProperties, self._options)
        return {f"go/{options.go_channel}"}

    def get_build_packages(self) -> Set[str]:
        """Return a set of required packages to install in the build environment."""
        return {"gcc"}

    def get_build_environment(self) -> Dict[str, str]:
        """Return a dictionary with the environment to use in the build step."""
        return {
            "PARTS_GO_LDFLAGS": "-ldflags -linkmode=external",
            "CGO_ENABLED": "1",
            "GOBIN": "{}/bin".format(self._part_info.part_install_dir),
        }

    def get_build_commands(self) -> List[str]:
        """Return a list of commands to run during the build step."""
        options = cast(GoPluginProperties, self._options)

        if options.go_buildtags:
            tags = "-tags={}".format(",".join(options.go_buildtags))
        else:
            tags = ""

        return [
            "go mod download",
            'go install -p "{}" {} ${{PARTS_GO_LDFLAGS}} ./...'.format(
                self._part_info.parallel_build_count,
                tags,
            ),
        ]
