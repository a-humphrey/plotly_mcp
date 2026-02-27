"""Generic Plotly trace engine — supports all trace types via dynamic dispatch."""

from __future__ import annotations

import datetime
import difflib
import inspect
from pathlib import Path
from typing import Any

import plotly.graph_objects as go
from plotly.subplots import make_subplots

from .config import get_default_height, get_default_width, get_output_dir


# ---------------------------------------------------------------------------
# Dynamic trace-type map — built once at import time
# ---------------------------------------------------------------------------

def _build_trace_type_map() -> dict[str, type]:
    """Inspect plotly.graph_objects for all top-level trace classes."""
    result: dict[str, type] = {}
    for name in dir(go):
        cls = getattr(go, name)
        if (
            inspect.isclass(cls)
            and hasattr(cls, "_parent_path_str")
            and cls._parent_path_str == ""
            and hasattr(cls, "_valid_props")
            and name not in ("Figure", "FigureWidget", "Frame", "Layout")
        ):
            result[name.lower()] = cls
    return result


TRACE_TYPE_MAP: dict[str, type] = _build_trace_type_map()

# Subplot type detection for dashboard auto-configuration
TRACE_SUBPLOT_TYPES: dict[str, str] = {}
_DOMAIN_TYPES = {"pie", "funnelarea", "sunburst", "treemap", "icicle", "sankey",
                 "indicator", "table", "parcats", "parcoords"}
_SCENE_TYPES = {"scatter3d", "mesh3d", "cone", "streamtube", "isosurface",
                "volume", "surface"}
_POLAR_TYPES = {"scatterpolar", "scatterpolargl", "barpolar"}
_GEO_TYPES = {"scattergeo", "choropleth"}
_MAPBOX_TYPES = {"scattermapbox", "choroplethmapbox", "densitymapbox"}
_TERNARY_TYPES = {"scatterternary"}
_SMITH_TYPES = {"scattersmith"}

for _tname in TRACE_TYPE_MAP:
    if _tname in _DOMAIN_TYPES:
        TRACE_SUBPLOT_TYPES[_tname] = "domain"
    elif _tname in _SCENE_TYPES:
        TRACE_SUBPLOT_TYPES[_tname] = "scene"
    elif _tname in _POLAR_TYPES:
        TRACE_SUBPLOT_TYPES[_tname] = "polar"
    elif _tname in _GEO_TYPES:
        TRACE_SUBPLOT_TYPES[_tname] = "geo"
    elif _tname in _MAPBOX_TYPES:
        TRACE_SUBPLOT_TYPES[_tname] = "mapbox"
    elif _tname in _TERNARY_TYPES:
        TRACE_SUBPLOT_TYPES[_tname] = "ternary"
    elif _tname in _SMITH_TYPES:
        TRACE_SUBPLOT_TYPES[_tname] = "smith"
    else:
        TRACE_SUBPLOT_TYPES[_tname] = "xy"


# Legacy aliases → (real_plotly_type, default_kwargs)
LEGACY_ALIASES: dict[str, tuple[str, dict[str, Any]]] = {
    "line": ("scatter", {"mode": "lines"}),
    "area": ("scatter", {"fill": "tozeroy"}),
    "scatter_3d": ("scatter3d", {}),
}

# Dashboard grid presets
DASHBOARD_PRESETS: dict[str, dict[str, Any]] = {
    "2x1": {"rows": 2, "cols": 1},
    "1x2": {"rows": 1, "cols": 2},
    "2x2": {"rows": 2, "cols": 2},
    "2x3": {"rows": 2, "cols": 3},
    "sidebar": {
        "rows": 1, "cols": 2,
        "column_widths": [0.7, 0.3],
    },
    "header_grid": {
        "rows": 2, "cols": 1,
        "row_heights": [0.3, 0.7],
    },
}

# Public list of supported types — all Plotly trace types + legacy aliases
SUPPORTED_CHART_TYPES = sorted(set(list(TRACE_TYPE_MAP.keys()) + list(LEGACY_ALIASES.keys())))


