---
name: install-autocad-mcp
description: Install and register this AutoCAD MCP server on the user's machine (venv, dependencies, claude mcp add, verification). Use when the user asks to install, set up, or register the autocad MCP, or runs /install-autocad-mcp.
---

# Install AutoCAD MCP

Goal: take a fresh clone of this repo to a working `autocad` MCP server registered with Claude Code. Work from the repo root (the folder containing `pyproject.toml`). Report each step's result briefly; stop and explain if a step fails.

## 1. Preconditions (check, do not fix silently)

- OS must be Windows (the server uses pywin32 COM). If not, stop and say so.
- Python >= 3.10. Try `py -3 --version`, then `python --version`. Note: the Microsoft Store `python` shortcut prints "Python was not found" — treat that as missing. If no usable Python, tell the user to install it from python.org and stop.
- AutoCAD installed (README tested with AutoCAD 2022). It does not need to be open for installation, only for use.

## 2. Create venv and install

Use PowerShell. Skip venv creation if `.venv\Scripts\python.exe` already exists.

```powershell
py -3 -m venv .venv          # or: python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

## 3. Run the tests

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Tests must not need AutoCAD. If they fail, show the failing output and stop; do not register a broken install.

## 4. Register the MCP server

Use the absolute path of the venv python (Claude does not activate venvs). Resolve it with `(Resolve-Path .\.venv\Scripts\python.exe).Path`.

First check `claude mcp list`. If an `autocad` entry already exists, show it and ask the user before replacing it.

```powershell
claude mcp add autocad -- "<ABSOLUTE>\.venv\Scripts\python.exe" -m autocad_mcp.server
```

Default scope is local to this project. If the user wants it available in every project, add `--scope user`. If the `claude` CLI is unavailable (Claude Desktop only), instead show the user this JSON for `claude_desktop_config.json` with the absolute path filled in, and let them paste it themselves:

```json
{
  "mcpServers": {
    "autocad": {
      "command": "<ABSOLUTE>\\.venv\\Scripts\\python.exe",
      "args": ["-m", "autocad_mcp.server"]
    }
  }
}
```

## 5. Verify

- `claude mcp list` should show `autocad` as connected.
- Tell the user to open AutoCAD with a drawing, restart Claude, then call `get_drawing_info`. A new MCP server is only picked up after a restart.

## 6. Final report

State what was done and what was not verified (e.g. AutoCAD connection not tested). Remind the user:

- Work on a COPY of the drawing first.
- Solar layout results are preliminary and must be checked by an engineer.
