"""Regression test for the GenericStorage/GenericSensor dangling-pointer
bug in engine.vizard.enable_vizard() -- see that function's docstring,
second "Real bug found" note, for the full story: VizSpacecraftData's
genericStorageList/genericSensorList (vizStructures.h) are raw pointer
vectors (std::vector<GenericStorage *>/std::vector<GenericSensor *>),
not value vectors, so the panel objects enable_vizard() builds were
being garbage-collected the moment the function returned while
VizInterface kept dangling pointers to them -- surfacing, several ticks
later, as an unrelated-looking ``basic_string::_M_create``/
``std::length_error`` crash from VizInterface's own background write
thread. Confirmed with a real ``gdb`` ``catch throw``/``bt`` on a
minimal, fully-isolated repro (station-keeping only, headless CLI,
``--vizard-save-file``, no live Vizard connection needed).

Requires a Basilisk build (marked ``requires_basilisk``; see
tests/conftest.py for the auto-skip behavior in this development
sandbox, which does not have one).
"""

from pathlib import Path

import numpy as np
import pytest

from spacemissionstudio.schema import load_scenario

pytestmark = pytest.mark.requires_basilisk

SCENARIO_PATH = (
    Path(__file__).resolve().parent.parent
    / "spacemissionstudio"
    / "scenarios"
    / "diagnostic_05f_station_keeping_fixed_step_integrator.json"
)


def test_station_keeping_with_vizard_save_file_does_not_crash(tmp_path):
    """The real bug: a station-keeping spacecraft (the only controller that
    creates a GenericStorage panel -- see engine.vizard's "Live-data
    panels" docstring section) run with Vizard output enabled used to
    crash within the first couple of dynamics ticks with a
    ``SimulationServiceError`` wrapping ``std::length_error``/
    ``std::bad_alloc`` from VizInterface's background write thread. This
    scenario is diagnostic_05f, a real, previously-reproducing crash --
    run() completing at all (an unhandled RuntimeError would otherwise
    propagate straight out of run()) is the actual regression check.
    """
    from spacemissionstudio.engine.service import SimulationService
    from spacemissionstudio.engine.vizard import VizardRequest

    scenario = load_scenario(SCENARIO_PATH)
    save_file = tmp_path / "diag.viz.bin"
    service = SimulationService(scenario, vizard_request=VizardRequest(save_file=str(save_file)))

    result = service.run()

    assert result is not None
    assert save_file.exists()


def test_generic_storage_and_sensor_lists_are_retained_after_build(tmp_path):
    """The actual fix: enable_vizard()'s GenericStorage/GenericSensor
    panel objects (and their embedded ReadFunctor readers) must survive
    past enable_vizard() returning, same as access_indicator_bridges --
    engine.service.SimulationService must hold the last Python reference
    to them for the simulation's lifetime, not just enable_vizard()'s own
    stack frame.
    """
    from spacemissionstudio.engine.service import SimulationService
    from spacemissionstudio.engine.vizard import VizardRequest

    scenario = load_scenario(SCENARIO_PATH)
    save_file = tmp_path / "diag.viz.bin"
    service = SimulationService(scenario, vizard_request=VizardRequest(save_file=str(save_file)))
    service.build()

    assert service._viz is not None
    assert service._viz_generic_storage_list is not None
    # follower-1 has station_keeping configured -- exactly one spacecraft's
    # entry in the per-spacecraft-parallel list should carry a real panel.
    assert any(entry for entry in service._viz_generic_storage_list)


def test_enable_vizard_with_a_ground_station_does_not_crash():
    """Real user report, reproduced exactly against a real Basilisk build
    (not just reasoned through) before being fixed here: running ANY
    scenario with a ground station AND Vizard output enabled crashed
    every time with ``SystemError: <built-in function
    LocationPbMsg_gHat_P_set> returned a result with an exception set``
    (itself wrapping ``TypeError: only 0-dimensional arrays can be
    converted to Python scalars``).

    Root cause, confirmed directly against this checkout's real Basilisk
    install, not assumed: ``groundLocation.GroundLocation.r_LP_P_Init``
    (an ``Eigen::Vector3d``) is exposed to Python as a NESTED
    ``[[x], [y], [z]]`` list, never a flat ``[x, y, z]`` one --
    ``enable_vizard()`` used to pass it to ``vizSupport.addLocation()``
    via a plain ``list(...)`` call, which leaves it nested.
    ``addLocation()`` tolerates that nested ``r_GP_P`` shape fine on its
    own, but since this call never passes its own ``gHat_P``,
    ``addLocation()`` computes one internally as
    ``r_GP_P / np.linalg.norm(r_GP_P)`` -- which, fed a nested (3, 1)
    -shaped input, produces a (3, 1)-shaped result instead of a flat
    (3,) one, and ITS setter then fails converting each 1-element
    sub-array to a scalar. The fix (matching every real Basilisk example
    that passes a ``GroundLocation``'s own ``r_LP_P_Init`` to
    ``addLocation()``, e.g. ``examples/scenarioAttLocPoint.py``/
    ``examples/scenarioGroundDownlink.py``) is
    ``simHelpers.EigenVector3d2list()`` instead of bare ``list()`` --
    this test is the regression guard for that fix, exercising the real
    ``engine.vizard.enable_vizard()`` ground-station loop directly
    against a real ``groundLocation.GroundLocation``/
    ``vizInterface.VizInterface``, deliberately NOT going through
    ``SimulationService.build()`` (which would also need real cached
    SPICE kernels -- a real, separate, already-documented gap in this
    development sandbox -- for something this bug has nothing to do
    with).
    """
    from Basilisk.simulation import groundLocation, spacecraft
    from Basilisk.utilities import SimulationBaseClass, macros

    from spacemissionstudio.engine.vizard import VizardRequest, enable_vizard

    scSim = SimulationBaseClass.SimBaseClass()
    task_name = "dynTask"
    dyn_process = scSim.CreateNewProcess("dynProc")
    dyn_process.addTask(scSim.CreateNewTask(task_name, macros.sec2nano(1.0)))

    sc_object = spacecraft.Spacecraft()
    sc_object.ModelTag = "sat-1"
    scSim.AddModelToTask(task_name, sc_object)

    gl = groundLocation.GroundLocation()
    gl.ModelTag = "gs-1"
    gl.planetRadius = 6378136.6  # [m] Earth mean equatorial radius
    gl.specifyLocation(np.radians(40.015), np.radians(-105.2705), 1655.0)
    scSim.AddModelToTask(task_name, gl)

    import tempfile

    save_file = Path(tempfile.mkdtemp()) / "ground_station.viz.bin"
    viz, _bridges, _storage, _sensors = enable_vizard(
        scSim, task_name, [sc_object], VizardRequest(save_file=str(save_file)), ground_stations={"gs-1": gl},
    )

    assert viz is not None
    assert len(viz.locations) == 1
    assert viz.locations[0].stationName == "gs-1"


