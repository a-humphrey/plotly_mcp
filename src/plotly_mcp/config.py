"""Configuration via environment variables."""

import os
from pathlib import Path


def get_output_dir() -> Path:
    """Return the output directory, creating it if needed."""
    d = Path(os.environ.get("PLOTLY_MCP_OUTPUT_DIR", str(Path.home() / "plotly_mcp_output")))
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_default_format() -> str:
    return os.environ.get("PLOTLY_MCP_DEFAULT_FORMAT", "html")


def get_default_width() -> int:
    return int(os.environ.get("PLOTLY_MCP_DEFAULT_WIDTH", "800"))


def get_default_height() -> int:
    return int(os.environ.get("PLOTLY_MCP_DEFAULT_HEIGHT", "600"))
