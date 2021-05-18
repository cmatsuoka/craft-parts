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

import shutil
import tarfile
import textwrap
from pathlib import Path

import pytest
import yaml

import craft_parts
from craft_parts import Action, Step

_LOCAL_DIR = Path(__file__).parent


@pytest.mark.usefixtures("new_dir")
def test_source_tar():
    _parts_yaml = textwrap.dedent(
        """\
        parts:
          foo:
            plugin: make
            source: foobar.tar.gz
        """
    )

    parts = yaml.safe_load(_parts_yaml)
    src = _LOCAL_DIR / "data" / "foobar.tar.gz"
    dest = Path("foobar.tar.gz")
    shutil.copyfile(src, dest)
    lf = craft_parts.LifecycleManager(parts, application_name="test_tar")

    with lf.action_executor() as ctx:
        ctx.execute(Action("foo", Step.PULL))

    foo_src_dir = Path("parts", "foo", "src")
    assert list(foo_src_dir.rglob("*")) == [foo_src_dir / "foobar.txt"]


@pytest.mark.usefixtures("new_dir")
def test_source_tar_error():
    _parts_yaml = textwrap.dedent(
        """\
        parts:
          foo:
            plugin: make
            source: foobar.tar.gz
        """
    )

    parts = yaml.safe_load(_parts_yaml)
    Path("foobar.tar.gz").write_text("not a tar file")
    lf = craft_parts.LifecycleManager(parts, application_name="test_tar")

    with pytest.raises(tarfile.ReadError) as raised, lf.action_executor() as ctx:
        ctx.execute(Action("foo", Step.PULL))

    assert str(raised.value) == "file could not be opened successfully"
