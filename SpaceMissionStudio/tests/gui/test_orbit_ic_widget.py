"""Tests for gui.orbit_ic_widget.OrbitIcWidget."""

import pytest

pytestmark = pytest.mark.requires_gui


@pytest.fixture
def widget(qtbot):
    from spacemissionstudio.gui.orbit_ic_widget import OrbitIcWidget

    w = OrbitIcWidget()
    qtbot.addWidget(w)
    return w


def test_default_is_classical_elements(widget):
    oe = widget.to_dataclass()
    assert oe.type == "classical_elements"
    assert oe.semi_major_axis_km == 7000.0


def test_editing_a_field_emits_changed_and_updates_value(widget, qtbot):
    with qtbot.waitSignal(widget.changed, timeout=1000):
        widget.sma_km.setValue(8000.0)
    assert widget.to_dataclass().semi_major_axis_km == 8000.0


def test_compute_sso_inclination_button_writes_inc_deg(widget, qtbot):
    from spacemissionstudio.engine.orbit_design import sun_synchronous_inclination_deg

    widget.sma_km.setValue(6878.1366)
    widget.ecc.setValue(0.0)
    widget.inc_deg.setValue(0.0)
    widget._on_compute_sso_inclination()
    assert widget.inc_deg.value() == pytest.approx(sun_synchronous_inclination_deg(6878.1366), abs=1.0e-6)


def test_compute_sso_raan_button_writes_raan_deg_using_epoch_provider(widget, qtbot):
    from spacemissionstudio.engine.orbit_design import raan_for_ltan_deg

    widget.set_epoch_provider(lambda: "2030-01-01T00:00:00")
    widget.sso_ltan_hour.setValue(10.5)
    widget.raan_deg.setValue(0.0)
    widget._on_compute_sso_raan()
    assert widget.raan_deg.value() == pytest.approx(raan_for_ltan_deg("2030-01-01T00:00:00", 10.5), abs=1.0e-6)


def test_compute_sso_raan_button_warns_with_no_epoch_provider(widget, qtbot, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    warned = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: warned.append(a))
    widget.raan_deg.setValue(42.0)
    widget._on_compute_sso_raan()
    assert warned  # a warning dialog was shown
    assert widget.raan_deg.value() == 42.0  # left untouched


def test_switching_type_emits_changed_and_updates_dataclass(widget, qtbot):
    with qtbot.waitSignal(widget.changed, timeout=1000):
        widget.type_combo.setCurrentIndex(widget.type_combo.findData("cartesian"))
    cart = widget.to_dataclass()
    assert cart.type == "cartesian"
    assert cart.position_km == [7000.0, 0.0, 0.0]


@pytest.mark.parametrize("orbit_kwargs", [
    dict(type="classical_elements", semi_major_axis_km=6800.0, eccentricity=0.01,
         inclination_deg=45.0, raan_deg=10.0, arg_periapsis_deg=20.0, true_anomaly_deg=30.0),
    dict(type="classical_elements", semi_major_axis_km=6800.0, eccentricity=0.01,
         inclination_deg=45.0, raan_deg=10.0, arg_periapsis_deg=20.0,
         anomaly_type="mean", mean_anomaly_deg=15.0),
    dict(type="cartesian", position_km=[1.0, 2.0, 3.0], velocity_km_s=[4.0, 5.0, 6.0]),
    dict(type="tle", tle_line1="1 25544U", tle_line2="2 25544"),
])
def test_from_dataclass_round_trips(widget, orbit_kwargs):
    from spacemissionstudio.schema.scenario import OrbitIC

    orbit = OrbitIC(**orbit_kwargs)
    widget.from_dataclass(orbit)
    got = widget.to_dataclass()
    assert got == orbit


def test_default_classical_elements_uses_true_anomaly(widget):
    oe = widget.to_dataclass()
    assert oe.anomaly_type == "true"
    assert oe.true_anomaly_deg == 0.0
    assert oe.mean_anomaly_deg is None


def test_switching_anomaly_type_to_mean_updates_dataclass(widget, qtbot):
    from spacemissionstudio.schema.scenario import ANOMALY_TYPES

    assert set(ANOMALY_TYPES) == {"true", "mean"}
    with qtbot.waitSignal(widget.changed, timeout=1000):
        widget.anomaly_type_combo.setCurrentIndex(widget.anomaly_type_combo.findData("mean"))
    widget.anomaly_deg.setValue(42.0)

    oe = widget.to_dataclass()
    assert oe.anomaly_type == "mean"
    assert oe.mean_anomaly_deg == 42.0
    assert oe.true_anomaly_deg is None


def test_from_dataclass_rejects_unknown_type(widget):
    from spacemissionstudio.schema.scenario import OrbitIC

    with pytest.raises(ValueError, match="doesn't know orbit type"):
        widget.from_dataclass(OrbitIC(type="wormhole"))


@pytest.mark.requirement("E-ST-10-09C 5.3.1b")
def test_tle_page_shows_the_tle_epoch_age_or_the_format_problem(widget):
    """Pasting a TLE shows its epoch and its distance from the scenario
    epoch; a wrong checksum shows the reason instead."""
    from spacemissionstudio.schema.scenario import OrbitIC

    line1 = "1 25544U 98067A   19343.69339541  .00001764  00000-0  38792-4 0  9991"
    line2 = "2 25544  51.6439 211.2001 0007417  17.6667  85.6398 15.50103472202482"
    widget.set_epoch_provider(lambda: "2019-12-20T00:00:00")
    widget.from_dataclass(OrbitIC(type="tle", tle_line1=line1, tle_line2=line2))
    assert widget.tle_status.text() == "2019-12-09 16:38:29 UTC (10.3 d before the scenario epoch)"
    widget.tle_line1.setText(line1[:-1] + "2")
    assert "checksum" in widget.tle_status.text()