def test_enable_vizard_with_comms_pointing_builds_the_three_new_panels():
    """Real user feedback: the GUI's mission dashboard (``gui.mission_
    dashboard_widget``, template 19's live telemetry) "shall also be in
    the vizard live visualization, not only in the GUI itself". This
    exercises ``engine.vizard.enable_vizard()``'s new
    ``comms_pointing_by_spacecraft`` wiring directly against a real
    ``engine.fsw.build_comms_pointing()`` arbitrator -- deliberately NOT
    through ``SimulationService.build()`` (SPICE-blocked in this sandbox,
    same already-documented gap as the ground-station test above; this
    bug has nothing to do with it), confirming both that nothing crashes
    AND that the three new panels (a "Pointing Error" GenericStorage bar,
    "Mode"/"Link status" GenericSensor badges) actually land in the
    per-spacecraft lists ``enable_vizard()`` hands to
    ``vizSupport.enableUnityVisualization()``.
    """
    from Basilisk.architecture import messaging
    from Basilisk.simulation import spacecraft
    from Basilisk.utilities import SimulationBaseClass, macros

    from spacemissionstudio.engine import fsw
    from spacemissionstudio.engine.vizard import VizardRequest, enable_vizard
    from spacemissionstudio.schema.scenario import CommsPointingConfig

    scSim = SimulationBaseClass.SimBaseClass()
    task_name = "dynTask"
    dyn_process = scSim.CreateNewProcess("dynProc")
    dyn_process.addTask(scSim.CreateNewTask(task_name, macros.sec2nano(1.0)))

    sc_object = spacecraft.Spacecraft()
    sc_object.ModelTag = "sat-1"
    scSim.AddModelToTask(task_name, sc_object)

    def _fixed_att_guid_msg(sigma_br, moduleID):
        payload = messaging.AttGuidMsgPayload()
        payload.sigma_BR = list(sigma_br)
        payload.omega_BR_B = [0.0, 0.0, 0.0]
        payload.omega_RN_B = [0.0, 0.0, 0.0]
        payload.domega_RN_B = [0.0, 0.0, 0.0]
        return messaging.AttGuidMsg().write(payload, 0, moduleID)

    sun_guid_msg = _fixed_att_guid_msg([0.05, 0.0, 0.0], moduleID=1)
    comms_guid_msg = _fixed_att_guid_msg([0.0, -0.08, 0.0], moduleID=2)
    access_msg = messaging.AccessMsg()
    access_payload = messaging.AccessMsgPayload()
    access_payload.hasAccess = 0
    access_msg.write(access_payload, 0, 3)

    comms_config = CommsPointingConfig(target_ground_station="gs-1", comms_power_w=0.0)
    arbitrator = fsw.build_comms_pointing(
        scSim, task_name, "sat-1", comms_config, sun_guid_msg, comms_guid_msg, access_msg,
    )

    import tempfile

    save_file = Path(tempfile.mkdtemp()) / "comms_pointing.viz.bin"
    viz, _bridges, storage_list, sensor_list = enable_vizard(
        scSim, task_name, [sc_object], VizardRequest(save_file=str(save_file)),
        comms_pointing_by_spacecraft={"sat-1": arbitrator},
    )

    assert viz is not None
    assert len(storage_list) == 1 and len(storage_list[0]) == 1  # exactly one GenericStorage panel
    assert storage_list[0][0].label == "Pointing Error"
    sensor_labels = {sensor.label for sensor in sensor_list[0]}
    assert sensor_labels == {"Mode", "Link status"}
