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

"""CCSDS 502.0-B-3 OPM/OMM/OEM in KVN (remediation R09).

The Annex G examples (``tests/data/ccsds``) must read and validate; each
validation rule is shown to fire on a message that breaks it; the
conversions round-trip. Figure G-6 (a TLE) and G-7 (its OMM) let the
TLE <-> OMM conversion be checked against the standard itself. Figure G-2
gives a state and its osculating elements: a, e, i, RAAN and argument of
pericenter are reproduced; its TRUE_ANOMALY (41.922339 deg) equals the
mean anomaly of that state (Basilisk rv2elem: true 43.549 deg, mean
41.92237 deg), an inconsistency in the informative example.
"""

import math
from datetime import datetime
from pathlib import Path

import numpy as np
import pytest

from spacemissionstudio.engine import ccsds_odm as odm

pytestmark = pytest.mark.requirement("CCSDS-502.0-B-3 3.2.2.2", "CCSDS-502.0-B-3 4.2.2.2", "CCSDS-502.0-B-3 5.2.2.2")

_DATA = Path(__file__).resolve().parent / "data" / "ccsds"
_G6 = ("1 23581U 95025A   07064.44075725 -.00000113  00000-0  10000-3 0  9250",
       "2 23581   3.0539  81.7939 0005013 249.2363 150.1602  1.00273272 43169")


def _example(name):
    return (_DATA / name).read_text()


def _errors(text):
    return [issue for issue in odm.validate(text) if issue.level == "error"]


@pytest.mark.requirement("CCSDS-502.0-B-3 3.1.1", "CCSDS-502.0-B-3 3.1.2", "CCSDS-502.0-B-3 3.1.5", "CCSDS-502.0-B-3 3.2.4.1", "CCSDS-502.0-B-3 3.2.4.4", "CCSDS-502.0-B-3 3.2.4.10", "CCSDS-502.0-B-3 3.2.4.12", "CCSDS-502.0-B-3 4.1.1", "CCSDS-502.0-B-3 4.1.5", "CCSDS-502.0-B-3 4.2.4.4", "CCSDS-502.0-B-3 4.2.4.5", "CCSDS-502.0-B-3 4.2.4.10", "CCSDS-502.0-B-3 5.1.1", "CCSDS-502.0-B-3 5.2.1.1", "CCSDS-502.0-B-3 5.2.1.2", "CCSDS-502.0-B-3 5.2.3.3", "CCSDS-502.0-B-3 5.2.4.2", "CCSDS-502.0-B-3 5.2.4.3", "CCSDS-502.0-B-3 5.2.4.6", "CCSDS-502.0-B-3 5.2.5.2", "CCSDS-502.0-B-3 5.2.5.5", "CCSDS-502.0-B-3 7.3.1", "CCSDS-502.0-B-3 7.3.5", "CCSDS-502.0-B-3 7.4.1", "CCSDS-502.0-B-3 7.4.1.1", "CCSDS-502.0-B-3 7.4.1.2", "CCSDS-502.0-B-3 7.4.1.3", "CCSDS-502.0-B-3 7.7.1.1", "CCSDS-502.0-B-3 7.8.3", "CCSDS-502.0-B-3 7.8.5", "CCSDS-502.0-B-3 7.8.6")
@pytest.mark.parametrize("name", sorted(p.name for p in _DATA.glob("*.txt")))
def test_every_annex_g_example_reads_and_conforms(name):
    """Figures G-1 to G-4, G-7 to G-9 and G-11 to G-13 have no errors."""
    text = _example(name)
    assert _errors(text) == []
    message = odm.read(text)
    assert message.kind == name[:3].upper()


@pytest.mark.requirement("CCSDS-502.0-B-3 3.2.3.3")
def test_a_frame_outside_the_recommended_set_is_a_warning():
    """G-3 uses ITRF1997, not in 3.2.3.3: a warning (needs an ICD), not an error."""
    issues = odm.validate(_example("opm_g3.txt"))
    assert [(i.level, i.clause) for i in issues] == [("warning", "3.2.3.3")]


