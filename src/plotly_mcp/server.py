"""FastMCP server exposing Plotly chart tools."""

from __future__ import annotations

import json
import logging
import sys
from typing import Any

from mcp.server.fastmcp import FastMCP, Image

from .charts import (
    DASHBOARD_PRESETS,
    SUPPORTED_CHART_TYPES,
    TRACE_SUBPLOT_TYPES,
    TRACE_TYPE_MAP,
    _parse_plotly_error,
    build_chart,
    build_chart_generic,
    build_dashboard,
    save_chart,
)
from .config import get_default_format, get_default_refresh_interval
from .dashboard_server import start_server, stop_server
from .data_utils import load_dataframe, summarize_dataframe
from .live_dashboard import build_live_dashboard, save_live_dashboard

# Log to stderr — required for stdio transport
logging.basicConfig(stream=sys.stderr, level=logging.INFO)
logger = logging.getLogger("plotly-mcp")

mcp = FastMCP("plotly-charts")


# ---------------------------------------------------------------------------
# Resource: supported chart types reference (dynamic)
# ---------------------------------------------------------------------------

@mcp.resource("plotly://chart-types")
def chart_types_resource() -> str:
    """List all supported Plotly trace types, organized by subplot category."""
    categories: dict[str, list[str]] = {}
    for name, stype in TRACE_SUBPLOT_TYPES.items():
        categories.setdefault(stype, []).append(name)

    result = {
        "total_types": len(TRACE_TYPE_MAP),
        "categories": {cat: sorted(types) for cat, types in sorted(categories.items())},
        "legacy_aliases": {
            alias: real_type
            for alias, (real_type, _) in sorted(
                # import here to avoid circular — already imported at top
                __import__("plotly_mcp.charts", fromlist=["LEGACY_ALIASES"]).LEGACY_ALIASES.items()
            )
        },
        "dashboard_presets": list(DASHBOARD_PRESETS.keys()),
    }
    return json.dumps(result, indent=2)


# ---------------------------------------------------------------------------
# Resource: trace property info
# ---------------------------------------------------------------------------

@mcp.resource("plotly://trace-info/{trace_type}")
def trace_info_resource(trace_type: str) -> str:
    """Return valid properties for a specific Plotly trace type."""
    from .charts import resolve_trace_class

    try:
        cls, defaults = resolve_trace_class(trace_type)
    except ValueError as e:
        return json.dumps({"error": str(e)})

    props = sorted(cls._valid_props) if hasattr(cls, "_valid_props") else []
    return json.dumps({
        "trace_type": trace_type,
        "plotly_class": cls.__name__,
        "subplot_type": TRACE_SUBPLOT_TYPES.get(cls.__name__.lower(), "xy"),
        "default_kwargs": defaults if defaults else None,
        "valid_properties": props,
        "property_count": len(props),
    }, indent=2)


# ---------------------------------------------------------------------------
# Tool 1: create_chart
# ---------------------------------------------------------------------------

