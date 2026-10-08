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
"""Generate the GMAT reference data of the Phase 3 validation (R13).

Writes one GMAT script per case of ``tests/validation/validation_cases.py``
into ``compliance/validation/gmat/``, runs it with GMAT's console
application, and stores the report, with a header naming the GMAT build and
the script's SHA-256, in ``tests/data/validation/gmat/``. The tests compare
the tool against these files, so GMAT is needed only to regenerate them.

GMAT is configured with the tool's constants (validation_cases docstring):
the GGM03S field is converted to GMAT's ``.grv`` format with the GM and
reference radius Basilisk actually applies, and the ephemerides are the same
DE430 file. Usage::

    python compliance/validation/make_gmat_references.py --gmat /path/to/GMAT/R2026a/bin
"""

from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOOL = HERE.parent.parent
sys.path.insert(0, str(TOOL / "tests" / "validation"))
sys.path.insert(0, str(TOOL))

import validation_cases as cases  # noqa: E402

SCRIPTS = HERE / "gmat"
BASILISK_EARTH_RADIUS_M = 6378136.6  # [m] Basilisk's REQ_EARTH, which its harmonics model applies
_BODY = {"sun": "Sun", "moon": "Luna"}


def _support_file(name: str) -> Path:
    from Basilisk.utilities.supportDataTools.dataFetcher import DataFile, get_path

    return Path(get_path({"de430": DataFile.EphemerisData.de430, "ggm03s": DataFile.LocalGravData.GGM03S}[name]))


def write_grv(path: Path, degree: int) -> None:
    """GGM03S to degree ``degree`` in GMAT's .grv format, with the GM and
    radius Basilisk's SphericalHarmonicsGravityModel applies (the body's,
    not the file header's)."""
    lines = ["stk.v.4.3", "Model GGM03S (converted for SpaceMissionStudio validation)", f"Degree {degree}",
             f"Order {degree}", f"Gm {cases.EARTH_GM_KM3_S2 * 1e9:.10e}", f"RefDistance {BASILISK_EARTH_RADIUS_M}",
             "Normalized Yes", "BEGIN Coefficients"]
    with open(_support_file("ggm03s"), encoding="utf-8") as f:
        next(f)  # header: radius, GM, ...
        for line in f:
            fields = [x.strip() for x in line.split(",")]
            n, m = int(fields[0]), int(fields[1])
            if 2 <= n <= degree and m <= degree:
                lines.append(f"{n} {m} {fields[2]} {fields[3]}")
    lines.append("END Coefficients")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def script(case: cases.PropagationCase, grv_path: Path) -> str:
    epoch = datetime.fromisoformat(case.epoch_utc)
    lines = [f"% SpaceMissionStudio validation case {case.name}: {case.note}",
             "Create Spacecraft sat;", "sat.DateFormat = UTCGregorian;",
             f"sat.Epoch = '{epoch.strftime('%d %b %Y %H:%M:%S.000')}';",
             "sat.CoordinateSystem = EarthMJ2000Eq;", "sat.DisplayStateType = Cartesian;"]
    lines += [f"sat.{k} = {v!r};" for k, v in zip(("X", "Y", "Z", "VX", "VY", "VZ"), case.r_km + case.v_km_s)]
    lines += [f"sat.DryMass = {case.mass_kg!r};", f"sat.Cr = {case.cr!r};", f"sat.Cd = {case.cd!r};",
              f"sat.SRPArea = {case.area_m2!r};", f"sat.DragArea = {case.area_m2!r};",
              f"Earth.Mu = {cases.EARTH_GM_KM3_S2!r};", f"Sun.Mu = {cases.SUN_GM_KM3_S2!r};",
              f"Luna.Mu = {cases.MOON_GM_KM3_S2!r};", f"Earth.EquatorialRadius = {cases.WGS84_A_KM!r};",
              f"Earth.Flattening = {1.0 / cases.WGS84_INV_F!r};",
              "SolarSystem.EphemerisSource = 'SPICE';", f"SolarSystem.SPKFilename = '{_support_file('de430')}';",
              "Create ForceModel fm;", "fm.CentralBody = Earth;", "fm.PrimaryBodies = {Earth};"]
    # GMAT takes the central body's GM from the potential file even at degree 0 (its default JGM-2 file
    # has 398600.4415), so every case uses the converted file with the tool's GM.
    lines += [f"fm.GravityField.Earth.PotentialFile = '{grv_path}';",
              f"fm.GravityField.Earth.Degree = {case.degree};", f"fm.GravityField.Earth.Order = {case.degree};"]
    if case.third_bodies:
        lines.append("fm.PointMasses = {" + ", ".join(_BODY[b] for b in case.third_bodies) + "};")
    if case.srp:
        lines += ["fm.SRP = On;", f"fm.SRP.Flux = {cases.SOLAR_FLUX_W_M2!r};", "fm.SRP.Nominal_Sun = 149597870.693;",
                  "fm.SRP.SRPModel = Spherical;"]
    if case.drag:
        lines += ["fm.Drag.AtmosphereModel = NRLMSISE00;", "fm.Drag.HistoricWeatherSource = 'CSSISpaceWeatherFile';",
                  "fm.Drag.PredictedWeatherSource = 'CSSISpaceWeatherFile';"]
    lines += ["Create Propagator prop;", "prop.FM = fm;", "prop.Type = PrinceDormand78;", "prop.InitialStepSize = 10;",
              "prop.Accuracy = 1e-13;", "prop.MinStep = 0;", "prop.MaxStep = 60;",
              "Create ReportFile rep;", f"rep.Filename = '{case.name}.txt';", "rep.Precision = 16;",
              "rep.WriteHeaders = false;", "Create Variable k;", "BeginMissionSequence;",
              f"For k = 0:{int(round(case.days * 86400.0 / cases.OUTPUT_STEP_S))}",
              "  Report rep sat.UTCModJulian sat.X sat.Y sat.Z sat.VX sat.VY sat.VZ;",
              f"  Propagate prop(sat) {{sat.ElapsedSecs = {cases.OUTPUT_STEP_S!r}}};", "EndFor;"]
    return "\n".join(lines) + "\n"


