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

import textwrap
from typing import List

import pytest
import yaml

import craft_parts
from craft_parts import Action, ActionType, Step


class TestOverlayLayerOrder:
    @pytest.fixture
    def lifecycle(self, new_dir):
        parts_yaml = textwrap.dedent(
            """
            parts:
              p1:
                plugin: nil
              p2:
                plugin: nil
              p3:
                plugin: nil
            """
        )
        parts = yaml.safe_load(parts_yaml)

        return craft_parts.LifecycleManager(parts, application_name="test_layers")

    def test_layer_order_bottom_layer(self, lifecycle):
        # prime p1
        actions = lifecycle.plan(Step.PRIME, ["p1"])
        assert actions == [
            Action("p1", Step.PULL),
            Action("p1", Step.OVERLAY),
            Action("p1", Step.BUILD),
            Action("p1", Step.STAGE),
            Action("p1", Step.PRIME),
        ]

    def test_layer_order_top_layer(self, lifecycle):
        # prime p3, requires p1 and p2 overlay
        actions = lifecycle.plan(Step.PRIME, ["p3"])
        assert actions == [
            Action("p3", Step.PULL),
            Action("p1", Step.PULL, reason="required to overlay 'p3'"),
            Action("p1", Step.OVERLAY, reason="required to overlay 'p3'"),
            Action("p2", Step.PULL, reason="required to overlay 'p3'"),
            Action("p2", Step.OVERLAY, reason="required to overlay 'p3'"),
            Action("p3", Step.OVERLAY),
            Action("p3", Step.BUILD),
            Action("p3", Step.STAGE),
            Action("p3", Step.PRIME),
        ]

    def test_layer_parameter_change(self, lifecycle):
        actions = lifecycle.plan(Step.OVERLAY, ["p3"])
        assert actions == [
            Action("p3", Step.PULL),
            Action("p1", Step.PULL, reason="required to overlay 'p3'"),
            Action("p1", Step.OVERLAY, reason="required to overlay 'p3'"),
            Action("p2", Step.PULL, reason="required to overlay 'p3'"),
            Action("p2", Step.OVERLAY, reason="required to overlay 'p3'"),
            Action("p3", Step.OVERLAY),
        ]
        with lifecycle.action_executor() as ctx:
            ctx.execute(actions)

        # plan again with no changes
        actions = lifecycle.plan(Step.OVERLAY, ["p3"])
        assert actions == [
            # fmt: off
            Action("p3", Step.PULL, action_type=ActionType.SKIP, reason="already ran"),
            Action("p3", Step.OVERLAY, action_type=ActionType.RERUN, reason="requested step"),
            # fmt: on
        ]

        # change a parameter in the parts definition, p2 overlay will rerun
        parts_yaml = textwrap.dedent(
            """
            parts:
              p1:
                plugin: nil
              p2:
                plugin: nil
                override-overlay: echo
              p3:
                plugin: nil
            """
        )
        parts = yaml.safe_load(parts_yaml)

        lf = craft_parts.LifecycleManager(parts, application_name="test_layers")
        actions = lf.plan(Step.OVERLAY, ["p3"])
        assert actions == [
            # fmt: off
            Action("p3", Step.PULL, action_type=ActionType.SKIP, reason="already ran"),
            Action("p2", Step.PULL, action_type=ActionType.SKIP, reason="already ran"),
            Action("p2", Step.OVERLAY, action_type=ActionType.RERUN, reason="required to overlay 'p3'"),
            Action("p3", Step.OVERLAY, action_type=ActionType.RERUN, reason="requested step"),
            # fmt: on
        ]


