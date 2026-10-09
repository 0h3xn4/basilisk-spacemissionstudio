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
"""Generate ``compliance/docs/SDD_components.md``, the SDD's component
descriptions (ECSS-E-ST-40C F.2.1<5.3>, <5.4>, <6>; remediation R14).

For every module of the ``spacemissionstudio`` package it lists, read from
the source with :mod:`ast` (nothing is imported):

* identifier (the dotted module path: hierarchical, parent first);
* type (Python module; its public classes and functions are its
  subordinates);
* purpose (the docstring's first sentence) and the SRS requirements it
  implements (from :data:`SRS_TO_COMPONENTS`);
* dependencies: the package modules it imports, and the third-party
  packages;
* size in lines.

It also writes the forward (requirement -> components) and backward
(component -> requirements) traceability. The build fails if the map names a
module that does not exist or an SRS requirement that ``SRS.md`` does not
define, or if an SRS requirement is not mapped. Usage::

    python compliance/tools/build_sdd_components.py
"""

from __future__ import annotations

import ast
import collections
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACKAGE = ROOT.parent / "spacemissionstudio"

#: SRS requirement -> the package modules that implement it (paths relative
#: to the package, without ``.py``). Kept by hand; checked by :func:`build`.
SRS_TO_COMPONENTS = {
    "SRS-F-01": ["schema/scenario", "schema/migrations", "schema/validation"],
    "SRS-F-02": ["schema/scenario", "engine/tle", "engine/service"],
    "SRS-F-03": ["engine/service", "engine/long_run", "engine/environment_models", "engine/facets"],
    "SRS-F-04": ["engine/planet_rotation", "engine/geodetic_atmosphere", "engine/geodesy"],
    "SRS-F-05": ["engine/spaceweather", "engine/service"],
    "SRS-F-06": ["engine/earth_orientation", "engine/service"],
    "SRS-F-07": ["engine/time_system", "engine/results"],
    "SRS-F-08": ["engine/geodesy", "engine/service", "engine/scenario_checks"],
    "SRS-F-09": ["engine/fsw", "engine/device_catalog", "engine/service"],
    "SRS-F-10": ["engine/orbit_maintenance", "engine/formation_control", "engine/geo_station_keeping",
                 "engine/formation", "engine/propellant_bookkeeping"],
    "SRS-F-11": ["schema/command", "engine/mission_engine"],
    "SRS-F-12": ["engine/results", "engine/series_names", "engine/frames"],
    "SRS-F-13": ["engine/lifetime", "engine/propellant_budget", "engine/monte_carlo", "engine/link_budget",
                 "engine/constellation", "engine/formation", "engine/orbit_design"],
    "SRS-F-14": ["engine/ccsds_odm", "engine/tle"],
    "SRS-F-15": ["gui/main_window", "gui/scenario_editor", "gui/results_widget", "gui/mission_dashboard_widget",
                 "gui/mission_output_widget", "gui/data_panel_widget", "gui/help_dialog", "gui/scenario_explainer_widget",
                 "gui/event_timeline_widget", "gui/time_cursor", "engine/events", "gui/command_palette",
                 "gui/undo_history", "gui/run_history", "engine/scenario_diff",
                 "gui/spacecraft_editor", "gui/orbit_ic_widget", "gui/sensor_actuator_editor", "gui/facet_editor",
                 "gui/ground_station_editor", "gui/propagation_setup_dialog", "gui/monte_carlo_editor",
                 "gui/budget_widget", "gui/lifetime_widget", "gui/constellation_dialog",
                 "gui/phasing_formation_dialog", "gui/spacecraft_template_dialog", "gui/app"],
    "SRS-F-16": ["engine/vizard", "gui/vizard_launcher", "gui/vizard_dialog"],
    "SRS-F-17": ["dependencies", "engine/service", "output_provenance"],
    "SRS-P-01": ["engine/service"],
    "SRS-P-02": ["engine/service", "engine/planet_rotation", "engine/earth_orientation"],
    "SRS-P-03": ["engine/service"],
    "SRS-P-04": ["engine/service", "engine/geodetic_atmosphere", "engine/spaceweather"],
    "SRS-P-05": ["engine/time_system"],
    "SRS-P-06": ["engine/earth_orientation"],
    "SRS-P-07": ["engine/geodesy", "engine/service"],
    "SRS-P-08": ["engine/lifetime"],
    "SRS-P-09": ["engine/service"],
    "SRS-I-01": ["schema/scenario", "schema/command", "schema/migrations"],
    "SRS-I-02": ["cli"],
    "SRS-I-03": ["engine/results"],
    "SRS-I-04": ["engine/ccsds_odm"],
    "SRS-I-05": ["engine/spaceweather"],
    "SRS-I-06": ["engine/kernels", "engine/earth_orientation"],
    "SRS-I-07": ["engine/service", "dependencies"],
    "SRS-I-08": ["engine/vizard", "gui/vizard_launcher"],
    "SRS-O-01": ["gui/run_worker", "cli", "engine/service"],
    "SRS-O-02": ["gui/main_window", "gui/load_scenario_widget", "gui/template_wizard"],
    "SRS-R-01": ["engine/service"],
    "SRS-R-02": ["engine/results"],
    "SRS-D-01": ["engine/service"],
    "SRS-D-02": ["engine/service", "dependencies"],
    "SRS-D-03": ["schema/scenario", "engine/spaceweather", "engine/ccsds_odm", "engine/geodesy", "engine/time_system",
                 "engine/frames"],
    "SRS-D-04": ["schema/scenario", "schema/validation"],
    "SRS-S-01": ["engine/spaceweather", "engine/earth_orientation", "engine/kernels", "engine/reference_data",
                 "_offline", "gui/startup_fetch_dialog", "gui/data_panel_widget", "gui/vizard_launcher"],
    "SRS-S-02": ["engine/spaceweather", "engine/earth_orientation", "engine/results"],
    "SRS-S-03": ["engine/mission_engine", "schema/command", "gui/main_window", "cli"],
    "SRS-S-04": ["schema/command", "engine/mission_engine"],
    "SRS-PO-01": ["dependencies"],
    "SRS-Q-01": [],
    "SRS-Q-02": [],
    "SRS-Q-03": [],
    "SRS-RE-01": ["engine/service", "engine/long_run", "gui/run_worker"],
    "SRS-RE-02": ["gui/autosave"],
    "SRS-M-01": [],
    "SRS-M-02": ["engine/planet_rotation", "engine/geodetic_atmosphere"],
    "SRS-DEL-01": [],
    "SRS-DF-01": ["engine/ccsds_odm"],
    "SRS-DF-02": ["engine/results"],
    "SRS-DF-03": ["schema/scenario", "engine/results"],
    "SRS-H-01": ["gui/widgets", "gui/param_form", "gui/feedback", "schema/validation"],
    "SRS-H-02": ["gui/template_wizard", "gui/load_scenario_widget", "engine/spacecraft_templates"],
    "SRS-H-03": ["engine/scenario_explainer", "gui/scenario_explainer_widget"],
    "SRS-A-01": ["engine/earth_orientation", "engine/spaceweather", "gui/vizard_launcher"],
    "SRS-A-02": ["engine/kernels"],
}

