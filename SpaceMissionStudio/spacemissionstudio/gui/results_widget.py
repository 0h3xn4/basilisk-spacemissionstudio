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

"""ResultsWidget: plots a :class:`engine.results.ResultSet` with Plotly,
embedded in a ``QWebEngineView`` -- replaces an earlier matplotlib
version, per explicit user request ("please rather use plotly, and not
matplotlib... make the plots visually more clear, professional and
appealing and informative") plus a real, separate complaint (matplotlib's
default axis formatting fell back to scientific/offset notation on
several series -- Plotly is configured below to never do that, on every
axis, regardless of data range). Takes a plain ``ResultSet`` -- no
Basilisk import in this module, so it's testable here with synthetic
data exactly like ``engine/results.py`` itself is.

``QWebEngineView``, not a static image: an embedded Plotly chart is a
real, interactive HTML/JS page (pan/zoom/box-select, a unified hover
tooltip showing every series' value at the cursor's x-position, a
built-in PNG-export button) -- a screenshot-style static render would
throw away exactly the interactivity that makes Plotly worth using over
matplotlib in the first place. ``plotly.js`` itself (~4.7 MB) is
referenced via a local ``file://`` src pointing directly at the copy
already installed as part of the ``plotly`` PyPI package's own
``package_data`` (:func:`_plotlyjs_path`) -- never a CDN reference (this
project avoids unnecessary network dependencies throughout, and a
SpaceMissionStudio desktop install has no reason to need one just to redraw a
plot), and never a second bundled copy of a multi-megabyte file this
project doesn't need to ship or keep in sync itself.

Running as root (this project's own CI/dev sandbox is; most real desktop
installs are not): Chromium refuses to start its renderer process as
root unless ``--no-sandbox`` is passed (a Chromium policy, not a Qt one
-- process sandboxing normally works by dropping privileges via setuid,
which is meaningless starting from an already-root process) -- confirmed
directly against a real ``QWebEngineView`` in this development sandbox,
which failed exactly that way without it. Handled below by setting
``QTWEBENGINE_CHROMIUM_FLAGS`` BEFORE ``PySide6.QtWebEngineWidgets`` is
imported (the only point at which QtWebEngine reads it) -- and ONLY when
actually running as root (``os.geteuid() == 0``), left off for a normal
non-root install, where Chromium's own process sandbox is real
defense-in-depth worth keeping even though this widget only ever loads
its own locally-generated HTML/JS, never remote or otherwise untrusted
content.

Verification status: the full local-``plotly.min.js``-via-``file://``
plus ``QWebEngineView.setHtml()`` pipeline was confirmed end-to-end in
this development sandbox (``QT_QPA_PLATFORM=offscreen`` -- no real
display here either) -- ``loadFinished`` fires ``True`` and a real
in-page JS check (``document.getElementsByClassName("plotly").length``)
confirms the chart div actually renders, not just that ``setHtml()``
didn't raise. The chosen design (re-send the FULL html, plotly.js
``<script src>`` reference included, on every redraw, rather than
loading the page shell once and pushing incremental updates via
``Plotly.react()`` through ``page().runJavaScript()``) was picked for
simplicity and testability (the built ``go.Figure`` object is directly
inspectable in a test, same role matplotlib's ``Axes`` used to play) --
NOT benchmarked against the incremental-update alternative for redraw
latency during a live (``set_live_result``) run; if that turns out to
feel sluggish on a real machine for a long/fast-updating run, the
incremental-update approach is the documented next step, not something
ruled out here.

Display choices below are all PLOT-only (``export_csv()``/``_on_export()``
keep writing exactly what ``TimeSeries`` holds -- raw SI units, elapsed
seconds -- since a CSV a user hands to another tool should stay
unambiguous, not follow a plot-only display preference):

* Per-category unit display (``_categorize()``, replacing an earlier
  blanket "every m/m-s series -> km/km-s" rule this project's own
  earlier version used): real user feedback was that the blanket rule
  went too far -- it converted the state vector (position/velocity) AND
  delta-V to km/km-s along with genuinely orbit-scale quantities like
  altitude and semi-major axis, but the explicit ask was the opposite
  for the first two ("delta-V shall always be displayed in m/s",
  "state vector elements shall be displayed in meters for position and
  m/s for velocity") while keeping it for the second two ("altitudes,
  semi-major axes shall be displayed in km"). Both can't be satisfied by
  one rule keyed on the literal unit string alone (position and
  semi-major axis are both recorded in plain "m"; velocity and delta-V
  are both plain "m/s") -- ``_categorize()`` keys off what each named
  series actually *is* instead (see its own docstring), with each
  category's own explicit unit choice, and only an uncategorized/future
  series (``_legacy_display()``) falls back to the old blanket rule.
  Orbital angle elements (inclination/RAAN/argument of periapsis/true
  anomaly, osculating and mean alike) additionally display in degrees,
  not Basilisk's native radians -- matching every angle INPUT field this
  app's own Scenario Editor already uses (e.g. ``inclination_deg``), and
  part of the same "convey more information" feedback that asked for
  titles/axis names/legends on every plot (see ``_categorize()``).
* The x-axis defaults to elapsed time (hours since the scenario epoch,
  as before) but can be switched to absolute epoch (UTC datetimes,
  ``series.time_s`` added to the epoch :meth:`set_result`/
  :meth:`set_live_result` were given) via ``x_axis_combo``. ``epoch_utc``
  is optional and defaults to ``None`` (falls back to elapsed time even
  if "Epoch (UTC)" is selected) so every existing caller/test that only
  ever passed a bare ``ResultSet`` keeps working unchanged.
"""

from __future__ import annotations

import base64
import os
import urllib.parse

# See module docstring's "Running as root" section -- MUST happen before
# PySide6.QtWebEngineWidgets is imported below (env var read at that
# module's own native init time; setting it any later has no effect).
if hasattr(os, "geteuid") and os.geteuid() == 0:
    os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--no-sandbox")

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np