@mcp.tool()
def create_chart(
    chart_type: str | None = None,
    data: dict[str, Any] | None = None,
    traces: list[dict[str, Any]] | None = None,
    layout: dict[str, Any] | None = None,
    output_format: str | None = None,
    width: int | None = None,
    height: int | None = None,
    filename: str | None = None,
) -> list:
    """Create a Plotly chart. Supports ANY Plotly trace type with full property pass-through.

    Two calling conventions:
      1. Simple (backward-compatible): chart_type + data dict
      2. Advanced (multi-trace): traces list of dicts, each with a "type" key

    All Plotly trace properties can be passed directly — no restrictions.
    Use the plotly://chart-types resource for available types, or
    plotly://trace-info/{type} for valid properties of a specific type.

    Args:
        chart_type: Plotly trace type (e.g. "bar", "scatter", "candlestick",
                    "sankey", "indicator"). Use with 'data' for single-trace charts.
        data: Chart data dict — all keys are passed to the Plotly trace constructor.
              Include a "style" key to separate styling from data.
        traces: List of trace dicts for multi-trace charts. Each dict must have
                a "type" key; all other keys go to the trace constructor.
                Example: [{"type": "scatter", "x": [...], "y": [...]},
                          {"type": "bar", "x": [...], "y": [...]}]
        layout: Plotly layout dict (title, axes, annotations, etc.)
        output_format: "html", "png", or "both" (default from config)
        width: Image width in px (default from config)
        height: Image height in px (default from config)
        filename: Base filename without extension (auto-generated if omitted)
    """
    fmt = output_format or get_default_format()

    try:
        if traces is not None:
            # Advanced multi-trace path
            logger.info("create_chart: multi-trace (%d traces) format=%s", len(traces), fmt)
            fig = build_chart_generic(traces, layout)
            trace_types = [t.get("type", "unknown") for t in traces]
        elif chart_type is not None and data is not None:
            # Simple single-trace path (backward compat)
            logger.info("create_chart: type=%s format=%s", chart_type, fmt)
            fig = build_chart(chart_type, data, layout)
            trace_types = [chart_type]
        else:
            return [json.dumps({
                "success": False,
                "error": {
                    "type": "invalid_arguments",
                    "message": "Provide either (chart_type + data) or (traces). See tool description.",
                },
            })]

        paths = save_chart(fig, output_format=fmt, filename=filename, width=width, height=height)

        result_info = json.dumps({
            "success": True,
            "files": paths,
            "trace_count": len(fig.data),
            "trace_types": trace_types,
        })
        result: list = [result_info]
        for p in paths:
            if p.endswith(".png"):
                result.append(Image(path=p))
        return result

    except ValueError as e:
        error_info = _parse_plotly_error(e)
        return [json.dumps({"success": False, "error": error_info})]
    except FileNotFoundError as e:
        return [json.dumps({
            "success": False,
            "error": {"type": "file_error", "message": str(e)},
        })]
    except Exception as e:
        return [json.dumps({
            "success": False,
            "error": {"type": "unexpected_error", "message": str(e)[:500]},
        })]


# ---------------------------------------------------------------------------
# Tool 2: analyze_data
# ---------------------------------------------------------------------------

@mcp.tool()
def analyze_data(file_path: str) -> str:
    """Load a data file and return a summary with chart suggestions.

    Supports CSV, TSV, Excel (.xls/.xlsx), and JSON files.

    Args:
        file_path: Absolute path to the data file.
    """
    logger.info("analyze_data: %s", file_path)
    try:
        df = load_dataframe(file_path)
        summary = summarize_dataframe(df)
        summary["success"] = True
        return json.dumps(summary, indent=2, default=str)
    except FileNotFoundError as e:
        return json.dumps({
            "success": False,
            "error": {"type": "file_error", "message": str(e)},
        })
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": {"type": "unexpected_error", "message": str(e)[:500]},
        })


# ---------------------------------------------------------------------------
# Tool 3: create_chart_from_file
# ---------------------------------------------------------------------------