#: Requirements met by the process or the delivery, not by a component.
NOT_A_COMPONENT = {
    "SRS-Q-01": "CI and `compliance/tools/metrics.py`",
    "SRS-Q-02": "CI (`ruff`)",
    "SRS-Q-03": "CI (`compliance/tools/metrics.py`)",
    "SRS-M-01": "CI workflow `.github/workflows/spacemissionstudio.yml`",
    "SRS-DEL-01": "`pyproject.toml`, `packaging/`",
}


def _summary(tree: ast.Module) -> str:
    doc = ast.get_docstring(tree) or ""
    first = doc.strip().split("\n\n")[0].replace("\n", " ")
    match = re.match(r"(.+?[.:])(\s|$)", first)
    return (match.group(1) if match else first)[:200].rstrip(":").replace("|", "/")


def _imports(tree: ast.Module, module: str) -> tuple:
    """(package modules, third-party top-level packages) a module imports."""
    internal, external = set(), set()
    package = module.rsplit("/", 1)[0] if "/" in module else ""
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("spacemissionstudio."):
                    internal.add(alias.name.split(".", 1)[1].replace(".", "/"))
                else:
                    external.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = package.split("/")[:len(package.split("/")) - (node.level - 1)] if package else []
                stem = "/".join([*base, *(node.module.split(".") if node.module else [])])
                for alias in node.names:
                    candidate = f"{stem}/{alias.name}".strip("/")
                    internal.add(candidate if (PACKAGE / f"{candidate}.py").exists() else stem)
            elif node.module and node.module.startswith("spacemissionstudio"):
                stem = node.module.split(".", 1)[1].replace(".", "/") if "." in node.module else ""
                for alias in node.names:
                    candidate = f"{stem}/{alias.name}".strip("/")
                    internal.add(candidate if (PACKAGE / f"{candidate}.py").exists() else stem)
            elif node.module:
                external.add(node.module.split(".")[0])
    stdlib = set(sys.stdlib_module_names) | {"__future__"}
    internal = {m for m in internal if m and m != module and (PACKAGE / f"{m}.py").exists()}
    return sorted(internal), sorted(external - stdlib - {"spacemissionstudio"})


