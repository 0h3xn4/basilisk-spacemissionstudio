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

"""Tests for engine.fsw._CommsPointingArbitrator/build_comms_pointing --
schema.scenario.CommsPointingConfig's mode-switch mechanism.

Like tests/test_location_pointing_target_body.py and
tests/test_mtb_desaturation.py, this calls engine.fsw's builder functions
directly against a bare SimulationBaseClass rather than going through
SimulationService (SPICE-blocked in this sandbox). Unlike those tests,
the two guidance chains the arbitrator switches between are NOT built
from real sunSafePoint/locationPointing modules here -- they are two
plain, FIXED-content AttGuidMsg sources ("sun_guid_msg"/"comms_guid_msg"
below), each standing in for whichever chain is "active" at a given
moment. This isolates what this feature actually ADDS (the arbitrator's
own mode-switching/power-gating logic) from the pre-existing, separately
-tested sunSafePoint/locationPointing modules themselves (already
confirmed by test_location_pointing_target_body.py and this project's own
'07'/'19' templates) -- matching this project's own "simplify what isn't
the thing under test, document the simplification" convention (the same
reasoning test_location_pointing_target_body.py gives for its own static
SpicePlanetStateMsgPayload stand-in). The real, physical pieces this test
DOES exercise end to end: a real spacecraft hub, a real mrpFeedback
-> idealized-actuation control loop driven by the arbitrator's own
output, and a real simplePowerSink gated live by the arbitrator.

The "hasAccess" input is similarly a plain, hand-driven AccessMsg
(re-``.write()``-ed between separate ``ExecuteSimulation()`` segments --
the same resume-from-NextTaskTime mechanism
``engine.service.SimulationService.run_live()`` already uses for its own
progress-chunked runs) rather than a real groundLocation.GroundLocation's
geometry -- that module's own access determination is Basilisk's
responsibility, already exercised throughout this project's other
ground-station-access-analysis code paths, not something this test
needs to re-derive from orbital geometry.

Requires a Basilisk build (marked ``requires_basilisk``; see
tests/conftest.py).
"""

import numpy as np
import pytest

from spacemissionstudio.schema.scenario import CommsPointingConfig

pytestmark = pytest.mark.requires_basilisk

_TASK_RATE_S = 0.1  # see build_06_attitude_pointing_basic()'s own comment: confirmed-stable for idealized actuation
_INERTIA = [10.0, 0.0, 0.0, 0.0, 10.0, 0.0, 0.0, 0.0, 10.0]
_COMMS_POWER_W = 12.0


def _write_access(access_msg, has_access: bool, moduleID: int, write_time_ns: int) -> None:
    from Basilisk.architecture import messaging

    payload = messaging.AccessMsgPayload()
    payload.hasAccess = 1 if has_access else 0
    access_msg.write(payload, write_time_ns, moduleID)


def _build_fixed_att_guid_msg(sigma_br, moduleID: int):
    from Basilisk.architecture import messaging

    payload = messaging.AttGuidMsgPayload()
    payload.sigma_BR = list(sigma_br)
    payload.omega_BR_B = [0.0, 0.0, 0.0]
    payload.omega_RN_B = [0.0, 0.0, 0.0]
    payload.domega_RN_B = [0.0, 0.0, 0.0]
    return messaging.AttGuidMsg().write(payload, 0, moduleID)


def _run_comms_pointing(segments):
    """``segments``: a list of ``(has_access, duration_s)`` pairs, run in
    order on the SAME simulation (``ConfigureStopTime``/
    ``ExecuteSimulation()`` called once per segment, resuming from
    wherever the sim left off -- see this module's own docstring).
    Returns ``(arbitrator, sigma_BN_history, sc_rec_times_s, power_sink)``.
    """
    from Basilisk.architecture import messaging
    from Basilisk.simulation import extForceTorque, simplePowerSink, spacecraft
    from Basilisk.utilities import SimulationBaseClass, macros, simHelpers

    from spacemissionstudio.engine import fsw

    scSim = SimulationBaseClass.SimBaseClass()
    task_name = "task"
    process = scSim.CreateNewProcess("proc")
    process.addTask(scSim.CreateNewTask(task_name, macros.sec2nano(_TASK_RATE_S)))

    sc_object = spacecraft.Spacecraft()
    sc_object.ModelTag = "sat"
    sc_object.hub.mHub = 100.0
    sc_object.hub.IHubPntBc_B = simHelpers.np2EigenMatrix3d(_INERTIA)
    sc_object.hub.sigma_BNInit = [[0.3], [0.0], [0.0]]  # a clear ~67 deg initial offset to integrate from
    sc_object.hub.omega_BN_BInit = [[0.0], [0.0], [0.0]]
    sc_object.hub.r_CN_NInit = [[7000.0e3], [0.0], [0.0]]
    sc_object.hub.v_CN_NInit = [[0.0], [7.5e3], [0.0]]
    scSim.AddModelToTask(task_name, sc_object, 10)

    # Two FIXED, easily-distinguishable guidance sources -- see module
    # docstring for why these stand in for real sunSafePoint/
    # locationPointing chains in this isolated test.
    sun_guid_msg = _build_fixed_att_guid_msg([0.05, 0.0, 0.0], moduleID=1)
    comms_guid_msg = _build_fixed_att_guid_msg([0.0, -0.08, 0.0], moduleID=2)
    access_msg = messaging.AccessMsg()
    _write_access(access_msg, segments[0][0], moduleID=3, write_time_ns=0)

    veh_config_msg = fsw.build_vehicle_config_msg(_INERTIA)
    power_sink = simplePowerSink.SimplePowerSink()
    power_sink.ModelTag = "commsPowerSink"
    power_sink.nodePowerOut = 0.0
    scSim.AddModelToTask(task_name, power_sink, 50)
    power_rec = power_sink.nodePowerOutMsg.recorder()
    scSim.AddModelToTask(task_name, power_rec)

    comms_config = CommsPointingConfig(target_ground_station="gs-1", comms_power_w=_COMMS_POWER_W)
    arbitrator = fsw.build_comms_pointing(
        scSim, task_name, "sat", comms_config, sun_guid_msg, comms_guid_msg, access_msg,
        comms_power_sink=power_sink,
    )
    mrp = fsw.build_mrp_feedback(scSim, task_name, "sat", arbitrator.attGuidOutMsg, veh_config_msg, {})
    fsw.build_idealized_actuation(scSim, task_name, "sat", sc_object, mrp)

    sc_rec = sc_object.scStateOutMsg.recorder()
    scSim.AddModelToTask(task_name, sc_rec)

    scSim.InitializeSimulation()
    elapsed_s = 0.0
    for has_access, duration_s in segments:
        _write_access(access_msg, has_access, moduleID=3, write_time_ns=macros.sec2nano(elapsed_s))
        elapsed_s += duration_s
        scSim.ConfigureStopTime(macros.sec2nano(elapsed_s))
        scSim.ExecuteSimulation()

    return arbitrator, np.array(sc_rec.sigma_BN), np.array(sc_rec.times()) * macros.NANO2SEC, power_rec