@pytest.mark.usefixtures("new_dir")
class TestOverlayBuildDependency:
    def test_part_overlay_visibility_dependency_top(self):
        parts_yaml = textwrap.dedent(
            """
            parts:
              p1:
                plugin: nil
              p2:
                plugin: nil
              p3:
                plugin: nil
                overlay-visibility: True
            """
        )
        parts = yaml.safe_load(parts_yaml)
        lf = craft_parts.LifecycleManager(parts, application_name="test_layers")

        actions = lf.plan(Step.BUILD, ["p3"])
        assert actions == [
            # fmt: off
            Action("p3", Step.PULL),
            Action("p1", Step.PULL, reason="required to overlay 'p3'"),
            Action("p1", Step.OVERLAY, reason="required to overlay 'p3'"),
            Action("p2", Step.PULL, reason="required to overlay 'p3'"),
            Action("p2", Step.OVERLAY, reason="required to overlay 'p3'"),
            Action("p3", Step.OVERLAY),
            Action("p3", Step.BUILD)
            # fmt: on
        ]

    def test_part_overlay_visibility_dependency_middle(self):
        parts_yaml = textwrap.dedent(
            """
            parts:
              p1:
                plugin: nil
              p2:
                plugin: nil
                overlay-visibility: True
              p3:
                plugin: nil
            """
        )
        parts = yaml.safe_load(parts_yaml)
        lf = craft_parts.LifecycleManager(parts, application_name="test_layers")

        actions = lf.plan(Step.BUILD, ["p2"])
        assert actions == [
            # fmt: off
            Action("p2", Step.PULL),
            Action("p1", Step.PULL, reason="required to overlay 'p2'"),
            Action("p1", Step.OVERLAY, reason="required to overlay 'p2'"),
            Action("p2", Step.OVERLAY),
            Action("p3", Step.PULL, reason="required to build 'p2'"),
            Action("p3", Step.OVERLAY, reason="required to build 'p2'"),
            Action("p2", Step.BUILD)
            # fmt: on
        ]

    def test_part_overlay_visibility_dependency_bottom(self):
        parts_yaml = textwrap.dedent(
            """
            parts:
              p1:
                plugin: nil
                overlay-visibility: True
              p2:
                plugin: nil
              p3:
                plugin: nil
            """
        )
        parts = yaml.safe_load(parts_yaml)
        lf = craft_parts.LifecycleManager(parts, application_name="test_layers")

        actions = lf.plan(Step.BUILD, ["p1"])
        assert actions == [
            # fmt: off
            Action("p1", Step.PULL),
            Action("p1", Step.OVERLAY),
            Action("p2", Step.PULL, reason="required to build 'p1'"),
            Action("p2", Step.OVERLAY, reason="required to build 'p1'"),
            Action("p3", Step.PULL, reason="required to build 'p1'"),
            Action("p3", Step.OVERLAY, reason="required to build 'p1'"),
            Action("p1", Step.BUILD)
            # fmt: on
        ]


@pytest.mark.usefixtures("new_dir")
class TestOverlayStageDependency:
    def test_part_overlay_stage_dependency_top(self):
        parts_yaml = textwrap.dedent(
            """
            parts:
              p1:
                plugin: nil
              p2:
                plugin: nil
              p3:
                plugin: nil
                override-overlay: echo overlay
            """
        )
        parts = yaml.safe_load(parts_yaml)
        lf = craft_parts.LifecycleManager(parts, application_name="test_layers")

        actions = lf.plan(Step.STAGE, ["p3"])
        assert actions == [
            # fmt: off
            Action("p3", Step.PULL),
            Action("p1", Step.PULL, reason="required to overlay 'p3'"),
            Action("p1", Step.OVERLAY, reason="required to overlay 'p3'"),
            Action("p2", Step.PULL, reason="required to overlay 'p3'"),
            Action("p2", Step.OVERLAY, reason="required to overlay 'p3'"),
            Action("p3", Step.OVERLAY),
            Action("p3", Step.BUILD),
            Action("p3", Step.STAGE)
            # fmt: on
        ]

    def test_part_overlay_stage_dependency_middle(self):
        parts_yaml = textwrap.dedent(
            """
            parts:
              p1:
                plugin: nil
              p2:
                plugin: nil
                override-overlay: echo overlay
              p3:
                plugin: nil
            """
        )
        parts = yaml.safe_load(parts_yaml)
        lf = craft_parts.LifecycleManager(parts, application_name="test_layers")

        actions = lf.plan(Step.STAGE, ["p2"])
        assert actions == [
            # fmt: off
            Action("p2", Step.PULL),
            Action("p1", Step.PULL, reason="required to overlay 'p2'"),
            Action("p1", Step.OVERLAY, reason="required to overlay 'p2'"),
            Action("p2", Step.OVERLAY),
            Action("p2", Step.BUILD),
            Action("p3", Step.PULL, reason="required to stage 'p2'"),
            Action("p3", Step.OVERLAY, reason="required to stage 'p2'"),
            Action("p2", Step.STAGE)
            # fmt: on
        ]

    def test_part_overlay_stage_dependency_bottom(self):
        parts_yaml = textwrap.dedent(
            """
            parts:
              p1:
                plugin: nil
                override-overlay: echo overlay
              p2:
                plugin: nil
              p3:
                plugin: nil
            """
        )
        parts = yaml.safe_load(parts_yaml)
        lf = craft_parts.LifecycleManager(parts, application_name="test_layers")

        actions = lf.plan(Step.STAGE, ["p1"])
        assert actions == [
            # fmt: off
            Action("p1", Step.PULL),
            Action("p1", Step.OVERLAY),
            Action("p1", Step.BUILD),
            Action("p2", Step.PULL, reason="required to stage 'p1'"),
            Action("p2", Step.OVERLAY, reason="required to stage 'p1'"),
            Action("p3", Step.PULL, reason="required to stage 'p1'"),
            Action("p3", Step.OVERLAY, reason="required to stage 'p1'"),
            Action("p1", Step.STAGE)
            # fmt: on
        ]