def _subordinates(tree: ast.Module) -> list:
    return [n.name for n in tree.body
            if isinstance(n, (ast.ClassDef, ast.FunctionDef)) and not n.name.startswith("_")]


def build() -> int:
    modules = sorted(str(p.relative_to(PACKAGE).with_suffix("")) for p in PACKAGE.rglob("*.py")
                     if p.name != "__init__.py" and "__pycache__" not in p.parts)
    srs = set(re.findall(r"^\| (SRS-[A-Z]+-\d+) \|", (ROOT / "docs" / "SRS.md").read_text(encoding="utf-8"),
                         re.MULTILINE))
    problems = [f"SRS requirement not mapped: {r}" for r in sorted(srs - SRS_TO_COMPONENTS.keys())]
    problems += [f"map names an unknown requirement: {r}" for r in sorted(SRS_TO_COMPONENTS.keys() - srs)]
    problems += [f"{r}: unknown module {m}" for r, ms in SRS_TO_COMPONENTS.items() for m in ms if m not in modules]
    problems += [f"{r}: maps to no component and has no process reason" for r, ms in SRS_TO_COMPONENTS.items()
                 if not ms and r not in NOT_A_COMPONENT]
    if problems:
        print(*problems, sep="\n", file=sys.stderr)
        return 1
    backward = collections.defaultdict(list)
    for requirement, components in SRS_TO_COMPONENTS.items():
        for component in components:
            backward[component].append(requirement)

    lines = ["# SDD component descriptions (generated)", "",
             "Generated by `compliance/tools/build_sdd_components.py` from the source of the `spacemissionstudio` "
             "package (read with `ast`, nothing imported). The SDD (`SDD.md`) gives the architecture; this file "
             "gives each component (F.2.1<5.3>, <5.4>) and the traceability (F.2.1<6>).", "",
             "Identifiers are module paths: `engine/service` is `spacemissionstudio/engine/service.py`. "
             "Every component is a Python module developed for this tool (development type: new); the reused "
             "software (Basilisk and the third-party packages) is listed under each module's external "
             "dependencies and in `SRF.md`.", "",
             "## Components", "",
             "| Identifier | Purpose | SRS | Subordinates (public classes, functions) | Uses (package) | Uses "
             "(third party) | Lines |", "|---|---|---|---|---|---|---|"]
    for module in modules:
        path = PACKAGE / f"{module}.py"
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        internal, external = _imports(tree, module)
        subordinates = _subordinates(tree)
        shown = ", ".join(f"`{s}`" for s in subordinates[:12]) + (f" (+{len(subordinates) - 12})"
                                                                   if len(subordinates) > 12 else "")
        lines.append(f"| `{module}` | {_summary(tree)} | {', '.join(backward.get(module, [])) or '-'} | "
                     f"{shown or '-'} | {', '.join(internal) or '-'} | {', '.join(external) or '-'} | "
                     f"{len(source.splitlines())} |")
    lines += ["", "## Forward traceability (requirement -> components)", "",
              "| Requirement | Components |", "|---|---|"]
    for requirement in sorted(SRS_TO_COMPONENTS, key=lambda r: (r.split("-")[1], int(r.split("-")[2]))):
        components = SRS_TO_COMPONENTS[requirement]
        shown = ", ".join(f"`{c}`" for c in components) or f"no component: {NOT_A_COMPONENT[requirement]}"
        lines.append(f"| {requirement} | {shown} |")
    untraced = [m for m in modules if m not in backward]
    lines += ["", "## Backward traceability (component -> requirements)", "",
              "The SRS column of the component table above gives each component's requirements. "
              f"{len(untraced)} of {len(modules)} components trace to no SRS requirement directly; they are "
              "support code (GUI widgets, helpers) used by the components that do: "
              + ", ".join(f"`{m}`" for m in untraced) + "."]
    out = ROOT / "docs" / "SDD_components.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{out.name}: {len(modules)} components, {len(SRS_TO_COMPONENTS)} requirements traced")
    return 0


if __name__ == "__main__":
    sys.exit(build())
