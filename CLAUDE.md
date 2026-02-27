# Plotly MCP Server

## Project Overview

MCP server that lets LLMs generate Plotly charts via Model Context Protocol tools. Uses a generic trace engine that dynamically supports all 51 Plotly trace types with full property pass-through.

## Architecture

The server is a thin validated bridge to Plotly, not a re-implementation. Core flow:

1. LLM calls an MCP tool (e.g. `create_chart`) with trace type + kwargs
2. `resolve_trace_class()` maps the type string to a `plotly.graph_objects` class
3. All kwargs are passed directly to the Plotly constructor — no filtering
4. `save_chart()` writes HTML/PNG output
5. Structured JSON is returned with `success`, `files`, `trace_count` fields

### Key modules

- **`charts.py`** — `TRACE_TYPE_MAP` (dynamic), `resolve_trace_class()`, `build_chart_generic()`, `build_dashboard()`, `build_chart()` (backward compat), `save_chart()`
- **`server.py`** — MCP tool definitions (`create_chart`, `analyze_data`, `create_chart_from_file`, `create_dashboard`), resources, error wrapping
- **`data_utils.py`** — DataFrame loading (CSV/TSV/Excel/JSON), summarization, chart suggestions
- **`config.py`** — Environment variable config (`PLOTLY_MCP_OUTPUT_DIR`, `PLOTLY_MCP_DEFAULT_FORMAT`, `PLOTLY_MCP_DEFAULT_WIDTH`, `PLOTLY_MCP_DEFAULT_HEIGHT`)

## Development

### Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### Running tests

```bash
.venv/bin/python -m pytest tests/ -v
```

Always use the venv Python — system Python lacks dependencies.

### Conventions

- **Plotly v5 only** (`>=5.18.0,<6`) — required for kaleido 0.2.1 compatibility
- **Kaleido pinned to 0.2.1** — self-contained Chromium for PNG export
- **Graph Objects, not Express** — LLMs send raw lists, not DataFrames
- **stdio transport** — standard for local MCP servers
- All tools return structured JSON with `success` boolean for error handling
- Legacy aliases (`line`, `area`, `scatter_3d`) are preserved for backward compat
- `build_chart()` is the backward-compat single-trace API; `build_chart_generic()` is the primary multi-trace API

### Error handling pattern

All server tools wrap operations in try/except and return structured error JSON:
```json
{"success": false, "error": {"type": "invalid_property", "message": "...", "suggestion": "..."}}
```

Error types: `invalid_property`, `validation_error`, `file_error`, `invalid_arguments`, `unexpected_error`.

### Adding new functionality

- New trace types are automatically supported — `TRACE_TYPE_MAP` discovers them from `plotly.graph_objects`
- For new subplot types, add to the category sets in `charts.py` (`_DOMAIN_TYPES`, `_SCENE_TYPES`, etc.)
- For new dashboard presets, add to `DASHBOARD_PRESETS` dict
- For new legacy aliases, add to `LEGACY_ALIASES` dict
