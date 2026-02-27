# Plotly MCP Server

An MCP (Model Context Protocol) server that enables LLMs to generate Plotly charts. Supports all 51 Plotly trace types with full property pass-through, multi-trace charts, and multi-panel dashboards.

## Features

- **All Plotly trace types** — scatter, bar, candlestick, sankey, choropleth, indicator, and 45+ more
- **Full property pass-through** — any valid Plotly trace or layout property is accepted directly
- **Multi-trace charts** — overlay multiple trace types on a single figure
- **Dashboard layouts** — multi-panel grids with presets (`2x2`, `sidebar`, etc.) and auto subplot type detection
- **File-based workflows** — load CSV/TSV/Excel/JSON, analyze data, and chart in one step
- **Structured error handling** — errors return JSON with type, message, and suggestions the LLM can act on
- **Dual output** — HTML (interactive) and/or PNG (static) output

## Installation

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Configuration

Environment variables (all optional):

| Variable | Default | Description |
|---|---|---|
| `PLOTLY_MCP_OUTPUT_DIR` | `~/plotly_mcp_output` | Directory for saved charts |
| `PLOTLY_MCP_DEFAULT_FORMAT` | `html` | Default output format (`html`, `png`, or `both`) |
| `PLOTLY_MCP_DEFAULT_WIDTH` | `800` | Default image width in px |
| `PLOTLY_MCP_DEFAULT_HEIGHT` | `600` | Default image height in px |

## MCP Client Setup

### Claude Desktop

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "plotly-charts": {
      "command": "/path/to/plotly_mcp/.venv/bin/plotly-mcp"
    }
  }
}
```

### Claude Code

```bash
claude mcp add plotly-charts /path/to/plotly_mcp/.venv/bin/plotly-mcp
```

## Tools

### `create_chart`

Create any Plotly chart. Two calling conventions:

**Simple (single trace):**
```json
{
  "chart_type": "candlestick",
  "data": {
    "x": ["2024-01-01", "2024-01-02"],
    "open": [10, 12], "high": [15, 14],
    "low": [9, 11], "close": [13, 12]
  },
  "layout": {"title": "Stock Price"},
  "output_format": "both"
}
```

**Advanced (multi-trace):**
```json
{
  "traces": [
    {"type": "scatter", "x": [1, 2, 3], "y": [4, 5, 6], "mode": "lines", "name": "Trend"},
    {"type": "bar", "x": [1, 2, 3], "y": [2, 3, 1], "name": "Volume"}
  ],
  "layout": {"title": "Multi-trace Chart"}
}
```

### `create_dashboard`

Create multi-panel dashboards with subplots:

```json
{
  "panels": [
    {"row": 1, "col": 1, "traces": [{"type": "bar", "x": ["A", "B"], "y": [10, 20]}]},
    {"row": 1, "col": 2, "traces": [{"type": "pie", "labels": ["X", "Y"], "values": [30, 70]}]},
    {"row": 2, "col": 1, "traces": [{"type": "scatter", "x": [1, 2], "y": [3, 4], "mode": "markers"}]},
    {"row": 2, "col": 2, "traces": [{"type": "histogram", "x": [1, 2, 2, 3, 3, 3]}]}
  ],
  "preset": "2x2",
  "layout": {"title": "Dashboard"}
}
```

Available presets: `2x1`, `1x2`, `2x2`, `2x3`, `sidebar` (70/30 columns), `header_grid` (30/70 rows).

### `analyze_data`

Load a data file and get a summary with chart suggestions:

```json
{
  "file_path": "/path/to/data.csv"
}
```

Supports CSV, TSV, Excel (.xls/.xlsx), and JSON.

### `create_chart_from_file`

Load a data file and create a chart in one step:

```json
{
  "file_path": "/path/to/sales.csv",
  "chart_type": "bar",
  "x_column": "quarter",
  "y_column": "revenue",
  "group_column": "region",
  "trace_properties": {"marker_color": "steelblue"},
  "output_format": "html"
}
```

## Resources

| URI | Description |
|---|---|
| `plotly://chart-types` | All supported trace types organized by subplot category |
| `plotly://trace-info/{type}` | Valid properties for a specific trace type (e.g. `plotly://trace-info/sankey`) |

## Structured Returns

All tools return JSON with a `success` field:

```json
{"success": true, "files": ["/path/to/chart.html"], "trace_count": 2, "trace_types": ["scatter", "bar"]}
```

Errors include type and actionable messages:

```json
{"success": false, "error": {"type": "invalid_property", "message": "...", "suggestion": "Did you mean 'marker_color'?"}}
```

## Development

```bash
pip install -e ".[dev]"
.venv/bin/python -m pytest tests/ -v
```

## Dependencies

- Python >= 3.10
- `mcp[cli]` >= 1.2.0
- `plotly` >= 5.18.0, < 6
- `kaleido` == 0.2.1
- `pandas` >= 2.0.0