@pytest.mark.usefixtures("new_dir")
class TestOverlayInvalidationFlow:
    def test_pull_dirty_single_part(self):
        parts_yaml = textwrap.dedent(
            """
            parts:
              p1:
                plugin: nil
            """
        )
        parts = yaml.safe_load(parts_yaml)
        lf = craft_parts.LifecycleManager(parts, application_name="test_layers")

        actions = lf.plan(Step.PRIME)
        assert actions == [
            Action("p1", Step.PULL),
            Action("p1", Step.OVERLAY),
            Action("p1", Step.BUILD),
            Action("p1", Step.STAGE),
            Action("p1", Step.PRIME),
        ]

        with lf.action_executor() as ctx:
            ctx.execute(actions)

        # change a property of interest
        parts_yaml = textwrap.dedent(
            """
            parts:
              p1:
                plugin: nil
                source: .
            """
        )
        parts = yaml.safe_load(parts_yaml)
        lf = craft_parts.LifecycleManager(parts, application_name="test_layers")

        actions = lf.plan(Step.PRIME)
        assert actions == [
            # fmt: off
            Action("p1", Step.PULL, action_type=ActionType.RERUN, reason="'source' property changed"),
            Action("p1", Step.OVERLAY),
            Action("p1", Step.BUILD),
            Action("p1", Step.STAGE),
            Action("p1", Step.PRIME),
            # fmt: on
        ]

    def test_pull_dirty_multipart(self):
        parts_yaml = textwrap.dedent(
            """
            parts:
              p1:
                plugin: nil
                overlay-visibility: True
              p2:
                plugin: nil
                override-overlay: echo overlay
              p3:
                plugin: nil
            """
        )
        parts = yaml.safe_load(parts_yaml)
        lf = craft_parts.LifecycleManager(parts, application_name="test_layers")

        actions = lf.plan(Step.PRIME)
        assert actions == [
            Action("p1", Step.PULL),
            Action("p2", Step.PULL),
            Action("p3", Step.PULL),
            Action("p1", Step.OVERLAY),
            Action("p2", Step.OVERLAY),
            Action("p3", Step.OVERLAY),
            Action("p1", Step.BUILD),
            Action("p2", Step.BUILD),
            Action("p3", Step.BUILD),
            Action("p1", Step.STAGE),
            Action("p2", Step.STAGE),
            Action("p3", Step.STAGE),
            Action("p1", Step.PRIME),
            Action("p2", Step.PRIME),
            Action("p3", Step.PRIME),
        ]

        with lf.action_executor() as ctx:
            ctx.execute(actions)

        # change a property of interest in p2
        parts_yaml = textwrap.dedent(
            """
            parts:
              p1:
                plugin: nil
                overlay-visibility: True
              p2:
                plugin: nil
                overlay-packages: [hello]
              p3:
                plugin: nil
            """
        )
        parts = yaml.safe_load(parts_yaml)
        lf = craft_parts.LifecycleManager(parts, application_name="test_layers")

        actions = lf.plan(Step.PRIME)
        assert actions == [
            # fmt: off
            Action("p1", Step.PULL, action_type=ActionType.SKIP, reason="already ran"),
            Action("p2", Step.PULL, action_type=ActionType.RERUN, reason="'overlay-packages' property changed"),
            Action("p3", Step.PULL, action_type=ActionType.SKIP, reason="already ran"),
            Action("p1", Step.OVERLAY, action_type=ActionType.SKIP, reason="already ran"),
            Action("p2", Step.OVERLAY),
            Action("p3", Step.OVERLAY, action_type=ActionType.REAPPLY, reason="previous layer changed"),
            Action("p1", Step.BUILD, action_type=ActionType.RERUN, reason="overlay changed"),
            Action("p2", Step.BUILD),
            Action("p3", Step.BUILD, action_type=ActionType.SKIP, reason="already ran"),
            Action("p1", Step.STAGE),
            Action("p2", Step.STAGE),
            Action("p3", Step.STAGE, action_type=ActionType.SKIP, reason="already ran"),
            Action("p1", Step.PRIME),
            Action("p2", Step.PRIME),
            Action("p3", Step.PRIME, action_type=ActionType.SKIP, reason="already ran"),
            # fmt: on
        ]

    def test_overlay_clean(self):
        parts_yaml = textwrap.dedent(
            """
            parts:
              p1:
                plugin: nil
              p2:
                plugin: nil
                override-overlay: echo overlay
              p3:
                plugin: nil
            """
        )
        parts = yaml.safe_load(parts_yaml)
        lf = craft_parts.LifecycleManager(parts, application_name="test_layers")

        actions = lf.plan(Step.PRIME)
        assert actions == [
            Action("p1", Step.PULL),
            Action("p2", Step.PULL),
            Action("p3", Step.PULL),
            Action("p1", Step.OVERLAY),
            Action("p2", Step.OVERLAY),
            Action("p3", Step.OVERLAY),
            Action("p1", Step.BUILD),
            Action("p2", Step.BUILD),
            Action("p3", Step.BUILD),
            Action("p1", Step.STAGE),
            Action("p2", Step.STAGE),
            Action("p3", Step.STAGE),
            Action("p1", Step.PRIME),
            Action("p2", Step.PRIME),
            Action("p3", Step.PRIME),
        ]

        with lf.action_executor() as ctx:
            ctx.execute(actions)

        # invalidate p2 overlay
        parts_yaml = textwrap.dedent(
            """
            parts:
              p1:
                plugin: nil
              p2:
                plugin: nil
                override-overlay: echo changed
              p3:
                plugin: nil
            """
        )
        parts = yaml.safe_load(parts_yaml)
        lf = craft_parts.LifecycleManager(parts, application_name="test_layers")

        actions = lf.plan(Step.PRIME)
        assert actions == [
            # fmt: off
            Action("p1", Step.PULL, action_type=ActionType.SKIP, reason="already ran"),
            Action("p2", Step.PULL, action_type=ActionType.SKIP, reason="already ran"),
            Action("p3", Step.PULL, action_type=ActionType.SKIP, reason="already ran"),
            Action("p1", Step.OVERLAY, action_type=ActionType.SKIP, reason="already ran"),
            Action("p2", Step.OVERLAY, action_type=ActionType.RERUN, reason="'override-overlay' property changed"),
            Action("p3", Step.OVERLAY, action_type=ActionType.REAPPLY, reason="previous layer changed"),
            Action("p1", Step.BUILD, action_type=ActionType.SKIP, reason="already ran"),
            Action("p2", Step.BUILD, action_type=ActionType.SKIP, reason="already ran"),
            Action("p3", Step.BUILD, action_type=ActionType.SKIP, reason="already ran"),
            Action("p1", Step.STAGE, action_type=ActionType.SKIP, reason="already ran"),
            Action("p2", Step.STAGE, action_type=ActionType.RERUN, reason="overlay changed"),
            Action("p3", Step.STAGE, action_type=ActionType.SKIP, reason="already ran"),
            Action("p1", Step.PRIME, action_type=ActionType.SKIP, reason="already ran"),
            Action("p2", Step.PRIME),
            Action("p3", Step.PRIME, action_type=ActionType.SKIP, reason="already ran"),
            # fmt: on
        ]


