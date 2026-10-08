#
#  ISC License
#
#  Copyright (c) 2026, Autonomous Vehicle Systems Lab, University of Colorado at Boulder
#
#  Permission to use, copy, modify, and/or distribute this software for any
#  purpose with or without fee is hereby granted, provided that the above
#  copyright notice and this permission notice appear in all copies.
#
#  THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
#  WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
#  MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
#  ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
#  WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
#  ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
#  OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.
#

"""Coverage gate of ``compliance/tools/metrics.py`` (coding standard rule
C-10; thresholds agreed with the customer, decision 15)."""

import importlib.util
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "metrics_tool", Path(__file__).resolve().parent.parent / "compliance" / "tools" / "metrics.py")
metrics_tool = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(metrics_tool)

pytestmark = pytest.mark.requirement("E-ST-40C 5.8.3.5b")


def _metrics(statement, branch):
    return {"coverage": {"statement_percent": statement, "branch_percent": branch}}


def test_gate_passes_at_and_above_the_thresholds():
    """Coverage equal to or above both thresholds gives no failure."""
    assert metrics_tool.coverage_gate(_metrics(90.0, 80.0), 90, 80) == []
    assert metrics_tool.coverage_gate(_metrics(91.5, 81.7), 90, 80) == []


def test_gate_reports_each_threshold_missed():
    """A statement or branch value below its threshold gives one message each."""
    failures = metrics_tool.coverage_gate(_metrics(89.9, 79.9), 90, 80)
    assert len(failures) == 2
    assert failures[0].startswith("statement coverage 89.9")
    assert failures[1].startswith("branch coverage 79.9")


def test_gate_fails_when_not_measured():
    """A requested threshold fails when its coverage value was not measured."""
    assert metrics_tool.coverage_gate({}, 90, None) == ["statement coverage None is below 90 % (rule C-10)"]
    assert metrics_tool.coverage_gate(_metrics(95.0, None), 90, 80) == [
        "branch coverage None is below 80 % (rule C-10)"]


def test_gate_without_thresholds_checks_nothing():
    """No threshold given means no check, even without coverage data."""
    assert metrics_tool.coverage_gate({}) == []