@pytest.mark.requirement("CCSDS-502.0-B-3 5.2.3.3", "CCSDS-502.0-B-3 5.2.4.6", "CCSDS-502.0-B-3 5.2.5.3", "CCSDS-502.0-B-3 7.7.2.1", "CCSDS-502.0-B-3 7.7.2.2")
def test_oem_example_content_is_read():
    """G-11 has two segments; the first starts at 2019-12-18T12:00:00.331
    with the state (2789.619, -280.045, -1746.755) km; G-13 carries two
    6x6 lower-triangular covariances."""
    oem = odm.read(_example("oem_g11.txt"))
    assert len(oem.segments) == 2
    assert oem.segments[0].epochs[0] == "2019-12-18T12:00:00.331"
    assert oem.segments[0].states[0][:3] == [2789.619, -280.045, -1746.755]
    covariances = odm.read(_example("oem_g13.txt")).segments[0].covariances
    assert [len(c["rows"]) for c in covariances] == [6, 6]
    assert covariances[1]["rows"][5][5] == pytest.approx(6.2244443e-10)


def _replace(text, old, new):
    assert old in text
    return text.replace(old, new, 1)


@pytest.fixture
def g1():
    return _example("opm_g1.txt")


@pytest.mark.parametrize("old, new, clause", [
    ("ORIGINATOR     = JAXA\n", "", "Table 3-1"),
    ("OBJECT_ID      = 1998-999A\n", "", "Table 3-2"),
    ("X_DOT =            -0.873160\n", "", "Table 3-3"),
    ("MASS =", "WEIGHT =", "Table 3-3, 7.9.2"),
    ("X =              6503.514000\nY =              1239.647000", "Y =              1239.647000\nX =              "
     "6503.514000", "7.4.8"),
    ("Y =              1239.647000", "COMMENT inside a block\nY =              1239.647000", "7.8.7"),
    ("EPOCH =          2022-12-18T14:28:15.1172", "EPOCH =          2022/12/18 14:28:15", "7.5.10"),
    ("X =              6503.514000", "X =              6503.51400000000000", "7.5.6-7.5.7"),
    ("X =              6503.514000", "X =              6503.514000 [m]", "7.7.1.1"),
    ("SOLAR_RAD_COEFF =   1.000000", "SOLAR_RAD_COEFF =   1.000000 [n/a]", "7.7.1.3"),
    ("REF_FRAME      = ITRF2000", "REF_FRAME      = Itrf2000", "7.5.3"),
    ("X =              6503.514000", "X =\t6503.514000", "7.3.4"),
    ("COMMENT          GEOCENTRIC", "COMMENT " + "x" * 260 + " GEOCENTRIC", "7.3.2"),
])
@pytest.mark.requirement("CCSDS-502.0-B-3 3.2.3.1", "CCSDS-502.0-B-3 3.2.4.2", "CCSDS-502.0-B-3 7.3.2", "CCSDS-502.0-B-3 7.3.4", "CCSDS-502.0-B-3 7.4.8", "CCSDS-502.0-B-3 7.5.3", "CCSDS-502.0-B-3 7.5.6", "CCSDS-502.0-B-3 7.5.7", "CCSDS-502.0-B-3 7.5.10", "CCSDS-502.0-B-3 7.7.1.1", "CCSDS-502.0-B-3 7.7.1.3", "CCSDS-502.0-B-3 7.8.7", "CCSDS-502.0-B-3 7.9.2.1")
def test_each_opm_rule_is_enforced(g1, old, new, clause):
    """A G-1 OPM broken in one way gives an error citing the rule."""
    errors = _errors(_replace(g1, old, new))
    assert errors and any(clause in e.clause for e in errors), [str(e) for e in errors]


@pytest.mark.requirement("CCSDS-502.0-B-3 3.1.2", "CCSDS-502.0-B-3 3.2.4.7", "CCSDS-502.0-B-3 3.2.4.8", "CCSDS-502.0-B-3 3.2.4.9", "CCSDS-502.0-B-3 3.2.4.10")
def test_opm_block_rules():
    """Keplerian elements and covariance are all-or-none; a maneuver needs
    MASS and all its parameters; MAN_DELTA_MASS must be negative."""
    g2 = _example("opm_g2.txt")
    assert any("3.1.2" in e.clause for e in _errors(_replace(g2, "GM                =  398600.4415        "
                                                                 "[km**3/s**2]\n", "")))
    g4 = _example("opm_g4.txt")
    assert any("4.2.4.5" in e.clause for e in _errors(_replace(g4, "CZ_Z =  3.231931992380369e-04           "
                                                                   "[km**2]\n", "")))
    assert any(e.clause == "3.2.4.9" for e in _errors(_replace(g2, "MASS              =    1913.000         [kg]\n",
                                                                "")))
    assert any(e.clause == "3.2.4.7" for e in _errors(_replace(g2, "-18.418", "18.418")))
    assert any(e.clause == "3.2.4.8" for e in _errors(_replace(g2, "MAN_DURATION      =     132.60          [s]\n",
                                                                "")))


