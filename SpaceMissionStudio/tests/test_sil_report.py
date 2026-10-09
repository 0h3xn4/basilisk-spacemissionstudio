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

"""The SIL comparison (SRS-F-19), without Basilisk: residual statistics
per signal, never-written outputs, NaN, the sampled series, timing
summaries and the report's JSON, CSV and plottable forms."""

import csv
import math
import struct

import numpy as np
import pytest

from spacemissionstudio.fsw_export.model import layout_hash
from spacemissionstudio.sil.contract import PortSpec
from spacemissionstudio.sil.report import Comparator, SilReport, timing_summary

# A payload of a double[3] and an int32, 4 bytes of padding: what leaves() reads, padding skipped.
LAYOUT = {"itemsize": 32, "fields": [{"name": "torque", "offset": 0, "shape": [3], "kind": "<f8"},
                                     {"name": "count", "offset": 24, "shape": [], "kind": "<i4"}]}
OUT = PortSpec("rw_torqueOutMsg", "Demo", 32, layout_hash("Demo", LAYOUT))
TLM = PortSpec("guid_out", "Demo", 32, layout_hash("Demo", LAYOUT))


def _payload(x, y, z, n):
    return struct.pack("<3di", x, y, z, n) + b"\xff" * 4  # padding differs on purpose: never compared


def _report(**changes):
    fields = dict(spacecraft="sat-1", binary="/x/fsw_host", binary_sha256="0" * 64, fsw_name="fake",
                  fsw_config_digest="0" * 64, scenario_config_digest="1" * 64, contract_version=1, rate_ns=1_000_000_000,
                  address_kind="unix")
    fields.update(changes)
    return SilReport(**fields)


def test_residuals_are_external_minus_reference_per_scalar_with_their_time():
    """Each scalar of each port: largest |residual| and when, RMS, largest
    |reference|; an output not written at a step is counted there, and a
    NaN on one side only is an infinite error."""
    comparator = Comparator([OUT], [TLM], {"Demo": LAYOUT}, expected_steps=4)
    ref = _payload(1.0, 2.0, 0.0, 5)
    comparator.add(0.0, [_payload(1.0, 2.5, 0.0, 5), ref], [ref, ref])
    comparator.add(1.0, [_payload(0.0, 2.0, 0.0, 6), None], [ref, ref])
    comparator.add(2.0, [_payload(float("nan"), 2.0, 0.0, 5), ref], [ref, ref])
    report = _report()
    comparator.finish(report)
    stats = {s.name: s for s in report.signals}
    assert set(stats) == {f"{p}.{f}" for p in ("rw_torqueOutMsg", "guid_out")
                          for f in ("torque[0]", "torque[1]", "torque[2]", "count")}
    assert stats["rw_torqueOutMsg.torque[1]"].max_abs_error == pytest.approx(0.5)
    assert stats["rw_torqueOutMsg.torque[1]"].time_of_max_s == 0.0
    assert stats["rw_torqueOutMsg.torque[1]"].rms_error == pytest.approx(math.sqrt(0.25 / 3))
    assert math.isinf(stats["rw_torqueOutMsg.torque[0]"].max_abs_error)
    assert stats["rw_torqueOutMsg.count"].max_abs_error == 1.0 and stats["rw_torqueOutMsg.count"].time_of_max_s == 1.0
    assert stats["guid_out.torque[0]"].steps_missing == 1 and stats["guid_out.torque[0]"].max_abs_error == 0.0
    assert stats["rw_torqueOutMsg.torque[1]"].max_abs_reference == 2.0
    assert "rw_torqueOutMsg.torque[2]" not in report.residuals  # zero on both sides throughout: no series
    assert report.sample_times_s == [0.0, 1.0, 2.0]
    assert np.isnan(report.residuals["guid_out.torque[0]"][1])


def test_a_flight_software_that_never_writes_is_reported_as_such():
    comparator = Comparator([OUT], [], {"Demo": LAYOUT}, expected_steps=2)
    for t in (0.0, 1.0):
        comparator.add(t, [None], [_payload(1.0, 0.0, 0.0, 0)])
    report = _report()
    comparator.finish(report)
    report.steps = comparator.steps
    assert report.signals_missing == 4 and report.max_abs_error == 0.0
    assert "4 never written" in report.summary_lines()[4]


def test_the_report_round_trips_and_exports(tmp_path):
    """JSON back to the same report; the CSV has a time column and one per
    sampled signal; to_result_set() gives one plottable series per port."""
    comparator = Comparator([OUT], [TLM], {"Demo": LAYOUT}, expected_steps=3)
    for t in (0.0, 1.0, 2.0):
        comparator.add(t, [_payload(t, 0.0, 0.0, 0), _payload(0.0, 0.0, 0.0, 0)], [_payload(0.0, 1.0, 0.0, 0)] * 2)
    report = _report(round_trip=timing_summary([1_000_000, 2_000_000, 3_000_000]))
    comparator.finish(report)
    report.steps = 3
    again = SilReport.from_json(report.to_json())
    assert again == report
    assert report.round_trip["max_s"] == pytest.approx(3e-3) and report.round_trip["mean_s"] == pytest.approx(2e-3)
    path = tmp_path / "residuals.csv"
    report.write_residuals_csv(path)
    rows = list(csv.reader(path.open()))
    assert rows[0][0] == "time_s" and len(rows) == 4 and "rw_torqueOutMsg.torque[0]" in rows[0]
    result = report.to_result_set()
    series = result.series["sat-1.sil_residual.rw_torqueOutMsg"]
    assert list(series.columns) == ["torque[0]", "torque[1]"] and series.data.shape == (3, 2)
    assert series.data[2, 0] == 2.0 and series.data[0, 1] == -1.0


def test_long_runs_keep_a_bounded_sample_of_the_residuals():
    from spacemissionstudio.sil import report as module

    comparator = Comparator([OUT], [], {"Demo": LAYOUT}, expected_steps=module.MAX_SAMPLES * 3)
    for step in range(module.MAX_SAMPLES * 3):
        comparator.add(float(step), [_payload(1.0, 0.0, 0.0, 0)], [_payload(0.0, 0.0, 0.0, 0)])
    report = _report()
    comparator.finish(report)
    assert len(report.sample_times_s) == module.MAX_SAMPLES and report.sample_times_s[1] == 3.0
