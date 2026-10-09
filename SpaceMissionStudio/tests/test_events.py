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
"""The event model (UX/UI guidelines, "events as a timeline with a
sortable, exportable table"): passes, eclipses, burns, thruster firings
and mode changes read from a run's recorded series."""

import csv
import math

import numpy as np
import pytest

from spacemissionstudio.engine import events
from spacemissionstudio.engine.results import ResultSet, TimeSeries

_T = np.arange(10, dtype=float) * 60.0  # [s] ten samples, one a minute


def _result(**series):
    result = ResultSet("test")
    for name, (columns, data) in series.items():
        result.add(TimeSeries(name.replace("__", "."), _T, columns, np.asarray(data, dtype=float)))
    return result


def test_a_pass_runs_from_its_first_to_its_last_sample_in_view_with_its_peak_elevation():
    """Same convention as the access timeline: first to last sample in view."""
    elevation = np.radians([0, 5, 20, 45, 30, 2, 0, 0, 0, 0])  # [rad]
    result = _result(**{"gs__access_to_sat__has_access": (("has_access",), [0, 1, 1, 1, 1, 1, 0, 0, 1, 1]),
                        "gs__access_to_sat__elevation": (("elevation",), elevation)})
    passes = [e for e in events.extract_events(result) if e.kind == events.ACCESS]
    assert [(e.start_s, e.end_s) for e in passes] == [(60.0, 300.0), (480.0, 540.0)]
    assert passes[0].spacecraft == "sat" and passes[0].other == "gs" and passes[0].row == "gs - sat"
    assert passes[0].detail == "max elevation 45.0 deg"
    assert math.isclose(passes[0].duration_s, 240.0)


def test_eclipses_are_umbra_or_penumbra_by_their_lowest_sunlight():
    factor = [1, 0.6, 0, 0, 0.5, 1, 1, 0.4, 1, 1]  # [-] illumination factor
    result = _result(**{"sat__eclipse__illumination_factor": (("illumination_factor",), factor)})
    eclipses = events.extract_events(result)
    assert [(e.label, e.start_s, e.end_s) for e in eclipses] == [
        ("eclipse (umbra)", 60.0, 240.0), ("eclipse (penumbra)", 420.0, 420.0)]
    assert eclipses[1].detail == "lowest sunlight 40%"


def test_a_station_keeping_burn_reports_the_delta_v_it_added():
    burn = [0, 0, 1, 1, 0, 0, 0, 0, 0, 0]
    delta_v = [0, 0, 0, 0.5, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0]  # [m/s] cumulative
    result = _result(**{"sat__station_keeping__burn_on": (("burn_on",), burn),
                        "sat__station_keeping__delta_v": (("cumulative_delta_v",), delta_v)})
    (event,) = events.extract_events(result)
    assert (event.kind, event.label, event.start_s, event.end_s) == (events.BURN, "station-keeping burn", 120.0,
                                                                     180.0)
    assert event.detail == "delta-V 1.000 m/s"


def test_geo_burns_are_split_east_west_and_north_south():
    burn = np.zeros((10, 2))
    burn[1, 0] = burn[5:7, 1] = 1
    result = _result(**{"geo__geo_station_keeping__burn_on": (("east_west", "north_south"), burn)})
    assert [e.label for e in events.extract_events(result)] == ["east-west burn", "north-south burn"]


def test_phasing_states_give_two_burns_and_the_drift_between_them():
    state = [0, 1, 1, 2, 2, 2, 3, 0, 0, 0]  # idle, burn out, drift, burn restore
    result = _result(**{"f1__phasing_keeping__state": (("state",), state)})
    found = [(e.kind, e.label, e.start_s, e.end_s) for e in events.extract_events(result)]
    assert found == [(events.BURN, "phasing burn (start drift)", 60.0, 120.0),
                     (events.MODE, "phasing drift", 180.0, 300.0),
                     (events.BURN, "phasing burn (stop drift)", 360.0, 360.0)]


def test_comms_pointing_alternates_sun_and_ground_station_pointing():
    result = _result(**{"sat__comms_pointing__active_mode": (("active_mode",), [0, 0, 1, 1, 1, 0, 0, 0, 0, 0])})
    found = [(e.label, e.start_s, e.end_s) for e in events.extract_events(result)]
    assert found == [("Sun pointing", 0.0, 60.0), ("ground-station pointing", 120.0, 240.0),
                     ("Sun pointing", 300.0, 540.0)]


