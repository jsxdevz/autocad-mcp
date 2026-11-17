import pytest

from autocad_mcp import cad
from autocad_mcp.solar import tools_solar

ROOF = [[0, 0], [10, 0], [10, 6], [0, 6]]
ARGS = dict(panel_length=2.278, panel_width=1.134, panel_watt=550, rotation_deg=0,
            orientation="portrait", gap_x=0.02, gap_y=0.02, edge_setback=0.5)


@pytest.fixture
def no_cad(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("dry_run must not touch AutoCAD")
    monkeypatch.setattr(cad, "get_doc", boom)
    monkeypatch.setattr(cad, "get_modelspace", boom)
    monkeypatch.setattr(cad, "ensure_layer", boom)


def test_dry_run_never_touches_cad(no_cad):
    r = tools_solar.layout_solar_panels(boundary_points=ROOF, **ARGS)
    assert r["dry_run"] and r["panel_count"] == 14
    assert r["total_kwp"] == pytest.approx(7.7)
    assert "handles" not in r


def test_boundary_from_handle(monkeypatch):
    monkeypatch.setattr(tools_solar.tools_read, "get_polyline",
                        lambda h: {"points": ROOF, "closed": True})
    assert tools_solar.layout_solar_panels(boundary_handle="1A", **ARGS)["panel_count"] == 14


def test_open_polyline_rejected(monkeypatch):
    monkeypatch.setattr(tools_solar.tools_read, "get_polyline",
                        lambda h: {"points": ROOF, "closed": False})
    with pytest.raises(cad.CadError, match="closed"):
        tools_solar.layout_solar_panels(boundary_handle="1A", **ARGS)


def test_unit_scale_mm():
    mm = [[x * 1000, y * 1000] for x, y in ROOF]
    r = tools_solar.layout_solar_panels(boundary_points=mm, unit_scale=1000, **ARGS)
    assert r["panel_count"] == 14


def test_needs_exactly_one_boundary():
    with pytest.raises(cad.CadError):
        tools_solar.layout_solar_panels(**ARGS)
    with pytest.raises(cad.CadError):
        tools_solar.layout_solar_panels(boundary_handle="1", boundary_points=ROOF, **ARGS)


def test_invalid_numbers():
    with pytest.raises(cad.CadError):
        tools_solar.layout_solar_panels(boundary_points=ROOF, **{**ARGS, "panel_watt": 0})


def test_row_spacing_error_wrapped():
    with pytest.raises(cad.CadError):
        tools_solar.compute_row_spacing(2, 15, 80)
