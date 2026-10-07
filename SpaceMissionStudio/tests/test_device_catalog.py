"""Tests for engine.device_catalog -- the real-device preset catalog behind
gui.sensor_actuator_editor's "Select from catalog" picker (see that
module's own docstring for the direct user feedback this answers). This
module has no Basilisk import and is fully unit-testable here with no
sandbox dependency.
"""

import pytest


def test_every_entry_kind_is_a_supported_sensor_or_actuator_kind():
    from spacemissionstudio.engine.device_catalog import CATALOG
    from spacemissionstudio.schema.scenario import SUPPORTED_ACTUATOR_KINDS, SUPPORTED_SENSOR_KINDS

    for entry in CATALOG:
        assert entry.kind in SUPPORTED_SENSOR_KINDS or entry.kind in SUPPORTED_ACTUATOR_KINDS, (
            f"{entry.display_name}: kind {entry.kind!r} is not a schema-recognized sensor/actuator kind"
        )


def test_every_entry_has_real_sourcing_metadata():
    """Every catalog entry must cite where its specs came from and what
    its export-control status note is -- see the module's own docstring
    on why these are never left blank/placeholder.
    """
    from spacemissionstudio.engine.device_catalog import CATALOG

    for entry in CATALOG:
        assert entry.manufacturer.strip()
        assert entry.product_name.strip()
        assert entry.country.strip()
        assert entry.source_url.startswith("https://"), f"{entry.display_name}: source_url must be a real URL"
        assert entry.itar_free_note.strip()
        assert entry.description.strip()


def test_every_entry_satisfies_its_own_kinds_required_params():
    """Mirrors gui.sensor_actuator_editor._KIND_PARAM_SPECS's own
    required-key list -- a catalog entry missing a required key would
    make "Apply device preset" produce an invalid sensor/actuator that
    fails validation right after being applied, defeating the whole
    point of a working preset.
    """
    pytest.importorskip("PySide6")
    from spacemissionstudio.gui.sensor_actuator_editor import _missing_required_keys

    from spacemissionstudio.engine.device_catalog import CATALOG

    for entry in CATALOG:
        missing = _missing_required_keys(entry.kind, entry.params)
        assert not missing, f"{entry.display_name} ({entry.kind}): missing required params {missing}"


def test_every_entry_params_key_is_recognized_by_its_kind():
    """The converse check: every key an entry sets must be one
    _KIND_PARAM_SPECS actually knows about for that kind -- catches a
    typo'd key (e.g. a renamed schema field) that would silently vanish
    into the "Other params" JSON box or a vector row nobody reads.
    """
    pytest.importorskip("PySide6")
    from spacemissionstudio.gui.sensor_actuator_editor import _KIND_PARAM_SPECS

    from spacemissionstudio.engine.device_catalog import CATALOG

    for entry in CATALOG:
        known_keys = {spec.key for spec in _KIND_PARAM_SPECS.get(entry.kind, [])}
        for key in entry.params:
            assert key in known_keys, f"{entry.display_name}: params key {key!r} is not a known {entry.kind} param"


def test_vector_params_are_three_element_lists():
    from spacemissionstudio.engine.device_catalog import CATALOG

    for entry in CATALOG:
        for key, value in entry.params.items():
            if isinstance(value, list):
                assert len(value) == 3, f"{entry.display_name}: {key} must be a 3-element vector, got {value!r}"
                assert all(isinstance(v, (int, float)) for v in value)


def test_catalog_entries_for_kind_filters_and_preserves_order():
    from spacemissionstudio.engine.device_catalog import CATALOG, catalog_entries_for_kind

    for kind in {entry.kind for entry in CATALOG}:
        filtered = catalog_entries_for_kind(kind)
        assert filtered == [entry for entry in CATALOG if entry.kind == kind]
        assert all(entry.kind == kind for entry in filtered)


def test_catalog_entries_for_kind_returns_empty_not_an_error_for_unknown_kind():
    from spacemissionstudio.engine.device_catalog import catalog_entries_for_kind

    assert catalog_entries_for_kind("no_such_kind") == []


def test_every_sensor_and_actuator_kind_has_at_least_one_catalog_entry():
    """Not a hard requirement of the feature (gui.sensor_actuator_editor
    degrades gracefully for a kind with none), but every kind this
    project currently ships DOES have a real entry -- this test documents
    and protects that current state, so losing coverage for a kind is a
    visible, deliberate test change, not a silent regression.

    ``"thermal"`` is the one deliberate exception: unlike every other
    sensor kind (each a real, physical, separately-selectable piece of
    hardware -- a star tracker, an IMU, ...), it models the temperature of
    ANY flat-plate component already represented by one of the OTHER
    sensor/actuator entries (or by no sensor at all, e.g. the spacecraft
    bus itself) -- there is no distinct "thermal sensor" product to catalog
    separately, so a catalog entry for it would not represent a real,
    additional, sourceable device the way every other entry does.
    """
    from spacemissionstudio.engine.device_catalog import catalog_entries_for_kind
    from spacemissionstudio.schema.scenario import SUPPORTED_ACTUATOR_KINDS, SUPPORTED_SENSOR_KINDS

    kinds_needing_a_catalog_entry = [k for k in list(SUPPORTED_SENSOR_KINDS) + list(SUPPORTED_ACTUATOR_KINDS)
                                      if k != "thermal"]
    for kind in kinds_needing_a_catalog_entry:
        assert catalog_entries_for_kind(kind), f"{kind!r} has no catalog entry"


def test_display_name_includes_manufacturer_product_and_country():
    from spacemissionstudio.engine.device_catalog import CATALOG

    for entry in CATALOG:
        assert entry.manufacturer in entry.display_name
        assert entry.product_name in entry.display_name
        assert entry.country in entry.display_name


def test_every_entry_states_its_heritage_and_procurement_status():
    """Supplier-database entries (and the original ones, updated from it)
    carry the database's flight heritage and procurement status, so the
    catalog picker shows them next to the export-control note."""
    from spacemissionstudio.engine.device_catalog import CATALOG

    for entry in CATALOG:
        assert entry.heritage.strip(), entry.display_name
        assert entry.procurement_status.strip(), entry.display_name


def test_no_supplier_database_entry_is_development_or_flagged_export_risk():
    """The inclusion rule: no 'Development - monitor' product, and no product
    the database flags 'Check / export risk' -- except the one pre-existing
    entry kept for existing scenarios, which says so in its note."""
    from spacemissionstudio.engine.device_catalog import CATALOG

    for entry in CATALOG:
        assert not entry.procurement_status.startswith("Development"), entry.display_name
        if entry.procurement_status.startswith("Check"):
            assert entry.product_name == "RSI 04-33-60A", entry.display_name
            assert "export risk" in entry.itar_free_note


def test_display_names_are_unique():
    from spacemissionstudio.engine.device_catalog import CATALOG

    names = [entry.display_name for entry in CATALOG]
    assert len(names) == len(set(names))