def test_thruster_firings_name_the_thrusters_that_fired():
    on_time = np.zeros((10, 2))  # [s] on-time requests
    on_time[3, 1] = 0.2
    on_time[4, 0] = 0.1
    result = _result(**{"sat__thruster_on_time": (("thruster_0", "thruster_1"), on_time)})
    (event,) = events.extract_events(result)
    assert (event.kind, event.start_s, event.end_s, event.detail) == (events.THRUSTER, 180.0, 240.0,
                                                                      "thruster_0, thruster_1")


def test_events_are_sorted_and_an_empty_or_missing_result_gives_none():
    result = _result(**{"sat__eclipse__illumination_factor": (("f",), [1, 1, 1, 1, 1, 0, 0, 1, 1, 1]),
                        "gs__access_to_sat__has_access": (("has_access",), [0, 1, 0, 0, 0, 0, 0, 0, 0, 0])})
    assert [e.kind for e in events.extract_events(result)] == [events.ACCESS, events.ECLIPSE]
    assert events.extract_events(None) == []
    assert events.extract_events(ResultSet("empty")) == []


def test_missing_kinds_say_why_a_kind_is_absent():
    """A kind appears only when the run recorded the series it comes from."""
    result = _result(**{"gs__access_to_sat__has_access": (("has_access",), np.zeros(10))})
    missing = events.missing_kinds(result)
    assert events.ACCESS not in missing
    assert "sun" in missing[events.ECLIPSE] and events.BURN in missing


def test_csv_export_has_seconds_and_utc_columns(tmp_path):
    result = _result(**{"gs__access_to_sat__has_access": (("has_access",), [0, 1, 1, 0, 0, 0, 0, 0, 0, 0])})
    path = events.write_csv(events.extract_events(result), tmp_path / "events.csv", "2026-01-01T00:00:00")
    rows = list(csv.DictReader(open(path, encoding="utf-8")))
    assert rows[0]["kind"] == "pass" and rows[0]["ground_station"] == "gs"
    assert (rows[0]["start_s"], rows[0]["end_s"], rows[0]["duration_s"]) == ("60.000", "120.000", "60.000")
    assert rows[0]["start_utc"].startswith("2026-01-01")
    plain = events.write_csv(events.extract_events(result), tmp_path / "plain.csv")
    assert "start_utc" not in open(plain, encoding="utf-8").readline()


@pytest.mark.requires_basilisk
def test_a_real_leo_run_writes_eclipses_that_match_the_orbit(tmp_path):
    """Template 06 (550 km Sun-synchronous orbit) for 0.15 day through the
    CLI: ``events.csv`` lists its eclipses, one per orbital period, each no
    longer than the cylindrical-shadow bound with the Sun in the orbit
    plane (plus a few seconds of penumbra at each end)."""
    import json
    from pathlib import Path

    from spacemissionstudio import cli
    from spacemissionstudio.schema import load_scenario

    templates = Path(__file__).resolve().parent.parent / "spacemissionstudio" / "scenarios" / "templates"
    scenario = load_scenario(templates / "06_attitude_pointing_basic.json")
    scenario.sim_settings.duration_days = 0.15  # [day] a little over two orbits
    path = tmp_path / "t06.json"
    path.write_text(json.dumps(scenario.to_dict()), encoding="utf-8")
    assert cli.main(["run", str(path), "--out-dir", str(tmp_path / "out")]) == 0
    rows = [r for r in csv.DictReader(open(tmp_path / "out" / "events.csv", encoding="utf-8"))
            if r["kind"] == "eclipse"]
    a_m = scenario.spacecraft[0].orbit.semi_major_axis_km * 1e3  # [m]
    period_s = 2 * math.pi * math.sqrt(a_m ** 3 / 3.986004418e14)  # [s] mu_Earth [m^3/s^2]
    longest_s = period_s / math.pi * math.asin(6378.1363e3 / a_m)  # [s] Sun in the orbit plane
    starts = [float(r["start_s"]) for r in rows]
    assert len(rows) >= 2
    assert starts[1] - starts[0] == pytest.approx(period_s, rel=0.005)
    for row in rows[:2]:  # the third is cut off by the end of the run
        assert 0.85 * longest_s < float(row["duration_s"]) < longest_s + 30.0  # [s]