def test_arbitrator_output_mirrors_the_active_chain_exactly():
    arbitrator, sigma_BN, t_s, _ = _run_comms_pointing([(False, 20.0), (True, 20.0), (False, 20.0)])

    assert not np.any(np.isnan(sigma_BN)), "attitude went non-physical (NaN)"

    mode_log = np.array(arbitrator.modeLog)
    t_log = np.array(arbitrator.tLog)
    # First segment: Sun-pointing (mode 0). Second: comms (mode 1). Third: back to Sun-pointing (mode 0).
    assert np.all(mode_log[t_log < 19.0] == 0)
    assert np.all(mode_log[(t_log > 21.0) & (t_log < 39.0)] == 1)
    assert np.all(mode_log[t_log > 41.0] == 0)


def test_pointing_error_deg_log_matches_the_active_chains_own_sigma_br():
    """theta = 4*atan(|sigma_BR|) of whichever chain is active -- not a
    separately-recomputed geometry, the exact relation
    _CommsPointingArbitrator.UpdateState's own docstring states.
    """
    arbitrator, _, _, _ = _run_comms_pointing([(False, 10.0), (True, 10.0)])

    expected_sun_deg = np.degrees(4.0 * np.arctan(np.linalg.norm([0.05, 0.0, 0.0])))
    expected_comms_deg = np.degrees(4.0 * np.arctan(np.linalg.norm([0.0, -0.08, 0.0])))

    mode_log = np.array(arbitrator.modeLog)
    error_log = np.array(arbitrator.pointingErrorDegLog)
    assert np.allclose(error_log[mode_log == 0], expected_sun_deg)
    assert np.allclose(error_log[mode_log == 1], expected_comms_deg)


def test_comms_power_sink_only_draws_power_while_comms_mode_is_active():
    _, _, _, power_rec = _run_comms_pointing([(False, 10.0), (True, 10.0), (False, 10.0)])

    net_power = np.array(power_rec.nodePowerOut)
    times_s = np.array(power_rec.times()) * 1.0e-9

    assert np.allclose(net_power[times_s < 9.0], 0.0)
    assert np.allclose(net_power[(times_s > 11.0) & (times_s < 19.0)], -_COMMS_POWER_W)
    assert np.allclose(net_power[times_s > 21.0], 0.0)


def test_switching_guidance_reference_does_not_reset_integrated_attitude():
    """The core claim this feature makes: only the attitude REFERENCE
    switches at a mode change -- the spacecraft's own integrated sigma_BN
    is never reset/jumped. Structurally guaranteed by this module's own
    design (the arbitrator never writes spacecraft state, only an
    AttGuidMsg the controller reads), but checked here directly: the
    per-tick step size right at the mode-switch boundary must stay the
    same order of magnitude as steady-state step sizes elsewhere in the
    run, not an order-of-magnitude discontinuity consistent with a reset.
    """
    _, sigma_BN, t_s, _ = _run_comms_pointing([(False, 20.0), (True, 20.0)])

    steps = np.linalg.norm(np.diff(sigma_BN, axis=0), axis=1)
    switch_index = int(np.searchsorted(t_s, 20.0))
    typical_step = np.median(steps)
    step_at_switch = steps[switch_index]

    assert step_at_switch < max(50.0 * typical_step, 1.0e-3), (
        f"attitude step at the mode switch ({step_at_switch:.3e}) looks like a discontinuity, "
        f"not a continuous slew (typical step elsewhere: {typical_step:.3e})"
    )