def time_script() -> str:
    """One spacecraft per V-01 epoch; reports its epoch in UTC, TAI, TT and TDB."""
    lines = ["% SpaceMissionStudio validation V-01: time scales"]
    for k, epoch_utc in enumerate(cases.TIME_EPOCHS):
        epoch = datetime.fromisoformat(epoch_utc)
        lines += [f"Create Spacecraft t{k};", f"t{k}.DateFormat = UTCGregorian;",
                  f"t{k}.Epoch = '{epoch.strftime('%d %b %Y %H:%M:%S.')}{epoch.microsecond // 1000:03d}';"]
    lines += ["Create ReportFile rep;", "rep.Filename = 'time_scales.txt';", "rep.Precision = 17;",
              "rep.WriteHeaders = false;", "BeginMissionSequence;"]
    lines += [f"Report rep t{k}.UTCModJulian t{k}.TAIModJulian t{k}.TTModJulian t{k}.TDBModJulian;"
              for k in range(len(cases.TIME_EPOCHS))]
    return "\n".join(lines) + "\n"


def contact_script(grv_path: Path) -> str:
    """V-05: GMAT ContactLocator for cases.STATION over the CONTACT_CASE orbit
    (WGS-84 ellipsoid horizon, no light time or aberration)."""
    base = script(cases.case(cases.CONTACT_CASE), grv_path)
    head = base[:base.index("Create ReportFile rep;")]
    st = cases.STATION
    lines = [f"Create GroundStation {st['name']};", f"{st['name']}.CentralBody = Earth;",
             f"{st['name']}.StateType = Spherical;", f"{st['name']}.HorizonReference = Ellipsoid;",
             f"{st['name']}.Location1 = {st['latitude_deg']!r};", f"{st['name']}.Location2 = {st['longitude_deg']!r};",
             f"{st['name']}.Location3 = {st['altitude_m'] / 1000.0!r};",
             f"{st['name']}.MinimumElevationAngle = {st['min_elevation_deg']!r};",
             "Create ContactLocator cl;", "cl.Target = sat;", f"cl.Observers = {{{st['name']}}};",
             "cl.Filename = 'contacts_berlin.txt';", "cl.UseLightTimeDelay = false;",
             "cl.UseStellarAberration = false;", "cl.StepSize = 10;", "cl.RunMode = 'Automatic';",
             "cl.UseEntireInterval = true;", "BeginMissionSequence;",
             f"Propagate prop(sat) {{sat.ElapsedDays = {cases.case(cases.CONTACT_CASE).days!r}}};"]
    return head.replace("validation case twobody_leo", "validation V-05 (ContactLocator)") + "\n".join(lines) + "\n"