@pytest.mark.requirement("CCSDS-502.0-B-3 7.3.6")
def test_the_first_line_must_be_the_version():
    """7.3.6: anything before CCSDS_xxx_VERS is refused."""
    issues = odm.validate("ORIGINATOR = X\n" + _example("opm_g1.txt"))
    assert issues and issues[0].level == "error" and "7.3.6" in issues[0].message


@pytest.mark.requirement("CCSDS-502.0-B-3 4.2.4.6")
def test_tle_based_omm_conventions():
    """4.2.4.6: a TLE-based OMM needs EARTH, TEME, UTC and MEAN_MOTION."""
    g7 = _example("omm_g7.txt")
    assert any(e.clause == "4.2.4.6" for e in _errors(_replace(g7, "REF_FRAME      = TEME", "REF_FRAME      = EME2000")))
    assert any(e.clause == "4.2.4.6" for e in _errors(_replace(g7, "MEAN_MOTION       = 1.00273272",
                                                                "SEMI_MAJOR_AXIS   = 42164.0")))


@pytest.mark.parametrize("old, new, clause", [
    ("TIME_SYSTEM          = UTC", "TIME_SYSTEM          = TAI", "5.2.4.5"),
    ("2019-12-28T22:00:02.267 -2458.079 -683.858 2007.684  6.36786 -3.339563 -0.946654",
     "2019-12-28T22:00:02.267 -2458.079 -683.858 2007.684  6.36786 -3.339563", "5.2.4.1-5.2.4.2"),
    ("2019-12-28T21:59:02.267", "COMMENT mid-block\n2019-12-28T21:59:02.267", "7.8.9"),
    ("STOP_TIME            = 2019-12-30T01:28:02.267", "STOP_TIME            = 2019-12-29T00:00:00", "Table 5-3"),
    ("INTERPOLATION_DEGREE = 7\nMETA_STOP\nCOMMENT  This file", "META_STOP\nCOMMENT  This file", "Table 5-3"),
])
@pytest.mark.requirement("CCSDS-502.0-B-3 5.2.3.2", "CCSDS-502.0-B-3 5.2.4.1", "CCSDS-502.0-B-3 5.2.4.2", "CCSDS-502.0-B-3 5.2.4.5", "CCSDS-502.0-B-3 7.8.9", "CCSDS-502.0-B-3 7.9.2.3")
def test_each_oem_rule_is_enforced(old, new, clause):
    """A G-11 OEM broken in one way gives an error citing the rule."""
    errors = _errors(_replace(_example("oem_g11.txt"), old, new))
    assert errors and any(clause in e.clause for e in errors), [str(e) for e in errors]


@pytest.mark.requirement("CCSDS-502.0-B-3 5.2.5.4")
def test_oem_covariance_shape_is_checked():
    """5.2.5.4: six lower-triangular rows."""
    g13 = _example("oem_g13.txt")
    broken = _replace(g13, " 4.6189273e-04  6.7824216e-04\n", " 4.6189273e-04\n")
    assert any(e.clause == "5.2.5.4" for e in _errors(broken))


@pytest.mark.requirement("CCSDS-502.0-B-3 3.1.3", "CCSDS-502.0-B-3 4.1.2", "CCSDS-502.0-B-3 4.1.3")
def test_tle_to_omm_to_tle_reproduces_figure_g6():
    """The G-6 TLE becomes an OMM with its elements and converts back to
    the identical two lines; the standard's own G-7 OMM gives G-6's lines
    except the epoch year (G-7 is dated 2020)."""
    omm = odm.omm_from_tle(*_G6, object_name="GOES 9", creation=datetime(2026, 1, 1))
    assert _errors(omm) == []
    message = odm.read(omm)
    assert message.get("OBJECT_ID") == "1995-025A"
    assert message.number("MEAN_MOTION") == pytest.approx(1.00273272)
    assert message.number("MEAN_MOTION_DOT") == pytest.approx(-0.00000113)
    assert odm.tle_from_omm(message) == _G6
    line1, line2 = odm.tle_from_omm(odm.read(_example("omm_g7.txt")))
    assert line2 == _G6[1]
    assert line1[:18] + line1[20:68] == _G6[0][:18] + _G6[0][20:68]