# ---------------------------------------------------------------------------
# Trace resolution
# ---------------------------------------------------------------------------

def resolve_trace_class(trace_type: str) -> tuple[type, dict[str, Any]]:
    """Normalize a trace type string and return (TraceClass, default_kwargs).

    Checks legacy aliases first, then the dynamic map.
    Raises ValueError with similar-name suggestions on miss.
    """
    key = trace_type.lower().strip().replace("-", "").replace("_", "")

    # Check legacy aliases (use original key with underscores for alias lookup)
    alias_key = trace_type.lower().strip()
    if alias_key in LEGACY_ALIASES:
        real_type, defaults = LEGACY_ALIASES[alias_key]
        return TRACE_TYPE_MAP[real_type], defaults

    # Check direct match (normalized without underscores/hyphens)
    if key in TRACE_TYPE_MAP:
        return TRACE_TYPE_MAP[key], {}

    # Also check with the original underscored form
    original_key = trace_type.lower().strip()
    if original_key in TRACE_TYPE_MAP:
        return TRACE_TYPE_MAP[original_key], {}

    # No match — suggest similar names
    all_names = list(TRACE_TYPE_MAP.keys()) + list(LEGACY_ALIASES.keys())
    close = difflib.get_close_matches(alias_key, all_names, n=3, cutoff=0.5)
    suggestion = f" Did you mean: {', '.join(close)}?" if close else ""
    raise ValueError(
        f"Unknown trace type '{trace_type}'.{suggestion} "
        f"Use the plotly://chart-types resource for a full list."
    )


# ---------------------------------------------------------------------------
# Generic chart builder
# ---------------------------------------------------------------------------

def build_chart_generic(traces: list[dict], layout: dict | None = None) -> go.Figure:
    """Build a Figure from a list of trace dicts.

    Each trace dict must have a "type" key. All other keys are passed
    directly to the Plotly trace constructor as kwargs.
    """
    fig = go.Figure()
    for i, trace_dict in enumerate(traces):
        trace_dict = dict(trace_dict)  # shallow copy
        type_str = trace_dict.pop("type", None)
        if type_str is None:
            raise ValueError(f"Trace at index {i} is missing a 'type' key.")
        cls, defaults = resolve_trace_class(type_str)
        merged = {**defaults, **trace_dict}
        fig.add_trace(cls(**merged))

    if layout:
        fig.update_layout(**layout)
    return fig


# ---------------------------------------------------------------------------
# Dashboard builder
# ---------------------------------------------------------------------------

def build_dashboard(
    panels: list[dict],
    grid: dict | None = None,
    preset: str | None = None,
    layout: dict | None = None,
) -> go.Figure:
    """Build a multi-panel dashboard figure using make_subplots.

    Args:
        panels: List of panel dicts, each with "row", "col", and "traces" (list of trace dicts).
        grid: Dict with "rows" and "cols" (and optional "column_widths", "row_heights").
        preset: Named preset from DASHBOARD_PRESETS (e.g. "2x2", "sidebar").
        layout: Optional layout dict applied after subplot creation.
    """
    # Resolve grid config
    if preset:
        if preset not in DASHBOARD_PRESETS:
            raise ValueError(
                f"Unknown preset '{preset}'. Available: {list(DASHBOARD_PRESETS.keys())}"
            )
        grid_config = dict(DASHBOARD_PRESETS[preset])
    elif grid:
        grid_config = dict(grid)
    else:
        # Auto-detect from panels
        max_row = max(p.get("row", 1) for p in panels)
        max_col = max(p.get("col", 1) for p in panels)
        grid_config = {"rows": max_row, "cols": max_col}

    rows = grid_config.pop("rows")
    cols = grid_config.pop("cols")

    # Detect subplot specs from trace types
    specs = [[{"type": "xy"} for _ in range(cols)] for _ in range(rows)]
    for panel in panels:
        r = panel.get("row", 1) - 1
        c = panel.get("col", 1) - 1
        traces = panel.get("traces", [])
        if traces:
            first_type = traces[0].get("type", "scatter")
            _, _ = resolve_trace_class(first_type)  # validate
            resolved_key = first_type.lower().strip()
            # Resolve through aliases
            if resolved_key in LEGACY_ALIASES:
                resolved_key = LEGACY_ALIASES[resolved_key][0]
            subplot_type = TRACE_SUBPLOT_TYPES.get(resolved_key, "xy")
            specs[r][c] = {"type": subplot_type}

    fig = make_subplots(rows=rows, cols=cols, specs=specs, **grid_config)

    # Add traces to each panel
    for panel in panels:
        r = panel.get("row", 1)
        c = panel.get("col", 1)
        for trace_dict in panel.get("traces", []):
            trace_dict = dict(trace_dict)
            type_str = trace_dict.pop("type", "scatter")
            cls, defaults = resolve_trace_class(type_str)
            merged = {**defaults, **trace_dict}
            fig.add_trace(cls(**merged), row=r, col=c)

    if layout:
        fig.update_layout(**layout)
    return fig