@mcp.tool()
def create_chart_from_file(
    file_path: str,
    chart_type: str,
    x_column: str,
    y_column: str | None = None,
    group_column: str | None = None,
    trace_properties: dict[str, Any] | None = None,
    style: dict[str, Any] | None = None,
    layout: dict[str, Any] | None = None,
    output_format: str | None = None,
    width: int | None = None,
    height: int | None = None,
    filename: str | None = None,
) -> list:
    """Load a data file and create a chart in one step. Supports any Plotly trace type.

    Args:
        file_path: Absolute path to the data file (CSV/TSV/Excel/JSON).
        chart_type: Any Plotly trace type (e.g. "bar", "scatter", "candlestick").
        x_column: Column to use for the x-axis (or labels for pie).
        y_column: Column for the y-axis (or values for pie). Required for
                  most chart types except histogram.
        group_column: Optional column to group/split data by.
        trace_properties: Dict of Plotly trace properties passed to the constructor.
        style: Alias for trace_properties (backward compat).
        layout: Optional Plotly layout dict.
        output_format: "html", "png", or "both".
        width: Image width in px.
        height: Image height in px.
        filename: Base filename without extension.
    """
    fmt = output_format or get_default_format()
    logger.info("create_chart_from_file: %s type=%s", file_path, chart_type)

    # Merge trace_properties and style (trace_properties takes precedence)
    props = {**(style or {}), **(trace_properties or {})}

    try:
        df = load_dataframe(file_path)
        ct = chart_type.lower().strip()

        # Build trace list from DataFrame columns
        if ct == "pie":
            traces_list = [{"type": ct, "labels": df[x_column].tolist(),
                            "values": df[y_column].tolist(), **props}]
        elif ct == "histogram":
            traces_list = [{"type": ct, "x": df[x_column].tolist(), **props}]
        elif group_column and group_column in df.columns:
            groups = df[group_column].unique()
            traces_list = []
            for g in groups:
                gdf = df[df[group_column] == g]
                if ct in ("box", "violin"):
                    traces_list.append({
                        "type": ct, "y": gdf[y_column].tolist(),
                        "name": str(g), **props,
                    })
                else:
                    traces_list.append({
                        "type": ct, "x": gdf[x_column].tolist(),
                        "y": gdf[y_column].tolist(), "name": str(g), **props,
                    })
        else:
            data: dict[str, Any] = {"type": ct, "x": df[x_column].tolist(), **props}
            if y_column:
                data["y"] = df[y_column].tolist()
            traces_list = [data]

        fig = build_chart_generic(traces_list, layout)
        paths = save_chart(fig, output_format=fmt, filename=filename, width=width, height=height)

        result_info = json.dumps({
            "success": True,
            "files": paths,
            "trace_count": len(fig.data),
            "trace_types": [chart_type],
        })
        result: list = [result_info]
        for p in paths:
            if p.endswith(".png"):
                result.append(Image(path=p))
        return result

    except ValueError as e:
        error_info = _parse_plotly_error(e)
        return [json.dumps({"success": False, "error": error_info})]
    except FileNotFoundError as e:
        return [json.dumps({
            "success": False,
            "error": {"type": "file_error", "message": str(e)},
        })]
    except Exception as e:
        return [json.dumps({
            "success": False,
            "error": {"type": "unexpected_error", "message": str(e)[:500]},
        })]


# ---------------------------------------------------------------------------
# Tool 4: create_dashboard
# ---------------------------------------------------------------------------

@mcp.tool()
def create_dashboard(
    panels: list[dict[str, Any]],
    grid: dict[str, Any] | None = None,
    preset: str | None = None,
    layout: dict[str, Any] | None = None,
    output_format: str | None = None,
    width: int | None = None,
    height: int | None = None,
    filename: str | None = None,
) -> list:
    """Create a multi-panel dashboard with subplots.

    Args:
        panels: List of panel dicts. Each panel has:
                - "row": row position (1-indexed)
                - "col": column position (1-indexed)
                - "traces": list of trace dicts (each with "type" key + Plotly kwargs)
        grid: Grid config dict with "rows", "cols", and optional
              "column_widths", "row_heights", "subplot_titles".
        preset: Named preset instead of grid: "2x1", "1x2", "2x2", "2x3",
                "sidebar" (70/30 columns), "header_grid" (30/70 rows).
        layout: Optional Plotly layout dict (title, etc.)
        output_format: "html", "png", or "both" (default from config)
        width: Image width in px (default from config)
        height: Image height in px (default from config)
        filename: Base filename without extension
    """
    fmt = output_format or get_default_format()
    logger.info("create_dashboard: %d panels, preset=%s format=%s", len(panels), preset, fmt)

    try:
        fig = build_dashboard(panels, grid=grid, preset=preset, layout=layout)
        paths = save_chart(fig, output_format=fmt, filename=filename, width=width, height=height)

        # Collect all trace types across panels
        all_types = []
        for panel in panels:
            for t in panel.get("traces", []):
                all_types.append(t.get("type", "scatter"))

        result_info = json.dumps({
            "success": True,
            "files": paths,
            "panel_count": len(panels),
            "trace_count": len(fig.data),
            "trace_types": all_types,
        })
        result: list = [result_info]
        for p in paths:
            if p.endswith(".png"):
                result.append(Image(path=p))
        return result

    except ValueError as e:
        error_info = _parse_plotly_error(e)
        return [json.dumps({"success": False, "error": error_info})]
    except Exception as e:
        return [json.dumps({
            "success": False,
            "error": {"type": "unexpected_error", "message": str(e)[:500]},
        })]


