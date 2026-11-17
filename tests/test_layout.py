import math

import pytest
from shapely.affinity import rotate
from shapely.geometry import Polygon

from autocad_mcp.solar.layout import layout_panels
from autocad_mcp.solar.spacing import compute_row_spacing

L, W = 2.278, 1.134
ROOF = [(0, 0), (10, 0), (10, 6), (0, 6)]
KW = dict(panel_length=L, panel_width=W, gap_x=0.02, gap_y=0.02, edge_setback=0.5,
          rotation_deg=0)


def test_rectangle_hand_count():
    # usable 9 x 5 m. portrait: 7 cols x 2 rows = 14; landscape: 3 x 4 = 12.
    p = layout_panels(ROOF, orientation="portrait", **KW)
    l = layout_panels(ROOF, orientation="landscape", **KW)
    assert (p.panel_count, l.panel_count) == (14, 12)


def test_auto_picks_more_panels():
    r = layout_panels(ROOF, orientation="auto", **KW)
    assert r.panel_count == 14 and r.orientation_used == "portrait"
    assert r.boundary_area == pytest.approx(60) and r.usable_area == pytest.approx(45)


def test_obstacle_in_middle_hand_count():
    # obstacle 4..6 x 2..4, clearance 0.5 -> blocked 3.5..6.5 x 1.5..4.5.
    # Plain grid from corner: 7 columns, columns 3..6 of index 2-5 hit blocked zone -> 3 cols x 2 rows = 6.
    ob = [[(4, 2), (6, 2), (6, 4), (4, 4)]]
    r = layout_panels(ROOF, ob, orientation="portrait", obstacle_clearance=0.5,
                      optimize_offset=False, **KW)
    assert r.panel_count == 6
    blocked = Polygon([(3.5, 1.5), (6.5, 1.5), (6.5, 4.5), (3.5, 4.5)])
    assert all(not p.intersects(blocked.buffer(-1e-6)) for p in r.panels)
    # optimising the offset can never be worse
    assert layout_panels(ROOF, ob, orientation="portrait", obstacle_clearance=0.5,
                         **KW).panel_count >= 6


def test_l_shape_unit_panels_fill_exactly():
    ell = [(0, 0), (10, 0), (10, 3), (4, 3), (4, 8), (0, 8)]  # area 50
    r = layout_panels(ell, panel_length=1, panel_width=1, orientation="portrait",
                      rotation_deg=0)
    assert r.panel_count == 50


def test_setback_too_large_gives_zero_not_crash():
    r = layout_panels(ROOF, orientation="auto", **{**KW, "edge_setback": 5})
    assert r.panel_count == 0 and r.usable_area == 0


def test_panel_larger_than_roof():
    assert layout_panels(ROOF, panel_length=20, panel_width=15, rotation_deg=0).panel_count == 0


def test_panels_are_inside_boundary_and_disjoint():
    r = layout_panels(ROOF, orientation="auto", **KW)
    roof = Polygon(ROOF)
    for i, a in enumerate(r.panels):
        assert roof.buffer(1e-6).contains(a)
        for b in r.panels[i + 1:]:
            assert a.intersection(b).area < 1e-9


def test_default_rotation_follows_longest_edge():
    rotated = rotate(Polygon(ROOF), 30, origin=(0, 0))
    pts = list(rotated.exterior.coords)[:-1]
    kw = {k: v for k, v in KW.items() if k != "rotation_deg"}
    r = layout_panels(pts, orientation="portrait", **kw)
    assert r.panel_count == 14
    assert r.rotation_deg == pytest.approx(30, abs=1e-6)


@pytest.mark.parametrize("kwargs", [
    dict(panel_length=0, panel_width=1),
    dict(panel_length=1, panel_width=1, gap_x=-1),
    dict(panel_length=1, panel_width=1, orientation="diagonal"),
])
def test_bad_params(kwargs):
    with pytest.raises(ValueError):
        layout_panels(ROOF, **kwargs)


def test_bad_boundary():
    with pytest.raises(ValueError):
        layout_panels([(0, 0), (1, 1), (1, 0), (0, 1)], panel_length=1, panel_width=1)


def test_row_spacing_chiang_mai():
    r = compute_row_spacing(2.278, 15, 18.8)
    alpha = 90 - 18.8 - 23.44
    shadow = 2.278 * math.sin(math.radians(15)) / math.tan(math.radians(alpha))
    assert r["alpha_used"] == pytest.approx(47.76)
    assert r["shadow_length"] == pytest.approx(shadow)
    assert r["pitch"] == pytest.approx(2.278 * math.cos(math.radians(15)) + shadow)
    assert 2.7 < r["pitch"] < 2.8  # hand calc ~2.736


def test_row_spacing_invalid():
    with pytest.raises(ValueError):
        compute_row_spacing(2, 0, 18)
    with pytest.raises(ValueError):
        compute_row_spacing(2, 15, 70)  # sun never rises at solstice noon
    with pytest.raises(ValueError):
        compute_row_spacing(-1, 15, 18)