class TestOverlaySpecScenarios:
    def test_overlay_spec_scenario_1(self):
        parts_yaml = textwrap.dedent(
            """
            parts:
              A:
                plugin: nil
                after: [B]
              B:
                plugin: nil
            """
        )
        parts = yaml.safe_load(parts_yaml)
        lf = craft_parts.LifecycleManager(parts, application_name="test_layers")

        actions = _filter_skip(lf.plan(Step.STAGE))
        assert actions == [
            Action("B", Step.PULL),
            Action("A", Step.PULL),
            Action("B", Step.OVERLAY),
            Action("A", Step.OVERLAY),
            Action("B", Step.BUILD),
            Action("B", Step.STAGE, reason="required to build 'A'"),
            Action("A", Step.BUILD),
            Action("A", Step.STAGE),
        ]

    def test_overlay_spec_scenario_2_stage_all(self):
        parts_yaml = textwrap.dedent(
            """
            parts:
              A:
                plugin: nil
                override-overlay: echo A
              B:
                plugin: nil
                override-overlay: echo B
            """
        )
        parts = yaml.safe_load(parts_yaml)
        lf = craft_parts.LifecycleManager(parts, application_name="test_layers")

        actions = _filter_skip(lf.plan(Step.STAGE))
        assert actions == [
            Action("A", Step.PULL),
            Action("B", Step.PULL),
            Action("A", Step.OVERLAY),
            Action("B", Step.OVERLAY),
            Action("A", Step.BUILD),
            Action("B", Step.BUILD),
            Action("A", Step.STAGE),
            Action("B", Step.STAGE),
        ]

    def test_overlay_spec_scenario_2_stage_a(self):
        parts_yaml = textwrap.dedent(
            """
            parts:
              A:
                plugin: nil
                override-overlay: echo A
              B:
                plugin: nil
                override-overlay: echo B
            """
        )
        parts = yaml.safe_load(parts_yaml)
        lf = craft_parts.LifecycleManager(parts, application_name="test_layers")

        actions = _filter_skip(lf.plan(Step.STAGE, part_names=["A"]))
        assert actions == [
            Action("A", Step.PULL),
            Action("A", Step.OVERLAY),
            Action("A", Step.BUILD),
            Action("B", Step.PULL, reason="required to stage 'A'"),
            Action("B", Step.OVERLAY, reason="required to stage 'A'"),
            Action("A", Step.STAGE),
        ]

    def test_overlay_spec_scenario_3_stage_a(self):
        parts_yaml = textwrap.dedent(
            """
            parts:
              A:
                plugin: nil
                overlay-visibility: True
              B:
                plugin: nil
                after: [A]
                override-overlay: echo B
            """
        )
        parts = yaml.safe_load(parts_yaml)
        lf = craft_parts.LifecycleManager(parts, application_name="test_layers")

        actions = _filter_skip(lf.plan(Step.STAGE, part_names=["A"]))
        assert actions == [
            Action("A", Step.PULL),
            Action("A", Step.OVERLAY),
            Action("B", Step.PULL, reason="required to build 'A'"),
            Action("B", Step.OVERLAY, reason="required to build 'A'"),
            Action("A", Step.BUILD),
            Action("A", Step.STAGE),
        ]

    def test_overlay_spec_scenario_3_stage_b(self):
        parts_yaml = textwrap.dedent(
            """
            parts:
              A:
                plugin: nil
                overlay-visibility: True
              B:
                plugin: nil
                after: [A]
                override-overlay: echo B
            """
        )
        parts = yaml.safe_load(parts_yaml)
        lf = craft_parts.LifecycleManager(parts, application_name="test_layers")

        actions = _filter_skip(lf.plan(Step.STAGE, part_names=["B"]))
        assert actions == [
            Action("B", Step.PULL),
            Action("A", Step.PULL, reason="required to overlay 'B'"),
            Action("A", Step.OVERLAY, reason="required to overlay 'B'"),
            Action("B", Step.OVERLAY),
            Action("A", Step.BUILD, reason="required to build 'B'"),
            Action("A", Step.STAGE, reason="required to build 'B'"),
            Action("B", Step.BUILD),
            Action("B", Step.STAGE),
        ]

    def test_overlay_spec_scenario_4_stage_a(self):
        parts_yaml = textwrap.dedent(
            """
            parts:
              A:
                plugin: nil
                overlay-visibility: True
              B:
                plugin: nil
                override-overlay: echo B
            """
        )
        parts = yaml.safe_load(parts_yaml)
        lf = craft_parts.LifecycleManager(parts, application_name="test_layers")

        actions = _filter_skip(lf.plan(Step.STAGE, part_names=["A"]))
        assert actions == [
            Action("A", Step.PULL),
            Action("A", Step.OVERLAY),
            Action("B", Step.PULL, reason="required to build 'A'"),
            Action("B", Step.OVERLAY, reason="required to build 'A'"),
            Action("A", Step.BUILD),
            Action("A", Step.STAGE),
        ]

    def test_overlay_spec_scenario_4_stage_b(self):
        parts_yaml = textwrap.dedent(
            """
            parts:
              A:
                plugin: nil
                overlay-visibility: True
              B:
                plugin: nil
                override-overlay: echo B
            """
        )
        parts = yaml.safe_load(parts_yaml)
        lf = craft_parts.LifecycleManager(parts, application_name="test_layers")

        actions = _filter_skip(lf.plan(Step.STAGE, part_names=["B"]))
        assert actions == [
            Action("B", Step.PULL),
            Action("A", Step.PULL, reason="required to overlay 'B'"),
            Action("A", Step.OVERLAY, reason="required to overlay 'B'"),
            Action("B", Step.OVERLAY),
            Action("B", Step.BUILD),
            Action("B", Step.STAGE),
        ]

    def test_overlay_spec_scenario_5_stage_a(self):
        parts_yaml = textwrap.dedent(
            """
            parts:
              A:
                plugin: nil
                overlay-visibility: True
                override-overlay: echo A
              B:
                plugin: nil
                overlay-visibility: True
                override-overlay: echo B
            """
        )
        parts = yaml.safe_load(parts_yaml)
        lf = craft_parts.LifecycleManager(parts, application_name="test_layers")

        actions = _filter_skip(lf.plan(Step.STAGE, part_names=["A"]))
        assert actions == [
            Action("A", Step.PULL),
            Action("A", Step.OVERLAY),
            Action("B", Step.PULL, reason="required to build 'A'"),
            Action("B", Step.OVERLAY, reason="required to build 'A'"),
            Action("A", Step.BUILD),
            Action("A", Step.STAGE),
        ]

    def test_overlay_spec_scenario_5_stage_b(self):
        parts_yaml = textwrap.dedent(
            """
            parts:
              A:
                plugin: nil
                overlay-visibility: True
                override-overlay: echo A
              B:
                plugin: nil
                overlay-visibility: True
                override-overlay: echo B
            """
        )
        parts = yaml.safe_load(parts_yaml)
        lf = craft_parts.LifecycleManager(parts, application_name="test_layers")

        actions = _filter_skip(lf.plan(Step.STAGE, part_names=["B"]))
        assert actions == [
            Action("B", Step.PULL),
            Action("A", Step.PULL, reason="required to overlay 'B'"),
            Action("A", Step.OVERLAY, reason="required to overlay 'B'"),
            Action("B", Step.OVERLAY),
            Action("B", Step.BUILD),
            Action("B", Step.STAGE),
        ]


def _filter_skip(actions: List[Action]) -> List[Action]:
    return [a for a in actions if a.action_type != ActionType.SKIP]