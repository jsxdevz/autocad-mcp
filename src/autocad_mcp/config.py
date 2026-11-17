"""Default settings. Edit ALLOWED_EXPORT_DIRS before using file tools."""
from pathlib import Path

LAYER_SOLAR_PANEL = "SOLAR_PANEL"
LAYER_SOLAR_TEXT = "SOLAR_TEXT"

# Folders where file tools may write. Empty = all file writes rejected.
ALLOWED_EXPORT_DIRS: list[Path] = [Path.home() / "Documents" / "autocad-mcp-exports"]

MAX_POINTS = 10_000
MAX_PANELS_DRAWN = 5_000
RETRY_ATTEMPTS = 5
RETRY_DELAY_S = 0.5
