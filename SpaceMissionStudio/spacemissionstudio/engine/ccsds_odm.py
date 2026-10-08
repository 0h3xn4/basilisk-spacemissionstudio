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

"""CCSDS Orbit Data Messages in KVN: OPM, OMM and OEM (CCSDS 502.0-B-3,
April 2023; remediation R09). Basilisk-free.

* :func:`read` parses a message and :func:`validate` checks it against
  the standard: keyword sets and order (tables 3-1 to 3-3, 4-1 to 4-3, 5-2
  to 5-4; 7.4.8), mandatory and all-or-none blocks, comment placement
  (7.8.7-7.8.9), line rules (7.3), value formats (7.5.4-7.5.10), units
  (7.7), and the OMM TLE conventions (4.2.4.6). A "shall"/"must" breach
  is an ``error``; a "should" (e.g. a REF_FRAME outside 3.2.3.3, to be
  documented in an ICD) is a ``warning``. Each issue names its clause.
* :func:`write_opm`, :func:`write_omm` and :func:`write_oem` produce
  messages that pass :func:`validate` with no errors (checked before
  returning).
* Conversions to and from the tool: :func:`opm_from_state`,
  :func:`state_from_opm`, :func:`omm_from_tle`, :func:`tle_from_omm`
  and :func:`oem_from_result`.

The OCM is out of scope (user decision 2026-10-08); XML is not
implemented yet (decision D6: KVN first).
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

VERSION = "3.0"
EARTH_GM_KM3_S2 = 398600.436  # [km^3/s^2] the GM the propagation uses: Basilisk 2.12 Earth, BODY399_GM of
# de-403-masses.tpc (not GGM03S's 398600.4415; deviation D-07; tests/test_ccsds_odm.py checks it)
MAX_LINE_LENGTH = 254  # [-] characters, 7.3.2
_TIME = re.compile(r"^\d{4}-(\d{2}-\d{2}|\d{3})T\d{2}:\d{2}:\d{2}(\.\d+)?Z?$")
_INTEGER = re.compile(r"^[+-]?\d+$")
_FIXED = re.compile(r"^[+-]?\d+\.\d+$")
_FLOAT = re.compile(r"^[+-]?\d\.\d+([eE][+-]?\d+)?$")
_KVN = re.compile(r"^\s*([^\s=]+)\s*=\s*(.*?)\s*$")
_UNITS = re.compile(r"^(.*?)\s+\[([^\]]*)\]$")

# 3.2.3.2 and 3.2.3.3 (recommended values; others need an ICD), 3.2.4.11.
TIME_SYSTEMS = ("GMST", "GPS", "MET", "MRT", "SCLK", "TAI", "TCB", "TDB", "TCG", "TT", "UT1", "UTC")
REF_FRAMES = ("EME2000", "GCRF", "GRC", "ICRF", "ITRF2000", "ITRF-93", "ITRF-97", "MCI", "TDR", "TEME", "TOD")
LOCAL_FRAMES = ("RSW", "RTN", "TNW")

_HEADER = ("COMMENT", "CLASSIFICATION", "CREATION_DATE", "ORIGINATOR", "MESSAGE_ID")
_COV = ("CX_X", "CY_X", "CY_Y", "CZ_X", "CZ_Y", "CZ_Z", "CX_DOT_X", "CX_DOT_Y", "CX_DOT_Z", "CX_DOT_X_DOT",
        "CY_DOT_X", "CY_DOT_Y", "CY_DOT_Z", "CY_DOT_X_DOT", "CY_DOT_Y_DOT", "CZ_DOT_X", "CZ_DOT_Y", "CZ_DOT_Z",
        "CZ_DOT_X_DOT", "CZ_DOT_Y_DOT", "CZ_DOT_Z_DOT")


def _cov_units(name: str) -> str:
    velocities = name[1:].count("DOT")
    return ("km**2", "km**2/s", "km**2/s**2")[velocities]


# (block, keyword, status, units); alternatives written "A|B". Status M/O/C.
_COV_BLOCK = [("covariance", "COV_REF_FRAME", "C", None)] + [("covariance", k, "C", _cov_units(k)) for k in _COV]
OPM_METADATA = [("metadata", "OBJECT_NAME", "M", None), ("metadata", "OBJECT_ID", "M", None),
                ("metadata", "CENTER_NAME", "M", None), ("metadata", "REF_FRAME", "M", None),
                ("metadata", "REF_FRAME_EPOCH", "C", None), ("metadata", "TIME_SYSTEM", "M", None)]
OPM_DATA = (
    [("state", "EPOCH", "M", None)] + [("state", k, "M", "km") for k in ("X", "Y", "Z")]
    + [("state", k, "M", "km/s") for k in ("X_DOT", "Y_DOT", "Z_DOT")]
    + [("kepler", "SEMI_MAJOR_AXIS", "C", "km"), ("kepler", "ECCENTRICITY", "C", None),
       ("kepler", "INCLINATION", "C", "deg"), ("kepler", "RA_OF_ASC_NODE", "C", "deg"),
       ("kepler", "ARG_OF_PERICENTER", "C", "deg"), ("kepler", "TRUE_ANOMALY|MEAN_ANOMALY", "C", "deg"),
       ("kepler", "GM", "C", "km**3/s**2")]
    + [("spacecraft", "MASS", "C", "kg"), ("spacecraft", "SOLAR_RAD_AREA", "O", "m**2"),
       ("spacecraft", "SOLAR_RAD_COEFF", "O", None), ("spacecraft", "DRAG_AREA", "O", "m**2"),
       ("spacecraft", "DRAG_COEFF", "O", None)]
    + _COV_BLOCK
    + [("maneuver", "MAN_EPOCH_IGNITION", "O", None), ("maneuver", "MAN_DURATION", "O", "s"),
       ("maneuver", "MAN_DELTA_MASS", "O", "kg"), ("maneuver", "MAN_REF_FRAME", "O", None),
       ("maneuver", "MAN_DV_1", "O", "km/s"), ("maneuver", "MAN_DV_2", "O", "km/s"),
       ("maneuver", "MAN_DV_3", "O", "km/s")]
)
OMM_METADATA = OPM_METADATA + [("metadata", "MEAN_ELEMENT_THEORY", "M", None)]
OMM_DATA = (
    [("mean", "EPOCH", "M", None), ("mean", "SEMI_MAJOR_AXIS|MEAN_MOTION", "M", "km|rev/day"),
     ("mean", "ECCENTRICITY", "M", None), ("mean", "INCLINATION", "M", "deg"),
     ("mean", "RA_OF_ASC_NODE", "M", "deg"), ("mean", "ARG_OF_PERICENTER", "M", "deg"),
     ("mean", "MEAN_ANOMALY", "M", "deg"), ("mean", "GM", "O", "km**3/s**2")]
    + [("spacecraft", "MASS", "O", "kg"), ("spacecraft", "SOLAR_RAD_AREA", "O", "m**2"),
       ("spacecraft", "SOLAR_RAD_COEFF", "O", None), ("spacecraft", "DRAG_AREA", "O", "m**2"),
       ("spacecraft", "DRAG_COEFF", "O", None)]
    + [("tle", "EPHEMERIS_TYPE", "O", None), ("tle", "CLASSIFICATION_TYPE", "O", None),
       ("tle", "NORAD_CAT_ID", "O", None), ("tle", "ELEMENT_SET_NO", "O", None),
       ("tle", "REV_AT_EPOCH", "O", None), ("tle", "BSTAR|BTERM", "C", "1/ER|m**2/kg"),
       ("tle", "MEAN_MOTION_DOT", "C", "rev/day**2"), ("tle", "MEAN_MOTION_DDOT|AGOM", "C", "rev/day**3|m**2/kg")]
    + _COV_BLOCK
)
OEM_METADATA = [("metadata", "OBJECT_NAME", "M", None), ("metadata", "OBJECT_ID", "M", None),
                ("metadata", "CENTER_NAME", "M", None), ("metadata", "REF_FRAME", "M", None),
                ("metadata", "REF_FRAME_EPOCH", "C", None), ("metadata", "TIME_SYSTEM", "M", None),
                ("metadata", "START_TIME", "M", None), ("metadata", "USEABLE_START_TIME", "O", None),
                ("metadata", "USEABLE_STOP_TIME", "O", None), ("metadata", "STOP_TIME", "M", None),
                ("metadata", "INTERPOLATION", "O", None), ("metadata", "INTERPOLATION_DEGREE", "C", None)]

# 7.5.3: normative text values, all uppercase or all lowercase.
_NORMATIVE = {"CENTER_NAME", "REF_FRAME", "TIME_SYSTEM", "COV_REF_FRAME", "MAN_REF_FRAME", "MEAN_ELEMENT_THEORY",
              "INTERPOLATION", "CLASSIFICATION_TYPE"}
_TIMES = {"CREATION_DATE", "REF_FRAME_EPOCH", "EPOCH", "MAN_EPOCH_IGNITION", "START_TIME", "USEABLE_START_TIME",
          "USEABLE_STOP_TIME", "STOP_TIME"}
_INTEGERS = {"EPHEMERIS_TYPE", "NORAD_CAT_ID", "ELEMENT_SET_NO", "REV_AT_EPOCH", "INTERPOLATION_DEGREE"}
_TEXT = {"OBJECT_NAME", "OBJECT_ID", "CLASSIFICATION", "ORIGINATOR", "MESSAGE_ID"} | _NORMATIVE


class OdmError(ValueError):
    """A message that cannot be read or does not conform; ``issues`` lists why."""

    def __init__(self, message: str, issues: Optional[List["Issue"]] = None):
        super().__init__(message)
        self.issues = issues or []


@dataclass(frozen=True)
class Issue:
    level: str  # "error" ("shall"/"must") or "warning" ("should")
    line: int  # [-] 1-based line number, 0 for the whole message
    clause: str  # CCSDS 502.0-B-3 clause or table
    message: str

    def __str__(self) -> str:
        where = f"line {self.line}: " if self.line else ""
        return f"{self.level}: {where}{self.message} (CCSDS 502.0-B-3 {self.clause})"


@dataclass
class Entry:
    keyword: str
    value: str
    units: Optional[str] = None
    line: int = 0


@dataclass
class OemSegment:
    metadata: List[Entry] = field(default_factory=list)
    comments: List[str] = field(default_factory=list)
    epochs: List[str] = field(default_factory=list)
    states: List[List[float]] = field(default_factory=list)  # [km, km/s, (km/s**2)] per line
    covariances: List[Dict[str, object]] = field(default_factory=list)  # epoch, frame, matrix (6x6)
    lines: List[int] = field(default_factory=list)

    def get(self, keyword: str, default: Optional[str] = None) -> Optional[str]:
        return next((e.value for e in self.metadata if e.keyword == keyword), default)


@dataclass
class OdmMessage:
    kind: str  # "OPM", "OMM" or "OEM"
    header: List[Entry] = field(default_factory=list)
    metadata: List[Entry] = field(default_factory=list)  # OPM/OMM
    data: List[Entry] = field(default_factory=list)  # OPM/OMM, comments included as COMMENT entries
    segments: List[OemSegment] = field(default_factory=list)  # OEM

    def get(self, keyword: str, default: Optional[str] = None) -> Optional[str]:
        for entry in self.header + self.metadata + self.data:
            if entry.keyword == keyword:
                return entry.value
        return default

    def number(self, keyword: str) -> Optional[float]:
        value = self.get(keyword)
        return None if value is None else float(value)


# --- Reading -------------------------------------------------------------------------------------------


def _split_units(value: str) -> Tuple[str, Optional[str]]:
    match = _UNITS.match(value)
    return (match.group(1).strip(), match.group(2)) if match else (value, None)


def _kind(text: str) -> str:
    for line in text.splitlines():
        if line.strip():
            match = _KVN.match(line)
            if match and match.group(1) in ("CCSDS_OPM_VERS", "CCSDS_OMM_VERS", "CCSDS_OEM_VERS"):
                return match.group(1)[6:9]
            raise OdmError("the first non-blank line must be CCSDS_OPM_VERS, CCSDS_OMM_VERS or CCSDS_OEM_VERS "
                           "(CCSDS 502.0-B-3 7.3.6, 7.9.1)")
    raise OdmError("empty message")


def read(text: str) -> OdmMessage:
    """Parse a KVN OPM, OMM or OEM (structure only; see :func:`validate`)."""
    kind = _kind(text)
    message = OdmMessage(kind=kind)
    header_keys = {f"CCSDS_{kind}_VERS", *_HEADER}
    lines = text.splitlines()
    if kind != "OEM":
        meta_keys = {k for _b, ks, _s, _u in (OPM_METADATA if kind == "OPM" else OMM_METADATA) for k in ks.split("|")}
        section = "header"
        pending: List[Entry] = []  # comments belong to the section of the keyword after them
        targets = {"header": message.header, "metadata": message.metadata, "data": message.data}
        for number, raw in enumerate(lines, 1):
            if not raw.strip():
                continue
            entry = _entry(raw, number)
            if entry.keyword == "COMMENT":
                if section == "header" and targets["header"] and targets["header"][-1].keyword in (
                        f"CCSDS_{kind}_VERS", "COMMENT") and not pending:
                    targets["header"].append(entry)  # 7.8.7: immediately after the version keyword
                else:
                    pending.append(entry)
                continue
            if section == "header" and entry.keyword not in header_keys:
                section = "metadata"
            if section == "metadata" and entry.keyword not in meta_keys:
                section = "data"
            targets[section].extend(pending + [entry])
            pending = []
        targets[section].extend(pending)
        return message
    segment: Optional[OemSegment] = None
    state = "header"
    covariance: Optional[Dict[str, object]] = None
    for number, raw in enumerate(lines, 1):
        stripped = raw.strip()
        if not stripped:
            continue
        if stripped == "META_START":
            segment = OemSegment()
            message.segments.append(segment)
            state = "metadata"
            continue
        if stripped == "META_STOP":
            state = "data"
            continue
        if stripped == "COVARIANCE_START":
            state = "covariance"
            continue
        if stripped == "COVARIANCE_STOP":
            state = "after_covariance"
            covariance = None
            continue
        if state == "header":
            message.header.append(_entry(raw, number))
        elif state == "metadata":
            segment.metadata.append(_entry(raw, number))
        elif state == "data":
            if stripped.startswith("COMMENT"):
                segment.comments.append(stripped[7:].strip())
                segment.lines.append(-number)
                continue
            fields = stripped.split()
            segment.epochs.append(fields[0])
            try:
                segment.states.append([float(v) for v in fields[1:]])
            except ValueError as exc:
                raise OdmError(f"line {number}: ephemeris data line has a non-numeric value ({exc})") from exc
            segment.lines.append(number)
        elif state == "covariance":
            if stripped.startswith("COMMENT"):
                continue
            match = _KVN.match(raw)
            if match and match.group(1) in ("EPOCH", "COV_REF_FRAME"):
                if match.group(1) == "EPOCH":
                    covariance = {"epoch": match.group(2), "frame": None, "rows": [], "line": number}
                    segment.covariances.append(covariance)
                else:
                    covariance["frame"] = match.group(2)
                continue
            if covariance is None:
                raise OdmError(f"line {number}: covariance data before its EPOCH (CCSDS 502.0-B-3 5.2.5.3)")
            covariance["rows"].append([float(v) for v in stripped.split()])
        else:
            raise OdmError(f"line {number}: data after COVARIANCE_STOP outside a new META_START block")
    return message


def _entry(raw: str, number: int) -> Entry:
    stripped = raw.strip()
    if stripped.startswith("COMMENT") and (len(stripped) == 7 or stripped[7] == " "):
        return Entry("COMMENT", raw.split("COMMENT", 1)[1][1:].rstrip(), None, number)
    match = _KVN.match(raw)
    if not match:
        raise OdmError(f"line {number}: expected 'KEYWORD = value' (CCSDS 502.0-B-3 7.4.1)")
    value, units = _split_units(match.group(2))
    return Entry(match.group(1), value, units, number)


# --- Validation ----------------------------------------------------------------------------------------


def _is_number(value: str) -> bool:
    return bool(_INTEGER.match(value) or _FIXED.match(value) or _FLOAT.match(value))


def _digits(value: str) -> int:
    mantissa = re.split("[eE]", value)[0]
    return sum(c.isdigit() for c in mantissa)


def _check_value(entry: Entry, units: Optional[str], issues: List[Issue]) -> None:
    keyword, value = entry.keyword, entry.value
    if not value:
        issues.append(Issue("error", entry.line, "7.5.1", f"{keyword} has an empty value"))
        return
    if keyword in _TIMES:
        if not _TIME.match(value):
            issues.append(Issue("error", entry.line, "7.5.10", f"{keyword} = {value!r} is not "
                                "YYYY-MM-DDThh:mm:ss[.d][Z] or YYYY-DDDThh:mm:ss[.d][Z]"))
    elif keyword in _INTEGERS:
        if not _INTEGER.match(value) or not -2 ** 31 <= int(value) <= 2 ** 31 - 1:
            issues.append(Issue("error", entry.line, "7.5.4", f"{keyword} = {value!r} is not an integer"))
    elif keyword in _TEXT or keyword.startswith("USER_DEFINED_"):
        if keyword in _NORMATIVE and value != value.upper() and value != value.lower():
            issues.append(Issue("error", entry.line, "7.5.3", f"{keyword} = {value!r} mixes upper and lower case"))
    elif not _is_number(value):
        issues.append(Issue("error", entry.line, "7.5.5-7.5.7", f"{keyword} = {value!r} is not a number in fixed- or "
                            "floating-point notation"))
    elif _digits(value) > 16:
        issues.append(Issue("error", entry.line, "7.5.6-7.5.7", f"{keyword} = {value!r} has more than 16 digits"))
    if entry.units is not None:
        if entry.units == "n/a":
            issues.append(Issue("error", entry.line, "7.7.1.3", f"{keyword}: '[n/a]' must not appear"))
        elif units is None or entry.units not in units.split("|"):
            issues.append(Issue("error", entry.line, "7.7.1.1", f"{keyword}: units [{entry.units}] do not match "
                                f"the table ({units or 'none'})"))


def _check_lines(text: str, issues: List[Issue]) -> None:
    for number, line in enumerate(text.splitlines(), 1):
        if len(line) > MAX_LINE_LENGTH:
            issues.append(Issue("error", number, "7.3.2", f"line has {len(line)} characters (max {MAX_LINE_LENGTH})"))
        if any(not (c.isprintable() and ord(c) < 128) for c in line):
            issues.append(Issue("error", number, "7.3.4", "line contains a non-printable or non-ASCII character"))


def _check_header(message: OdmMessage, issues: List[Issue]) -> None:
    table = f"Table {dict(OPM='3-1', OMM='4-1', OEM='5-2')[message.kind]}"
    order = [f"CCSDS_{message.kind}_VERS", *_HEADER]
    seen = [e.keyword for e in message.header]
    for keyword in (f"CCSDS_{message.kind}_VERS", "CREATION_DATE", "ORIGINATOR"):
        if keyword not in seen:
            issues.append(Issue("error", 0, table, f"mandatory header keyword {keyword} is missing"))
    last = -1
    for entry in message.header:
        if entry.keyword not in order:
            issues.append(Issue("error", entry.line, f"{table}, 7.9.2", f"{entry.keyword} is not a header keyword"))
            continue
        position = order.index(entry.keyword)
        if entry.keyword == "COMMENT" and last not in (0, 1):
            issues.append(Issue("error", entry.line, "7.8.7-7.8.9", "header comments are allowed only immediately "
                                "after the version keyword"))
        elif position < last:
            issues.append(Issue("error", entry.line, "7.4.8", f"{entry.keyword} is out of the order of {table}"))
        last = max(last, position)
        if entry.keyword == f"CCSDS_{message.kind}_VERS":
            if not re.match(r"^\d+\.\d+$", entry.value):
                issues.append(Issue("error", entry.line, "7.9.1", f"version {entry.value!r} is not 'x.y'"))
        elif entry.keyword != "COMMENT":
            _check_value(entry, None, issues)


def _check_keyword_table(entries: List[Entry], table: list, table_name: str, issues: List[Issue],
                         comment_clause: str, repeat_block: Optional[str] = None) -> Dict[str, List[Entry]]:
    """Order, allowed keywords, comment placement and values for one
    section; returns the entries by block."""
    order = []  # (block, keyword, status, units)
    for block, keywords, status, units in table:
        for index, keyword in enumerate(keywords.split("|")):
            unit = units.split("|")[index] if units and "|" in units else units
            order.append((block, keyword, status, unit))
    by_block: Dict[str, List[Entry]] = {}
    last_position, last_block = -1, None
    pending_comment: Optional[Entry] = None
    for entry in entries:
        if entry.keyword == "COMMENT":
            pending_comment = pending_comment or entry
            continue
        if entry.keyword.startswith("USER_DEFINED_"):
            block, position, units = "user", len(order), None
        else:
            matches = [i for i, row in enumerate(order) if row[1] == entry.keyword]
            if not matches:
                issues.append(Issue("error", entry.line, f"{table_name}, 7.9.2",
                                    f"{entry.keyword} is not a keyword of {table_name}"))
                continue
            position = matches[0]
            block, units = order[position][0], order[position][3]
            if repeat_block and block == repeat_block and last_block == repeat_block \
                    and entry.keyword == order[next(i for i, r in enumerate(order) if r[0] == repeat_block)][1]:
                last_position, last_block = position - 1, None  # a new maneuver: a new logical block (3.2.4.8)
        if position < last_position:
            issues.append(Issue("error", entry.line, "7.4.8", f"{entry.keyword} is out of the order of {table_name}"))
        if pending_comment is not None and block == last_block:
            issues.append(Issue("error", pending_comment.line, comment_clause,
                                "comments are allowed only at the beginning of a logical block"))
        pending_comment = None
        last_position, last_block = max(last_position, position), block
        by_block.setdefault(block, []).append(entry)
        _check_value(entry, units, issues)
    if pending_comment is not None:
        issues.append(Issue("error", pending_comment.line, comment_clause, "a comment must precede a logical block"))
    return by_block


def _keys(entries: List[Entry]) -> List[str]:
    return [e.keyword for e in entries]


def _require(entries: List[Entry], keywords: Sequence[str], clause: str, issues: List[Issue], what: str) -> None:
    present = _keys(entries)
    for keyword in keywords:
        options = keyword.split("|")
        if not any(option in present for option in options):
            issues.append(Issue("error", 0, clause, f"{what}: mandatory {' or '.join(options)} is missing"))


def text_value(value: Optional[str]) -> str:
    """A text value as compared (7.5.9: underscore = blank, runs of blanks
    = one blank), upper case."""
    return re.sub(" +", " ", (value or "").replace("_", " ")).strip().upper()


def _check_frames(metadata: List[Entry], kind: str, issues: List[Issue]) -> None:
    values = {e.keyword: e for e in metadata}
    frame, time_system = values.get("REF_FRAME"), values.get("TIME_SYSTEM")
    if time_system is not None and text_value(time_system.value) not in TIME_SYSTEMS:
        issues.append(Issue("warning", time_system.line, "3.2.3.2", f"TIME_SYSTEM {time_system.value} is not in the "
                            "recommended set: document it in an ICD"))
    if frame is not None:
        if text_value(frame.value) not in {text_value(f) for f in REF_FRAMES}:
            issues.append(Issue("warning", frame.line, "3.2.3.3", f"REF_FRAME {frame.value} is not in the "
                                "recommended set: document it in an ICD"))
        elif text_value(frame.value) == "TEME" and kind != "OMM":
            issues.append(Issue("warning", frame.line, "3.2.3.3, 4.2.4.9", "TEME is meant only for TLE-based OMMs"))


def _all_or_none(entries: List[Entry], keywords: Sequence[str], clause: str, issues: List[Issue], what: str) -> None:
    present = [k for k in keywords if any(option in _keys(entries) for option in k.split("|"))]
    if present and len(present) != len(keywords):
        missing = [k for k in keywords if k not in present]
        issues.append(Issue("error", 0, clause, f"{what}: all or none must be given; missing {', '.join(missing)}"))


def _check_opm_omm(message: OdmMessage, issues: List[Issue]) -> None:
    opm = message.kind == "OPM"
    meta_table, data_table = (OPM_METADATA, OPM_DATA) if opm else (OMM_METADATA, OMM_DATA)
    names = ("Table 3-2", "Table 3-3") if opm else ("Table 4-2", "Table 4-3")
    comment = "7.8.7" if opm else "7.8.8"
    _check_keyword_table(message.metadata, meta_table, names[0], issues, comment)
    _require(message.metadata, [k for _b, k, s, _u in meta_table if s == "M"], names[0], issues, "metadata")
    _check_frames(message.metadata, message.kind, issues)
    blocks = _check_keyword_table(message.data, data_table, names[1], issues, comment,
                                  repeat_block="maneuver" if opm else None)
    if opm:
        _require(blocks.get("state", []), ["EPOCH", "X", "Y", "Z", "X_DOT", "Y_DOT", "Z_DOT"], "Table 3-3", issues,
                 "state vector")
        _all_or_none(blocks.get("kepler", []), ["SEMI_MAJOR_AXIS", "ECCENTRICITY", "INCLINATION", "RA_OF_ASC_NODE",
                     "ARG_OF_PERICENTER", "TRUE_ANOMALY|MEAN_ANOMALY", "GM"], "3.1.2, Table 3-3", issues,
                     "osculating Keplerian elements")
        maneuvers = blocks.get("maneuver", [])
        if maneuvers:
            if "MASS" not in _keys(blocks.get("spacecraft", [])):
                issues.append(Issue("error", 0, "3.2.4.9", "a maneuver is given, so MASS must be provided"))
            per = ["MAN_EPOCH_IGNITION", "MAN_DURATION", "MAN_DELTA_MASS", "MAN_REF_FRAME",
                   "MAN_DV_1", "MAN_DV_2", "MAN_DV_3"]
            if len(maneuvers) % len(per) or _keys(maneuvers) != per * (len(maneuvers) // len(per)):
                issues.append(Issue("error", maneuvers[0].line, "3.2.4.8", "each maneuver must repeat all "
                                    "maneuver parameters in the order of Table 3-3"))
            for entry in maneuvers:
                if entry.keyword == "MAN_DELTA_MASS" and _is_number(entry.value) and float(entry.value) >= 0.0:
                    issues.append(Issue("error", entry.line, "3.2.4.7", "MAN_DELTA_MASS must be negative"))
    else:
        _require(blocks.get("mean", []), [k for _b, k, s, _u in OMM_DATA if _b == "mean" and s == "M"],
                 "Table 4-3", issues, "mean elements")
        theory = text_value(message.get("MEAN_ELEMENT_THEORY"))
        if theory in ("SGP", "SGP4", "SGP/SGP4"):
            for keyword, required in (("CENTER_NAME", "EARTH"), ("REF_FRAME", "TEME"), ("TIME_SYSTEM", "UTC")):
                if text_value(message.get(keyword)) != required:
                    issues.append(Issue("error", 0, "4.2.4.6", f"a TLE-based OMM needs {keyword} = {required}"))
            if "MEAN_MOTION" not in _keys(blocks.get("mean", [])):
                issues.append(Issue("error", 0, "4.2.4.6", "a TLE-based OMM must use MEAN_MOTION"))
            if "BSTAR" not in _keys(blocks.get("tle", [])) and "SGP4" in theory:
                issues.append(Issue("error", 0, "Table 4-3", "BSTAR is required for SGP4"))
        if theory in ("SGP", "PPT3", "SGP/SGP4") and "MEAN_MOTION_DOT" not in _keys(blocks.get("tle", [])):
            issues.append(Issue("error", 0, "Table 4-3", "MEAN_MOTION_DOT is required for SGP and PPT3"))
    covariance = blocks.get("covariance", [])
    _all_or_none([e for e in covariance if e.keyword != "COV_REF_FRAME"], list(_COV), "3.2.4.10 / 4.2.4.5", issues,
                 "covariance matrix")


def _check_oem(message: OdmMessage, text: str, issues: List[Issue]) -> None:
    if not message.segments:
        issues.append(Issue("error", 0, "Table 5-1", "an OEM needs at least one metadata and ephemeris data block"))
        return
    time_systems = set()
    previous_useable_stop = None
    for segment in message.segments:
        _check_keyword_table(segment.metadata, OEM_METADATA, "Table 5-3", issues, "7.8.9")
        _require(segment.metadata, [k for _b, k, s, _u in OEM_METADATA if s == "M"], "Table 5-3", issues, "metadata")
        _check_frames(segment.metadata, "OEM", issues)
        if segment.get("INTERPOLATION") is not None and segment.get("INTERPOLATION_DEGREE") is None:
            issues.append(Issue("error", 0, "Table 5-3", "INTERPOLATION_DEGREE must be given with INTERPOLATION"))
        degree = segment.get("INTERPOLATION_DEGREE")
        if degree is not None and _INTEGER.match(degree):
            method = text_value(segment.get("INTERPOLATION"))
            needed = (int(degree) + 2) // 2 if method == "HERMITE" else int(degree) + 1  # [-] nodes
            if len(segment.states) < needed:
                issues.append(Issue("error", 0, "5.2.4.7", f"{len(segment.states)} ephemeris record(s) are too few "
                                    f"for {method or 'the'} interpolation of degree {degree} ({needed} needed)"))
        time_systems.add(text_value(segment.get("TIME_SYSTEM")))
        if not segment.states:
            issues.append(Issue("error", 0, "Table 5-1", "a metadata block must be followed by ephemeris data"))
        seen_data = False
        for number in segment.lines:
            if number < 0 and seen_data:
                issues.append(Issue("error", -number, "7.8.9", "comments must not appear within ephemeris lines"))
            seen_data = seen_data or number > 0
        for epoch, state, number in zip(segment.epochs, segment.states, [n for n in segment.lines if n > 0]):
            if not _TIME.match(epoch):
                issues.append(Issue("error", number, "5.2.4.1, 7.5.10", f"epoch {epoch!r} is not a valid time"))
            raw_values = text.splitlines()[number - 1].split()[1:]
            if not all(_is_number(v) for v in raw_values):
                issues.append(Issue("error", number, "7.5.5-7.5.7", "an ephemeris value is not a valid number"))
            if len(state) not in (6, 9):
                issues.append(Issue("error", number, "5.2.4.1-5.2.4.2", "an ephemeris line needs an epoch and 6 "
                                    f"(or 9 with accelerations) values, found {len(state)}"))
        start, stop = segment.get("START_TIME"), segment.get("STOP_TIME")
        try:
            epochs = [_parse_time(e) for e in segment.epochs]
            if start and stop and epochs and (min(epochs) < _parse_time(start) or max(epochs) > _parse_time(stop)):
                issues.append(Issue("error", 0, "Table 5-3", "ephemeris data lie outside START_TIME..STOP_TIME"))
            if any(b < a for a, b in zip(epochs, epochs[1:])):
                issues.append(Issue("error", 0, "5.2.4", "ephemeris epochs must increase"))
            useable_start = segment.get("USEABLE_START_TIME") or start
            if previous_useable_stop is not None and useable_start is not None \
                    and _parse_time(useable_start) < previous_useable_stop:
                issues.append(Issue("error", 0, "5.2.4.4", "useable spans of consecutive blocks must not overlap"))
            useable_stop = segment.get("USEABLE_STOP_TIME") or stop
            previous_useable_stop = _parse_time(useable_stop) if useable_stop else None
            covariance_epochs = [_parse_time(c["epoch"]) for c in segment.covariances]
            if any(b < a for a, b in zip(covariance_epochs, covariance_epochs[1:])):
                issues.append(Issue("error", 0, "5.2.5.7", "covariance matrices must be ordered by increasing time"))
        except ValueError:
            pass  # the time format issues are reported above
        for covariance in segment.covariances:
            rows = covariance["rows"]
            if [len(r) for r in rows] != [1, 2, 3, 4, 5, 6]:
                issues.append(Issue("error", covariance["line"], "5.2.5.4", "a covariance matrix needs six lower-"
                                    "triangular rows of 1 to 6 values"))
    if len(time_systems) > 1:
        issues.append(Issue("error", 0, "5.2.4.5", "the TIME_SYSTEM must remain fixed within an OEM"))
    objects = {(text_value(s.get("OBJECT_NAME")), text_value(s.get("OBJECT_ID"))) for s in message.segments}
    if len(objects) > 1:
        issues.append(Issue("error", 0, "5.1.3", "an OEM holds orbit data for a single object"))


def validate(text: str) -> List[Issue]:
    """All conformance issues of a KVN message (empty when it conforms)."""
    issues: List[Issue] = []
    try:
        message = read(text)
    except OdmError as exc:
        return [Issue("error", 0, "7", str(exc))]
    _check_lines(text, issues)
    _check_header(message, issues)
    if message.kind == "OEM":
        _check_oem(message, text, issues)
    else:
        _check_opm_omm(message, issues)
    return sorted(issues, key=lambda issue: (issue.level != "error", issue.line))


def read_checked(text: str) -> Tuple[OdmMessage, List[Issue]]:
    """Parse and validate; raises :class:`OdmError` when there are errors."""
    issues = validate(text)
    errors = [i for i in issues if i.level == "error"]
    if errors:
        raise OdmError(f"{len(errors)} conformance error(s): " + "; ".join(str(e) for e in errors[:5]), issues)
    return read(text), issues


# --- Time strings --------------------------------------------------------------------------------------


def _parse_time(value: str) -> datetime:
    """A 7.5.10 time string as a naive datetime (seconds = 60 folded into
    the next minute)."""
    value = value.rstrip("Z")
    date, clock = value.split("T")
    if len(date) == 8:  # YYYY-DDD
        base = datetime.strptime(date, "%Y-%j")
    else:
        base = datetime.strptime(date, "%Y-%m-%d")
    hours, minutes, seconds = clock.split(":")
    return base + timedelta(hours=int(hours), minutes=int(minutes), seconds=float(seconds))


def format_time(moment: datetime) -> str:
    """``YYYY-MM-DDThh:mm:ss.ffffff`` (7.5.10)."""
    return moment.strftime("%Y-%m-%dT%H:%M:%S.%f")


def _number(value: float) -> str:
    """The shortest text that reads back as ``value`` and conforms to 7.5.6
    (fixed point, <= 16 digits) or 7.5.7 (d.ddd[E+-x])."""
    if not math.isfinite(value):
        raise OdmError(f"{value} cannot be written in an ODM (7.5.5)")
    text = repr(float(value))
    if "e" in text:
        mantissa, exponent = text.split("e")
        text = f"{mantissa if '.' in mantissa else mantissa + '.0'}e{exponent}"
    if not (_FIXED.match(text) or _FLOAT.match(text)) or _digits(text) > 16:
        text = f"{value:.15e}"
    return text


# --- Writing -------------------------------------------------------------------------------------------


def _line(keyword: str, value: str, units: Optional[str] = None) -> str:
    return f"{keyword:<20s} = {value}" + (f" [{units}]" if units else "")


def _header(kind: str, originator: str, creation: Optional[datetime], comments: Sequence[str],
            message_id: Optional[str]) -> List[str]:
    lines = [_line(f"CCSDS_{kind}_VERS", VERSION)]
    lines += [f"COMMENT {c}" for c in comments]
    lines.append(_line("CREATION_DATE", format_time(creation or datetime.utcnow().replace(microsecond=0))))
    lines.append(_line("ORIGINATOR", originator))
    if message_id:
        lines.append(_line("MESSAGE_ID", message_id))
    return lines


def _finish(text: str) -> str:
    errors = [i for i in validate(text) if i.level == "error"]
    if errors:
        raise OdmError("generated message does not conform: " + "; ".join(map(str, errors)), errors)
    return text


def write_opm(*, object_name: str, object_id: str, center_name: str, ref_frame: str, time_system: str,
              epoch: datetime, r_km: Sequence[float], v_km_s: Sequence[float], gm_km3_s2: Optional[float] = None,
              mass_kg: Optional[float] = None, srp_area_m2: Optional[float] = None,
              srp_coeff: Optional[float] = None, drag_area_m2: Optional[float] = None,
              drag_coeff: Optional[float] = None, originator: str = "SPACEMISSIONSTUDIO",
              comments: Sequence[str] = (), creation: Optional[datetime] = None) -> str:
    """An OPM with a state vector, osculating elements (when ``gm_km3_s2``
    is given) and spacecraft parameters."""
    lines = _header("OPM", originator, creation, comments, None)
    lines += ["", _line("OBJECT_NAME", object_name), _line("OBJECT_ID", object_id),
              _line("CENTER_NAME", center_name.upper()), _line("REF_FRAME", ref_frame), _line("TIME_SYSTEM", time_system),
              "", _line("EPOCH", format_time(epoch))]
    lines += [_line(k, _number(float(v)), "km") for k, v in zip(("X", "Y", "Z"), r_km)]
    lines += [_line(k, _number(float(v)), "km/s") for k, v in zip(("X_DOT", "Y_DOT", "Z_DOT"), v_km_s)]
    if gm_km3_s2 is not None:
        a, e, i, raan, argp, nu = _elements(np.asarray(r_km, float), np.asarray(v_km_s, float), gm_km3_s2)
        lines += ["", "COMMENT Osculating Keplerian elements", _line("SEMI_MAJOR_AXIS", _number(a), "km"),
                  _line("ECCENTRICITY", _number(e)), _line("INCLINATION", _number(i), "deg"),
                  _line("RA_OF_ASC_NODE", _number(raan), "deg"), _line("ARG_OF_PERICENTER", _number(argp), "deg"),
                  _line("TRUE_ANOMALY", _number(nu), "deg"), _line("GM", _number(gm_km3_s2), "km**3/s**2")]
    params = [("MASS", mass_kg, "kg"), ("SOLAR_RAD_AREA", srp_area_m2, "m**2"), ("SOLAR_RAD_COEFF", srp_coeff, None),
              ("DRAG_AREA", drag_area_m2, "m**2"), ("DRAG_COEFF", drag_coeff, None)]
    if any(value is not None for _k, value, _u in params):
        lines.append("")
        lines += [_line(k, _number(float(value)), u) for k, value, u in params if value is not None]
    return _finish("\n".join(lines) + "\n")


def _elements(r, v, mu):
    """Osculating a [km], e, i, RAAN, argp, true anomaly [deg]."""
    h = np.cross(r, v)
    n = np.cross([0.0, 0.0, 1.0], h)
    rn, vn = np.linalg.norm(r), np.linalg.norm(v)
    e_vec = ((vn ** 2 - mu / rn) * r - np.dot(r, v) * v) / mu
    e = np.linalg.norm(e_vec)
    a = 1.0 / (2.0 / rn - vn ** 2 / mu)
    i = math.degrees(math.acos(h[2] / np.linalg.norm(h)))
    nn = np.linalg.norm(n)
    raan = math.degrees(math.atan2(n[1], n[0])) % 360.0 if nn > 1e-12 else 0.0
    if e > 1e-12 and nn > 1e-12:
        argp = math.degrees(math.acos(np.clip(np.dot(n, e_vec) / (nn * e), -1, 1)))
        argp = 360.0 - argp if e_vec[2] < 0 else argp
        nu = math.degrees(math.acos(np.clip(np.dot(e_vec, r) / (e * rn), -1, 1)))
    else:  # circular or equatorial: argument of latitude / true longitude in nu
        argp = 0.0
        ref = n / nn if nn > 1e-12 else np.array([1.0, 0.0, 0.0])
        nu = math.degrees(math.acos(np.clip(np.dot(ref, r) / rn, -1, 1)))
    nu = 360.0 - nu if np.dot(r, v) < 0 else nu
    return a, e, i, raan, argp, nu


def write_omm(*, object_name: str, object_id: str, epoch: datetime, mean_motion_rev_day: float, eccentricity: float,
              inclination_deg: float, raan_deg: float, arg_pericenter_deg: float, mean_anomaly_deg: float,
              norad_cat_id: int, bstar: float, mean_motion_dot: float, mean_motion_ddot: float,
              element_set_no: int = 999, rev_at_epoch: int = 0, classification: str = "U",
              originator: str = "SPACEMISSIONSTUDIO", comments: Sequence[str] = (),
              creation: Optional[datetime] = None) -> str:
    """A TLE-based OMM (4.2.4.6: EARTH, TEME, UTC, MEAN_MOTION, SGP4)."""
    lines = _header("OMM", originator, creation, comments, None)
    lines += ["", _line("OBJECT_NAME", object_name), _line("OBJECT_ID", object_id), _line("CENTER_NAME", "EARTH"),
              _line("REF_FRAME", "TEME"), _line("TIME_SYSTEM", "UTC"), _line("MEAN_ELEMENT_THEORY", "SGP4"), "",
              _line("EPOCH", format_time(epoch)), _line("MEAN_MOTION", _number(mean_motion_rev_day), "rev/day"),
              _line("ECCENTRICITY", _number(eccentricity)), _line("INCLINATION", _number(inclination_deg), "deg"),
              _line("RA_OF_ASC_NODE", _number(raan_deg), "deg"),
              _line("ARG_OF_PERICENTER", _number(arg_pericenter_deg), "deg"),
              _line("MEAN_ANOMALY", _number(mean_anomaly_deg), "deg"), "",
              _line("EPHEMERIS_TYPE", "0"), _line("CLASSIFICATION_TYPE", classification),
              _line("NORAD_CAT_ID", str(int(norad_cat_id))), _line("ELEMENT_SET_NO", str(int(element_set_no))),
              _line("REV_AT_EPOCH", str(int(rev_at_epoch))), _line("BSTAR", _number(bstar), "1/ER"),
              _line("MEAN_MOTION_DOT", _number(mean_motion_dot), "rev/day**2"),
              _line("MEAN_MOTION_DDOT", _number(mean_motion_ddot), "rev/day**3")]
    return _finish("\n".join(lines) + "\n")


def write_oem(segments: Sequence[Dict[str, object]], *, originator: str = "SPACEMISSIONSTUDIO",
              comments: Sequence[str] = (), creation: Optional[datetime] = None) -> str:
    """An OEM. Each segment: ``object_name``, ``object_id``, ``center_name``,
    ``ref_frame``, ``time_system``, ``epochs`` (datetimes), ``r_km`` (N x 3),
    ``v_km_s`` (N x 3), optional ``comments``, ``interpolation``,
    ``interpolation_degree``."""
    lines = _header("OEM", originator, creation, comments, None)
    for segment in segments:
        epochs = list(segment["epochs"])
        lines += ["", "META_START", _line("OBJECT_NAME", str(segment["object_name"])),
                  _line("OBJECT_ID", str(segment["object_id"])),
                  _line("CENTER_NAME", str(segment["center_name"]).upper()),
                  _line("REF_FRAME", str(segment["ref_frame"])), _line("TIME_SYSTEM", str(segment["time_system"])),
                  _line("START_TIME", format_time(epochs[0])), _line("STOP_TIME", format_time(epochs[-1]))]
        hermite_nodes = (int(segment.get("interpolation_degree") or 0) + 2) // 2
        if segment.get("interpolation") and len(epochs) >= hermite_nodes:
            lines += [_line("INTERPOLATION", str(segment["interpolation"])),
                      _line("INTERPOLATION_DEGREE", str(int(segment["interpolation_degree"])))]
        lines += ["META_STOP", ""]
        lines += [f"COMMENT {c}" for c in segment.get("comments", ())]
        for epoch, r, v in zip(epochs, np.asarray(segment["r_km"]), np.asarray(segment["v_km_s"])):
            # Fixed point (7.5.6): 1 mm and 1 um/s resolution.
            lines.append(" ".join([format_time(epoch)] + [f"{float(x):.6f}" for x in r] + [f"{float(x):.9f}" for x in v]))
    return _finish("\n".join(lines) + "\n")


# --- Conversions with the tool -------------------------------------------------------------------------

# The tool's inertial frame is EME2000 (SPICE J2000; decision D7). SPICE
# treats ICRF/GCRF as the same frame (difference ~23 mas, ~0.8 m in LEO).
_TOOL_COMPATIBLE_FRAMES = ("EME2000", "ICRF", "GCRF")
_TIME_SCALES = ("UTC", "TAI", "TT", "TDB")


def _to_utc(moment: datetime, time_system: str) -> datetime:
    """An epoch in UTC, TAI, TT or TDB expressed in UTC."""
    from . import time_system as ts

    scale = time_system.upper()
    if scale == "UTC":
        return moment
    if scale not in _TIME_SCALES:
        raise OdmError(f"TIME_SYSTEM {time_system} cannot be converted (supported: {', '.join(_TIME_SCALES)})")
    offset = {"TAI": 0.0, "TT": ts.TT_MINUS_TAI_S}.get(scale)
    guess = moment
    for _ in range(3):  # fixed point: UTC -> scale offset depends weakly on the date
        if scale == "TDB":
            delta = (ts.tdb_seconds_past_j2000(guess) - (guess - datetime(2000, 1, 1, 12)).total_seconds())
        else:
            delta = ts.tai_minus_utc_s(guess) + offset
        guess = moment - timedelta(seconds=delta)
    return guess


def state_from_opm(message: OdmMessage) -> Tuple[datetime, np.ndarray, np.ndarray, List[str]]:
    """(UTC epoch, r [m], v [m/s], notes) of an OPM in a frame the tool
    uses directly (EME2000/ICRF/GCRF)."""
    if message.kind != "OPM":
        raise OdmError(f"expected an OPM, got an {message.kind}")
    frame = text_value(message.get("REF_FRAME"))
    if frame not in _TOOL_COMPATIBLE_FRAMES:
        raise OdmError(f"REF_FRAME {frame} is not supported for import (supported: "
                       f"{', '.join(_TOOL_COMPATIBLE_FRAMES)})")
    notes = []
    if frame != "EME2000":
        notes.append(f"{frame} taken as EME2000 (SPICE J2000): the frames differ by ~23 mas")
    epoch = _to_utc(_parse_time(message.get("EPOCH")), message.get("TIME_SYSTEM") or "")
    r = np.array([message.number(k) for k in ("X", "Y", "Z")]) * 1e3  # [m]
    v = np.array([message.number(k) for k in ("X_DOT", "Y_DOT", "Z_DOT")]) * 1e3  # [m/s]
    return epoch, r, v, notes


def tle_from_omm(message: OdmMessage) -> Tuple[str, str]:
    """TLE lines of a TLE-based OMM (4.1.2), via the sgp4 package."""
    from sgp4.api import WGS72, Satrec
    from sgp4.exporter import export_tle

    if message.kind != "OMM":
        raise OdmError(f"expected an OMM, got an {message.kind}")
    if text_value(message.get("MEAN_ELEMENT_THEORY")) not in ("SGP4", "SGP/SGP4", "SGP"):
        raise OdmError(f"MEAN_ELEMENT_THEORY {message.get('MEAN_ELEMENT_THEORY')} cannot be converted to a TLE")
    epoch = _parse_time(message.get("EPOCH"))
    days_1949 = (epoch - datetime(1949, 12, 31)).total_seconds() / 86400.0  # [day] sgp4init epoch convention
    satrec = Satrec()
    satrec.sgp4init(WGS72, "i", int(message.get("NORAD_CAT_ID") or 0), days_1949,
                    float(message.get("BSTAR") or 0.0),
                    float(message.get("MEAN_MOTION_DOT") or 0.0) * 2.0 * math.pi / 1440.0 ** 2,  # [rad/min^2]
                    float(message.get("MEAN_MOTION_DDOT") or 0.0) * 2.0 * math.pi / 1440.0 ** 3,  # [rad/min^3]
                    message.number("ECCENTRICITY"), math.radians(message.number("ARG_OF_PERICENTER")),
                    math.radians(message.number("INCLINATION")), math.radians(message.number("MEAN_ANOMALY")),
                    message.number("MEAN_MOTION") * 2.0 * math.pi / 1440.0,  # [rad/min]
                    math.radians(message.number("RA_OF_ASC_NODE")))
    satrec.classification = (message.get("CLASSIFICATION_TYPE") or "U")[0]
    satrec.elnum = int(message.get("ELEMENT_SET_NO") or 0)
    satrec.revnum = int(message.get("REV_AT_EPOCH") or 0)
    satrec.intldesg = _intldesg(message.get("OBJECT_ID") or "")
    line1, line2 = export_tle(satrec)
    return line1, line2


def _intldesg(object_id: str) -> str:
    """'1995-025A' -> '95025A' (TLE international designator)."""
    match = re.match(r"^(\d{4})-(\d{3})([A-Z]{1,3})$", object_id.upper())
    return f"{match.group(1)[2:]}{match.group(2)}{match.group(3)}" if match else ""


def omm_from_tle(line1: str, line2: str, object_name: str, **kwargs) -> str:
    """A TLE-based OMM carrying exactly the TLE's elements (4.1.2)."""
    from . import tle

    satrec = tle.parse(line1, line2)
    designator = line1[9:17].strip()
    object_id = "UNKNOWN"
    if len(designator) >= 5 and designator[:5].isdigit():
        year = int(designator[:2])
        object_id = f"{1900 + year if year >= 57 else 2000 + year}-{designator[2:5]}{designator[5:]}"
    return write_omm(object_name=object_name, object_id=object_id, epoch=tle.tle_epoch_utc(satrec),
                     mean_motion_rev_day=satrec.no_kozai * 1440.0 / (2.0 * math.pi), eccentricity=satrec.ecco,
                     inclination_deg=math.degrees(satrec.inclo), raan_deg=math.degrees(satrec.nodeo),
                     arg_pericenter_deg=math.degrees(satrec.argpo), mean_anomaly_deg=math.degrees(satrec.mo),
                     norad_cat_id=satrec.satnum, bstar=satrec.bstar,
                     mean_motion_dot=satrec.ndot * 1440.0 ** 2 / (2.0 * math.pi),
                     mean_motion_ddot=satrec.nddot * 1440.0 ** 3 / (2.0 * math.pi),
                     element_set_no=satrec.elnum, rev_at_epoch=satrec.revnum, classification=satrec.classification,
                     **kwargs)