@pytest.mark.requirement("CCSDS-502.0-B-3 3.1.2", "CCSDS-502.0-B-3 3.1.3", "CCSDS-502.0-B-3 4.1.3")
def test_opm_round_trip_and_elements_match_figure_g2():
    """write_opm -> state_from_opm returns the state; with the G-2 state
    and GM the written elements equal G-2's a, e, i, RAAN, argument of
    pericenter (TRUE_ANOMALY: see the module docstring)."""
    g2 = odm.read(_example("opm_g2.txt"))
    r = [g2.number(k) for k in ("X", "Y", "Z")]
    v = [g2.number(k) for k in ("X_DOT", "Y_DOT", "Z_DOT")]
    text = odm.write_opm(object_name="EUTELSAT W4", object_id="2021-028A", center_name="earth",
                         ref_frame="EME2000", time_system="UTC", epoch=datetime(2021, 6, 3), r_km=r, v_km_s=v,
                         gm_km3_s2=g2.number("GM"), mass_kg=1913.0, creation=datetime(2026, 1, 1))
    assert _errors(text) == []
    written = odm.read(text)
    for keyword, tolerance in (("SEMI_MAJOR_AXIS", 2e-3), ("ECCENTRICITY", 2e-8), ("INCLINATION", 2e-6),
                               ("RA_OF_ASC_NODE", 5e-6), ("ARG_OF_PERICENTER", 5e-5)):
        assert written.number(keyword) == pytest.approx(g2.number(keyword), abs=tolerance), keyword
    epoch, r_m, v_m_s, notes = odm.state_from_opm(written)
    assert epoch == datetime(2021, 6, 3) and notes == []
    np.testing.assert_allclose(r_m, np.array(r) * 1e3, rtol=1e-15)
    np.testing.assert_allclose(v_m_s, np.array(v) * 1e3, rtol=1e-15)


def test_opm_epochs_in_other_time_systems_are_converted_to_utc():
    """TAI = UTC + 37 s, TT = TAI + 32.184 s, TDB ~ TT (2021)."""
    base = odm.read(_example("opm_g1.txt").replace("REF_FRAME      = ITRF2000", "REF_FRAME      = EME2000"))
    for system, offset in (("TAI", 37.0), ("TT", 69.184), ("TDB", 69.184)):
        message = odm.read(_example("opm_g1.txt").replace("ITRF2000", "EME2000").replace("TIME_SYSTEM    = UTC",
                                                                                         f"TIME_SYSTEM    = {system}"))
        epoch = odm.state_from_opm(message)[0]
        assert (odm.state_from_opm(base)[0] - epoch).total_seconds() == pytest.approx(offset, abs=2e-3)
    with pytest.raises(odm.OdmError, match="REF_FRAME ITRF2000 is not supported"):
        odm.state_from_opm(odm.read(_example("opm_g1.txt")))


@pytest.mark.requirement("CCSDS-502.0-B-3 7.5.6", "CCSDS-502.0-B-3 7.5.7")
def test_written_values_read_back_exactly():
    """The writer's numbers are the shortest text that reads back as the
    same double, in 7.5.6/7.5.7 form."""
    for value in (81.7939, 1e-6, -1.13e-06, 0.0, 6503.514, 1 / 3, 5e-324, 1e20):
        text = odm._number(value)
        assert float(text) == pytest.approx(value, rel=1e-15) and odm._is_number(text) and odm._digits(text) <= 16


def test_orbit_ic_from_omm_is_a_tle_orbit():
    """A TLE-based OMM becomes a TLE initial condition (propagated like a TLE)."""
    orbit, epoch, _notes = odm.orbit_ic_from_odm(_example("omm_g7.txt"))
    assert orbit.type == "tle" and epoch is None
    assert orbit.tle_line2 == _G6[1]


