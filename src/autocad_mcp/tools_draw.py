"""Drawing tools. Create-only (no delete/modify of existing objects). Each call is one undo step."""
from __future__ import annotations

import math
from typing import Any, Sequence

from . import cad, config


def _num(v: Any, name: str) -> float:
    try:
        f = float(v)
    except (TypeError, ValueError):
        raise cad.CadError(f"{name} must be a number") from None
    if not math.isfinite(f):
        raise cad.CadError(f"{name} must be finite")
    return f


def _positive(v: Any, name: str) -> float:
    f = _num(v, name)
    if f <= 0:
        raise cad.CadError(f"{name} must be > 0")
    return f


def _pt(p: Sequence[float], name: str) -> tuple[float, float, float]:
    if not isinstance(p, (list, tuple)) or len(p) not in (2, 3):
        raise cad.CadError(f"{name} must be [x, y] or [x, y, z]")
    vals = [_num(v, name) for v in p]
    return (vals[0], vals[1], vals[2] if len(vals) == 3 else 0.0)


def _pts2d(points: Sequence[Sequence[float]], minimum: int = 2) -> list[tuple[float, float]]:
    if not isinstance(points, (list, tuple)) or not minimum <= len(points) <= config.MAX_POINTS:
        raise cad.CadError(f"points must be a list of {minimum} to {config.MAX_POINTS} items")
    return [_pt(p, "point")[:2] for p in points]


def _finish(obj: Any, layer: str | None) -> str:
    if layer:
        obj.Layer = layer
    return obj.Handle


def add_polyline_raw(pts: list[tuple[float, float]], closed: bool, layer: str | None) -> str:
    """Add a polyline without its own undo group (caller owns the group). Returns handle."""
    obj = cad.with_retry(lambda: cad.get_modelspace().AddLightWeightPolyline(cad.to_flat_2d(pts)))
    obj.Closed = bool(closed)
    return _finish(obj, layer)


def _check_layer(layer: str | None) -> None:
    if layer:
        cad.ensure_layer(layer)


def create_layer(name: str, color_index: int | None = None) -> str:
    """Create a layer if missing (optional AutoCAD color index 1-255). Returns the name."""
    if not name or not name.strip():
        raise cad.CadError("name must not be empty")
    if color_index is not None and not 1 <= int(color_index) <= 255:
        raise cad.CadError("color_index must be 1-255")
    with cad.undo_group():
        return cad.ensure_layer(name.strip(), color_index)


def draw_line(start: list[float], end: list[float], layer: str | None = None) -> str:
    """Draw a line. Returns its handle."""
    s, e = _pt(start, "start"), _pt(end, "end")
    with cad.undo_group():
        _check_layer(layer)
        obj = cad.with_retry(lambda: cad.get_modelspace().AddLine(cad.to_point(*s), cad.to_point(*e)))
        return _finish(obj, layer)


def draw_polyline(points: list[list[float]], closed: bool = False,
                  layer: str | None = None) -> str:
    """Draw a 2D lightweight polyline through [x, y] points. Returns its handle."""
    pts = _pts2d(points, 2)
    with cad.undo_group():
        _check_layer(layer)
        return add_polyline_raw(pts, closed, layer)


def draw_rectangle(origin: list[float], width: float, height: float,
                   rotation_deg: float = 0.0, layer: str | None = None) -> str:
    """Closed rectangle polyline from its lower-left corner, rotated about origin. Returns handle."""
    ox, oy, _ = _pt(origin, "origin")
    w, h = _positive(width, "width"), _positive(height, "height")
    a = math.radians(_num(rotation_deg, "rotation_deg"))
    c, s = math.cos(a), math.sin(a)
    pts = [(ox + x * c - y * s, oy + x * s + y * c) for x, y in ((0, 0), (w, 0), (w, h), (0, h))]
    return draw_polyline([list(p) for p in pts], closed=True, layer=layer)


def draw_circle(center: list[float], radius: float, layer: str | None = None) -> str:
    """Draw a circle. Returns its handle."""
    c, r = _pt(center, "center"), _positive(radius, "radius")
    with cad.undo_group():
        _check_layer(layer)
        obj = cad.with_retry(lambda: cad.get_modelspace().AddCircle(cad.to_point(*c), r))
        return _finish(obj, layer)


def add_text(position: list[float], text: str, height: float, layer: str | None = None) -> str:
    """Add single-line text. Returns its handle."""
    p, h = _pt(position, "position"), _positive(height, "height")
    if not text or len(text) > 1000:
        raise cad.CadError("text must be 1-1000 characters")
    with cad.undo_group():
        _check_layer(layer)
        obj = cad.with_retry(lambda: cad.get_modelspace().AddText(text, cad.to_point(*p), h))
        return _finish(obj, layer)


def zoom_extents() -> str:
    """Zoom the view to show all objects."""
    cad.with_retry(lambda: cad.get_app().ZoomExtents())
    return "ok"


def register(mcp) -> None:
    for fn in (create_layer, draw_line, draw_polyline, draw_rectangle,
               draw_circle, add_text, zoom_extents):
        mcp.tool()(fn)
