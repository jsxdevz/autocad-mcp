"""Read-only tools."""
from __future__ import annotations

from typing import Any

from . import cad

_TYPE_ALIASES = {"line": "AcDbLine", "polyline": "AcDbPolyline", "circle": "AcDbCircle",
                 "text": "AcDbText", "mtext": "AcDbMText", "arc": "AcDbArc"}


def _pt(p: Any) -> list[float]:
    return [round(float(v), 6) for v in p]


def _bbox(obj: Any) -> dict | None:
    try:
        lo, hi = obj.GetBoundingBox()
        return {"min": _pt(lo), "max": _pt(hi)}
    except Exception:  # noqa: BLE001
        return None


def get_drawing_info() -> dict:
    """Name, path, INSUNITS and ModelSpace object count of the active drawing."""
    doc = cad.get_doc()
    return {
        "name": doc.Name,
        "path": doc.FullName,
        "saved": bool(doc.Saved),
        "insunits": doc.GetVariable("INSUNITS"),
        "object_count": cad.with_retry(lambda: doc.ModelSpace.Count),
    }


def list_layers() -> list[dict]:
    """All layers with color index, on/off and locked state."""
    doc = cad.get_doc()
    out = []
    for i in range(doc.Layers.Count):
        ly = doc.Layers.Item(i)
        out.append({"name": ly.Name, "color": ly.Color,
                    "on": bool(ly.LayerOn), "locked": bool(ly.Lock)})
    return out


def list_objects(layer: str | None = None, type: str | None = None,
                 limit: int = 200) -> dict:
    """List ModelSpace objects (handle, type, layer, bbox). type: line/polyline/circle/text/mtext/arc or a raw ObjectName."""
    if not 1 <= limit <= 2000:
        raise cad.CadError("limit must be between 1 and 2000")
    wanted = _TYPE_ALIASES.get(type.lower(), type) if type else None
    ms = cad.get_modelspace()
    items: list[dict] = []
    for i in range(ms.Count):
        obj = ms.Item(i)
        if layer and obj.Layer != layer:
            continue
        if wanted and obj.ObjectName != wanted:
            continue
        items.append({"handle": obj.Handle, "type": obj.ObjectName,
                      "layer": obj.Layer, "bbox": _bbox(obj)})
        if len(items) >= limit:
            break
    return {"objects": items, "truncated": len(items) >= limit}


def get_polyline(handle: str) -> dict:
    """Points (x, y), closed flag, area and length of a lightweight polyline."""
    doc = cad.get_doc()
    try:
        obj = doc.HandleToObject(handle)
    except Exception as exc:  # noqa: BLE001
        raise cad.CadError(f"Object with handle {handle} not found") from exc
    if obj.ObjectName != "AcDbPolyline":
        raise cad.CadError(f"Object {handle} is not a lightweight polyline ({obj.ObjectName})")
    flat = list(obj.Coordinates)
    pts = [[flat[i], flat[i + 1]] for i in range(0, len(flat) - 1, 2)]
    return {"handle": handle, "points": pts, "closed": bool(obj.Closed),
            "area": float(obj.Area), "length": float(obj.Length)}


def get_text_in_layer(layer: str) -> list[dict]:
    """Text/MText strings and positions on a layer."""
    ms = cad.get_modelspace()
    out = []
    for i in range(ms.Count):
        obj = ms.Item(i)
        if obj.Layer == layer and obj.ObjectName in ("AcDbText", "AcDbMText"):
            out.append({"handle": obj.Handle, "text": obj.TextString,
                        "position": _pt(obj.InsertionPoint)})
    return out


def register(mcp) -> None:
    for fn in (get_drawing_info, list_layers, list_objects, get_polyline, get_text_in_layer):
        mcp.tool()(fn)
