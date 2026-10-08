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
    if case.degree:
        lines += [f"fm.GravityField.Earth.PotentialFile = '{grv_path}';",
                  f"fm.GravityField.Earth.Degree = {case.degree};", f"fm.GravityField.Earth.Order = {case.degree};"]
    else:
        lines += ["fm.GravityField.Earth.Degree = 0;", "fm.GravityField.Earth.Order = 0;"]
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
    for case in cases.PROPAGATION_CASES:
        if args.only and case.name not in args.only:
            continue
        text = script(case, grv)
        path = SCRIPTS / f"{case.name}.script"
        path.write_text(text, encoding="utf-8")
        run = subprocess.run(["./GmatConsole", "--run", str(path)], cwd=gmat_bin, capture_output=True, text=True)
        report = gmat_bin.parent / "output" / f"{case.name}.txt"
        if run.returncode or not report.exists():
            print(run.stdout[-4000:], file=sys.stderr)
            return 1
        sha = hashlib.sha256(text.encode()).hexdigest()
        header = (f"# {case.name}: {case.note}\n# Generated by {build} from compliance/validation/gmat/{path.name} "
                  f"(SHA-256 {sha}) on {datetime.now().date().isoformat()}\n"
                  "# columns: UTC modified Julian date (GMAT, JD - 2430000.0), X Y Z [km], VX VY VZ [km/s], "
                  "EarthMJ2000Eq\n")
        (cases.GMAT_DATA / f"{case.name}.txt").write_text(header + report.read_text(), encoding="utf-8")
        report.unlink()
        print(f"{case.name}: {sum(1 for _ in open(cases.GMAT_DATA / f'{case.name}.txt')) - 3} rows")
    return 0


if __name__ == "__main__":
    sys.exit(main())
