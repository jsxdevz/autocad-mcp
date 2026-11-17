"""Row spacing for tilted panels on flat roofs/ground. Preliminary estimate only."""
from __future__ import annotations

import math

AXIAL_TILT_DEG = 23.44
NOTE = ("Preliminary estimate (noon on winter solstice, no terrain/obstruction shading). "
        "Must be confirmed by an engineer.")


def compute_row_spacing(panel_length: float, tilt_deg: float, latitude_deg: float,
                        design_hour_note: str | None = None) -> dict:
    if panel_length <= 0:
        raise ValueError("panel_length must be > 0")
    if not 0 < tilt_deg < 90:
        raise ValueError("tilt_deg must be between 0 and 90 (exclusive)")
    if abs(latitude_deg) > 90:
        raise ValueError("latitude_deg must be within -90..90")
    alpha = 90.0 - abs(latitude_deg) - AXIAL_TILT_DEG
    if alpha <= 0:
        raise ValueError("Sun altitude at winter solstice noon is <= 0 at this latitude; "
                         "row spacing cannot be computed with this method")
    t = math.radians(tilt_deg)
    height = panel_length * math.sin(t)
    shadow = height / math.tan(math.radians(alpha))
    pitch = panel_length * math.cos(t) + shadow
    out = {"pitch": pitch, "shadow_length": shadow, "alpha_used": alpha, "note": NOTE}
    if design_hour_note:
        out["design_hour_note"] = design_hour_note
    return out
