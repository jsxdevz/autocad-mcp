"""Rectangular-grid solar panel layout. Pure shapely, no COM.

Limitations: grid-based (not a theoretical optimum), ignores shading from
neighbouring buildings, does not replace engineering design.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Sequence

from shapely.affinity import rotate
from shapely.geometry import Polygon, box
from shapely.geometry.base import BaseGeometry
from shapely.prepared import prep

Point = tuple[float, float]
_EPS = 1e-6  # tolerance for float error when testing containment
_OFFSET_FRACTIONS = (0.0, 0.25, 0.5, 0.75)


@dataclass
class LayoutResult:
    panels: list[Polygon] = field(default_factory=list)
    orientation_used: str = "portrait"
    boundary_area: float = 0.0
    usable_area: float = 0.0
    rotation_deg: float = 0.0

    @property
    def panel_count(self) -> int:
        return len(self.panels)


def longest_edge_angle(poly: Polygon) -> float:
    """Angle (deg) of the longest exterior edge, normalised to [0, 180)."""
    coords = list(poly.exterior.coords)
    best, angle = -1.0, 0.0
    for (x1, y1), (x2, y2) in zip(coords, coords[1:]):
        length = math.hypot(x2 - x1, y2 - y1)
        if length > best:
            best, angle = length, math.degrees(math.atan2(y2 - y1, x2 - x1))
    return angle % 180.0


def _usable_area(boundary: Polygon, obstacles: Sequence[Polygon],
                 edge_setback: float, obstacle_clearance: float) -> BaseGeometry:
    usable = boundary.buffer(-edge_setback, join_style="mitre") if edge_setback > 0 else boundary
    for ob in obstacles:
        blocked = ob.buffer(obstacle_clearance, join_style="mitre") if obstacle_clearance > 0 else ob
        usable = usable.difference(blocked)
    return usable


def _grid(usable: BaseGeometry, w: float, h: float, gap_x: float, gap_y: float,
          ox_frac: float, oy_frac: float) -> list[Polygon]:
    minx, miny, maxx, maxy = usable.bounds
    step_x, step_y = w + gap_x, h + gap_y
    test = prep(usable.buffer(_EPS))
    out: list[Polygon] = []
    y = miny + oy_frac * step_y
    while y + h <= maxy + _EPS:
        x = minx + ox_frac * step_x
        while x + w <= maxx + _EPS:
            rect = box(x, y, x + w, y + h)
            if test.contains(rect):
                out.append(rect)
            x += step_x
        y += step_y
    return out


def _best_grid(usable: BaseGeometry, w: float, h: float, gap_x: float, gap_y: float,
               optimize_offset: bool) -> list[Polygon]:
    if usable.is_empty:
        return []
    fractions = _OFFSET_FRACTIONS if optimize_offset else (0.0,)
    best: list[Polygon] = []
    for fx in fractions:
        for fy in fractions:
            cand = _grid(usable, w, h, gap_x, gap_y, fx, fy)
            if len(cand) > len(best):
                best = cand
    return best


def layout_panels(
    boundary: Sequence[Point],
    obstacles: Sequence[Sequence[Point]] = (),
    *,
    panel_length: float,
    panel_width: float,
    orientation: str = "auto",
    gap_x: float = 0.0,
    gap_y: float = 0.0,
    edge_setback: float = 0.0,
    obstacle_clearance: float = 0.0,
    rotation_deg: float | None = None,
    optimize_offset: bool = True,
) -> LayoutResult:
    """Place panels inside `boundary`. Returns panel rectangles in original coordinates."""
    if panel_length <= 0 or panel_width <= 0:
        raise ValueError("panel size must be > 0")
    if min(gap_x, gap_y, edge_setback, obstacle_clearance) < 0:
        raise ValueError("gaps, setback and clearance must be >= 0")
    if orientation not in ("portrait", "landscape", "auto"):
        raise ValueError("orientation must be portrait, landscape or auto")

    poly = Polygon(boundary)
    if poly.is_empty or not poly.is_valid or poly.area <= 0:
        raise ValueError("boundary is not a valid polygon")
    obs = []
    for o in obstacles:
        op = Polygon(o)
        if op.is_empty or not op.is_valid:
            raise ValueError("an obstacle is not a valid polygon")
        obs.append(op)

    angle = longest_edge_angle(poly) if rotation_deg is None else float(rotation_deg)
    center = poly.centroid
    # Work in a frame where the grid is axis-aligned.
    rpoly = rotate(poly, -angle, origin=center)
    robs = [rotate(o, -angle, origin=center) for o in obs]
    usable = _usable_area(rpoly, robs, edge_setback, obstacle_clearance)

    result = LayoutResult(boundary_area=poly.area, usable_area=usable.area,
                          rotation_deg=angle)
    orientations = ("portrait", "landscape") if orientation == "auto" else (orientation,)
    best: list[Polygon] = []
    for ori in orientations:
        w, h = (panel_width, panel_length) if ori == "portrait" else (panel_length, panel_width)
        cand = _best_grid(usable, w, h, gap_x, gap_y, optimize_offset)
        if len(cand) > len(best) or (not result.panels and not best):
            best = cand
            result.orientation_used = ori
    result.panels = [rotate(p, angle, origin=center) for p in best]
    return result
