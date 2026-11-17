# AutoCAD MCP Server

MCP server (Python, FastMCP, stdio) that lets Claude drive an open AutoCAD 2022 on Windows via COM.
Work on a COPY of your drawing first. Solar layout results are preliminary and must be checked by an engineer.

## Setup
```
python -m venv .venv
.venv\Scripts\pip install -e .[dev]
.venv\Scripts\python -m autocad_mcp.server
```
See plan.md for milestones and tool list.
