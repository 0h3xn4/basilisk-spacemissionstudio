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
"""Build ``compliance/ics_ccsds_502.csv``: the CCSDS 502.0-B-3 Annex A
Implementation Conformance Statement requirements list for the OPM, OMM and
OEM, with this tool's support for reading/validating and for writing each
item. Read support comes from the keyword tables of
``spacemissionstudio.engine.ccsds_odm``; write support from the keywords
actually present in messages its writers produce. Usage::

    python compliance/tools/build_ics.py
"""

from __future__ import annotations

import csv
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT.parent))

from spacemissionstudio.engine import ccsds_odm as odm  # noqa: E402

_TLE = ("1 25544U 98067A   19343.69339541  .00001764  00000-0  38792-4 0  9991",
        "2 25544  51.6439 211.2001 0007417  17.6667  85.6398 15.50103472202482")


def _read_keywords(kind: str) -> set:
    tables = {"OPM": odm.OPM_METADATA + odm.OPM_DATA, "OMM": odm.OMM_METADATA + odm.OMM_DATA,
              "OEM": odm.OEM_METADATA}[kind]
    keywords = {k for _b, ks, _s, _u in tables for k in ks.split("|")}
    keywords |= {f"CCSDS_{kind}_VERS", *odm._HEADER, "USER_DEFINED_x"}
    if kind == "OEM":
        keywords |= {"META_START", "META_STOP", "COVARIANCE_START", "COVARIANCE_STOP", "EPOCH", "COV_REF_FRAME"}
    return keywords


def _written_keywords(kind: str) -> set:
    when = datetime(2026, 1, 1)
    if kind == "OPM":
        text = odm.write_opm(object_name="A", object_id="UNKNOWN", center_name="earth", ref_frame="EME2000",
                             time_system="UTC", epoch=when, r_km=[7000.0, 0.0, 0.0], v_km_s=[0.0, 7.5, 1.0],
                             gm_km3_s2=odm.EARTH_GM_KM3_S2, mass_kg=100.0, srp_area_m2=1.0, srp_coeff=1.3,
                             drag_area_m2=1.0, drag_coeff=2.2, comments=["x"], creation=when)
    elif kind == "OMM":
        text = odm.omm_from_tle(*_TLE, object_name="ISS", creation=when, comments=["x"])
    else:
        text = odm.write_oem([{"object_name": "A", "object_id": "UNKNOWN", "center_name": "earth",
                               "ref_frame": "EME2000", "time_system": "UTC",
                               "epochs": [when.replace(minute=m) for m in range(8)],
                               "r_km": [[7000.0, 0.0, 0.0]] * 8, "v_km_s": [[0.0, 7.5, 1.0]] * 8,
                               "interpolation": "HERMITE", "interpolation_degree": 7, "comments": ["x"]}],
                             comments=["x"], creation=when)
    keywords = set()
    for line in text.splitlines():
        match = re.match(r"^\s*([A-Z_0-9]+)\s*(=|$|\s)", line)
        if match:
            keywords.add(match.group(1))
    return keywords


_BLOCKS = {"Keplerian Elements": "kepler", "Mean Keplerian": "mean", "Spacecraft Parameters": "spacecraft",
           "Covariance Matrix": "covariance", "Maneuver": "maneuver", "TLE": "tle", "State Vector": "state"}


def _block_keywords(kind: str, text: str):
    """Keywords of the logical block an ICS item names, or None for a part
    every message has (header, metadata, data, ephemeris lines)."""
    if "User-Defined" in text:
        return ["USER_DEFINED_x"]
    if kind == "OEM" and "Covariance" in text:
        return ["COVARIANCE_START"]
    table = odm.OPM_DATA if kind == "OPM" else odm.OMM_DATA
    for marker, block in _BLOCKS.items():
        if marker in text:
            return [k for b, ks, _s, _u in table if b == block for k in ks.split("|")]
    return None


def build() -> int:
    with open(ROOT / "requirements" / "CCSDS-502.0-B-3.csv", encoding="utf-8") as f:
        items = [r for r in csv.DictReader(f) if r["ID"].split("-")[1:2] and r["ID"].split("-")[1] in
                 ("OPM", "OMM", "OEM")]
    rows = []
    for item in items:
        kind = item["ID"].split("-")[1]
        match = re.search(r"keyword (.+?), (Table [0-9-]+), status ([MOC])", item["requirement_text"])
        keyword_text, table, status = match.groups() if match else ("N/A", "", item["level"][:1].upper())
        if keyword_text == "N/A" or keyword_text.startswith("…"):  # a message part or logical block
            keywords = _block_keywords(kind, item["requirement_text"])
            read = "Y"
            write = "Y" if keywords is None or any(k in _written_keywords(kind) for k in keywords) else "N"
        else:
            keywords = [k.strip() for k in re.split(r" or |/", keyword_text) if k.strip()]
            keywords = ["USER_DEFINED_x" if k.startswith("USER_DE") else k for k in keywords]
            feature = item["requirement_text"].split(": keyword")[0]
            if feature.endswith(" or"):  # "TRUE_ANOMALY or" + keyword "MEAN_ANOMALY"
                keywords.insert(0, feature.split()[-2])
            read = "Y" if all(k in _read_keywords(kind) for k in keywords) else "N"
            written = _written_keywords(kind)
            write = "Y" if any(k in written for k in keywords) else "N"
        rows.append({"item": item["ID"], "message": kind,
                     "description": item["requirement_text"].split(": keyword")[0].removeprefix(f"{kind} "),
                     "keyword": keyword_text, "reference": table, "status": status, "read_validate": read,
                     "write": write})
    with open(ROOT / "ics_ccsds_502.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    unsupported = [r["item"] for r in rows if r["read_validate"] != "Y"]
    # COVARIANCE_START/_STOP are mandatory only inside the optional covariance block.
    missing_mandatory = [r["item"] for r in rows if r["status"] == "M" and r["write"] == "N"
                         and not r["keyword"].startswith("COVARIANCE_")]
    print(f"ics_ccsds_502.csv: {len(rows)} items; read/validate unsupported: {unsupported or 'none'}; "
          f"mandatory items not written: {missing_mandatory or 'none'}")
    return 1 if unsupported or missing_mandatory else 0


if __name__ == "__main__":
    sys.exit(build())
