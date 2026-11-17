"""FastMCP app entry point. NEVER print to stdout (it carries MCP traffic)."""
import logging
import sys

from mcp.server.fastmcp import FastMCP

logging.basicConfig(stream=sys.stderr, level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("autocad_mcp")

mcp = FastMCP("autocad")


def main() -> None:
    log.info("Starting AutoCAD MCP server (stdio)")
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