@pytest.mark.requirement("CCSDS-502.0-B-3 5.1.1", "CCSDS-502.0-B-3 7.7.2.1", "CCSDS-502.0-B-3 7.8.1", "CCSDS-502.0-B-3 7.8.2")
@pytest.mark.requires_basilisk
def test_oem_from_a_run_conforms_and_carries_the_ephemeris(tmp_path):
    """An OEM written from a real run conforms, uses EME2000/UTC, and its
    states are the run's position/velocity (1 mm, 1 um/s resolution)."""
    from spacemissionstudio.engine import time_system
    from spacemissionstudio.engine.service import SimulationService
    from spacemissionstudio.schema import load_scenario

    scenario = load_scenario(Path(__file__).resolve().parent.parent / "spacemissionstudio" / "scenarios"
                             / "two_body_validation.json")
    scenario.sim_settings.duration_days = 0.02  # [day]
    result = SimulationService(scenario).run()
    text = odm.oem_from_result(result, scenario.epoch_utc, "earth", ["sat-1"], stride=5)["sat-1"]
    assert _errors(text) == []
    segment = odm.read(text).segments[0]
    assert segment.get("REF_FRAME") == "EME2000" and segment.get("TIME_SYSTEM") == "UTC"
    position = result.series["sat-1.position_N"]
    sampled = np.asarray(position.data)[::5]
    np.testing.assert_allclose(np.array(segment.states)[:len(sampled), :3], sampled / 1e3, atol=1e-6)  # [km]
    np.testing.assert_allclose(segment.states[-1][:3], np.asarray(position.data)[-1] / 1e3, atol=1e-6)  # last state
    utc = time_system.elapsed_to_utc(scenario.epoch_utc, position.time_s[::5])
    assert segment.epochs[1] == odm.format_time(utc[1])
    assert any("SpaceMissionStudio" in c for c in segment.comments)  # provenance comment (7.8.1, 7.8.2)


def test_cli_validate_reports_conformance(capsys, tmp_path):
    """ccsds-validate exits 0 for the examples and 1 for a broken file."""
    from spacemissionstudio import cli

    assert cli.main(["ccsds-validate", str(_DATA / "opm_g1.txt"), str(_DATA / "oem_g13.txt")]) == 0
    broken = tmp_path / "broken.opm"
    broken.write_text(_example("opm_g1.txt").replace("ORIGINATOR     = JAXA\n", ""))
    assert cli.main(["ccsds-validate", str(broken)]) == 1
    assert "ORIGINATOR is missing" in capsys.readouterr().out


def test_cli_import_sets_the_orbit_from_an_omm(tmp_path):
    """ccsds-import puts a TLE-based OMM's elements into a spacecraft."""
    from spacemissionstudio import cli
    from spacemissionstudio.schema import load_scenario

    source = Path(__file__).resolve().parent.parent / "spacemissionstudio" / "scenarios" / "two_body_validation.json"
    out = tmp_path / "imported.json"
    assert cli.main(["ccsds-import", str(_DATA / "omm_g7.txt"), str(source), "--spacecraft", "sat-1",
                     "--out", str(out)]) == 0
    assert load_scenario(out).spacecraft[0].orbit.tle_line2 == _G6[1]


@pytest.mark.requires_basilisk
def test_cli_export_writes_conforming_opms(tmp_path):
    """ccsds-export writes one conforming OPM per spacecraft; reading it
    back gives the spacecraft's initial state."""
    from spacemissionstudio import cli
    from spacemissionstudio.engine.service import _orbit_ic_to_rv
    from spacemissionstudio.schema import load_scenario

    source = Path(__file__).resolve().parent.parent / "spacemissionstudio" / "scenarios" / "two_body_validation.json"
    assert cli.main(["ccsds-export", str(source), "--out", str(tmp_path)]) == 0
    text = (tmp_path / "sat-1.opm").read_text()
    assert _errors(text) == []
    scenario = load_scenario(source)
    r, v = _orbit_ic_to_rv(odm.EARTH_GM_KM3_S2 * 1e9, scenario.spacecraft[0].orbit, scenario.epoch_utc)
    _epoch, r_m, v_m_s, _notes = odm.state_from_opm(odm.read(text))
    np.testing.assert_allclose(r_m, r, rtol=1e-14)
    np.testing.assert_allclose(v_m_s, v, rtol=1e-14)
    assert math.isclose(odm.read(text).number("GM"), odm.EARTH_GM_KM3_S2)