def oem_from_result(result, epoch_utc: str, central_body: str, spacecraft: Sequence[str],
                    object_ids: Optional[Dict[str, str]] = None, stride: int = 1, **kwargs) -> Dict[str, str]:
    """One OEM per spacecraft from a run's ``position_N``/``velocity_N``
    series: EME2000, centre = central body, UTC epochs converted from the
    run's TDB time (engine.time_system). Returns ``{spacecraft: text}``."""
    from . import time_system as ts

    messages = {}
    for name in spacecraft:
        position = result.series[f"{name}.position_N"]
        velocity = result.series[f"{name}.velocity_N"]
        index = np.arange(0, len(position.time_s), max(1, int(stride)))
        if index[-1] != len(position.time_s) - 1:
            index = np.append(index, len(position.time_s) - 1)
        epochs = ts.elapsed_to_utc(epoch_utc, position.time_s[index])
        segment = {"object_name": name, "object_id": (object_ids or {}).get(name, "UNKNOWN"),
                   "center_name": central_body, "ref_frame": "EME2000", "time_system": "UTC", "epochs": epochs,
                   "r_km": np.asarray(position.data)[index] / 1e3, "v_km_s": np.asarray(velocity.data)[index] / 1e3,
                   "interpolation": "HERMITE", "interpolation_degree": 7,
                   "comments": ["Produced by a SpaceMissionStudio (Basilisk) simulation; EME2000 is SPICE J2000",
                                "Planetary ephemeris DE430; positions in km, velocities in km/s, as recorded"]}
        messages[name] = write_oem([segment], **kwargs)
    return messages


def orbit_ic_from_odm(text: str):
    """(schema OrbitIC, UTC epoch of the state or None, notes) from an OPM
    (cartesian state at its epoch) or a TLE-based OMM (TLE orbit, propagated
    by SGP4 to the scenario epoch like any TLE)."""
    from ..schema.scenario import OrbitIC

    message, issues = read_checked(text)
    notes = [str(issue) for issue in issues]
    if message.kind == "OPM":
        epoch, r, v, frame_notes = state_from_opm(message)
        orbit = OrbitIC(type="cartesian", position_km=list(r / 1e3), velocity_km_s=list(v / 1e3))
        return orbit, epoch, notes + frame_notes
    if message.kind == "OMM":
        line1, line2 = tle_from_omm(message)
        return OrbitIC(type="tle", tle_line1=line1, tle_line2=line2), None, notes
    raise OdmError("an OEM is an ephemeris, not an initial condition: import an OPM or OMM")