def oem_cases() -> dict:
    """V-06: GMAT writes an OEM of CONTACT_CASE; the tool writes its own
    (``tests/data/validation/tool_written.oem``, from a tool run) and GMAT
    reads it back through its CCSDS-OEM ephemeris propagator."""
    from dataclasses import replace

    from spacemissionstudio.engine import ccsds_odm
    from spacemissionstudio.engine.service import SimulationService

    case = replace(cases.case(cases.CONTACT_CASE), days=cases.OEM_HOURS / 24.0)
    result = SimulationService(cases.tool_scenario(case)).run()
    tool_oem = cases.DATA / "tool_written.oem"
    text = ccsds_odm.oem_from_result(result, case.epoch_utc, "earth", ["sat-1"], stride=cases.OEM_STRIDE,
                                     interpolation="LAGRANGE")["sat-1"]
    tool_oem.write_text(text, encoding="utf-8")
    # GMAT R2026a reads only version 1.0 (3.0 refused, 2.0 only in its testing mode; finding F-08): it gets a
    # copy whose only change is the version line (the header has no MESSAGE_ID, which 3.0 added).
    gmat_copy = SCRIPTS / "tool_written_as_v1.oem"
    gmat_copy.write_text(text.replace(f"CCSDS_OEM_VERS       = {ccsds_odm.VERSION}", "CCSDS_OEM_VERS       = 1.0", 1),
                         encoding="utf-8")
    base = script(case, SCRIPTS / "GGM03S_20.grv")
    head = base[:base.index("Create ReportFile rep;")]
    write = head + "\n".join(["Create EphemerisFile eph;", "eph.Spacecraft = sat;", "eph.Filename = 'gmat_written.oem';",
                               "eph.FileFormat = CCSDS-OEM;", "eph.EpochFormat = UTCGregorian;",
                               "eph.CoordinateSystem = EarthMJ2000Eq;", "eph.Interpolator = Lagrange;",
                               "eph.InterpolationOrder = 7;", "eph.StepSize = 60;", "BeginMissionSequence;",
                               f"Propagate prop(sat) {{sat.ElapsedSecs = {cases.OEM_HOURS * 3600.0!r}}};"]) + "\n"
    epoch = datetime.fromisoformat(case.epoch_utc)
    read = ["% SpaceMissionStudio validation V-06: GMAT reads the tool's OEM", "Create Spacecraft sat;",
            "sat.DateFormat = UTCGregorian;", f"sat.Epoch = '{epoch.strftime('%d %b %Y %H:%M:%S.000')}';",
            f"sat.EphemerisName = '{gmat_copy}';", "Create Propagator ep;", "ep.Type = CCSDS-OEM;",
            "ep.StepSize = 60;", "ep.CentralBody = Earth;", "ep.EpochFormat = UTCGregorian;",
            "ep.StartEpoch = 'FromSpacecraft';", "Create ReportFile rep;", "rep.Filename = 'gmat_reads_tool_oem.txt';",
            "rep.Precision = 16;", "rep.WriteHeaders = false;", "BeginMissionSequence;"]
    previous = 0.0
    for t_s in cases.OEM_QUERY_S:
        read += [f"Propagate ep(sat) {{sat.ElapsedSecs = {t_s - previous!r}}};",
                 "Report rep sat.UTCModJulian sat.X sat.Y sat.Z sat.VX sat.VY sat.VZ;"]
        previous = t_s
    return {"gmat_written_oem": write, "gmat_reads_tool_oem": "\n".join(read) + "\n"}