# ---------------------------------------------------------------------------
# Backward-compatible build_chart
# ---------------------------------------------------------------------------

def build_chart(chart_type: str, data: dict, layout: dict | None = None) -> go.Figure:
    """Build a Figure for the given chart type (backward-compatible API).

    Accepts old-style data dicts with a "style" key merged into trace kwargs.
    """
    data = dict(data)  # shallow copy to avoid mutating caller's dict
    style = data.pop("style", {})

    # Resolve the trace class and get alias defaults
    cls, alias_defaults = resolve_trace_class(chart_type)

    # Merge: alias defaults < data fields < explicit style overrides
    merged = {**alias_defaults, **data, **style}

    fig = go.Figure()
    fig.add_trace(cls(**merged))

    if layout:
        fig.update_layout(**layout)
    return fig


# ---------------------------------------------------------------------------
# Save logic
# ---------------------------------------------------------------------------

def save_chart(
    fig: go.Figure,
    output_format: str = "html",
    filename: str | None = None,
    width: int | None = None,
    height: int | None = None,
) -> list[str]:
    """Save figure to file(s). Returns list of saved file paths."""
    out_dir = get_output_dir()
    w = width or get_default_width()
    h = height or get_default_height()
    base = filename or f"chart_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
    base = Path(base).stem

    fmt = output_format.lower().strip()
    saved: list[str] = []

    try:
        if fmt in ("html", "both"):
            path = out_dir / f"{base}.html"
            fig.write_html(str(path), include_plotlyjs=True)
            saved.append(str(path))

        if fmt in ("png", "both"):
            path = out_dir / f"{base}.png"
            fig.write_image(str(path), width=w, height=h, engine="kaleido")
            saved.append(str(path))
    except Exception:
        raise

    if not saved:
        raise ValueError(f"Invalid output_format '{output_format}'. Use html, png, or both.")

    return saved


# ---------------------------------------------------------------------------
# Error parsing helper
# ---------------------------------------------------------------------------

def _parse_plotly_error(e: Exception) -> dict[str, str]:
    """Extract structured info from a Plotly/ValueError exception."""
    msg = str(e)

    # Truncate Plotly's verbose property lists
    if len(msg) > 500:
        # Try to keep the "Did you mean" part
        did_you_mean = ""
        if "Did you mean" in msg:
            idx = msg.index("Did you mean")
            did_you_mean = " " + msg[idx:idx + 200]
        msg = msg[:300] + "..." + did_you_mean

    result: dict[str, str] = {"message": msg}

    if "Invalid property" in msg or "invalid value" in msg.lower():
        result["type"] = "invalid_property"
    elif "did you mean" in msg.lower():
        result["type"] = "invalid_property"
    else:
        result["type"] = "validation_error"

    # Extract suggestion if present
    if "did you mean" in msg.lower():
        idx = msg.lower().index("did you mean")
        result["suggestion"] = msg[idx:idx + 200].strip()

    return result
