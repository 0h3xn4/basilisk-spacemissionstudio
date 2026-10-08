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

r"""Batch/headless CLI, separate from the interactive GUI -- and built on
exactly the same ``schema``/``engine`` layer the GUI uses, nothing
duplicated. This is also the architectural proof that the "decoupled from
the sim engine via a clean API/service layer" goal actually held: every
command below is a thin wrapper over ``schema.load_scenario()``,
``engine.service.SimulationService``, ``engine.kernels``, and
``engine.spaceweather`` -- the exact same calls
``gui.main_window.MainWindow`` makes.

``run`` dispatches on ``scenario.mission_sequence``: a non-empty one is
executed via ``engine.mission_engine.MissionEngine`` (propagate/maneuver/
.../script_block commands drive the simulation, and a Command Summary CSV
is written alongside the usual per-series ones if any ``report`` commands
ran) instead of a single ``SimulationService.run()`` call -- the only
place this CLI (and, once it exists, the GUI) needs to know that
distinction exists; a scenario with no mission_sequence behaves exactly
as it always has.

Commands that don't need Basilisk (``validate``) work without a Basilisk
build; commands that do (``run``, ``kernels-status``) import it lazily and
report a clear, specific error instead of an ``ImportError`` traceback if
it's missing -- see each command function's own lazy import.

Usage::

    spacemissionstudio validate scenario.json
    spacemissionstudio run scenario.json --out-dir results/
    spacemissionstudio monte-carlo scenario.json --archive-dir mc_results/
    spacemissionstudio kernels-status
    spacemissionstudio spaceweather-resolve scenario.json
    spacemissionstudio generate-constellation template.json --out constellation.json \
        --total-satellites 12 --planes 3 --phasing-factor 1 --altitude-km 780 --inclination-deg 86.4
    spacemissionstudio generate-phasing-formation chief_only.json --out formation.json \
        --chief chief-1 --follower-name follower-1 --along-track-km 50
    spacemissionstudio gui
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

from . import dependencies
from .logging_setup import configure_logging
from .schema import ScenarioValidationError, load_scenario


def cmd_validate(args: argparse.Namespace) -> int:
    try:
        scenario = load_scenario(args.scenario)
    except ScenarioValidationError as exc:
        print(f"INVALID: {exc}", file=sys.stderr)
        return 1
    print(f"OK: {scenario.name!r} -- {len(scenario.spacecraft)} spacecraft, "
          f"schema version {scenario.schema_version}, epoch {scenario.epoch_utc}")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    try:
        scenario = load_scenario(args.scenario)
    except ScenarioValidationError as exc:
        print(f"INVALID: {exc}", file=sys.stderr)
        return 1

    if args.vizard_save_file and args.vizard_live_stream:
        print("ERROR: pass at most one of --vizard-save-file / --vizard-live-stream", file=sys.stderr)
        return 1

    try:
        from .engine.service import SimulationService
    except ImportError as exc:
        print(f"ERROR: Basilisk is not installed/built ({exc}) -- see SpaceMissionStudio/README.md", file=sys.stderr)
        return 2
    version_note = dependencies.basilisk_check()
    if version_note:
        print(f"WARNING: {version_note}", file=sys.stderr)

    vizard_request = None
    if args.vizard_save_file or args.vizard_live_stream:
        from .engine.vizard import VizardRequest

        vizard_request = VizardRequest(
            save_file=args.vizard_save_file, live_stream=args.vizard_live_stream,
            camera_target=args.vizard_camera_target, show_orbit_lines=not args.vizard_no_orbit_lines,
            show_trajectory_trail=args.vizard_trail, show_ground_tracks=args.vizard_ground_tracks,
        )

    print(f"Running {scenario.name!r} ({len(scenario.spacecraft)} spacecraft, "
          f"{scenario.sim_settings.duration_days} day(s), {scenario.sim_settings.integrator})...")
    service = SimulationService(scenario, vizard_request=vizard_request)
    command_summary = None
    try:
        if scenario.mission_sequence:
            # A non-empty mission_sequence takes over how far/how the sim
            # actually runs (propagate/maneuver/... commands drive
            # ConfigureStopTime()/ExecuteSimulation(), not a single
            # duration_days-long run()) -- see engine/mission_engine.py.
            # An empty mission_sequence (still the default -- see
            # schema/command.py) keeps the exact pre-Phase-6 behavior
            # below, unchanged.
            from .engine.mission_engine import MissionEngine

            print(f"Executing mission_sequence ({len(scenario.mission_sequence)} top-level command(s))...")
            result, command_summary = MissionEngine(scenario, service=service).run()
        else:
            result = service.run()
    except Exception as exc:  # noqa: BLE001 -- report ANY run failure with a specific message, not a bare traceback
        print(f"ERROR: run failed: {exc}", file=sys.stderr)
        return 3

    paths = result.export_csv(args.out_dir)
    print(f"Wrote {len(paths)} result file(s) to {args.out_dir}:")
    for name, path in sorted(paths.items()):
        print(f"  {name}: {path}")
    if args.oem:
        from .engine import ccsds_odm

        names = [sc.name for sc in scenario.spacecraft if f"{sc.name}.position_N" in result.series]
        for name, text in ccsds_odm.oem_from_result(result, scenario.epoch_utc, scenario.gravity.central_body,
                                                    names, stride=args.oem_stride,
                                                    interpolation=args.oem_interpolation).items():
            oem_path = args.out_dir / f"{name}.oem"
            oem_path.write_text(text, encoding="ascii")
            print(f"  CCSDS OEM: {oem_path}")

    # Informational only -- never affects the exit code (see
    # ResultSet.warnings's own docstring: a non-empty list here is a
    # numerical-health diagnostic, not a validation failure).
    for warning in result.warnings:
        print(f"WARNING: {warning}", file=sys.stderr)

    if command_summary is not None:
        print(f"Mission sequence: executed {command_summary.commands_executed} command(s), "
              f"{len(command_summary.reports)} report(s).")
        if command_summary.reports:
            summary_path = command_summary.export_csv(args.out_dir / "command_summary.csv")
            print(f"  command_summary: {summary_path}")

    if any(sc.station_keeping is not None for sc in scenario.spacecraft):
        print("Station-keeping summary:")
        _print_station_keeping_summary(scenario, result)
    if any(sc.constant_thrust is not None for sc in scenario.spacecraft):
        print("Constant-thrust summary:")
        _print_constant_thrust_summary(scenario, result)
    return 0


def _print_station_keeping_summary(scenario, result) -> None:
    """Prints total delta-V used and propellant used/remaining per
    spacecraft with ``station_keeping`` configured -- the headline numbers
    ``engine.orbit_maintenance`` tracks, surfaced directly rather than
    leaving the user to dig them out of a CSV. Reads the final sample of
    each spacecraft's ``.station_keeping.delta_v``/``.propellant_remaining``
    series (see ``engine.service.SimulationService.run()``); silently
    skips a spacecraft whose series aren't present (station_keeping was
    configured but, e.g., the run failed before the series could be built).

    A spacecraft with ``phasing_keeping`` ALSO configured shares one
    propellant tank between the two controllers (see
    ``schema.scenario.PhasingKeepingConfig``'s docstring), so
    ``propellant_used_kg`` here already covers both; delta-V is tracked
    separately per controller, so the total reported is their sum, with a
    breakdown line underneath.
    """
    for sc in scenario.spacecraft:
        if sc.station_keeping is None:
            continue
        delta_v_series = result.series.get(f"{sc.name}.station_keeping.delta_v")
        propellant_series = result.series.get(f"{sc.name}.station_keeping.propellant_remaining")
        if delta_v_series is None or propellant_series is None or len(delta_v_series.data) == 0:
            continue
        station_keeping_delta_v_m_s = float(delta_v_series.data[-1, 0])
        propellant_remaining_kg = float(propellant_series.data[-1, 0])
        propellant_used_kg = sc.station_keeping.propellant_kg - propellant_remaining_kg

        phasing_delta_v_m_s = 0.0
        if sc.phasing_keeping is not None:
            phasing_delta_v_series = result.series.get(f"{sc.name}.phasing_keeping.delta_v")
            if phasing_delta_v_series is not None and len(phasing_delta_v_series.data) > 0:
                phasing_delta_v_m_s = float(phasing_delta_v_series.data[-1, 0])

        total_delta_v_m_s = station_keeping_delta_v_m_s + phasing_delta_v_m_s
        print(f"  {sc.name}: {total_delta_v_m_s:.3f} m/s delta-V, "
              f"{propellant_used_kg:.3f} kg propellant used ({propellant_remaining_kg:.3f} kg remaining)")
        if sc.phasing_keeping is not None:
            print(f"    (altitude-keeping: {station_keeping_delta_v_m_s:.3f} m/s, "
                  f"phasing vs. {sc.phasing_keeping.chief_spacecraft!r}: {phasing_delta_v_m_s:.3f} m/s)")


def _print_constant_thrust_summary(scenario, result) -> None:
    """Same idea as :func:`_print_station_keeping_summary`, for
    ``constant_thrust`` -- an INDEPENDENT propellant budget/tank from
    station_keeping's (see ``schema.scenario.ConstantThrustConfig``'s
    docstring), so this is always its own separate line, never combined
    with the station-keeping summary above even when both are configured
    on the same spacecraft.
    """
    for sc in scenario.spacecraft:
        if sc.constant_thrust is None:
            continue
        delta_v_series = result.series.get(f"{sc.name}.constant_thrust.delta_v")
        propellant_series = result.series.get(f"{sc.name}.constant_thrust.propellant_remaining")
        if delta_v_series is None or propellant_series is None or len(delta_v_series.data) == 0:
            continue
        delta_v_m_s = float(delta_v_series.data[-1, 0])
        propellant_remaining_kg = float(propellant_series.data[-1, 0])
        propellant_used_kg = sc.constant_thrust.propellant_kg - propellant_remaining_kg
        print(f"  {sc.name}: {delta_v_m_s:.3f} m/s delta-V ({sc.constant_thrust.frame} frame), "
              f"{propellant_used_kg:.3f} kg propellant used ({propellant_remaining_kg:.3f} kg remaining)")


def cmd_monte_carlo(args: argparse.Namespace) -> int:
    try:
        scenario = load_scenario(args.scenario)
    except ScenarioValidationError as exc:
        print(f"INVALID: {exc}", file=sys.stderr)
        return 1

    if not scenario.monte_carlo.enabled:
        print("ERROR: scenario.monte_carlo.enabled is false in this scenario file -- "
              "set it true (and configure dispersions) before running Monte Carlo", file=sys.stderr)
        return 1

    try:
        from .engine.monte_carlo import MonteCarloError, run_monte_carlo
    except ImportError as exc:
        print(f"ERROR: Basilisk is not installed/built ({exc}) -- see SpaceMissionStudio/README.md", file=sys.stderr)
        return 2

    print(f"Running {scenario.monte_carlo.num_runs} Monte Carlo case(s) of {scenario.name!r} "
          f"({len(scenario.monte_carlo.dispersions)} dispersion(s), {scenario.monte_carlo.thread_count} thread(s))...")
    try:
        failures = run_monte_carlo(scenario, scenario.monte_carlo, args.archive_dir)
    except MonteCarloError as exc:
        print(f"ERROR: Monte Carlo run failed: {exc}", file=sys.stderr)
        return 3

    print(f"Archived results to {args.archive_dir}")
    if failures:
        print(f"FAILED runs: {failures}", file=sys.stderr)
        return 4
    print(f"All {scenario.monte_carlo.num_runs} run(s) succeeded.")
    return 0


def cmd_lifetime(args: argparse.Namespace) -> int:
    try:
        scenario = load_scenario(args.scenario)
    except ScenarioValidationError as exc:
        print(f"INVALID: {exc}", file=sys.stderr)
        return 1
    name = args.spacecraft or scenario.spacecraft[0].name
    try:
        from .engine import lifetime
    except ImportError as exc:
        print(f"ERROR: Basilisk is not installed/built ({exc}) -- see SpaceMissionStudio/README.md", file=sys.stderr)
        return 2
    try:
        drag_coeff = None if args.drag_coeff == "own" else float(args.drag_coeff)
        end = lifetime.end_of_life(scenario, name, deorbit_perigee_km=args.deorbit_perigee_km,
                                   max_years=args.max_years, forecast_percentile=args.forecast_percentile,
                                   drag_coeff=drag_coeff)
    except lifetime.LifetimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 3
    result = end.lifetime
    if end.deorbit is not None:
        plan = end.deorbit
        print(f"Deorbit burn: {plan.delta_v_m_s:.1f} m/s, {plan.propellant_kg:.2f} kg of "
              f"{plan.propellant_available_kg:.2f} kg -> perigee {plan.perigee_km:.0f} km")
    if result.reentered:
        print(f"{name}: re-entry {result.reentry_utc:%Y-%m-%d}, {result.lifetime_years:.2f} years from "
              f"{result.start_utc:%Y-%m-%d}")
    else:
        print(f"{name}: still in orbit after {result.horizon_years:.1f} years")
    for years, label in ((lifetime.ZERO_DEBRIS_YEARS, "5-year rule"), (lifetime.IADC_YEARS, "25-year guideline")):
        verdict = ("met" if result.meets(years) else "not met") if result.known(years) else "not known"
        print(f"  {label}: {verdict}")
    for warning in result.warnings:
        print(f"WARNING: {warning}", file=sys.stderr)
    return 0


def _print_altitude_trade(pb, scenario, name, result, altitudes) -> int:
    print(f"{name}: launch-delay sweep per altitude (several minutes; altitudes run in parallel)...")
    try:
        trade = pb.altitude_trade(scenario, name, altitudes or None, result)
    except pb.BudgetError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 3
    print(f"{'Altitude':>8} {'Incl.':>6} {'Worst launch':<12} {'In-plane dV':>12} {'Disposal dV':>12} "
          f"{'Prop. [kg]':>10}  Fits tank")
    for case in trade.altitudes:
        worst = case.worst
        fits = {True: "yes", False: "no", None: "-"}[trade.fits(case)]
        print(f"{case.altitude_km:>6g}km {case.inclination_deg:>6.2f} {worst.launch_utc:%Y-%m-%d}   "
              f"{worst.delta_v_of('Operations', 'In-plane'):>12.2f} {worst.delta_v_of('End of life', ''):>12.2f} "
              f"{worst.budget.total_propellant_kg:>10.3f}  {fits}")
    for note in trade.notes:
        print(f"NOTE: {note}")
    return 0


def _altitudes_arg(text: str) -> list:
    if text == "auto":
        return []
    try:
        altitudes = [float(v) for v in text.split(",") if v.strip()]
    except ValueError:
        raise argparse.ArgumentTypeError(f"{text!r}: comma-separated altitudes in km, e.g. 400,450,500") from None
    if not altitudes or any(not 150.0 <= a <= 2000.0 for a in altitudes):
        raise argparse.ArgumentTypeError(f"{text!r}: altitudes between 150 and 2000 km")
    return altitudes


def _drag_coeff_arg(text: str) -> str:
    if text != "own":
        try:
            if not 0.0 < float(text) <= 10.0:
                raise ValueError
        except ValueError:
            raise argparse.ArgumentTypeError(f"{text!r}: a drag coefficient in (0, 10], or 'own'") from None
    return text


def cmd_budget(args: argparse.Namespace) -> int:
    try:
        scenario = load_scenario(args.scenario)
    except ScenarioValidationError as exc:
        print(f"INVALID: {exc}", file=sys.stderr)
        return 1
    name = args.spacecraft or scenario.spacecraft[0].name
    try:
        from .engine import propellant_budget as pb
        from .engine.service import SimulationService
    except ImportError as exc:
        print(f"ERROR: Basilisk is not installed/built ({exc}) -- see SpaceMissionStudio/README.md", file=sys.stderr)
        return 2
    result = None
    if args.run:
        print(f"Running {scenario.name!r} for the simulated contributors...")
        try:
            result = SimulationService(scenario).run()
        except Exception as exc:  # noqa: BLE001 -- report ANY run failure with a specific message
            print(f"ERROR: run failed: {exc}", file=sys.stderr)
            return 3
    if args.altitudes is not None:
        return _print_altitude_trade(pb, scenario, name, result, args.altitudes)
    if args.launch_delays:
        return _print_launch_delays(pb, scenario, name, result)
    try:
        budget = pb.compute_budget(scenario, name, result)
    except pb.BudgetError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 3
    print(f"{name}: dry mass {budget.dry_mass_kg:.1f} kg, Isp {budget.isp_s:g} s, efficiency {budget.efficiency:.3f}")
    print(f"{'Phase':<18} {'Contributor':<52} {'dV [m/s]':>9} {'Prop. [kg]':>10}  Margin")
    for row in budget.rows:
        dv = "" if row.delta_v_m_s is None else f"{row.delta_v_m_s:.2f}"
        print(f"{row.phase:<18} {row.contributor:<52} {dv:>9} {row.propellant_kg:>10.3f}  {row.margin} ({row.source})")
    print(f"{'Total':<71} {budget.total_delta_v_m_s:>9.2f} {budget.total_propellant_kg:>10.3f}")
    for note in budget.notes:
        print(f"NOTE: {note}")
    return 0


def _print_launch_delays(pb, scenario, name, result) -> int:
    print(f"{name}: budget for the planned launch and up to 5 years late (ESA AD10 Sec. 5.5)...")
    try:
        sweep = pb.launch_delay_sweep(scenario, name, result)
    except pb.BudgetError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 3
    print(f"{'Launch':<11} {'Delay':>6} {'In-plane dV':>12} {'Disposal dV':>12} {'Total dV':>9} {'Prop. [kg]':>10}")
    worst = sweep.worst
    for case in sweep.cases:
        in_plane = case.delta_v_of("Operations", "In-plane")
        disposal = case.delta_v_of("End of life", "")
        mark = "  <- worst" if case is worst else ""
        print(f"{case.launch_utc:%Y-%m-%d} {case.delay_years:>5g}y {in_plane:>12.2f} {disposal:>12.2f} "
              f"{case.budget.total_delta_v_m_s:>9.2f} {case.budget.total_propellant_kg:>10.3f}{mark}")
    for note in sweep.notes:
        print(f"NOTE: {note}")
    return 0


def cmd_kernels_status(args: argparse.Namespace) -> int:
    try:
        from .engine import kernels
    except ImportError as exc:
        print(f"ERROR: Basilisk is not installed/built ({exc}) -- see SpaceMissionStudio/README.md", file=sys.stderr)
        return 2

    statuses = kernels.ensure_kernels()
    for status in statuses:
        if status.available:
            cached_note = f" (cached, last modified {status.modified_utc})" if status.modified_utc else ""
            print(f"  OK    {status.filename}: {status.path}{cached_note}")
        else:
            print(f"  FAIL  {status.filename}: {status.error}")
    return 0 if all(s.available for s in statuses) else 1


def cmd_earth_orientation(args: argparse.Namespace) -> int:
    """Status of the Earth orientation files; --fetch downloads them from
    NAIF (network: only when asked), --import installs files from disk,
    --rollback restores the previous set."""
    from .engine import earth_orientation as eo

    try:
        if args.fetch:
            print(f"Downloading from {eo.NAIF_PCK_URL}: {', '.join(eo.available_files())} ...")
            eo.fetch()
        elif args.import_files:
            eo.import_files(args.import_files)
        elif args.rollback:
            eo.rollback()
    except eo.EarthOrientationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    kernels = eo.installed()
    if not kernels:
        print(f"No Earth orientation files installed: runs use {eo.FALLBACK_EARTH_FRAME}. "
              "Run 'spacemissionstudio earth-orientation --fetch' (needs internet) or --import FILE.")
        return 1
    for kernel in kernels:
        print(f"  {kernel.role:15s} {Path(kernel.path).name}  {kernel.size_bytes / 1e6:.1f} MB  "
              f"last datum {kernel.last_datum_utc or 'unknown'}  sha256 {kernel.sha256[:16]}  from {kernel.source}")
    until = eo.high_accuracy_until(kernels)
    print(f"Earth-fixed frame: {eo.EARTH_FIXED_FRAME}; high accuracy until "
          f"{until:%Y-%m-%d}, predicted after." if until else f"Earth-fixed frame: {eo.EARTH_FIXED_FRAME}.")
    return 0


def cmd_ccsds_validate(args: argparse.Namespace) -> int:
    """Check KVN OPM/OMM/OEM files against CCSDS 502.0-B-3."""
    from .engine import ccsds_odm

    failed = False
    for path in args.files:
        issues = ccsds_odm.validate(Path(path).read_text(encoding="ascii", errors="replace"))
        errors = [i for i in issues if i.level == "error"]
        failed = failed or bool(errors)
        print(f"{path}: {'conforms' if not errors else f'{len(errors)} error(s)'}"
              + (f", {len(issues) - len(errors)} warning(s)" if len(issues) > len(errors) else ""))
        for issue in issues:
            print(f"  {issue}")
    return 1 if failed else 0


def cmd_ccsds_export(args: argparse.Namespace) -> int:
    """OPM of each spacecraft's initial state, or a TLE spacecraft's OMM."""
    try:
        scenario = load_scenario(args.scenario)
    except ScenarioValidationError as exc:
        print(f"INVALID: {exc}", file=sys.stderr)
        return 1
    from .engine import ccsds_odm, time_system

    args.out.mkdir(parents=True, exist_ok=True)
    epoch = time_system.elapsed_to_utc(scenario.epoch_utc, [0.0])[0]
    for sc in scenario.spacecraft:
        if sc.orbit.type == "tle":
            text = ccsds_odm.omm_from_tle(sc.orbit.tle_line1, sc.orbit.tle_line2, sc.name)
            path = args.out / f"{sc.name}.omm"
        else:
            try:
                from .engine.service import _orbit_ic_to_rv
            except ImportError as exc:
                print(f"ERROR: Basilisk is not installed/built ({exc})", file=sys.stderr)
                return 2
            r, v = _orbit_ic_to_rv(ccsds_odm.EARTH_GM_KM3_S2 * 1e9 if scenario.gravity.central_body == "earth"
                                   else _central_mu(scenario), sc.orbit, scenario.epoch_utc)
            gm = ccsds_odm.EARTH_GM_KM3_S2 if scenario.gravity.central_body == "earth" else None
            text = ccsds_odm.write_opm(
                object_name=sc.name, object_id="UNKNOWN", center_name=scenario.gravity.central_body,
                ref_frame="EME2000", time_system="UTC", epoch=epoch, r_km=[x / 1e3 for x in r],
                v_km_s=[x / 1e3 for x in v], gm_km3_s2=gm, mass_kg=sc.dry_mass_kg,
                srp_area_m2=sc.srp_area_m2 if sc.enable_srp else None, srp_coeff=sc.srp_coeff if sc.enable_srp else None,
                drag_area_m2=sc.drag_area_m2 if sc.enable_drag else None,
                drag_coeff=sc.drag_coeff if sc.enable_drag else None,
                comments=[f"Initial state of scenario {scenario.name!r}; EME2000 is SPICE J2000"])
            path = args.out / f"{sc.name}.opm"
        path.write_text(text, encoding="ascii")
        print(f"wrote {path}")
    return 0


def _central_mu(scenario) -> float:
    from Basilisk.utilities import simIncludeGravBody

    factory = simIncludeGravBody.gravBodyFactory()
    return getattr(factory, f"create{scenario.gravity.central_body.capitalize()}")().mu


def cmd_ccsds_import(args: argparse.Namespace) -> int:
    """Set a spacecraft's initial orbit from an OPM or TLE-based OMM."""
    from .engine import ccsds_odm

    try:
        scenario = load_scenario(args.scenario)
        orbit, epoch, notes = ccsds_odm.orbit_ic_from_odm(args.message.read_text(encoding="ascii", errors="replace"))
    except (ScenarioValidationError, ccsds_odm.OdmError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        for issue in getattr(exc, "issues", []):
            print(f"  {issue}", file=sys.stderr)
        return 1
    matches = [sc for sc in scenario.spacecraft if sc.name == args.spacecraft]
    if not matches:
        print(f"ERROR: no spacecraft {args.spacecraft!r} in {args.scenario}", file=sys.stderr)
        return 1
    if epoch is not None:
        scenario_epoch = datetime.fromisoformat(scenario.epoch_utc)
        if abs((epoch - scenario_epoch.replace(tzinfo=None)).total_seconds()) > 1e-3 and not args.set_epoch:
            print(f"ERROR: the OPM state is at {epoch.isoformat()} UTC, the scenario epoch is {scenario.epoch_utc}; "
                  "pass --set-epoch to move the scenario epoch to the OPM's", file=sys.stderr)
            return 1
        scenario.epoch_utc = epoch.isoformat()
    matches[0].orbit = orbit
    scenario.validate()
    scenario.save(args.out or args.scenario)
    for note in notes:
        print(f"  {note}")
    print(f"{args.spacecraft}: orbit set from {args.message} -> {args.out or args.scenario}")
    return 0


def cmd_spaceweather_resolve(args: argparse.Namespace) -> int:
    try:
        scenario = load_scenario(args.scenario)
    except ScenarioValidationError as exc:
        print(f"INVALID: {exc}", file=sys.stderr)
        return 1

    from .engine import spaceweather as sw

    start = datetime.fromisoformat(scenario.epoch_utc)
    end = start + timedelta(days=scenario.sim_settings.duration_days)
    try:
        resolved = sw.resolve_for(scenario.space_weather, start, end)
    except Exception as exc:  # noqa: BLE001 -- report ANY resolve failure with a specific message, not a bare traceback
        print(f"ERROR: space weather resolve failed: {exc}", file=sys.stderr)
        return 3
    print(f"Resolved to: {resolved.path}")
    print(f"From real data: {resolved.data_file}")
    for warning in resolved.warnings:
        print(f"  warning: {warning}")
    return 0


def cmd_generate_constellation(args: argparse.Namespace) -> int:
    try:
        scenario = load_scenario(args.scenario)
    except ScenarioValidationError as exc:
        print(f"INVALID: {exc}", file=sys.stderr)
        return 1

    if args.template_spacecraft is not None:
        template = next((sc for sc in scenario.spacecraft if sc.name == args.template_spacecraft), None)
        if template is None:
            print(f"ERROR: no spacecraft named {args.template_spacecraft!r} in {args.scenario} -- "
                  f"this scenario has: {[sc.name for sc in scenario.spacecraft]}", file=sys.stderr)
            return 1
    elif len(scenario.spacecraft) == 1:
        template = scenario.spacecraft[0]
    else:
        print(f"ERROR: {args.scenario} has {len(scenario.spacecraft)} spacecraft -- pass "
              "--template-spacecraft NAME to say which one to clone into the constellation", file=sys.stderr)
        return 1

    from .engine.constellation import WalkerConstellationRequest, generate_walker_constellation

    # central_body always comes from the scenario itself, never an
    # independent flag -- see gui.constellation_dialog's docstring for why
    # a mismatch there would silently produce satellites at the wrong
    # altitude relative to whatever body actually gets simulated.
    request = WalkerConstellationRequest(
        total_satellites=args.total_satellites, num_planes=args.planes, phasing_factor=args.phasing_factor,
        altitude_km=args.altitude_km, inclination_deg=args.inclination_deg,
        central_body=scenario.gravity.central_body, eccentricity=args.eccentricity,
        arg_periapsis_deg=args.arg_periapsis_deg, pattern=args.pattern,
        raan_offset_deg=args.raan_offset_deg, name_prefix=args.name_prefix,
    )
    try:
        generated = generate_walker_constellation(request, template)
    except ScenarioValidationError as exc:
        print(f"INVALID: {exc}", file=sys.stderr)
        return 1

    scenario.spacecraft = (scenario.spacecraft + generated) if args.append else generated
    try:
        scenario.save(args.out)
    except ScenarioValidationError as exc:
        print(f"INVALID: {exc}", file=sys.stderr)
        return 1

    print(f"Generated {len(generated)} spacecraft ({args.planes} plane(s), {request.pattern} pattern) "
          f"from template {template.name!r}, wrote {len(scenario.spacecraft)}-spacecraft scenario to {args.out}")
    return 0


def cmd_generate_phasing_formation(args: argparse.Namespace) -> int:
    try:
        scenario = load_scenario(args.scenario)
    except ScenarioValidationError as exc:
        print(f"INVALID: {exc}", file=sys.stderr)
        return 1

    chief = next((sc for sc in scenario.spacecraft if sc.name == args.chief), None)
    if chief is None:
        print(f"ERROR: no spacecraft named {args.chief!r} in {args.scenario} -- "
              f"this scenario has: {[sc.name for sc in scenario.spacecraft]}", file=sys.stderr)
        return 1
    if args.template_spacecraft is not None:
        template = next((sc for sc in scenario.spacecraft if sc.name == args.template_spacecraft), None)
        if template is None:
            print(f"ERROR: no spacecraft named {args.template_spacecraft!r} in {args.scenario} -- "
                  f"this scenario has: {[sc.name for sc in scenario.spacecraft]}", file=sys.stderr)
            return 1
    else:
        template = chief

    # engine.formation itself has no Basilisk import at module level (see
    # its own docstring) -- the real Basilisk import is lazy, INSIDE
    # generate_phasing_follower() below, so the ImportError this needs to
    # catch can only happen around that call, not this one.
    from .engine.formation import PhasingFormationRequest, generate_phasing_follower

    request = PhasingFormationRequest(
        chief_name=chief.name, follower_name=args.follower_name,
        radial_km=args.radial_km, along_track_km=args.along_track_km, cross_track_km=args.cross_track_km,
        reconfiguration_interval_days=args.reconfiguration_interval_days,
        tolerance_fraction=args.tolerance_fraction, restore_tolerance_fraction=args.restore_tolerance_fraction,
        correction_window_days=args.correction_window_days, max_drift_days=args.max_drift_days,
        max_delta_semi_major_axis_km=args.max_delta_semi_major_axis_km,
        station_keeping_target_altitude_km=args.station_keeping_target_altitude_km,
        station_keeping_deadband_km=args.station_keeping_deadband_km,
        thrust_n=args.thrust_n, isp_s=args.isp_s, propellant_kg=args.propellant_kg,
        eclipse_sunlit_threshold=args.eclipse_sunlit_threshold,
        min_on_time_s=args.min_on_time_s,
        eccentricity_neutral_burns=args.eccentricity_neutral_burns,
    )
    try:
        follower = generate_phasing_follower(request, chief, template, scenario.gravity.central_body)
    except ImportError as exc:
        print(f"ERROR: Basilisk is not installed/built ({exc}) -- generating a phasing formation needs a real "
              f"Basilisk build (it computes the follower's orbit via a real Hill-frame state-vector transform) "
              f"-- see SpaceMissionStudio/README.md", file=sys.stderr)
        return 2
    except ScenarioValidationError as exc:
        print(f"INVALID: {exc}", file=sys.stderr)
        return 1

    if follower.name in {sc.name for sc in scenario.spacecraft}:
        print(f"ERROR: a spacecraft named {follower.name!r} already exists in {args.scenario}", file=sys.stderr)
        return 1
    scenario.spacecraft = scenario.spacecraft + [follower]
    try:
        scenario.save(args.out)
    except ScenarioValidationError as exc:
        print(f"INVALID: {exc}", file=sys.stderr)
        return 1

    print(f"Generated follower {follower.name!r} (target along-track separation "
          f"{follower.phasing_keeping.target_separation_km[0]:.3f} km from chief {chief.name!r}), wrote "
          f"{len(scenario.spacecraft)}-spacecraft scenario to {args.out}")
    return 0


def cmd_gui(args: argparse.Namespace) -> int:
    try:
        from .gui.app import main as gui_main
    except ImportError as exc:
        print(f"ERROR: the GUI needs PySide6 and plotly installed "
              f"(pip install -e '.[gui]') -- {exc}", file=sys.stderr)
        return 2
    return gui_main([])


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="spacemissionstudio", description=__doc__,
                                      formatter_class=argparse.RawDescriptionHelpFormatter)
    subparsers = parser.add_subparsers(dest="command", required=True)

    p_validate = subparsers.add_parser("validate", help="validate a scenario file (no Basilisk needed)")
    p_validate.add_argument("scenario", type=Path)
    p_validate.set_defaults(func=cmd_validate)

    p_run = subparsers.add_parser("run", help="run a scenario headlessly and export results to CSV")
    p_run.add_argument("scenario", type=Path)
    p_run.add_argument("--out-dir", type=Path, default=Path("results"), help="directory to write CSV results to")
    p_run.add_argument("--oem", action="store_true",
                       help="also write each spacecraft's ephemeris as a CCSDS OEM (KVN, EME2000, UTC)")
    p_run.add_argument("--oem-stride", type=int, default=1, metavar="N",
                       help="write every Nth recorded state to the OEM (default 1: all)")
    p_run.add_argument("--oem-interpolation", choices=("hermite", "lagrange"), default="hermite",
                       help="interpolation the OEM suggests, degree 7 (GMAT reads only lagrange)")
    p_run.add_argument("--vizard-save-file", type=str, default=None,
                        help="write a Vizard .bin playback file to this path (see engine/vizard.py)")
    p_run.add_argument("--vizard-live-stream", action="store_true",
                        help="live-stream to a Vizard instance already running on this machine")
    p_run.add_argument("--vizard-camera-target", type=str, default=None,
                        help="spacecraft or celestial body name for Vizard's camera to start locked on "
                             "(default: the scenario's central body -- an Earth-centered view with the orbit "
                             "tracing around it, like STK/GMAT/FreeFlyer, rather than a spacecraft-locked close-up)")
    p_run.add_argument("--vizard-no-orbit-lines", action="store_true",
                        help="don't draw each spacecraft's orbit in Vizard (on by default)")
    p_run.add_argument("--vizard-trail", action="store_true",
                        help="also draw the flown path in Vizard (builds up into a band over long runs)")
    p_run.add_argument("--vizard-ground-tracks", action="store_true", help="also draw ground tracks in Vizard")
    p_run.set_defaults(func=cmd_run)

    p_mc = subparsers.add_parser("monte-carlo", help="run a Monte Carlo batch and archive retained results")
    p_mc.add_argument("scenario", type=Path)
    p_mc.add_argument("--archive-dir", type=Path, default=Path("monte_carlo_results"),
                       help="directory to archive per-run parameters and retained data to")
    p_mc.set_defaults(func=cmd_monte_carlo)

    p_life = subparsers.add_parser("lifetime", help="estimate when a spacecraft re-enters (orbit-averaged drag)")
    p_life.add_argument("scenario", type=Path)
    p_life.add_argument("--spacecraft", help="spacecraft name (default: the first)")
    p_life.add_argument("--deorbit-perigee-km", type=float, default=None,
                        help="first lower the perigee to this altitude [km] with the orbit thruster")
    p_life.add_argument("--max-years", type=float, default=30.0, help="how far ahead to look [years]")
    p_life.add_argument("--forecast-percentile", type=float, choices=(95.0, 50.0, 5.0), default=50.0,
                        help="MSFC solar-activity percentile (ESA AD10: 50 for end of life)")
    p_life.add_argument("--drag-coeff", default="2.2", type=_drag_coeff_arg,
                        help="drag coefficient, or 'own' for the spacecraft's (default 2.2: ESA AD10 end of life)")
    p_life.set_defaults(func=cmd_lifetime)

    p_budget = subparsers.add_parser("budget", help="delta-V and propellant budget (ESA AD10 style)")
    p_budget.add_argument("scenario", type=Path)
    p_budget.add_argument("--spacecraft", help="spacecraft name (default: the first)")
    p_budget.add_argument("--run", action="store_true",
                          help="run the scenario first, for orbit control and formation keeping")
    p_budget.add_argument("--launch-delays", action="store_true",
                          help="repeat the budget for launches 1-5 years late (ESA AD10 Sec. 5.5)")
    p_budget.add_argument("--altitudes", nargs="?", const="auto", type=_altitudes_arg, default=None,
                          metavar="KM,KM,...",
                          help="launch-delay sweep at each altitude [km] (default: five around the "
                               "spacecraft's own), against the tank")
    p_budget.set_defaults(func=cmd_budget)

    p_kernels = subparsers.add_parser("kernels-status", help="fetch/check SPICE kernel cache status")
    p_kernels.set_defaults(func=cmd_kernels_status)

    p_eop = subparsers.add_parser("earth-orientation",
                                  help="IERS-based Earth orientation files: status, --fetch, --import, --rollback")
    eop_action = p_eop.add_mutually_exclusive_group()
    eop_action.add_argument("--fetch", action="store_true", help="download the current NAIF Earth PCKs (internet)")
    eop_action.add_argument("--import", dest="import_files", nargs="+", type=Path, metavar="FILE",
                            help="install Earth PCK .bpc files from disk (a .cmt next to each is read too)")
    eop_action.add_argument("--rollback", action="store_true", help="restore the previously installed files")
    p_eop.set_defaults(func=cmd_earth_orientation)

    p_ccsds = subparsers.add_parser("ccsds-validate", help="check CCSDS OPM/OMM/OEM (KVN) files (no Basilisk needed)")
    p_ccsds.add_argument("files", nargs="+", type=Path)
    p_ccsds.set_defaults(func=cmd_ccsds_validate)
    p_ccsds_out = subparsers.add_parser("ccsds-export",
                                        help="write each spacecraft's initial state as a CCSDS OPM (or OMM for a TLE)")
    p_ccsds_out.add_argument("scenario", type=Path)
    p_ccsds_out.add_argument("--out", type=Path, required=True, help="output directory")
    p_ccsds_out.set_defaults(func=cmd_ccsds_export)
    p_ccsds_in = subparsers.add_parser("ccsds-import", help="set a spacecraft's orbit from a CCSDS OPM or TLE-based OMM")
    p_ccsds_in.add_argument("message", type=Path)
    p_ccsds_in.add_argument("scenario", type=Path)
    p_ccsds_in.add_argument("--spacecraft", required=True)
    p_ccsds_in.add_argument("--set-epoch", action="store_true", help="move the scenario epoch to the OPM's epoch")
    p_ccsds_in.add_argument("--out", type=Path, help="write the updated scenario here (default: overwrite)")
    p_ccsds_in.set_defaults(func=cmd_ccsds_import)

    p_sw = subparsers.add_parser("spaceweather-resolve",
                                  help="resolve space weather for a scenario without running it (no Basilisk needed)")
    p_sw.add_argument("scenario", type=Path)
    p_sw.set_defaults(func=cmd_spaceweather_resolve)

    p_const = subparsers.add_parser(
        "generate-constellation",
        help="generate a Walker-pattern constellation from a template scenario (no Basilisk needed)",
    )
    p_const.add_argument("scenario", type=Path, help="scenario file to load the template spacecraft/gravity from")
    p_const.add_argument("--out", type=Path, required=True, help="scenario file to write the result to")
    p_const.add_argument("--template-spacecraft", type=str, default=None,
                          help="name of the spacecraft to clone into the constellation (required if the input "
                               "scenario has more than one spacecraft)")
    p_const.add_argument("--total-satellites", type=int, required=True, help="T -- total satellite count")
    p_const.add_argument("--planes", type=int, required=True, help="P -- number of orbital planes")
    p_const.add_argument("--phasing-factor", type=int, required=True, help="F -- Walker phasing factor, 0 <= F < P")
    p_const.add_argument("--altitude-km", type=float, required=True, help="circular-orbit altitude [km]")
    p_const.add_argument("--inclination-deg", type=float, required=True, help="orbit inclination [deg]")
    p_const.add_argument("--pattern", choices=["delta", "star"], default="delta",
                          help="Walker-Delta (RAAN spread over 360deg) or Walker-Star (180deg); default delta")
    p_const.add_argument("--eccentricity", type=float, default=0.0)
    p_const.add_argument("--arg-periapsis-deg", type=float, default=0.0)
    p_const.add_argument("--raan-offset-deg", type=float, default=0.0,
                          help="rotates the whole constellation's RAAN reference")
    p_const.add_argument("--name-prefix", type=str, default="sat",
                          help="generated spacecraft are named '{prefix}-{plane:02d}-{slot:02d}'")
    p_const.add_argument("--append", action="store_true",
                          help="add the generated satellites to the template scenario's existing spacecraft "
                               "instead of replacing them")
    p_const.set_defaults(func=cmd_generate_constellation)

    p_phasing = subparsers.add_parser(
        "generate-phasing-formation",
        help="generate a follower spacecraft holding a phasing formation with an existing chief "
             "(needs a Basilisk build -- computes the follower's orbit via a real Hill-frame transform)",
    )
    p_phasing.add_argument("scenario", type=Path, help="scenario file to load the chief/template spacecraft from")
    p_phasing.add_argument("--out", type=Path, required=True, help="scenario file to write the result to")
    p_phasing.add_argument("--chief", type=str, required=True, help="name of the existing chief spacecraft")
    p_phasing.add_argument("--follower-name", type=str, required=True, help="name for the new follower spacecraft")
    p_phasing.add_argument("--template-spacecraft", type=str, default=None,
                            help="name of the spacecraft to clone the follower's non-orbit fields from "
                                 "(default: the chief itself)")
    p_phasing.add_argument("--radial-km", type=float, default=0.0,
                            help="Hill-frame radial (R) offset at epoch [km] -- starting geometry only, not "
                                 "actively held (see PhasingKeepingController's own docstring)")
    p_phasing.add_argument("--along-track-km", type=float, required=True,
                            help="Hill-frame along-track (T) offset at epoch [km] -- becomes "
                                 "phasing_keeping.target_separation_km, the ACTIVELY HELD separation")
    p_phasing.add_argument("--cross-track-km", type=float, default=0.0,
                            help="Hill-frame cross-track (N) offset at epoch [km] -- starting geometry only, "
                                 "not actively held")
    p_phasing.add_argument("--reconfiguration-interval-days", type=float, default=90.0)
    p_phasing.add_argument("--tolerance-fraction", type=float, default=0.10)
    p_phasing.add_argument("--restore-tolerance-fraction", type=float, default=0.02)
    p_phasing.add_argument("--correction-window-days", type=float, default=3.0)
    p_phasing.add_argument("--max-drift-days", type=float, default=90.0)
    p_phasing.add_argument("--max-delta-semi-major-axis-km", type=float, default=3.0)
    p_phasing.add_argument("--station-keeping-target-altitude-km", type=float, default=None,
                            help="default: derived from the chief's own altitude at generation time")
    p_phasing.add_argument("--station-keeping-deadband-km", type=float, default=2.0)
    p_phasing.add_argument("--thrust-n", type=float, default=0.05, help="shared thruster thrust [N]")
    p_phasing.add_argument("--isp-s", type=float, default=1500.0, help="shared thruster specific impulse [s]")
    p_phasing.add_argument("--propellant-kg", type=float, default=5.0, help="shared tank propellant [kg]")
    p_phasing.add_argument("--eclipse-sunlit-threshold", type=float, default=0.99,
                            help="minimum shadow factor [-] (1.0 = full sunlight) before a station-keeping "
                                 "reboost burn may fire")
    p_phasing.add_argument("--min-on-time-s", type=float, default=0.0,
                            help="shared thruster's minimum firing duration [s] (minimum impulse bit = "
                                 "thrust x this); 0 = ideal")
    p_phasing.add_argument("--eccentricity-neutral-burns", action="store_true",
                            help="gate firings so long eclipse-interrupted burns don't change eccentricity")
    p_phasing.set_defaults(func=cmd_generate_phasing_formation)

    p_gui = subparsers.add_parser("gui", help="launch the PySide6 GUI shell")
    p_gui.set_defaults(func=cmd_gui)

    return parser


def main(argv: list | None = None) -> int:
    # First thing, before anything else can fail -- see logging_setup's
    # own module docstring for why. Also covers `spacemissionstudio gui`
    # (cmd_gui() dispatches into gui.app.main(), which calls this same,
    # idempotent function itself too -- see its own docstring -- so
    # direct-launching the GUI via `python3 -m spacemissionstudio.gui.app`
    # gets it either way).
    configure_logging()
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
