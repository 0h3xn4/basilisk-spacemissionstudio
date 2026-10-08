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
"""Mid-step planet orientation for the gravity model
(``engine/planet_rotation.py``; ECSS-Q-ST-80C 7.1.7a; Phase 3 finding)."""

import math
from pathlib import Path

import numpy as np
import pytest

pytestmark = pytest.mark.requirement("Q-ST-80C 7.1.7a")

_SCENARIO = Path(__file__).resolve().parent.parent / "spacemissionstudio" / "scenarios" / "two_body_validation.json"
_R0_KM = [6778.137, 0.0, 0.0]  # [km]
_V0_KM_S = [0.0, 4.6, 6.0]  # [km/s]


def _kepler(r0, v0, mu, times):
    """Universal-variable two-body solution at ``times`` [s] (km, km^3/s^2)."""
    r0, v0 = np.asarray(r0, float), np.asarray(v0, float)
    rn = np.linalg.norm(r0)
    vr = r0 @ v0 / rn
    alpha = 2.0 / rn - v0 @ v0 / mu
    out = []
    for t in times:
        chi = math.sqrt(mu) * alpha * t
        for _ in range(50):
            z = alpha * chi * chi
            c = (1.0 - math.cos(math.sqrt(z))) / z if z > 1e-12 else 0.5
            s = (math.sqrt(z) - math.sin(math.sqrt(z))) / z ** 1.5 if z > 1e-12 else 1.0 / 6.0
            f = rn * vr / math.sqrt(mu) * chi ** 2 * c + (1.0 - alpha * rn) * chi ** 3 * s + rn * chi - math.sqrt(mu) * t
            df = rn * vr / math.sqrt(mu) * chi * (1.0 - z * s) + (1.0 - alpha * rn) * chi ** 2 * c + rn
            chi -= f / df
        z = alpha * chi * chi
        c = (1.0 - math.cos(math.sqrt(z))) / z if z > 1e-12 else 0.5
        s = (math.sqrt(z) - math.sin(math.sqrt(z))) / z ** 1.5 if z > 1e-12 else 1.0 / 6.0
        out.append((1.0 - chi ** 2 / rn * c) * r0 + (t - chi ** 3 / math.sqrt(mu) * s) * v0)
    return np.array(out)


def test_nearest_rotation_removes_the_linear_extrapolation_stretch():
    """R + R_dot dt is not a rotation; the corrected matrix is orthonormal
    to 1e-15 and equals the exact rotation to third order in omega dt."""
    from spacemissionstudio.engine.planet_rotation import _nearest_rotation

    omega, dt = 7.2921159e-5, 10.0  # [rad/s], [s]

    def rz(angle):
        c, s = math.cos(angle), math.sin(angle)
        return np.array([[c, s, 0.0], [-s, c, 0.0], [0.0, 0.0, 1.0]])

    rate = (rz(1e-3) - rz(-1e-3)) / (2e-3) * omega  # d/dt of rz(omega t) at t = 0
    linear = rz(0.0) + rate * dt
    assert abs(np.linalg.norm(linear @ [1.0, 0.0, 0.0]) - 1.0) > 2e-7  # the stretch Basilisk applies
    corrected = _nearest_rotation(linear)
    np.testing.assert_allclose(corrected @ corrected.T, np.eye(3), atol=1e-15)
    np.testing.assert_allclose(corrected, rz(omega * dt), atol=5e-10)  # (omega dt)^3 / 6 = 6e-11


def _run(rate_s, degree=0, days=0.5):
    from spacemissionstudio.engine.service import SimulationService
    from spacemissionstudio.schema import load_scenario

    scenario = load_scenario(_SCENARIO)
    scenario.epoch_utc = "2024-06-01T00:00:00"
    orbit = scenario.spacecraft[0].orbit
    orbit.type, orbit.position_km, orbit.velocity_km_s = "cartesian", _R0_KM, _V0_KM_S
    scenario.sim_settings.duration_days = days  # [day]
    scenario.sim_settings.dynamics_task_rate_s = rate_s  # [s]
    scenario.gravity.central_body_degree = degree
    service = SimulationService(scenario)
    result = service.run()
    series = result.series["sat-1.position_N"]
    return service, np.asarray(series.time_s), np.asarray(series.data) / 1e3


@pytest.mark.requires_basilisk
def test_two_body_at_the_default_step_matches_kepler():
    """A 400 km orbit at the 10 s default step stays within 1 cm of Kepler's
    solution for half a day (148 m after a day without the correction)."""
    service, t, r_km = _run(10.0)
    mu_km3_s2 = service.grav_factory.gravBodies["earth"].mu / 1e9  # [km^3/s^2]
    error_m = np.linalg.norm(r_km[1:] - _kepler(_R0_KM, _V0_KM_S, mu_km3_s2, t[1:]), axis=1) * 1e3
    assert error_m.max() < 0.01


@pytest.mark.requires_basilisk
def test_spherical_harmonics_converge_with_the_step():
    """Degree 10 at 10 s agrees with 2 s to 0.5 m over half a day (66 m
    between 10 s and 0.25 s without the correction)."""
    _service, t_coarse, r_coarse = _run(10.0, degree=10)
    _service, t_fine, r_fine = _run(2.0, degree=10)
    index = np.searchsorted(t_fine, t_coarse)
    assert np.linalg.norm(r_coarse - r_fine[index], axis=1).max() * 1e3 < 0.5


@pytest.mark.requires_basilisk
def test_the_spice_message_other_models_read_is_left_unchanged():
    """Ground stations and guidance keep SPICE's own orientation: the SPICE
    output equals pxform(J2000, IAU_EARTH) at the end time, while the
    gravity body's copy has zero rate."""
    from Basilisk.topLevelModules import pyswice

    from spacemissionstudio.engine.time_system import utc_iso_to_spice_string

    from Basilisk.utilities.supportDataTools.dataFetcher import DataFile, get_path

    service, t, _r = _run(10.0, days=0.01)
    for kernel in (DataFile.EphemerisData.naif0012, DataFile.EphemerisData.pck00010):
        pyswice.furnsh_c(str(get_path(kernel)))  # a finished run unloads its kernels
    et = pyswice.new_doubleArray(1)
    pyswice.str2et_c(utc_iso_to_spice_string("2024-06-01T00:00:00"), et)
    out = pyswice.new_doubleArray(9)
    pyswice.pxform_c("J2000", service.earth_frame, pyswice.doubleArray_getitem(et, 0) + t[-1], out)
    expected = np.array([pyswice.doubleArray_getitem(out, i) for i in range(9)]).reshape(3, 3)
    np.testing.assert_allclose(service.spice_object.planetStateOutMsgs[0].read().J20002Pfix, expected, atol=1e-12)
    copy = service._planet_orientation_modules[0].planetOutMsg.read()
    assert not np.array(copy.J20002Pfix_dot).any()