@pytest.mark.requirement("CCSDS-502.0-B-3 5.1.3", "CCSDS-502.0-B-3 5.2.4.7", "CCSDS-502.0-B-3 7.5.9")
def test_more_oem_rules_and_text_equivalence():
    """5.1.3 one object per OEM; 5.2.4.7 enough records for the stated
    interpolation; 7.5.9 underscores equal blanks in text values."""
    g11 = _example("oem_g11.txt")
    two_objects = g11.replace("OBJECT_NAME          = MARS GLOBAL SURVEYOR", "OBJECT_NAME          = MARS ODYSSEY")
    assert any(e.clause == "5.1.3" for e in _errors(two_objects))
    few = _replace(g11, "INTERPOLATION_DEGREE = 7\nMETA_STOP\nCOMMENT  This file",
                   "INTERPOLATION_DEGREE = 9\nMETA_STOP\nCOMMENT  This file")
    assert any(e.clause == "5.2.4.7" for e in _errors(few))  # Hermite degree 9 needs 5 nodes, the block has 4
    assert not any(e.clause == "5.2.4.7" for e in _errors(g11))  # degree 7 needs 4: enough
    fewer = _replace(g11, "INTERPOLATION       = HERMITE\nINTERPOLATION_DEGREE = 7",
                     "INTERPOLATION       = LAGRANGE\nINTERPOLATION_DEGREE = 7")
    assert any(e.clause == "5.2.4.7" for e in _errors(fewer))  # Lagrange degree 7 needs 8 points, block has 4
    underscored = _example("omm_g7.txt").replace("TIME_SYSTEM    = UTC", "TIME_SYSTEM    = _UTC_")
    assert _errors(underscored) == []


@pytest.mark.requirement("ICS-OPM-*", "ICS-OMM-*", "ICS-OEM-*")
def test_every_ics_keyword_is_read_and_validated():
    """Every keyword of the Annex A OPM/OMM/OEM ICS lists is in the
    reader's keyword tables (the ICS file compliance/ics_ccsds_502.csv is
    built from the same tables)."""
    import csv
    import re

    requirements = Path(__file__).resolve().parent.parent / "compliance" / "requirements" / "CCSDS-502.0-B-3.csv"
    with open(requirements, encoding="utf-8") as f:
        items = [r for r in csv.DictReader(f) if r["ID"].split("-")[1] in ("OPM", "OMM", "OEM")]
    known = {k for table in (odm.OPM_METADATA, odm.OPM_DATA, odm.OMM_METADATA, odm.OMM_DATA, odm.OEM_METADATA)
             for _b, ks, _s, _u in table for k in ks.split("|")}
    known |= {"CCSDS_OPM_VERS", "CCSDS_OMM_VERS", "CCSDS_OEM_VERS", *odm._HEADER, "META_START", "META_STOP",
              "COVARIANCE_START", "COVARIANCE_STOP", "EPOCH", "COV_REF_FRAME"}
    missing = []
    for item in items:
        match = re.search(r"keyword (\S+), Table", item["requirement_text"])
        keyword = match.group(1) if match else "N/A"
        if keyword not in ("N/A", "…") and not keyword.startswith("USER_DE") and keyword not in known:
            missing.append((item["ID"], keyword))
    assert len(items) == 176 and missing == []


@pytest.mark.requirement("CCSDS-502.0-B-3 7.3.5", "CCSDS-502.0-B-3 7.3.7", "CCSDS-502.0-B-3 7.4.5",
                         "CCSDS-502.0-B-3 7.4.6", "CCSDS-502.0-B-3 7.4.7", "CCSDS-502.0-B-3 5.2.4.3")
def test_line_endings_blank_lines_and_white_space_carry_no_meaning():
    """CR, LF or CR LF endings, extra blank lines and white space around
    keywords, the equals sign and line ends read as the same message."""
    g1 = _example("opm_g1.txt")
    reference = odm.read(g1)
    variants = [g1.replace("\n", "\r\n"), g1.replace("\n", "\r"), g1.replace("\n", "\n\n"),
                g1.replace("X =              6503.514000", "   X   =   6503.514000   ")]
    for text in variants:
        assert _errors(text) == []
        message = odm.read(text)
        assert message.number("X") == reference.number("X") and message.get("OBJECT_NAME") == "OSPREY 5"
    g13 = _example("oem_g13.txt")
    spaced = _replace(g13, " -2432.166 -063.042", "     -2432.166    -063.042")
    assert _errors(spaced) == []
    assert odm.read(spaced).segments[0].states[0][:2] == [-2432.166, -63.042]


