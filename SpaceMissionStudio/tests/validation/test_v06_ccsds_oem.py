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
"""V-06: CCSDS OEM exchange with GMAT R2026a (Phase 3, R13).

* GMAT -> tool: GMAT's OEM (``gmat/gmat_written.oem``, version 1.0) is read
  and checked against CCSDS 502.0-B-3; its states equal GMAT's own report.
* tool -> GMAT: the tool's OEM (``tool_written.oem``) conforms, and GMAT,
  reading it through its CCSDS-OEM ephemeris propagator, returns the tool's
  trajectory between the ephemeris nodes. GMAT reads only version 1.0 and
  Lagrange interpolation (finding F-08), so it was given a copy whose only
  change is the version line (``compliance/validation/gmat/tool_written_as_v1.oem``).
"""

from dataclasses import replace

import numpy as np
import pytest
import validation_cases as cases

pytestmark = pytest.mark.requirement("CCSDS-502.0-B-3 5.1.1", "CCSDS-502.0-B-3 7.5.3", "E-ST-40C 5.6.3.1")


def test_tool_reads_and_checks_the_oem_gmat_writes():
    """GMAT's OEM reads; against 502.0-B-3 it has one error (CENTER_NAME =
    'Earth' mixes case, 7.5.3) and a warning that it is a version 1.0
    message; its states every 600 s equal GMAT's own two-body report to 1 mm."""
    from spacemissionstudio.engine import ccsds_odm as odm

    text = (cases.GMAT_DATA / "gmat_written.oem").read_text()
    issues = odm.validate(text)
    assert [(i.level, i.clause) for i in issues if i.level == "error"] == [("error", "7.5.3")]
    assert "CENTER_NAME" in next(i.message for i in issues if i.level == "error")
    assert any(i.level == "warning" and "version 1.0" in i.message for i in issues)
    segment = odm.read(text).segments[0]
    states = np.array(segment.states)
    report = np.loadtxt(cases.gmat_reference(cases.CONTACT_CASE))
    rows = int(cases.OEM_HOURS * 3600.0 / cases.OUTPUT_STEP_S) + 1
    np.testing.assert_allclose(states[::10][:rows, :3], report[:rows, 1:4], atol=1e-6)  # [km]


def test_the_oem_the_tool_writes_conforms():
    """The committed tool OEM (Lagrange, degree 7, 60 s) has no issues."""
    from spacemissionstudio.engine import ccsds_odm as odm

    assert odm.validate((cases.DATA / "tool_written.oem").read_text()) == []


@pytest.mark.requires_basilisk
def test_gmat_reading_the_tool_oem_returns_the_tool_trajectory(record_property):
    """GMAT's interpolation of the tool's OEM between nodes is within 1 cm
    of the tool's own run at the same instants."""
    from test_v04_propagation import _gmat_elapsed_tdb_s, _hermite, _tool_run

    gmat = np.loadtxt(cases.gmat_reference("gmat_reads_tool_oem"))
    case = replace(cases.case(cases.CONTACT_CASE), days=cases.OEM_HOURS / 24.0)
    t, x, v = _tool_run(case)
    difference_m = np.linalg.norm(_hermite(t, x, v, _gmat_elapsed_tdb_s(case, gmat[:, 0])) - gmat[:, 1:4],
                                  axis=1) * 1e3
    record_property("max_difference_m", float(difference_m.max()))
    print(f"GMAT reading the tool's OEM: largest difference {difference_m.max():.4f} m")
    assert difference_m.max() < cases.OEM_TOLERANCE_M