def extract_eop(gmat_bin: Path, step_days: int = 15) -> Path:
    """V-02 reference: every ``step_days``-th observed row of the IERS 20 C04
    series GMAT ships (rows with error flags 0.999 are predictions, left out),
    from 1990, with the file's own header lines for attribution."""
    source = gmat_bin.parent / "data" / "planetary_coeff" / "eopc04_08.62-now"
    header, rows = [], []
    for line in source.read_text(encoding="utf-8").splitlines():
        fields = line.split()
        if len(fields) >= 14 and fields[0].isdigit() and len(fields[0]) == 4:
            if int(fields[0]) >= 1990 and float(fields[10]) < 0.5:
                rows.append(line)
        elif not rows:
            header.append(line)
    out = cases.DATA / "eopc04_excerpt.txt"
    sha = hashlib.sha256(source.read_bytes()).hexdigest()
    out.write_text("\n".join([f"# Excerpt (every {step_days}th observed day from 1990) of {source.name} as shipped "
                               f"with GMAT, SHA-256 {sha}", *("# " + h for h in header if h.strip()), *rows[::step_days]])
                   + "\n", encoding="utf-8")
    return out


def gmat_build(gmat_bin: Path) -> str:
    out = subprocess.run(["./GmatConsole", "--version"], cwd=gmat_bin, capture_output=True, text=True)
    build = next((line.strip() for line in out.stdout.splitlines() if line.startswith("Build Date")), "unknown")
    return f"GMAT {gmat_bin.parent.name} ({build})"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--gmat", type=Path, required=True, help="GMAT bin directory (contains GmatConsole)")
    parser.add_argument("--only", nargs="*", help="case names (default: all)")
    args = parser.parse_args(argv)
    gmat_bin = args.gmat.resolve()
    SCRIPTS.mkdir(exist_ok=True)
    cases.GMAT_DATA.mkdir(parents=True, exist_ok=True)
    grv = SCRIPTS / "GGM03S_20.grv"
    write_grv(grv, 20)
    build = gmat_build(gmat_bin)
    if not args.only or "eop" in args.only:
        print(f"eop: {extract_eop(gmat_bin)}")
    jobs = [(c.name, c.note, script(c, grv)) for c in cases.PROPAGATION_CASES]
    jobs.append(("time_scales", "V-01 time scales at TIME_EPOCHS", time_script()))
    jobs.append(("contacts_berlin", "V-05 passes over cases.STATION (GMAT ContactLocator)", contact_script(grv)))
    if not args.only or {"gmat_written_oem", "gmat_reads_tool_oem"} & set(args.only):
        oem = oem_cases()
        jobs.append(("gmat_written_oem", "V-06 OEM written by GMAT", oem["gmat_written_oem"]))
        jobs.append(("gmat_reads_tool_oem", "V-06 GMAT's interpolation of tests/data/validation/tool_written.oem",
                     oem["gmat_reads_tool_oem"]))
    for name, note, text in jobs:
        if args.only and name not in args.only:
            continue
        path = SCRIPTS / f"{name}.script"
        path.write_text(text, encoding="utf-8")
        run = subprocess.run(["./GmatConsole", "--run", str(path)], cwd=gmat_bin, capture_output=True, text=True)
        report = gmat_bin.parent / "output" / ("gmat_written.oem" if name == "gmat_written_oem" else f"{name}.txt")
        if run.returncode or not report.exists():
            print(run.stdout[-4000:], file=sys.stderr)
            return 1
        sha = hashlib.sha256(text.encode()).hexdigest()
        header = (f"# {name}: {note}\n# Generated by {build} from compliance/validation/gmat/{path.name} "
                  f"(SHA-256 {sha}) on {datetime.now().date().isoformat()}\n"
                  + ("# columns: UTC, TAI, TT, TDB modified Julian dates (GMAT, JD - 2430000.0)\n"
                     if name == "time_scales" else "# GMAT ContactLocator report, times UTC\n"
                     if name == "contacts_berlin" else
                     "# columns: UTC modified Julian date (GMAT, JD - 2430000.0), X Y Z [km], VX VY VZ [km/s], "
                     "EarthMJ2000Eq\n"))
        if name == "gmat_written_oem":  # kept as GMAT wrote it: it is the file under test
            (cases.GMAT_DATA / "gmat_written.oem").write_text(report.read_text(), encoding="utf-8")
            report.unlink()
            print(f"{name}: written")
            continue
        (cases.GMAT_DATA / f"{name}.txt").write_text(header + report.read_text(), encoding="utf-8")
        report.unlink()
        print(f"{name}: {sum(1 for _ in open(cases.GMAT_DATA / f'{name}.txt')) - 3} rows")
    return 0


if __name__ == "__main__":
    sys.exit(main())