# ---------------------------------------------------------------------------
# Tool 5: create_live_dashboard
# ---------------------------------------------------------------------------

@mcp.tool()
def create_live_dashboard(
    file_path: str,
    title: str = "Dashboard",
    metrics: list[str] | None = None,
    time_column: str | None = None,
    category_column: str | None = None,
    theme: str = "light",
    refresh_interval: int | None = None,
    serve: bool = True,
    port: int = 8050,
    filename: str | None = None,
) -> str:
    """Create an interactive HTML dashboard from a data file.

    Auto-analyzes the data to generate KPI cards, charts, filters,
    cross-filtering, and theme toggle. Works standalone as a single
    HTML file, or with a live data server for auto-refresh.

    Args:
        file_path: Absolute path to the data file (CSV/TSV/Excel/JSON).
        title: Dashboard title displayed in the header.
        metrics: Column names for KPI cards (auto-detected if None).
        time_column: Column for time axis (auto-detected if None).
        category_column: Column for filters (auto-detected if None).
        theme: Color theme — "light" or "dark".
        refresh_interval: Seconds between data polls (None = no refresh).
                          Requires serve=True to work.
        serve: Start a local HTTP server for live data refresh (default True).
        port: Server port (default 8050). Auto-increments if in use.
        filename: Output filename (auto-generated if omitted).
    """
    logger.info("create_live_dashboard: %s serve=%s", file_path, serve)

    # Use default refresh interval from config if not specified
    if refresh_interval is None:
        refresh_interval = get_default_refresh_interval()

    # Only enable refresh if serve=True
    effective_refresh = refresh_interval if serve else None

    try:
        html, config = build_live_dashboard(
            data_source=file_path,
            title=title,
            metrics=metrics,
            time_column=time_column,
            category_column=category_column,
            theme=theme,
            refresh_interval=effective_refresh,
        )

        path = save_live_dashboard(html, filename=filename)

        result: dict[str, Any] = {
            "success": True,
            "files": [path],
            "panel_count": len(config.panels),
            "filter_count": len(config.filters),
            "kpi_count": len(config.kpis),
            "theme": theme,
            "server": None,
        }

        if serve:
            server_info = start_server(html, file_path, port=port)
            result["server"] = server_info
            if effective_refresh:
                result["refresh_interval"] = effective_refresh

        return json.dumps(result, indent=2)

    except FileNotFoundError as e:
        return json.dumps({
            "success": False,
            "error": {"type": "file_error", "message": str(e)},
        })
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": {"type": "unexpected_error", "message": str(e)[:500]},
        })


# ---------------------------------------------------------------------------
# Tool 6: stop_dashboard_server
# ---------------------------------------------------------------------------

@mcp.tool()
def stop_dashboard_server(port: int = 8050) -> str:
    """Stop a running live dashboard server.

    Args:
        port: Port of the server to stop (default 8050).
    """
    logger.info("stop_dashboard_server: port=%d", port)
    try:
        stopped = stop_server(port=port)
        if stopped:
            return json.dumps({
                "success": True,
                "message": f"Server on port {port} stopped.",
            })
        else:
            return json.dumps({
                "success": False,
                "error": {
                    "type": "validation_error",
                    "message": f"No active server found on port {port}.",
                },
            })
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": {"type": "unexpected_error", "message": str(e)[:500]},
        })


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    mcp.run()


if __name__ == "__main__":
    main()