import plotly.graph_objects as go
from PySide6.QtCore import QElapsedTimer, Qt, QTimer, QUrl, Signal
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (
    QCompleter,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .. import output_provenance
from ..engine import time_system
from ..engine.results import ResultSet, TimeSeries
from ..plot_categories import categorize as _categorize
from ..plot_categories import legacy_display as _legacy_display
from ..plot_categories import parse_access_pair as _parse_access_pair
from .flow_layout import FlowLayout
from .theme import FONTS_DIR, PALETTE, SERIES_COLORS
from .widgets import ComboBox

# Categorical series colours: Carbon's data-visualisation hues, stepped and
# ordered so they pass the dataviz validator on this white chart surface
# (gui/theme.py's SERIES_COLORS has the numbers). The first three are the
# common case: every (x, y, z) series. A legend is shown for more than one
# line, so colour is never the only way to tell lines apart.
_SERIES_COLORS = list(SERIES_COLORS)

# Chart chrome from the theme's Carbon tokens, so a chart reads as part of
# the application.
_INK_PRIMARY = PALETTE["text"]  # text-primary
_INK_MUTED = PALETTE["text_muted"]  # text-secondary
_GRID_COLOR = PALETTE["border"]  # border-subtle
_SURFACE = PALETTE["surface"]  # layer-01
_EMPTY_STATE_TEXT = PALETTE["text_muted"]
# IBM Plex Sans from the bundled file (an @font-face in _PAGE_STYLE): the
# chart page cannot see fonts loaded into Qt.
_FONT_FAMILY = "'IBM Plex Sans', system-ui, -apple-system, 'Segoe UI', sans-serif"

# A fixed id (rather than Plotly's own randomly-generated default) so
# _on_save_plot_png's injected JS can reliably find the chart div to
# rasterize -- see that method's own docstring for why a client-side
# Plotly.toImage() call is used instead of a server-side renderer
# (kaleido) this project doesn't otherwise depend on.
_PLOT_DIV_ID = "spacemissionstudio-plot"

# _on_save_plot_png/_poll_plot_png's poll-for-an-async-JS-result protocol
# -- see _on_save_plot_png's own docstring for why polling a page-global
# variable is used instead of relying on QWebEnginePage.runJavaScript()
# awaiting a top-level Promise itself (confirmed directly: it doesn't, on
# this PySide6 version). The sentinel distinguishes "still rendering"
# from a real result because a bare JS null/undefined also bridges back
# as an empty string here, not None.
_PNG_RESULT_JS_VAR = "__spacemissionstudioPngResult"
_SAVE_PNG_PENDING_SENTINEL = "__spacemissionstudio_png_pending__"
_SAVE_PNG_ERROR_PREFIX = "__spacemissionstudio_png_error__:"
_SAVE_PNG_POLL_INTERVAL_MS = 100
_SAVE_PNG_MAX_POLL_ATTEMPTS = 100  # 100 * 100ms = 10s -- Plotly.toImage took ~200ms in practice
_SAVE_PNG_MAX_WAIT_TICKS = 10  # poll ticks without an answer before asking again (1 s at 100 ms)

# [ms] Real user report: during a live-updating run, clicking the Series
# dropdown to switch plots appeared to do nothing. Root cause:
# set_live_result() used to call _redraw() -- a FULL QWebEngineView.setHtml()
# page reload (re-parsing the whole HTML document, reloading plotly.js,
# re-running Plotly.newPlot()) -- on every single progress chunk, with no
# throttling. A scenario that simulates faster than it can be watched (the
# common case for anything but a very long run) fires chunks faster than a
# full page reload can settle, so each setHtml() call interrupts the
# previous one's still-in-flight page load before it ever finishes
# rendering -- the view never visibly updates to anything, including a
# series the user just picked, because no reload during the storm ever
# completes. Throttling live redraws to this interval guarantees the
# QWebEngineView gets a real chance to finish each page load it starts.
# 300ms still reads as "live" to someone watching a plot update, while
# being generous enough for a full page reload to settle on a typical
# machine -- not tuned to any specific scenario.
_LIVE_REDRAW_MIN_INTERVAL_MS = 300


# Real user report: during a long run, switching to chief-1.position_N or
# .velocity_N "just doesn't change" -- the plot stayed on the previous
# series. Each was a 5.8 MB page (86,400 samples x 3 lines) and
# QWebEngineView.setHtml() silently shows nothing above 2 MB. Pages are
# now loaded from a file (no size limit), and each line is thinned to at
# most this many points for display (min and max of every stretch kept, so
# burns and peaks still show). Exports keep every sample.
_MAX_PLOT_POINTS_PER_LINE = 10000


# The shared time cursor (gui.time_cursor) on a plot: a click puts this
# prefix, the clicked x value and a click counter in the page title, which
# the view reports through titleChanged (there is no QWebChannel in this
# app, and this needs no QWebEnginePage subclass). The cursor is drawn as
# a layout shape of this name, updated with Plotly.relayout (no reload).
_CURSOR_MESSAGE = "spacemissionstudio-cursor:"
_CURSOR_SHAPE = "spacemissionstudio-cursor"
_CLICK_SCRIPT = f"""<script>
(function attach(attemptsLeft) {{
    var gd = document.getElementById({_PLOT_DIV_ID!r});
    if (!gd || !gd.on) {{
        if (attemptsLeft > 0) {{ setTimeout(function() {{ attach(attemptsLeft - 1); }}, 50); }}
        return;
    }}
    var clicks = 0;
    gd.on('plotly_click', function(event) {{
        if (event && event.points && event.points.length) {{
            clicks += 1;
            document.title = {_CURSOR_MESSAGE!r} + event.points[0].x + '|' + clicks;
        }}
    }});
}})(40);
</script>"""


def _clicked_x(title: str) -> Optional[str]:
    """The x value a plot click put in the page title, or None."""
    if not title.startswith(_CURSOR_MESSAGE):
        return None
    return title[len(_CURSOR_MESSAGE):].rsplit("|", 1)[0]


def _display_indices(values: np.ndarray, max_points: int = _MAX_PLOT_POINTS_PER_LINE) -> np.ndarray:
    """Indices of ``values`` to draw: all of them when there are few
    enough, otherwise the first, last, and the minimum and maximum of each
    of ``max_points // 2`` equal stretches (min-max decimation)."""
    n = len(values)
    if n <= max_points:
        return np.arange(n)
    buckets = max(1, (max_points - 2) // 2)
    edges = np.linspace(0, n, buckets + 1).astype(int)
    keep = [0, n - 1]
    finite = np.where(np.isfinite(values), values, np.nan)
    for start, end in zip(edges[:-1], edges[1:]):
        if end <= start:
            continue
        chunk = finite[start:end]
        if np.all(np.isnan(chunk)):
            keep.append(start)
            continue
        keep.append(start + int(np.nanargmin(chunk)))
        keep.append(start + int(np.nanargmax(chunk)))
    return np.unique(np.asarray(keep))


def _wrapping_display_indices(n: int, max_points: int = _MAX_PLOT_POINTS_PER_LINE) -> np.ndarray:
    """Evenly spaced indices for a wrapping angle: min-max decimation would
    pair ~0 and ~360 deg in every stretch and draw a solid band."""
    if n <= max_points:
        return np.arange(n)
    return np.unique(np.linspace(0, n - 1, max_points).astype(int))


def _break_at_wraps(x: np.ndarray, y: np.ndarray, period: float):
    """Inserts a gap wherever ``y`` wraps (jumps by more than half a
    ``period``), so 359 -> 1 deg isn't drawn as a vertical line."""
    jumps = np.flatnonzero(np.abs(np.diff(y)) > period / 2.0) + 1
    if not len(jumps):
        return x, y
    return np.insert(x, jumps, x[jumps - 1]), np.insert(y.astype(float), jumps, np.nan)


def _series_label(name: str, series: TimeSeries) -> str:
    """The name shown for a series in the Series list -- the same title
    its plot gets (e.g. "chief-1: Mean Semi-Major Axis"), not the dotted
    code name. Uncategorized series keep their code name."""
    display = _categorize(name, series) or _legacy_display(name, series)
    subject = name.split(".", 1)[0]
    return display.title if display.standalone_title else f"{subject}: {display.title}"


def _has_access_series(result: Optional[ResultSet]) -> bool:
    return result is not None and any(
        (parsed := _parse_access_pair(name)) is not None and parsed[2] == "has_access" for name in result.series
    )


_DRIFT_WARNING_TOOLTIP = (
    "These spacecraft use two-body gravity only, so orbital energy and angular momentum should stay "
    "constant. A drift this large usually means a numerical-integration problem, not real physics: try a "
    "smaller dynamics step (Propagation Setup) or a higher-order integrator."
)


def _short_utc(timestamp: str) -> str:
    """"2026-10-07T14:33:38.434854+00:00" -> "2026-10-07 14:33 UTC" (the
    text unchanged if it doesn't parse)."""
    try:
        parsed = datetime.fromisoformat(timestamp)
    except ValueError:
        return timestamp
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc)
    return parsed.strftime("%Y-%m-%d %H:%M UTC")


# Plotly's full page keeps the browser's default 8 px body margin under a
# 100%-height plot, which put a scroll bar beside every plot.
_CURSOR_COLOR = PALETTE["danger"]  # as on the Events timeline
_PAGE_STYLE = ("<style>html, body { margin: 0; height: 100%; overflow: hidden; } "
               "@font-face { font-family: 'IBM Plex Sans'; font-weight: 400; src: url('"
               + QUrl.fromLocalFile(str(FONTS_DIR / "IBMPlexSans-Regular.woff")).toString() + "'); } "
               "@font-face { font-family: 'IBM Plex Sans'; font-weight: 600; src: url('"
               + QUrl.fromLocalFile(str(FONTS_DIR / "IBMPlexSans-SemiBold.woff")).toString() + "'); }</style>")


def _plotlyjs_path() -> Path:
    """Absolute filesystem path to the ``plotly.min.js`` bundle already
    installed as part of the ``plotly`` PyPI package -- see module
    docstring's "QWebEngineView, not a static image" section for why
    this is referenced directly rather than re-bundled or CDN-loaded.
    """
    import plotly

    return Path(plotly.__file__).parent / "package_data" / "plotly.min.js"


def _empty_state_html() -> str:
    """Shown before any run has produced a result -- previously a blank
    white canvas with no explanation (part of the "looks unfinished"
    feedback the matplotlib version's own docstring already addressed);
    kept as plain HTML/CSS here, no Plotly involved, so it costs nothing
    to render.
    """
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><style>
  html, body {{ margin: 0; height: 100%; background: {_SURFACE};
                font-family: {_FONT_FAMILY}; }}
  .empty {{ display: flex; align-items: center; justify-content: center;
            height: 100%; color: {_EMPTY_STATE_TEXT}; font-size: 14px; }}
</style></head>
<body><div class="empty">Run a simulation to see results here</div></body></html>"""


class ResultsWidget(QWidget):
    open_in_vizard = Signal(str)  # the last run's playback file

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._result: ResultSet | None = None
        self._epoch_utc: Optional[str] = None
        self.figure: Optional[go.Figure] = None  # the currently-plotted go.Figure, or None (empty state)
        self._time_cursor = None  # gui.time_cursor.TimeCursor, set by set_time_cursor()
        self._x_is_epoch = False  # the shown figure's x axis is UTC (else elapsed hours)
        self._png_poll_state: Optional[dict] = None  # set by _on_save_plot_png, read by _poll_plot_png
        self._live_redraw_elapsed = QElapsedTimer()  # throttles set_live_result()'s own redraws -- see
        # _LIVE_REDRAW_MIN_INTERVAL_MS's own comment

        layout = QVBoxLayout(self)

        top_row = QHBoxLayout()
        # Design-philosophy roadmap item M5 (docs/ux_roadmap.md): a
        # second, purely additive view mode alongside the existing
        # single-series plot -- "most of the value of 'see access
        # windows at a glance' comes from one more chart, not a new
        # interaction model" (the roadmap's own scoping). Switching to
        # "Ground station access timeline" disables series_combo (it
        # has no effect in that view) and redraws; switching back
        # restores the single-series view exactly as it was.
        # Shown only for a result with ground-station access series --
        # without them there is nothing to choose.
        self.view_label = QLabel("View:")
        self.view_label.setVisible(False)
        self.view_combo = ComboBox()
        self.view_combo.addItem("Single series", "single")
        self.view_combo.addItem("Access timeline", "access_timeline")
        self.view_combo.setToolTip("\"Access timeline\" shows every ground station's passes over every "
                                   "spacecraft in one chart.")
        self.view_combo.setVisible(False)
        self.view_combo.currentIndexChanged.connect(self._on_view_changed)
        top_row.addWidget(QLabel("Series:"))
        self.series_combo = ComboBox()
        # Editable + a substring-matching QCompleter -- a real scenario
        # (e.g. the built-in 6-satellite Walker constellation template)
        # produces 30-40+ series, all named after the dotted scheme
        # engine.service/engine.link_budget use
        # ("leo-02-03.orbit_elements_mean.inclination", ...); a plain,
        # unsearchable dropdown list that long is tedious to scan.
        # MatchContains (not the default MatchStartsWith) matters here
        # specifically because the useful discriminator is usually in
        # the MIDDLE of the name (the spacecraft, or the category after
        # the first dot), not always the start. InsertPolicy.NoInsert
        # keeps typed-but-not-selected text from being added as a fake
        # new entry -- this combo's contents are always exactly
        # result.series's keys, nothing a user types can add to them.
        self.series_combo.setEditable(True)
        self.series_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.series_combo.setToolTip("Type to filter, or use the dropdown")
        # A long real series name (e.g. "leo-02-03.orbit_elements_mean.inclination")
        # needs real room to be readable -- without a floor, this is the
        # one widget on the row with stretch=1, so it's also the first
        # one Qt shrinks below its natural size when the row is tight
        # (see button_row's own comment for the regression this guards
        # against going forward).
        self.series_combo.setMinimumWidth(220)
        completer = QCompleter(self.series_combo.model(), self.series_combo)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self.series_combo.setCompleter(completer)
        self.series_combo.currentIndexChanged.connect(self._redraw)
        # Real user-reported bug: picking a series via the completer popup
        # (type to filter, then click/Enter a suggestion -- this combo's
        # whole reason for being editable, see the comment above) often
        # left the line edit showing the new series name while the plot
        # kept showing the old one. Root cause: QComboBox.currentIndexChanged
        # above only fires when the combo's OWN internal index-selection
        # path changes the index -- a completer operates on the line edit
        # directly and, confirmed in this Qt version, does not reliably
        # drive that same path (a known-inconsistent area of
        # QComboBox+QCompleter interaction, not unique to this app). Two
        # more explicit hooks close the gap: the completer's own
        # ``activated`` fires the instant a popup suggestion is picked
        # (click or Enter-within-the-popup), and the line edit's
        # ``editingFinished`` catches the remaining case of typing an
        # exact, already-complete name and pressing Enter with no popup
        # open. Both funnel through ``_on_series_text_committed`` so the
        # combo's own index is explicitly synced (not just its displayed
        # text) before redrawing -- harmless if ``currentIndexChanged``
        # also fires for the same pick (``_redraw()`` is idempotent).
        completer.activated.connect(self._on_series_text_committed)
        self.series_combo.lineEdit().editingFinished.connect(
            lambda: self._on_series_text_committed(self.series_combo.currentText())
        )
        top_row.addWidget(self.series_combo, stretch=1)
        top_row.addWidget(QLabel("X-axis:"))
        self.x_axis_combo = ComboBox()
        self.x_axis_combo.addItem("Elapsed time", "elapsed")
        self.x_axis_combo.addItem("Epoch (UTC)", "epoch")
        self.x_axis_combo.setToolTip(
            "\"Epoch (UTC)\" needs the scenario's epoch, which is only known once a run has actually "
            "produced this result -- falls back to elapsed time if it isn't available."
        )
        self.x_axis_combo.currentIndexChanged.connect(self._redraw)
        top_row.addWidget(self.x_axis_combo)
        layout.addLayout(top_row)

        # One-click shortcuts to the series the scenario's own description
        # points at ("What to look at"), so nobody has to find
        # berlin-gs.access_to_leo-comms-1.link_margin_db among 40 entries.
        # Filled from set_featured_series(); hidden when there are none.
        self._featured: list = []
        self._suggestion_chips: list = []
        self.suggestion_row = QWidget()
        suggestion_layout = QHBoxLayout(self.suggestion_row)
        suggestion_layout.setContentsMargins(0, 0, 0, 0)
        suggestion_label = QLabel("Suggested:")
        suggestion_label.setStyleSheet(f"color: {PALETTE['text_muted']};")
        suggestion_layout.addWidget(suggestion_label, 0, Qt.AlignmentFlag.AlignTop)
        self._suggestion_box = QWidget()
        self._suggestion_flow = FlowLayout(self._suggestion_box)
        suggestion_layout.addWidget(self._suggestion_box, 1)
        self.suggestion_row.setStyleSheet(
            f"QPushButton#suggestionChip {{ border: 1px solid {PALETTE['border']}; border-radius: 10px; "
            f"padding: 2px 10px; background-color: {PALETTE['surface']}; color: {PALETTE['text']}; }}"
            f"QPushButton#suggestionChip:hover {{ border-color: {PALETTE['accent']}; }}"
            f"QPushButton#suggestionChip:checked {{ background-color: {PALETTE['accent_soft']}; "
            f"border-color: {PALETTE['accent']}; color: {PALETTE['accent']}; }}"
        )
        self.suggestion_row.setVisible(False)
        layout.addWidget(self.suggestion_row)

        # Real UI regression, caught from a screenshot: this row used to
        # share ONE QHBoxLayout with the "View"/"Series"/"X-axis" combos
        # above. Adding the "View" combo (roadmap item M5) and the "Save
        # plot as SVG..." button (roadmap item M2) on top of what was
        # already there left too many widgets competing for one row's
        # width inside the (non-full-window) Results panel -- Qt resolved
        # that by squeezing series_combo (the one widget with
        # stretch=1, i.e. the one meant to actually use spare space) down
        # toward its minimum size instead, which on a real window left it
        # showing only a few truncated characters of whatever was
        # selected/typed, looking exactly like garbled text. Splitting
        # "what am I looking at" (above) from "do something with it"
        # (below) onto separate rows removes that width pressure
        # entirely rather than trying to tune individual widths against
        # an unbounded number of future buttons on the same row.
        button_row = QHBoxLayout()
        self.export_button = QPushButton("Export CSV...")
        self.export_button.setToolTip("Export every series in this result as CSV files (SI units)")
        self.export_button.clicked.connect(self._on_export)
        self.export_button.setEnabled(False)
        button_row.addWidget(self.export_button)
        self.save_png_button = QPushButton("Save PNG...")
        self.save_png_button.setToolTip("Save the currently displayed plot (not every series -- see "
                                         "\"Export CSV...\" for that) as a PNG image")
        self.save_png_button.clicked.connect(self._on_save_plot_png)
        self.save_png_button.setEnabled(False)
        button_row.addWidget(self.save_png_button)
        # Design-philosophy roadmap item M2 (docs/ux_roadmap.md): a vector
        # export alongside the existing raster one, for a plot a user wants
        # to drop into a paper/report at arbitrary scale without it going
        # blurry. Shares _on_save_plot_png's whole dialog/kickoff/poll
        # machinery via its ``fmt`` parameter -- see that method's own
        # docstring -- rather than duplicating it.
        self.save_svg_button = QPushButton("Save SVG...")
        self.save_svg_button.setToolTip("Save the currently displayed plot as a scalable vector (SVG) image")
        self.save_svg_button.clicked.connect(self._on_save_plot_svg)
        self.save_svg_button.setEnabled(False)
        button_row.addWidget(self.save_svg_button)
        # The last run's Vizard playback file (UX/UI guidelines, decision 3:
        # open only -- Vizard has no interface to follow the time cursor).
        self.vizard_button = QPushButton("Open in Vizard")
        self.vizard_button.setToolTip("Opens the playback file this run wrote in Vizard. Vizard cannot follow "
                                      "the time cursor.")
        self.vizard_button.clicked.connect(lambda: self.open_in_vizard.emit(self._vizard_file or ""))
        self.vizard_button.setVisible(False)
        self._vizard_file: Optional[str] = None
        button_row.addWidget(self.vizard_button)
        button_row.addStretch(1)
        # Run comparison (UX/UI guidelines): the same series from an earlier
        # run of this session, dashed, and the inputs that differ.
        self._runs: list = []  # gui.run_history.RunRecord, oldest first
        self._current_run = None  # the RunRecord shown, when it is one
        self.compare_label = QLabel("Compare with:")
        self.compare_combo = ComboBox()
        self.compare_combo.setToolTip("Draws the same series from an earlier run of this session, dashed.")
        self.compare_combo.currentIndexChanged.connect(self._redraw)
        self.diff_button = QPushButton("Input differences...")
        self.diff_button.setToolTip("Lists every scenario input that differs between the two runs.")
        self.diff_button.clicked.connect(self.show_input_differences)
        for widget in (self.compare_label, self.compare_combo, self.diff_button):
            widget.setVisible(False)
            button_row.addWidget(widget)
        button_row.addWidget(self.view_label)
        button_row.addWidget(self.view_combo)
        layout.addLayout(button_row)

        # Design-philosophy audit finding (docs/ux_audit.md, "no run
        # provenance captured with results"): one line, always visible
        # once a result exists, naming exactly what produced it --
        # ResultSet.provenance is None for a hand-built/synthetic result
        # (e.g. a test), so this stays blank rather than guessing.
        self.provenance_label = QLabel("")
        self.provenance_label.setStyleSheet("color: palette(mid); font-size: 90%;")
        self.provenance_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.provenance_label.setWordWrap(True)  # never forces the pane wider
        # Real UI bug, caught from a screenshot: this label and web_view
        # both default to QSizePolicy.Preferred vertically with 0
        # stretch, which Qt's QVBoxLayout resolved by handing almost ALL
        # of the layout's surplus height to this one-line label (a large
        # blank area below its own text, pushing the actual plot down
        # and off the bottom of the window) instead of to the plot that
        # should obviously be the one expanding to fill the space.
        # Fixed=vertical pins it to its own sizeHint no matter how much
        # extra room the layout has -- paired with web_view's own
        # stretch=1 below, which is what actually directs the surplus to
        # it explicitly rather than relying on size-policy tie-breaking.
        self.provenance_label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        layout.addWidget(self.provenance_label)

        # Design-philosophy audit finding (docs/ux_audit.md, "no active
        # conservation/drift diagnostic") -- see
        # engine.results.conservation_drift_warnings's own docstring.
        # Hidden (no empty banner taking up space) whenever
        # ResultSet.warnings is empty, which is the common case: most
        # scenarios have SOME perturbation/thrust configured, so the
        # check never even runs for them (see
        # engine.service._is_two_body_only). Reuses PALETTE["danger"] --
        # this app's one existing "needs attention" color (feedback.py's
        # own error-toast color) -- rather than inventing a second
        # semantic color never used elsewhere; the wording itself (not
        # just the color) makes clear this is informational, not fatal.
        self.warnings_label = QLabel("")
        self.warnings_label.setWordWrap(True)
        self.warnings_label.setStyleSheet(f"color: {PALETTE['warning']}; font-size: 90%;")
        self.warnings_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.warnings_label.setVisible(False)
        # Same fix as provenance_label just above, for the same reason --
        # this is wrapped text whose natural height already varies with
        # width and warning count; it must still never grow to consume
        # leftover layout space beyond that natural height.
        self.warnings_label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        layout.addWidget(self.warnings_label)

        self.web_view = QWebEngineView()
        self.web_view.titleChanged.connect(self._on_page_title)
        self.web_view.loadFinished.connect(lambda _ok: self.apply_cursor_line())
        # Plot pages are written here and loaded from file -- see
        # _MAX_PLOT_POINTS_PER_LINE for why setHtml() can't be used.
        self._page_dir = tempfile.TemporaryDirectory(prefix="spacemissionstudio-plot-")
        self._page_counter = 0
        # stretch=1: the one widget in this column that should actually
        # claim all leftover vertical space -- see provenance_label's own
        # comment above for the real bug this fixes.
        layout.addWidget(self.web_view, stretch=1)
        self._redraw()  # shows the empty-state message immediately, not just after the first set_result() call

    def set_result(self, result: ResultSet | None, epoch_utc: Optional[str] = None) -> None:
        self._result = result
        self._epoch_utc = epoch_utc
        self._fill_series_combo(result)
        self.export_button.setEnabled(result is not None and bool(result.series))
        self._update_provenance_label()
        self._update_warnings_label()
        self._redraw()

    def _fill_series_combo(self, result: Optional[ResultSet]) -> None:
        """One entry per series, shown by its plot title; the code name
        (the CSV file name) is the item's data and tooltip."""
        self.series_combo.blockSignals(True)
        self.series_combo.clear()
        if result is not None:
            labels = {name: _series_label(name, series) for name, series in result.series.items()}
            label_counts: dict = {}
            for label in labels.values():
                label_counts[label] = label_counts.get(label, 0) + 1
            for name, label in labels.items():
                self.series_combo.addItem(label if label_counts[label] == 1 else name, name)
                self.series_combo.setItemData(self.series_combo.count() - 1, name, Qt.ItemDataRole.ToolTipRole)
        featured_present = [name for name in self._featured if result is not None and name in result.series]
        if featured_present:  # open on what the scenario says to look at, not whatever comes first
            self.series_combo.setCurrentIndex(self.series_combo.findData(featured_present[0]))
        self.series_combo.blockSignals(False)
        self._refresh_suggestions()
        has_access = _has_access_series(result)
        if not has_access and self.view_combo.currentData() != "single":
            self.view_combo.setCurrentIndex(self.view_combo.findData("single"))
        self.view_label.setVisible(has_access)
        self.view_combo.setVisible(has_access)

    def set_featured_series(self, names) -> None:
        """The series to offer as one-click suggestions (normally
        ``engine.series_names.featured_series(scenario)`` for the scenario
        being run). Only those present in the result are shown, and a new
        result opens on the first of them."""
        self._featured = list(names)
        self._refresh_suggestions()

    def _refresh_suggestions(self) -> None:
        for chip in self._suggestion_chips:
            self._suggestion_flow.removeWidget(chip)
            chip.deleteLater()
        self._suggestion_chips = []
        result = self._result
        names = [name for name in self._featured if result is not None and name in result.series]
        for name in names:
            chip = QPushButton(self._chip_label(name))
            chip.setObjectName("suggestionChip")
            chip.setCheckable(True)
            chip.setAutoDefault(False)
            chip.setToolTip(name)
            chip.setProperty("series_name", name)
            chip.clicked.connect(lambda _checked=False, n=name: self.show_series(n))
            self._suggestion_flow.addWidget(chip)
            self._suggestion_chips.append(chip)
        self.suggestion_row.setVisible(bool(names))
        self._update_suggestion_states()

    def _chip_label(self, name: str) -> str:
        """The plot title, minus what every chip would repeat: the
        spacecraft when the result has only one, and the station ->
        spacecraft pair when there is only one (the tooltip and the plot
        title still name them)."""
        result = self._result
        label = _series_label(name, result.series[name])
        pairs = {_parse_access_pair(n)[:2] for n in result.series if _parse_access_pair(n) is not None}
        spacecraft = {n.split(".", 1)[0] for n in result.series if _parse_access_pair(n) is None}
        if len(spacecraft) == 1 and label.startswith(f"{next(iter(spacecraft))}: "):
            label = label.split(": ", 1)[1]
        if len(pairs) == 1:
            gs, sc = next(iter(pairs))
            label = label.removesuffix(f": {gs} -> {sc}")
        return label

    def _update_suggestion_states(self) -> None:
        showing = self.current_series_name() if self.view_combo.currentData() == "single" else ""
        for chip in self._suggestion_chips:
            chip.setChecked(chip.property("series_name") == showing)

    def show_series(self, name: str) -> None:
        """Show one series (switching out of the access timeline if needed)."""
        if self.view_combo.currentData() != "single":
            self.view_combo.setCurrentIndex(self.view_combo.findData("single"))
        index = self.series_combo.findData(name)
        if index >= 0 and index != self.series_combo.currentIndex():
            self.series_combo.setCurrentIndex(index)  # redraws via currentIndexChanged
        self._update_suggestion_states()

    def current_series_name(self) -> str:
        """Code name of the selected series ("" when there is none)."""
        return self.series_combo.currentData() or ""

    def _update_warnings_label(self) -> None:
        warnings = self._result.warnings if self._result is not None else []
        if not warnings:
            self.warnings_label.setVisible(False)
            self.warnings_label.setText("")
            return
        self.warnings_label.setText("\n".join(f"⚠ {w}" for w in warnings))
        self.warnings_label.setToolTip(_DRIFT_WARNING_TOOLTIP)
        self.warnings_label.setVisible(True)

    def _update_provenance_label(self) -> None:
        provenance = self._result.provenance if self._result is not None else None
        if provenance is None:
            self.provenance_label.setText("")
            self.provenance_label.setToolTip("")
            return
        self.provenance_label.setText(
            f"SpaceMissionStudio {provenance.spacemissionstudio_version} · "
            f"Basilisk {provenance.basilisk_version} · {provenance.integrator.upper()}, "
            f"{provenance.dynamics_task_rate_s:g} s step · {_short_utc(provenance.run_started_utc)}"
        )
        self.provenance_label.setToolTip(provenance.rng_seed_note)

    def set_live_result(self, result: ResultSet, epoch_utc: Optional[str] = None) -> None:
        """Updates the plot with one chunk's worth of a still-running
        simulation (see ``gui.run_worker.RunWorker``'s ``progress`` signal /
        :meth:`engine.service.SimulationService.run_live`). Unlike
        :meth:`set_result`, this never rebuilds ``series_combo`` once it
        already holds this result's series names -- the set of series a
        live run reports is fixed from its very first callback (which
        series exist is decided by the scenario, not by how much data has
        been recorded), so rebuilding it every chunk would keep resetting
        whatever series the user is currently looking at, fighting them
        while they watch it run.

        The actual ``QWebEngineView`` redraw is throttled to at most once
        per :data:`_LIVE_REDRAW_MIN_INTERVAL_MS` -- see that constant's
        own comment for the real bug this fixes (a fast-running scenario
        firing chunks faster than a full page reload can settle, which
        left the plot visibly stuck and made switching series look like
        clicking did nothing). :attr:`figure` itself is still rebuilt
        from ``result`` on every single call, throttled or not.
        """
        is_first_update = self._result is None or set(self._result.series) != set(result.series)
        self._result = result
        self._epoch_utc = epoch_utc  # same every chunk of one run, but cheap enough not to bother guarding
        # Unlike provenance (fixed once at run start), warnings can only
        # become non-empty partway through a long live run (more samples
        # -> more opportunity for drift to exceed tolerance) -- updated
        # on every call, not just is_first_update, and never throttled
        # like the webview redraw below (a QLabel update is cheap, no
        # page reload).
        self._update_warnings_label()
        if is_first_update:
            self._fill_series_combo(result)
            self.export_button.setEnabled(bool(result.series))
            self._update_provenance_label()
            self._redraw()
            self._live_redraw_elapsed.start()
            return
        # Throttled -- see _LIVE_REDRAW_MIN_INTERVAL_MS's own comment: a
        # scenario that simulates faster than it can be watched fires
        # chunks faster than a full QWebEngineView page reload can settle,
        # so redrawing on every single chunk left the view stuck mid
        # -reload forever, including while the user tried to switch which
        # series is shown. Skipping a throttled chunk's WEBVIEW push only
        # delays the on-screen display catching up to self._result by at
        # most this interval -- self.figure itself is kept fresh every
        # single chunk regardless (_update_figure() is cheap, no page
        # reload), a user-initiated series/x-axis change still calls
        # _redraw() directly (see series_combo/x_axis_combo's own
        # currentIndexChanged connections) and is never throttled, and the
        # final frame always renders anyway once the run finishes and
        # set_result() is called.
        self._update_figure()
        if self._live_redraw_elapsed.elapsed() >= _LIVE_REDRAW_MIN_INTERVAL_MS:
            self._push_figure_to_webview()
            self._live_redraw_elapsed.restart()

    def _x_axis_values(self, time_s):
        """Returns ``(x_values, axis_label)``. "Epoch (UTC)" needs both a
        real epoch (``set_result``/``set_live_result`` were given one --
        absent for e.g. a bare synthetic ``ResultSet`` in a test, or
        before any run has actually happened yet) and for it to parse;
        either problem falls back to elapsed time rather than raising,
        matching this widget's existing "never crash the GUI over
        display preferences" behavior (see e.g. ``_redraw``'s own
        empty-state handling).
        """
        if self.x_axis_combo.currentData() == "epoch" and self._epoch_utc:
            try:
                # time_s is TDB seconds since the epoch (engine.time_system).
                return list(time_system.elapsed_to_utc(self._epoch_utc, time_s)), "Epoch (UTC)"
            except ValueError:
                pass
        return time_s / 3600.0, "Elapsed time [hr]"

    def _build_figure(self, name: str, series: TimeSeries) -> go.Figure:
        display = _categorize(name, series) or _legacy_display(name, series)
        display_data = series.data * display.factor
        x_values, x_label = self._x_axis_values(series.time_s)
        is_datetime_axis = self.x_axis_combo.currentData() == "epoch" and x_label == "Epoch (UTC)"
        self._x_is_epoch = is_datetime_axis

        fig = go.Figure()
        column_labels = display.columns or {}
        x_array = np.asarray(x_values, dtype=object if isinstance(x_values, list) else None)
        # A Monte Carlo batch's per-run series (columns run_0, run_1, ...):
        # the runs are interchangeable, so one thin, translucent colour and
        # one legend entry rather than a colour (and legend row) each.
        ensemble = len(series.columns) > 1 and all(str(c).startswith("run_") for c in series.columns)
        for i, column in enumerate(series.columns):
            if display.wrap_period:
                keep = _wrapping_display_indices(len(display_data))
                x_shown, y_shown = _break_at_wraps(x_array[keep], display_data[keep, i], display.wrap_period)
            else:
                keep = _display_indices(display_data[:, i])  # see _MAX_PLOT_POINTS_PER_LINE
                x_shown, y_shown = x_array[keep], display_data[keep, i]
            fig.add_trace(go.Scatter(
                x=list(x_shown) if x_array.dtype == object else x_shown, y=y_shown, mode="lines",
                name=(f"Each run ({len(series.columns)})" if ensemble else column_labels.get(column, column)),
                line=(dict(color=_SERIES_COLORS[0], width=1) if ensemble
                      else dict(color=_SERIES_COLORS[i % len(_SERIES_COLORS)], width=2)),
                **(dict(opacity=0.45, legendgroup="runs", showlegend=i == 0,
                        hovertemplate=f"Run {str(column)[4:]}: %{{y:.4g}}<extra></extra>") if ensemble else {}),
            ))
        self._add_comparison_traces(fig, name, display)

        axis_common = dict(
            gridcolor=_GRID_COLOR, zerolinecolor=_GRID_COLOR, linecolor=_GRID_COLOR,
            tickfont=dict(color=_INK_MUTED), title_font=dict(color=_INK_MUTED),
        )
        y_title = f"{display.y_label} [{display.unit}]" if display.y_label else (f"[{display.unit}]" if display.unit else None)
        y_axis = dict(axis_common, title_text=y_title)
        x_axis = dict(axis_common, title_text=x_label)
        if not is_datetime_axis:
            # Both fix the exact complaint that started this: matplotlib's
            # default tick formatter fell back to an offset/scientific
            # notation (e.g. "1e6") on several of this app's own plots.
            # exponentformat="none" forbids it entirely, on every axis,
            # regardless of how large/small the data range is;
            # separatethousands adds comma grouping so a plain large
            # number (e.g. "7,123,456") still reads cleanly instead of as
            # one long digit run. Skipped for a datetime axis, where
            # neither setting is meaningful (Plotly formats dates on its
            # own date-axis path).
            y_axis["exponentformat"] = "none"
            y_axis["separatethousands"] = True
            x_axis["exponentformat"] = "none"
            x_axis["separatethousands"] = True

        fig.update_layout(
            title=dict(text=_series_label(name, series), font=dict(size=16, color=_INK_PRIMARY, family=_FONT_FAMILY)),
            xaxis=x_axis,
            yaxis=y_axis,
            font=dict(family=_FONT_FAMILY, color=_INK_PRIMARY),
            plot_bgcolor=_SURFACE,
            paper_bgcolor=_SURFACE,
            hovermode="x unified",
            # a single series names itself in the title -- no legend box needed, unless compared
            showlegend=len(series.columns) > 1 or self.comparison_run() is not None,
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font=dict(color=_INK_MUTED)),
            margin=dict(l=70, r=30, t=60, b=50),
        )
        if ensemble:  # one hover row per run would list them all; show the run under the pointer
            fig.update_layout(hovermode="closest")
        return fig

    def _on_view_changed(self) -> None:
        """``view_combo``'s own ``currentIndexChanged`` handler -- see
        that combo's construction comment (roadmap item M5).
        ``series_combo`` (and its completer) have no effect in the
        access-timeline view, so they're disabled rather than merely
        ignored -- a disabled, grayed-out control is a clearer signal
        that it doesn't currently apply than a control that still looks
        interactive but silently does nothing.
        """
        is_single_series = self.view_combo.currentData() == "single"
        self.series_combo.setEnabled(is_single_series)
        self._redraw()

    def _update_figure(self) -> None:
        """Rebuilds :attr:`figure` from the current :attr:`_result`/selected
        series (or, in the access-timeline view, from every access-pair
        series at once -- see :meth:`_build_access_timeline_figure`) --
        cheap (no HTML string building, no ``QWebEngineView`` page
        reload), so it's always kept fresh even on a chunk
        :meth:`set_live_result` otherwise throttles (see that method's own
        comment): other code (the PNG-save button's enabled state,
        tests) reads :attr:`figure` directly and must never see stale
        data just because the webview push itself was skipped.
        """
        self.figure = None
        self._x_is_epoch = False
        if self._result is None:
            return
        if self.view_combo.currentData() == "access_timeline":
            self.figure = self._build_access_timeline_figure()
            return
        if self.series_combo.count() > 0:
            name = self.current_series_name()
            series = self._result.series.get(name)
            if series is not None:
                self.figure = self._build_figure(name, series)

    def _build_access_timeline_figure(self) -> Optional[go.Figure]:
        """Roadmap item M5: one combined Gantt-style chart showing every
        ``{station}.access_to_{spacecraft}.has_access`` series in
        :attr:`_result` at once -- "most of the value of 'see access
        windows at a glance' comes from one more chart, not a new
        interaction model" (the roadmap's own scoping decision; a
        click-to-jump interaction linking a clicked bar to the main
        plot's x-axis range was explicitly left as unimplemented future
        scope -- this app has no JS<->Python click bridge
        (``QWebChannel``) anywhere yet, and inventing one for this alone
        would be a far bigger lift than the chart itself).

        Returns ``None`` (an explanatory empty-state figure, same
        pattern as :func:`_empty_state_html` for the no-result case) if
        :attr:`_result` has no access-pair series at all -- e.g. a
        scenario with no ``ground_stations`` configured.

        Deliberately uses ELAPSED TIME ONLY, ignoring ``x_axis_combo``
        -- a horizontal bar's ``base``/width on Plotly's date axis needs
        real ``timedelta``-typed values, not the plain float seconds
        ``TimeSeries.time_s`` already is, and this view's whole value is
        "see every pass at a glance," which elapsed time already serves
        perfectly well; the main single-series view is still there for
        anyone who specifically wants epoch/UTC timestamps.
        """
        pairs: list = []
        for name, series in self._result.series.items():
            parsed = _parse_access_pair(name)
            if parsed is None or parsed[2] != "has_access":
                continue
            gs, sc, _field = parsed
            pairs.append((f"{gs} -> {sc}", series))
        pairs.sort(key=lambda item: item[0])

        fig = go.Figure()
        t_end_hr = max((float(series.time_s[-1]) for _label, series in pairs if len(series.time_s)),
                       default=0.0) / 3600.0
        if not pairs:
            fig.update_layout(
                annotations=[dict(
                    text="No ground-station access series in this result (no ground stations configured?)",
                    showarrow=False, font=dict(color=_EMPTY_STATE_TEXT, size=14),
                    xref="paper", yref="paper", x=0.5, y=0.5,
                )],
                plot_bgcolor=_SURFACE, paper_bgcolor=_SURFACE,
                xaxis=dict(visible=False), yaxis=dict(visible=False),
            )
            return fig

        for row_index, (pair_label, series) in enumerate(pairs):
            t_hours = series.time_s / 3600.0
            has_access = series.data[:, series.columns.index("has_access")] != 0
            color = _SERIES_COLORS[row_index % len(_SERIES_COLORS)]
            # Each contiguous True run in has_access is one thick line
            # segment; all of a pair's segments share ONE trace, separated
            # by None gaps. One trace per pass made thousands of traces on
            # a long run (2,865 for six pairs over a month), which Plotly
            # is slow to draw.
            padded = np.concatenate([[False], has_access, [False]])
            changes = np.flatnonzero(np.diff(padded.astype(int)))
            starts, ends = changes[0::2], changes[1::2] - 1
            if len(starts):
                xs: list = []
                ys: list = []
                for start, end in zip(starts, ends):
                    xs += [t_hours[start], t_hours[end], None]
                    ys += [pair_label, pair_label, None]
                # A tick at each end keeps a short pass visible on a long
                # run, where its segment is narrower than a pixel.
                fig.add_trace(go.Scatter(
                    x=xs, y=ys, mode="lines+markers", line=dict(color=color, width=16), connectgaps=False,
                    marker=dict(symbol="line-ns", size=16, line=dict(color=color, width=1)),
                    name=pair_label, hovertemplate=f"{pair_label}<br>%{{x:.3f}} hr<extra></extra>",
                ))
            else:
                # No access window at all for this pair -- still give it
                # a row (an invisible trace) so it appears in the legend
                # and on the y-axis, same as every other pair, rather
                # than silently vanishing from the chart.
                fig.add_trace(go.Scatter(
                    x=[t_hours[0]], y=[pair_label], mode="markers",
                    marker=dict(size=0, color=color), name=pair_label, legendgroup=pair_label,
                    hoverinfo="skip",
                ))

        axis_common = dict(
            gridcolor=_GRID_COLOR, zerolinecolor=_GRID_COLOR, linecolor=_GRID_COLOR,
            tickfont=dict(color=_INK_MUTED), title_font=dict(color=_INK_MUTED),
        )
        fig.update_layout(
            title=dict(text="Ground Station Access Timeline", font=dict(size=16, color=_INK_PRIMARY,
                                                                          family=_FONT_FAMILY)),
            # Fixed to the run: the end-of-pass ticks would otherwise pad
            # the axis to before t = 0.
            xaxis=dict(axis_common, title_text="Elapsed time [hr]", exponentformat="none",
                       separatethousands=True, range=[0.0, t_end_hr]),
            yaxis=dict(axis_common, title_text=None, categoryorder="category descending"),
            font=dict(family=_FONT_FAMILY, color=_INK_PRIMARY),
            plot_bgcolor=_SURFACE, paper_bgcolor=_SURFACE,
            showlegend=False,  # the y-axis category labels already name every pair -- a legend would be redundant
            margin=dict(l=160, r=30, t=60, b=50),
        )
        return fig

    def _push_figure_to_webview(self) -> None:
        """Pushes :attr:`figure` (already current -- see
        :meth:`_update_figure`) to the ``QWebEngineView`` via a full
        ``setHtml()`` page reload. The expensive, disruptive half of what
        used to be one ``_redraw()`` -- see :meth:`set_live_result`'s own
        throttling comment for why this is split out separately.
        """
        if self.figure is None:
            self.web_view.setHtml(_empty_state_html(), QUrl())  # small: setHtml's 2 MB limit is no issue
        else:
            html = self.figure.to_html(
                include_plotlyjs=QUrl.fromLocalFile(str(_plotlyjs_path())).toString(), full_html=True,
                div_id=_PLOT_DIV_ID, config={"displaylogo": False, "responsive": True},
            )
            html = html.replace("<head>", "<head>" + _PAGE_STYLE, 1)
            html = html.replace("</body>", _CLICK_SCRIPT + "</body>", 1)
            # Alternating file names, so a new page never overwrites one
            # that is still loading.
            self._page_counter += 1
            page = Path(self._page_dir.name) / f"plot-{self._page_counter % 2}.html"
            if not page.parent.is_dir():
                # Shutting down: Python removed the temporary directory
                # before Qt destroyed this widget, and a late signal (the
                # series box losing focus) asked for one more redraw.
                return
            page.write_text(html, encoding="utf-8")
            self.web_view.load(QUrl.fromLocalFile(str(page)))
        # Never force-enable while a save-as-PNG poll is in flight (e.g. a
        # live-updating run calling _redraw() repeatedly via
        # set_live_result() while the user's earlier click is still being
        # polled) -- see _on_save_plot_png's own re-entrancy-guard comment
        # for what a second concurrent poll would do. _poll_plot_png's own
        # completion paths already re-enable the button once that poll
        # actually finishes.
        if self._png_poll_state is None:
            self.save_png_button.setEnabled(self.figure is not None)
            self.save_svg_button.setEnabled(self.figure is not None)

    def set_runs(self, runs: list, current=None) -> None:
        """The session's runs (``gui.run_history.RunRecord``) and the one shown;
        the others are offered under "Compare with"."""
        chosen = self.compare_combo.currentData()
        self._runs, self._current_run = list(runs), current
        others = [r for r in self._runs if current is None or r.number != current.number]
        self.compare_combo.blockSignals(True)
        self.compare_combo.clear()
        self.compare_combo.addItem("(no comparison)", None)
        for record in reversed(others):
            self.compare_combo.addItem(record.label, record.number)
        index = self.compare_combo.findData(chosen) if chosen is not None else 0
        self.compare_combo.setCurrentIndex(max(index, 0))
        self.compare_combo.blockSignals(False)
        for widget in (self.compare_label, self.compare_combo, self.diff_button):
            widget.setVisible(bool(others) and current is not None)
        self._redraw()

    def comparison_run(self):
        number = self.compare_combo.currentData()
        return next((r for r in self._runs if r.number == number), None) if number is not None else None

    def input_differences(self) -> list:
        """``(input, shown run's value, compared run's value)`` rows."""
        from ..engine import scenario_diff

        other = self.comparison_run()
        if other is None or self._current_run is None:
            return []
        return scenario_diff.diff(self._current_run.scenario, other.scenario)

    def show_input_differences(self) -> None:
        from PySide6.QtWidgets import QDialog, QDialogButtonBox, QTableWidget, QTableWidgetItem

        from ..engine.scenario_diff import short

        other = self.comparison_run()
        rows = self.input_differences()
        dialog = QDialog(self)
        dialog.setWindowTitle("Input differences")
        dialog.resize(760, 420)  # [px]
        table = QTableWidget(len(rows), 3, dialog)
        table.setHorizontalHeaderLabels(["Input", f"Run {self._current_run.number} (shown)",
                                         f"Run {other.number}" if other else "-"])
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.verticalHeader().setVisible(False)
        for row, (path, mine, theirs) in enumerate(rows):
            for column, text in enumerate((path, short(mine), short(theirs))):
                item = QTableWidgetItem(text)
                item.setToolTip(str((path, mine, theirs)[column]))
                table.setItem(row, column, item)
        table.resizeColumnsToContents()
        table.horizontalHeader().setStretchLastSection(True)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, parent=dialog)
        buttons.rejected.connect(dialog.reject)
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel(f"{len(rows)} input(s) differ." if rows else "The inputs are the same."))
        layout.addWidget(table)
        layout.addWidget(buttons)
        dialog.exec()

    def _add_comparison_traces(self, fig: go.Figure, name: str, display) -> None:
        """The compared run's copy of ``name``, dashed, in the same colours."""
        other = self.comparison_run()
        series = other.result.series.get(name) if other is not None else None
        if series is None or series.data.shape[0] == 0:
            return
        if self._x_is_epoch and other.epoch_utc:
            try:
                x_values = np.asarray(list(time_system.elapsed_to_utc(other.epoch_utc, series.time_s)), dtype=object)
            except ValueError:
                return
        else:
            x_values = series.time_s / 3600.0  # [h]
        data = series.data * display.factor
        labels = display.columns or {}
        for i, column in enumerate(series.columns):
            if display.wrap_period:  # broken at the 0/360 wraps, as the shown run
                keep = _wrapping_display_indices(len(data))
                x_shown, y_shown = _break_at_wraps(x_values[keep], data[keep, i], display.wrap_period)
            else:
                keep = _display_indices(data[:, i])
                x_shown, y_shown = x_values[keep], data[keep, i]
            fig.add_trace(go.Scatter(
                x=list(x_shown) if x_values.dtype == object else x_shown, y=y_shown, mode="lines",
                name=f"{labels.get(column, column)} (Run {other.number})", opacity=0.75,
                line=dict(color=_SERIES_COLORS[i % len(_SERIES_COLORS)], width=2, dash="dash"),
            ))

    def set_vizard_file(self, path: Optional[str]) -> None:
        """Offer "Open in Vizard" for ``path`` (the run's playback file), or hide it."""
        self._vizard_file = path
        self.vizard_button.setVisible(bool(path))

    # -- the shared time cursor -------------------------------------------

    def set_time_cursor(self, cursor) -> None:
        """Follow ``cursor`` (a :class:`gui.time_cursor.TimeCursor`) and set it on a plot click."""
        self._time_cursor = cursor
        cursor.changed.connect(lambda _t: self.apply_cursor_line())
        self.apply_cursor_line()

    def plot_x_to_elapsed_s(self, x: str) -> Optional[float]:
        """Elapsed (TDB) seconds of a clicked x value: hours, or UTC text on an epoch axis."""
        try:
            if not self._x_is_epoch:
                return float(x) * 3600.0  # [s]
            clicked = datetime.fromisoformat(x.strip().replace("T", " "))
            epoch = datetime.fromisoformat(self._epoch_utc.replace("Z", "").replace("T", " "))
        except (TypeError, ValueError, AttributeError):
            return None
        first_guess = (clicked - epoch).total_seconds()  # [s]
        try:  # one correction for the TDB - UTC change since the epoch (time_system.elapsed_to_utc)
            back = time_system.elapsed_to_utc(self._epoch_utc, [first_guess])[0]
        except ValueError:
            return first_guess
        return first_guess + (clicked - back).total_seconds()  # [s]

    def _on_page_title(self, title: str) -> None:
        x = _clicked_x(title)
        if x is not None:
            self._on_plot_clicked(x)

    def _on_plot_clicked(self, x: str) -> None:
        time_s = self.plot_x_to_elapsed_s(x)
        if time_s is not None and self._time_cursor is not None:
            self._time_cursor.set_time(time_s)

    def cursor_x_literal(self) -> str:
        """The cursor as a JavaScript x value for the shown figure, or ``null``."""
        time_s = None if self._time_cursor is None else self._time_cursor.time_s
        if time_s is None or self.figure is None:
            return "null"
        if self._x_is_epoch:
            try:
                moment = time_system.elapsed_to_utc(self._epoch_utc, [time_s])[0]
            except ValueError:
                return "null"
            return json.dumps(moment.isoformat(sep=" "))
        return repr(time_s / 3600.0)  # [h]

    def apply_cursor_line(self) -> None:
        """Draw (or remove) the cursor line on the loaded plot, without a reload."""
        if self.figure is None:
            return
        script = f"""
        (function() {{
            var gd = document.getElementById({_PLOT_DIV_ID!r});
            if (typeof Plotly === 'undefined' || !gd || !gd.layout) {{ return; }}
            var x = {self.cursor_x_literal()};
            var shapes = (gd.layout.shapes || []).filter(function(s) {{ return s.name !== {_CURSOR_SHAPE!r}; }});
            if (x !== null) {{
                shapes.push({{type: 'line', name: {_CURSOR_SHAPE!r}, xref: 'x', yref: 'paper', x0: x, x1: x,
                              y0: 0, y1: 1, line: {{color: {_CURSOR_COLOR!r}, width: 2}}}});
            }}
            Plotly.relayout(gd, {{shapes: shapes}});
        }})();
        """
        self.web_view.page().runJavaScript(script)

    def _redraw(self) -> None:
        self._update_figure()
        self._push_figure_to_webview()
        self._update_suggestion_states()

    def _on_series_text_committed(self, text: str) -> None:
        """A series name was committed via the completer popup or by
        pressing Enter in the line edit -- see ``series_combo``'s own
        construction comment for why ``currentIndexChanged`` alone isn't
        a reliable signal for either of those paths. Explicitly syncs
        the combo's real selected index to match the committed text
        (not just its displayed string) before redrawing, so
        ``_redraw()``/``_on_save_plot_png()`` -- both of which read
        ``current_series_name()`` -- agree with what's actually
        showing.
        """
        index = self.series_combo.findText(text)
        if index < 0:
            index = self.series_combo.findData(text)  # a code name typed in full
        if index >= 0:
            self.series_combo.setCurrentIndex(index)
        self._redraw()

    def _on_export(self) -> None:
        if self._result is None:
            return
        out_dir = QFileDialog.getExistingDirectory(self, "Export results to CSV")
        if not out_dir:
            return
        try:
            paths = self._result.export_csv(Path(out_dir))
        except OSError as exc:
            QMessageBox.critical(self, "Export failed", str(exc))
            return
        QMessageBox.information(self, "Export complete", f"Wrote {len(paths)} CSV file(s) to {out_dir}")

    def _on_save_plot_svg(self) -> None:
        """Thin wrapper around :meth:`_on_save_plot_png` -- see that
        method's own docstring for the whole dialog/kickoff/poll
        mechanism, which is format-agnostic and shared as-is. Named/kept
        separate (rather than exposing ``fmt`` on the button's own
        ``clicked`` connection) purely so ``save_svg_button``'s signal
        handler has the same zero-argument shape every other button's
        does, and so a test can call it by name symmetrically with
        ``_on_save_plot_png()``.
        """
        self._on_save_plot_png(fmt="svg")

    def _on_save_plot_png(self, fmt: str = "png") -> None:
        """Saves the CURRENTLY DISPLAYED plot (only -- see
        ``_on_export`` for every series at once) to a user-chosen
        location via a native "Save As" dialog, as either a PNG
        (``fmt="png"``, the default -- every existing call site/test
        calls this with no arguments and must keep behaving exactly as
        before) or an SVG (``fmt="svg"``, via :meth:`_on_save_plot_svg`).
        Real user request for the PNG case ("would be great to also have
        a button to save the plots as png images in a desired
        location"); SVG added alongside it (roadmap item M2) for a plot
        a user wants to drop into a paper/report at arbitrary scale
        without it going blurry.

        Plotly's own modebar already has a built-in camera/download-as
        -png icon (``config={"displaylogo": False}`` above leaves it in;
        see this module's own docstring), but inside an embedded
        ``QWebEngineView`` that triggers Chromium's OWN download
        machinery, which this app never wires up
        (``QWebEngineProfile.downloadRequested``) -- confirmed directly
        that clicking it does nothing observable here, not assumed. This
        button instead renders the chart CLIENT-SIDE, via the SAME
        ``plotly.js`` already loaded on the page (``Plotly.toImage()``),
        rather than pulling in a server-side renderer (the ``kaleido``
        package) this project doesn't otherwise depend on -- consistent
        with this module's own "no unnecessary dependency" choice for
        ``plotly.js`` itself. ``scale: 2`` (meaningful for the PNG raster
        case; harmless/ignored by Plotly for SVG) asks for a
        higher-than-screen-resolution render (sharper on a high-DPI
        display/print) at the chart's own current on-screen size, rather
        than a hardcoded width/height that might not match what's
        actually visible.

        ``Plotly.toImage()`` is asynchronous (it returns a ``Promise``).
        ``QWebEnginePage.runJavaScript()`` does NOT await a top-level
        returned ``Promise`` on this PySide6 version (confirmed directly,
        not assumed -- an earlier version of this method relied on that
        and silently got back an empty string every time, which looked
        exactly like a render failure but wasn't one), so this instead
        kicks the render off into a page-global variable and polls for it
        via :meth:`_poll_plot_png` -- ``_SAVE_PNG_PENDING_SENTINEL``
        distinguishes "still rendering" from a real (possibly falsy)
        result, since a bare JS ``null``/``undefined`` also bridges back
        as an empty string here, not ``None`` as plain Python code might
        expect.
        """
        if self.figure is None:
            return
        if self._png_poll_state is not None:
            # Re-entrancy guard, same convention as
            # gui.kernel_status_widget.KernelStatusWidget.refresh()'s own:
            # a live-updating run calls _redraw() repeatedly (see its own
            # comment on why it must NOT blindly re-enable the save
            # buttons while a poll is in flight), but belt-and-suspenders
            # here too -- a second _on_save_plot_png() call (PNG or SVG,
            # either button) while one poll is already running would
            # overwrite self._png_poll_state AND the page-global JS
            # result variable both polls share, orphaning the first
            # poll_timer (nothing would ever stop it, since
            # state["timer"] would now point at the SECOND timer) -- it
            # would keep firing forever, re-triggering
            # _on_plot_png_rendered() (a duplicate file write + a
            # duplicate "saved" dialog, repeating every poll interval)
            # long after the user thinks they're done.
            return
        is_access_timeline = self.view_combo.currentData() == "access_timeline"
        default_name = f"{'access_timeline' if is_access_timeline else self.current_series_name()}.{fmt}"
        file_filter = "SVG images (*.svg)" if fmt == "svg" else "PNG images (*.png)"
        path, _ = QFileDialog.getSaveFileName(self, f"Save plot as {fmt.upper()}", default_name, file_filter)
        if not path:
            return
        if not path.lower().endswith(f".{fmt}"):
            path += f".{fmt}"

        # Guards against a second click (either button) racing this
        # one's own poll -- see the re-entrancy-guard comment above.
        self.save_png_button.setEnabled(False)
        self.save_svg_button.setEnabled(False)
        # tryRender's retry loop guards a real (if narrow) race: this
        # button's own enabled state is set synchronously inside
        # _redraw(), right after kicking off setHtml() -- but setHtml()
        # itself loads/executes the page (including plotly.js and the
        # Plotly.newPlot() call that defines window.Plotly) ASYNCHRONOUSLY.
        # An ordinary human click is far slower than that load, but an
        # automated one (a UI test, accessibility tooling) could win the
        # race and hit "Plotly is not defined" -- confirmed directly, not
        # hypothetical (this project's own test for this method did
        # exactly that before it was changed to wait for loadFinished).
        # A short, near-zero-cost-in-the-common-case retry loop is more
        # robust than asserting the race away.
        kickoff_script = f"""
        window.{_PNG_RESULT_JS_VAR} = {_SAVE_PNG_PENDING_SENTINEL!r};
        (function tryRender(attemptsLeft) {{
            var el = document.getElementById({_PLOT_DIV_ID!r});
            if (typeof Plotly === 'undefined' || !el) {{
                if (attemptsLeft > 0) {{
                    setTimeout(function() {{ tryRender(attemptsLeft - 1); }}, 50);
                }} else {{
                    window.{_PNG_RESULT_JS_VAR} = '{_SAVE_PNG_ERROR_PREFIX}the plot had not finished loading';
                }}
                return;
            }}
            Plotly.toImage(el, {{format: {fmt!r}, scale: 2}})
                .then(function(url) {{ window.{_PNG_RESULT_JS_VAR} = url; }})
                .catch(function(err) {{
                    window.{_PNG_RESULT_JS_VAR} =
                        '{_SAVE_PNG_ERROR_PREFIX}' + (err && err.message ? err.message : err);
                }});
        }})(40);
        """
        self.web_view.page().runJavaScript(kickoff_script)

        poll_timer = QTimer(self)
        self._png_poll_state = {"path": path, "fmt": fmt, "timer": poll_timer, "attempts": 0}
        poll_timer.timeout.connect(self._poll_plot_png)
        poll_timer.start(_SAVE_PNG_POLL_INTERVAL_MS)

    def _poll_plot_png(self) -> None:
        # runJavaScript() answers asynchronously, while the timer keeps
        # firing (SRelD K-08): a tick can arrive after the poll finished
        # (state None: the traceback in the CI logs), and on a slow machine
        # several queries could be in flight, each answer finishing the save
        # again (a second file write and "saved" dialog). One query at a
        # time, and answers to a finished poll are ignored.
        state = self._png_poll_state
        if state is None:
            return
        if state.get("in_flight"):
            # An answer that never comes must not stall the save: after a
            # second without one, ask again (a late answer is then ignored).
            state["waited_ticks"] = state.get("waited_ticks", 0) + 1
            if state["waited_ticks"] < _SAVE_PNG_MAX_WAIT_TICKS:
                return
        state["waited_ticks"] = 0
        state["attempts"] += 1
        state["in_flight"] = True

        def on_poll_result(value: object) -> None:
            state["in_flight"] = False
            if self._png_poll_state is not state:
                return  # this poll already finished (or was replaced)
            if value == _SAVE_PNG_PENDING_SENTINEL:
                if state["attempts"] >= _SAVE_PNG_MAX_POLL_ATTEMPTS:
                    state["timer"].stop()
                    self._png_poll_state = None  # see _on_save_plot_png's own re-entrancy-guard comment
                    self.save_png_button.setEnabled(self.figure is not None)
                    self.save_svg_button.setEnabled(self.figure is not None)
                    QMessageBox.critical(self, "Save failed", "Timed out waiting for the plot to render.")
                return
            state["timer"].stop()
            self._png_poll_state = None  # see _on_save_plot_png's own re-entrancy-guard comment
            self.save_png_button.setEnabled(self.figure is not None)
            self.save_svg_button.setEnabled(self.figure is not None)
            self._on_plot_png_rendered(value, state["path"], state["fmt"])

        self.web_view.page().runJavaScript(f"window.{_PNG_RESULT_JS_VAR}", on_poll_result)

    def _on_plot_png_rendered(self, data_url: object, path: str, fmt: str = "png") -> None:
        """Decodes ``data_url`` (``Plotly.toImage()``'s resolved value --
        see :meth:`_on_save_plot_png`'s own docstring for why this
        arrives via polling rather than an awaited ``Promise``) and
        writes it to ``path``. PNG and SVG use genuinely different
        encodings on the JS side -- confirmed directly against the
        installed ``plotly.min.js`` bundle's own ``encodeSVG``, not
        assumed -- so this is NOT a single shared prefix-strip: PNG is
        base64 (``data:image/png;base64,...``), SVG is a
        percent-encoded TEXT data URL (``data:image/svg+xml,...``,
        ``encodeURIComponent``-escaped, no base64 anywhere), decoded with
        ``urllib.parse.unquote`` and written as UTF-8 text, never
        ``base64.b64decode``.
        """
        if isinstance(data_url, str) and data_url.startswith(_SAVE_PNG_ERROR_PREFIX):
            QMessageBox.critical(self, "Save failed", data_url[len(_SAVE_PNG_ERROR_PREFIX):])
            return
        if fmt == "svg":
            prefix = "data:image/svg+xml,"
            if not isinstance(data_url, str) or not data_url.startswith(prefix):
                QMessageBox.critical(self, "Save failed", "Could not render the plot to an SVG image.")
                return
            try:
                svg_text = urllib.parse.unquote(data_url[len(prefix):])
                provenance = self._result.provenance if self._result is not None else None
                if provenance is not None:  # provenance on every output (UX/UI guidelines)
                    svg_text = output_provenance.svg_with_provenance(svg_text, provenance.summary_lines(),
                                                                     provenance.to_dict())
                Path(path).write_text(svg_text, encoding="utf-8")
            except OSError as exc:
                QMessageBox.critical(self, "Save failed", str(exc))
                return
            QMessageBox.information(self, "Plot saved", f"Saved plot to {path}")
            return
        prefix = "data:image/png;base64,"
        if not isinstance(data_url, str) or not data_url.startswith(prefix):
            QMessageBox.critical(self, "Save failed", "Could not render the plot to a PNG image.")
            return
        try:
            png_bytes = base64.b64decode(data_url[len(prefix):])
            provenance = self._result.provenance if self._result is not None else None
            if provenance is not None:  # provenance on every output (UX/UI guidelines)
                png_bytes = output_provenance.png_with_provenance(png_bytes, provenance.to_dict())
            Path(path).write_bytes(png_bytes)
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, "Save failed", str(exc))
            return
        QMessageBox.information(self, "Plot saved", f"Saved plot to {path}")
