"""MCP tools for solar layout: reads boundary from CAD, runs layout, optionally draws."""
from __future__ import annotations

import math

from .. import cad, config, tools_draw, tools_read
from . import layout, spacing

_LIMITATIONS = ("Grid-based layout (not a theoretical optimum); ignores shading from nearby "
                "buildings; polyline arcs (bulges) are treated as straight segments. "
                "Preliminary only: must be reviewed by an engineer.")


def _closed_polyline_points(handle: str, what: str) -> list[tuple[float, float]]:
    pl = tools_read.get_polyline(handle)
    if not pl["closed"]:
        raise cad.CadError(f"{what} {handle} must be a closed polyline")
    return [tuple(p) for p in pl["points"]]


def layout_solar_panels(
    panel_length: float,
    panel_width: float,
    panel_watt: float,
    boundary_handle: str | None = None,
    boundary_points: list[list[float]] | None = None,
    obstacle_handles: list[str] | None = None,
    orientation: str = "auto",
    gap_x: float = 0.02,
    gap_y: float = 0.02,
    edge_setback: float = 0.5,
    obstacle_clearance: float = 0.5,
    rotation_deg: float | None = None,
    unit_scale: float = 1.0,
    dry_run: bool = True,
) -> dict:
    """Lay out solar panels inside a closed boundary polyline.

    Panel sizes, gaps, setback and clearance are in the user's unit; multiply by unit_scale
    to get drawing units (e.g. drawing in mm, inputs in metres -> unit_scale=1000).
    Boundary points/handles are in drawing units; reported areas are in drawing units squared.
    dry_run=true (default) computes only and does NOT modify the drawing.
    """
    if (boundary_handle is None) == (boundary_points is None):
        raise cad.CadError("Provide exactly one of boundary_handle or boundary_points")
    for name, v in (("panel_length", panel_length), ("panel_width", panel_width),
                    ("panel_watt", panel_watt), ("unit_scale", unit_scale)):
        if not isinstance(v, (int, float)) or not math.isfinite(v) or v <= 0:
            raise cad.CadError(f"{name} must be > 0")
    for name, v in (("gap_x", gap_x), ("gap_y", gap_y), ("edge_setback", edge_setback),
                    ("obstacle_clearance", obstacle_clearance)):
        if not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0:
            raise cad.CadError(f"{name} must be >= 0")
    if orientation not in ("portrait", "landscape", "auto"):
        raise cad.CadError("orientation must be portrait, landscape or auto")

    if boundary_handle is not None:
        boundary = _closed_polyline_points(boundary_handle, "Boundary")
    else:
        boundary = [tuple(map(float, p[:2])) for p in boundary_points]
        if not 3 <= len(boundary) <= config.MAX_POINTS:
            raise cad.CadError(f"boundary_points must have 3 to {config.MAX_POINTS} points")
    obstacles = [_closed_polyline_points(h, "Obstacle") for h in (obstacle_handles or [])]

    s = float(unit_scale)
    try:
        res = layout.layout_panels(
            boundary, obstacles,
            panel_length=panel_length * s, panel_width=panel_width * s,
            orientation=orientation, gap_x=gap_x * s, gap_y=gap_y * s,
            edge_setback=edge_setback * s, obstacle_clearance=obstacle_clearance * s,
            rotation_deg=rotation_deg)
    except ValueError as exc:
        raise cad.CadError(str(exc)) from exc

    count = res.panel_count
    kwp = count * panel_watt / 1000.0
    out: dict = {
        "panel_count": count,
        "total_kwp": round(kwp, 3),
        "orientation_used": res.orientation_used,
        "rotation_deg_used": round(res.rotation_deg, 3),
        "area_boundary": round(res.boundary_area, 3),
        "area_usable": round(res.usable_area, 3),
        "coverage_ratio": round(
            sum(p.area for p in res.panels) / res.boundary_area, 4) if res.boundary_area else 0.0,
        "dry_run": dry_run,
        "limitations": _LIMITATIONS,
    }
    origins = [[round(p.exterior.coords[0][0], 3), round(p.exterior.coords[0][1], 3)]
               for p in res.panels[:50]]
    out["panel_origins"] = origins
    out["panel_origins_truncated"] = count > 50

    if dry_run:
        return out
    if count == 0:
        out["handles"] = {"panels": [], "text": None}
        return out
    if count > config.MAX_PANELS_DRAWN:
        raise cad.CadError(f"{count} panels exceeds the per-call drawing limit "
                           f"({config.MAX_PANELS_DRAWN}); use dry_run or a smaller area")

    bx = [p[0] for p in boundary]
    by = [p[1] for p in boundary]
    text_h = 0.03 * max(max(bx) - min(bx), max(by) - min(by))
    summary = f"Panels: {count} | {kwp:.2f} kWp | {res.orientation_used}"
    with cad.undo_group():
        cad.ensure_layer(config.LAYER_SOLAR_PANEL)
        cad.ensure_layer(config.LAYER_SOLAR_TEXT)
        handles = [
            tools_draw.add_polyline_raw(list(p.exterior.coords)[:-1], True,
                                        config.LAYER_SOLAR_PANEL)
            for p in res.panels
        ]
        text_obj = cad.with_retry(lambda: cad.get_modelspace().AddText(
            summary, cad.to_point(min(bx), min(by) - 2 * text_h), text_h))
        text_obj.Layer = config.LAYER_SOLAR_TEXT
        out["handles"] = {"panels": handles, "text": text_obj.Handle}
    return out


def compute_row_spacing(panel_length: float, tilt_deg: float, latitude_deg: float,
                        design_hour_note: str | None = None) -> dict:
    """Row pitch for tilted panels (noon at winter solstice). Preliminary estimate."""
    try:
        return spacing.compute_row_spacing(panel_length, tilt_deg, latitude_deg,
                                           design_hour_note)
    except ValueError as exc:
        raise cad.CadError(str(exc)) from exc


def register(mcp) -> None:
    mcp.tool()(layout_solar_panels)
    mcp.tool()(compute_row_spacing)
