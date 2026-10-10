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

"""The startup fetch/update prompt -- the one piece of this app's
"closed-off/offline" policy that runs automatically, once, each time the
GUI starts (everything else that touches the network, e.g.
``gui.vizard_launcher.fetch_vizard``, is reached only via an explicit,
separate user click). Real user decision this module exists to satisfy:
"A one time fetch during each startup of the app is also allowed, to
store everything that is needed locally so it can be used later again.
But the user always should be asked if they want to fetch/update."

So: :func:`maybe_run_startup_fetch` is called once per
``gui.main_window.MainWindow`` session (see that class's own
``prompt_startup_fetch`` constructor parameter), and it ALWAYS shows
:class:`StartupFetchDialog` first -- there is no "don't ask again"
setting, no silent default, and nothing here ever fetches anything
before the user clicks "Fetch now". Clicking "Skip" (or unchecking both
items) touches no network at all, same as if this module didn't exist.

Two independent items, either/both selectable:

* **Support-data kernels** (``engine.kernels.ensure_kernels()``) -- the
  SPICE/gravity-harmonics/magnetic-field files every packaging/
  installer already pre-fetches once at install time. Re-running this is
  a no-op (no network touched) if everything is already cached; it only
  matters as a safety net for a dev checkout or a corrupted/cleared
  cache.
* **Real space-weather history** (``engine.spaceweather.fetch``) -- a
  real CelesTrak F10.7/Ap CSV, downloaded fresh every time the user
  agrees (``force=True``: asking again each startup implies "check for
  an update", not "only if missing"), cached locally. Once fetched, it's
  an ordinary local file -- ``gui.propagation_setup_dialog`` pre-fills
  its Local file field with the most recently fetched path (via
  ``engine.spaceweather.cached_fetch_path()``) as a convenience, so using
  it needs no further network access, same as any other user-supplied
  CSV.

Both run on a background :class:`StartupFetchWorker` thread (the same
cooperative-QThread pattern already used by
``gui.kernel_status_widget``/``gui.vizard_launcher``), so a slow or
stalled network call never freezes the GUI; this prompt's own progress
dialog has no Cancel button (unlike the Vizard download's cooperative
cancellation) since both fetches here are normally fast cache-hits, and
a real fetch that hangs is better surfaced by letting it time out
(``requests``/``urllib`` timeouts already apply inside each) than by
adding cancellation machinery for a rare case.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from PySide6.QtCore import QEventLoop, Qt, QThread, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QMessageBox,
    QProgressDialog,
    QVBoxLayout,
    QWidget,
)

_logger = logging.getLogger(__name__)


class StartupFetchWorker(QThread):
    """Runs the selected fetch(es) on a background thread. Constructed
    and started only from :func:`maybe_run_startup_fetch`, itself only
    reached after :class:`StartupFetchDialog`'s "Fetch now" button was
    clicked -- never automatically.
    """

    finished_all = Signal(dict)  # {"kernels": (ok, message), "space_weather": (ok, message)}

    def __init__(self, fetch_kernels: bool, fetch_space_weather: bool, parent: Optional[QWidget] = None,
                 fetch_earth_orientation: bool = False):
        super().__init__(parent)
        self.fetch_kernels = fetch_kernels
        self.fetch_space_weather = fetch_space_weather
        self.fetch_earth_orientation = fetch_earth_orientation

    def run(self) -> None:
        # finished_all MUST be emitted no matter what -- maybe_run_startup_fetch()
        # waits for it inside a blocking QEventLoop behind a progress dialog
        # with NO cancel button (see that function's own docstring on why).
        # If anything below raised past this point uncaught, that loop would
        # never be told to quit() and the dialog would hang forever with no
        # way for the user to dismiss it. _fetch_kernels/_fetch_space_weather
        # already catch their own expected failures, but this outer guard
        # (matching gui.kernel_status_widget._KernelFetchWorker's own
        # broad-except convention) is what makes that a GUARANTEE rather
        # than something that merely holds today.
        result = {}
        try:
            if self.fetch_kernels:
                result["kernels"] = self._fetch_kernels()
            if self.fetch_space_weather:
                result["space_weather"] = self._fetch_space_weather()
            if self.fetch_earth_orientation:
                result["earth_orientation"] = self._fetch_earth_orientation()
        except Exception as exc:  # noqa: BLE001 -- see the comment above: this signal must always fire
            _logger.exception("Startup fetch failed unexpectedly")
            result["error"] = (False, str(exc))
        self.finished_all.emit(result)

    @staticmethod
    def _fetch_kernels() -> "tuple[bool, str]":
        try:
            from ..engine import kernels
        except ImportError as exc:
            return False, (
                f"Basilisk is not installed/built ({exc}) -- support-data kernels are unavailable until it is."
            )
        try:
            statuses = kernels.ensure_kernels()
        except Exception as exc:  # noqa: BLE001 -- surface ANY failure, never crash the worker thread silently
            _logger.exception("Startup kernel fetch failed")
            return False, str(exc)
        ok_count = sum(1 for s in statuses if s.available)
        if ok_count == len(statuses):
            return True, f"{ok_count}/{len(statuses)} support-data file(s) available."
        failed = "; ".join(f"{s.name} ({s.error})" for s in statuses if not s.available)
        return False, f"{ok_count}/{len(statuses)} support-data file(s) available -- failed: {failed}"

    @staticmethod
    def _fetch_earth_orientation() -> "tuple[bool, str]":
        from ..engine import earth_orientation as eo
        try:
            kernels = eo.fetch()
        except eo.EarthOrientationError as exc:
            return False, str(exc)
        until = eo.high_accuracy_until(kernels)
        return True, (f"{len(kernels)} file(s), ITRF93, high accuracy until {until:%Y-%m-%d}" if until
                      else f"{len(kernels)} file(s), ITRF93")

    @staticmethod
    def _fetch_space_weather() -> "tuple[bool, str]":
        from ..engine import spaceweather as sw
        try:
            path = sw.fetch(dataset="SW-All", force=True)
        except sw.SpaceWeatherError as exc:
            return False, str(exc)
        return True, str(path)


class StartupFetchDialog(QDialog):
    """The consent prompt itself. Two independently selectable
    checkboxes (both checked by default, matching the "opt out of a
    specific item" rather than "opt in" framing this app's own installer
    pre-fetch already uses), "Fetch now"/"Skip" buttons. Never
    auto-accepts -- the user must click one or the other.
    """

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("Fetch/update data?")
        layout = QVBoxLayout(self)

        label = QLabel(
            "SpaceMissionStudio runs fully offline otherwise. It can optionally check for updates now, "
            "at startup, and store the result locally so no further network access is needed until you "
            "agree again next time. This requires internet access."
        )
        label.setWordWrap(True)
        label.setMaximumWidth(420)
        layout.addWidget(label)

        from ..engine.reference_data import DOWNLOADS

        support, weather = DOWNLOADS["support_data"], DOWNLOADS["space_weather"]
        self.kernels_checkbox = QCheckBox(f"Support data (SPICE, gravity, magnetic field) -- {support.approx_size}")
        self.kernels_checkbox.setChecked(True)
        self.kernels_checkbox.setToolTip(
            f"From {support.source}: {', '.join(support.files)}. "
            "Normally only needed once, ever (every packaging/ installer already pre-fetches these) -- "
            "this is a safety net for a dev checkout or a corrupted/cleared cache, and a no-op (no "
            "network touched) if everything is already cached."
        )
        layout.addWidget(self.kernels_checkbox)

        self.space_weather_checkbox = QCheckBox(f"Space weather from CelesTrak (SW-All.csv) -- {weather.approx_size}")
        self.space_weather_checkbox.setChecked(True)
        self.space_weather_checkbox.setToolTip(
            f"From {weather.source}. The file is checked before it replaces the current one, which is kept "
            "for rollback (Data tab). Downloads a real F10.7/Ap CSV, refreshed every time you agree. The Propagation Setup "
            "dialog's Local file field pre-fills with it automatically once fetched."
        )
        layout.addWidget(self.space_weather_checkbox)

        from ..engine import earth_orientation as eo

        installed = eo.installed()
        until = eo.high_accuracy_until(installed)
        self.earth_orientation_checkbox = QCheckBox("Earth orientation from NAIF (ITRF93 Earth PCKs) -- about 36 MB")
        # Checked when nothing is installed or the high-accuracy span is over.
        self.earth_orientation_checkbox.setChecked(not installed or until is None or until < datetime.now(timezone.utc).replace(tzinfo=None))
        self.earth_orientation_checkbox.setToolTip(
            f"From {eo.NAIF_PCK_URL}: the combined (1962-2126) and the high-precision Earth PCK with their "
            "comment files. The previous files are kept for rollback.\n"
            + (f"Installed: high accuracy until {until:%Y-%m-%d}." if until else "Not installed: runs use IAU_EARTH."))
        layout.addWidget(self.earth_orientation_checkbox)

        buttons = QDialogButtonBox()
        self.fetch_button = buttons.addButton("Fetch now", QDialogButtonBox.ButtonRole.AcceptRole)
        self.skip_button = buttons.addButton("Skip", QDialogButtonBox.ButtonRole.RejectRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def selected_earth_orientation(self) -> bool:
        return self.earth_orientation_checkbox.isChecked()

    def selected(self) -> "tuple[bool, bool]":
        """``(fetch_kernels, fetch_space_weather)``."""
        return self.kernels_checkbox.isChecked(), self.space_weather_checkbox.isChecked()


def maybe_run_startup_fetch(parent: QWidget) -> None:
    """Shows :class:`StartupFetchDialog`; on "Fetch now" with at least one
    item checked, runs :class:`StartupFetchWorker` behind a progress
    dialog and shows a one-line-per-item summary. Does nothing at all --
    no network touched -- if the user clicks "Skip", closes the dialog,
    or unchecks both items.
    """
    dialog = StartupFetchDialog(parent)
    if dialog.exec() != QDialog.DialogCode.Accepted:
        return

    fetch_kernels, fetch_space_weather = dialog.selected()
    fetch_earth_orientation = dialog.selected_earth_orientation()
    if not fetch_kernels and not fetch_space_weather and not fetch_earth_orientation:
        return

    # cancelButtonText=None (not "") -- the real Qt idiom for "no cancel
    # button at all", not an empty-looking one; see this module's own
    # docstring on why there's nothing to cancel here.
    progress = QProgressDialog("Fetching/updating...", None, 0, 0, parent)
    progress.setWindowModality(Qt.WindowModality.WindowModal)
    progress.setMinimumDuration(0)
    progress.setAutoClose(False)
    progress.setAutoReset(False)

    worker = StartupFetchWorker(fetch_kernels, fetch_space_weather, parent=parent,
                                fetch_earth_orientation=fetch_earth_orientation)
    loop = QEventLoop()
    outcome: dict = {}

    def on_finished(result: dict) -> None:
        outcome.update(result)
        loop.quit()

    worker.finished_all.connect(on_finished)
    worker.start()
    progress.show()
    # See gui.main_window.MainWindow._fetch_vizard_with_progress's own
    # comment on this exact idiom: QEventLoop.quit() is a no-op if the
    # loop isn't running yet, so a worker that finishes synchronously
    # inside start() needs this outcome check before the unconditional
    # exec() below, or it would hang forever waiting for a quit() that
    # already happened.
    if not outcome:
        loop.exec()
    progress.close()
    worker.wait()

    lines = []
    if "kernels" in outcome:
        _ok, message = outcome["kernels"]
        lines.append(f"Support-data kernels: {message}")
    if "space_weather" in outcome:
        ok, message = outcome["space_weather"]
        if ok:
            lines.append(f"Space weather: fetched and cached at {message}")
        else:
            lines.append(f"Space weather: could not fetch ({message})")
    if "earth_orientation" in outcome:
        ok, message = outcome["earth_orientation"]
        lines.append(f"Earth orientation: {message}" if ok else f"Earth orientation: could not fetch ({message})")
    if "error" in outcome:
        # See StartupFetchWorker.run()'s own comment: this key only
        # appears if something unexpected (not one of the specific,
        # already-handled failure modes above) blew up mid-fetch -- still
        # surfaced here rather than silently dropped, even though it
        # can't be attributed to "kernels" or "space weather" specifically.
        _ok, message = outcome["error"]
        lines.append(f"Fetch/update failed unexpectedly: {message}")

    if lines:
        QMessageBox.information(parent, "Fetch/update complete", "\n\n".join(lines))