@pytest.mark.parametrize("example, old, new, clause", [
    ("opm_g1.txt", "X =              6503.514000", "X = 6503.514000 Y = 1239.647", "7.5"),  # 7.4.3: one per line
    ("opm_g1.txt", "X_DOT =", "X DOT =", "7"),  # 7.4.4: no blanks in keywords
    ("opm_g1.txt", "X =  ", "x =  ", "Table 3-3"),  # 7.4.4: uppercase
    ("opm_g1.txt", "OBJECT_NAME    = OSPREY 5", "OBJECT_NAME    =", "7.5.1"),
    ("oem_g11.txt", "INTERPOLATION_DEGREE = 7", "INTERPOLATION_DEGREE = 7.0", "7.5.4"),
    ("opm_g1.txt", "6503.514000", "6503. 514000", "7.5"),  # 7.5.8: no blanks in numbers
    ("opm_g1.txt", "COMMENT          GEOCENTRIC", "COMMENTGEOCENTRIC", "7"),  # 7.8.5
    ("opm_g1.txt", "TIME_SYSTEM    = UTC", "TIME_SYSTEM    = XYZ", "3.2.3.2"),
    ("omm_g7.txt", "TIME_SYSTEM    = UTC", "TIME_SYSTEM    = UTC\nFOO = 1", "Table 4-3, 7.9.2"),  # 4.2.3.2
    ("omm_g7.txt", "MEAN_MOTION       = 1.00273272", "MEAN_MOTION       = 1.00273272\nFOO = 1",
     "Table 4-3, 7.9.2"),
    ("omm_g7.txt", "ORIGINATOR     = NOAA\n", "", "Table 4-1"),
    ("oem_g11.txt", "INTERPOLATION_DEGREE = 7\nMETA_STOP", "INTERPOLATION_DEGREE = 7\nFOO = 1\nMETA_STOP",
     "Table 5-3, 7.9.2"),
    ("oem_g11.txt", "ORIGINATOR = NASA/JPL\n", "", "Table 5-2"),
    ("omm_g7.txt", "MEAN_MOTION       = 1.00273272", "COMMENT x\nMEAN_MOTION       = 1.00273272", "7.8.8"),
    ("oem_g11.txt", "2019-12-28T21:59:02.267 -2445.234", "EPOCH = 2019-12-28T21:59:02.267 -2445.234", "7"),
    ("oem_g11.txt", "USEABLE_START_TIME   = 2019-12-28T22:08:02.5", "USEABLE_START_TIME   = 2019-12-28T20:00:00",
     "5.2.4.4"),
    ("oem_g13.txt", "EPOCH = 2019-12-29T21:00:00", "EPOCH = 2019-12-28T21:00:00", "5.2.5.7"),
    ("oem_g13.txt", "EPOCH = 2019-12-29T21:00:00\n", "", "5.2.5"),  # 5.2.5.3: each matrix has its EPOCH
])
@pytest.mark.requirement("CCSDS-502.0-B-3 7.4.3", "CCSDS-502.0-B-3 7.4.4", "CCSDS-502.0-B-3 7.5.1",
                         "CCSDS-502.0-B-3 7.5.4", "CCSDS-502.0-B-3 7.5.8", "CCSDS-502.0-B-3 7.8.5",
                         "CCSDS-502.0-B-3 3.2.3.2", "CCSDS-502.0-B-3 4.2.2.1", "CCSDS-502.0-B-3 4.2.3.2",
                         "CCSDS-502.0-B-3 4.2.4.2", "CCSDS-502.0-B-3 5.2.2.1", "CCSDS-502.0-B-3 5.2.3.2",
                         "CCSDS-502.0-B-3 7.4.1.2", "CCSDS-502.0-B-3 7.8.8", "CCSDS-502.0-B-3 7.9.2.2",
                         "CCSDS-502.0-B-3 7.9.2.3", "CCSDS-502.0-B-3 5.2.4.4", "CCSDS-502.0-B-3 5.2.5.3",
                         "CCSDS-502.0-B-3 5.2.5.7")
def test_each_kvn_syntax_and_segment_rule_is_enforced(example, old, new, clause):
    """An Annex G example broken in one way gives an issue citing the rule
    (TIME_SYSTEM outside the 3.2.3.2 set is a warning: it needs an ICD)."""
    issues = [i for i in odm.validate(_replace(_example(example), old, new)) if i.level in ("error", "warning")]
    assert issues and any(i.clause.startswith(clause) for i in issues), [str(i) for i in issues]
