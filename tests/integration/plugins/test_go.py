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

import subprocess
import textwrap
from pathlib import Path

import yaml

from craft_parts import LifecycleManager, Step


def test_go_plugin(new_dir, mocker):
    parts_yaml = textwrap.dedent(
        """
        parts:
          foo:
            plugin: go
            source: .
            go-buildtags: [my_tag]
        """
    )
    parts = yaml.safe_load(parts_yaml)

    Path("go.mod").write_text(
        textwrap.dedent(
            """
            module example.com/hello
            go 1.13
            require golang.org/x/crypto v0.0.0-20210513164829-c07d793c2f9a
            """
        )
    )

    Path("hello.go").write_text(
        textwrap.dedent(
            """
            // +build my_tag
            package main

            import "fmt"
            import "golang.org/x/crypto/md4"

            func main() {
                h := md4.New()
                h.Write([]byte("These pretzels are making me thirsty."))
                fmt.Printf("%x", h.Sum(nil))
            }
            """
        )
    )

    # go installed in the ci test setup
    mock_install = mocker.patch("craft_parts.packages.snaps.install_snaps")

    lf = LifecycleManager(parts, application_name="test_go")
    actions = lf.plan(Step.PRIME)

    with lf.action_executor() as ctx:
        ctx.execute(actions)

    mock_install.assert_called_once_with({"go/latest/stable"})

    binary = Path(lf.project_info.prime_dir, "bin", "hello")

    output = subprocess.check_output([str(binary)], text=True)
    assert output == "48c4e365090b30a32f084c4888deceaa"
