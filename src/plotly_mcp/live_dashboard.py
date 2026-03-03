"""Live dashboard HTML generation engine.

Generates self-contained interactive HTML dashboards with embedded Plotly.js,
vanilla JS for interactivity (filters, cross-filtering, theme toggle),
and CSS for light/dark theming.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from .auto_layout import build_auto_layout
from .config import get_output_dir
from .data_utils import load_dataframe

# CDN URL for Plotly.js (self-contained in HTML)
_PLOTLY_CDN = "https://cdn.plot.ly/plotly-2.35.0.min.js"

# Maximum rows to embed in HTML for standalone mode
_MAX_EMBEDDED_ROWS = 5000


@dataclass
class FilterConfig:
    column: str
    filter_type: str  # "dropdown" or "date_range"
    label: str
    options: list[str] = field(default_factory=list)


@dataclass
class PanelConfig:
    panel_id: str
    panel_type: str  # "time_series", "bar", "pie", "histogram", "table"
    chart_type: str
    title: str
    config: dict[str, Any] = field(default_factory=dict)


@dataclass
class DashboardConfig:
    title: str
    theme: str
    refresh_interval: int | None
    data_json: str
    columns: list[str]
    kpis: list[dict[str, Any]]
    panels: list[PanelConfig]
    filters: list[FilterConfig]
    grid_cols: int
    serve: bool = False


def build_live_dashboard(
    data_source: str,
    title: str = "Dashboard",
    metrics: list[str] | None = None,
    time_column: str | None = None,
    category_column: str | None = None,
    theme: str = "light",
    refresh_interval: int | None = None,
) -> tuple[str, DashboardConfig]:
    """Build a live dashboard HTML from a data file.

    Returns (html_string, config).
    """
    df = load_dataframe(data_source)
    layout_spec = build_auto_layout(
        df,
        title=title,
        metrics=metrics,
        time_column=time_column,
        category_column=category_column,
    )

    # Truncate data for embedding
    if len(df) > _MAX_EMBEDDED_ROWS:
        embed_df = df.tail(_MAX_EMBEDDED_ROWS)
    else:
        embed_df = df

    # Serialize data to JSON (handle datetime, etc.)
    data_records = embed_df.to_dict(orient="records")
    data_json = json.dumps(data_records, default=str)

    # Build config objects
    filters = [
        FilterConfig(
            column=f["column"],
            filter_type=f["type"],
            label=f["label"],
            options=f.get("options", []),
        )
        for f in layout_spec["filters"]
    ]

    panels = []
    for p in layout_spec["panels"]:
        extra = {k: v for k, v in p.items() if k not in ("id", "type", "chart_type", "title")}
        panels.append(PanelConfig(
            panel_id=p["id"],
            panel_type=p["type"],
            chart_type=p["chart_type"],
            title=p["title"],
            config=extra,
        ))

    config = DashboardConfig(
        title=title,
        theme=theme,
        refresh_interval=refresh_interval,
        data_json=data_json,
        columns=df.columns.tolist(),
        kpis=layout_spec["kpis"],
        panels=panels,
        filters=filters,
        grid_cols=layout_spec["grid_cols"],
    )

    html = generate_dashboard_html(config)
    return html, config


def generate_dashboard_html(config: DashboardConfig) -> str:
    """Generate the complete HTML string for the dashboard."""
    css = _generate_css(config)
    filter_html = _generate_filter_html(config)
    kpi_html = _generate_kpi_html(config)
    panel_html = _generate_panel_html(config)
    js = _generate_javascript(config)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{_escape_html(config.title)}</title>
    <script src="{_PLOTLY_CDN}"></script>
    <style>
{css}
    </style>
</head>
<body class="theme-{config.theme}">
    <header class="dashboard-header">
        <h1>{_escape_html(config.title)}</h1>
        <div class="header-controls">
            <button id="theme-toggle" onclick="toggleTheme()">Toggle Theme</button>
            {_refresh_indicator_html(config)}
        </div>
    </header>

    {filter_html}
    {kpi_html}

    <main class="dashboard-grid" style="grid-template-columns: repeat({config.grid_cols}, 1fr);">
        {panel_html}
    </main>

    <script type="application/json" id="dashboard-data">
{config.data_json}
    </script>

    <script>
{js}
    </script>
</body>
</html>"""


def save_live_dashboard(
    html: str,
    filename: str | None = None,
) -> str:
    """Save dashboard HTML to the output directory. Returns the file path."""
    import datetime

    out_dir = get_output_dir()
    base = filename or f"dashboard_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
    base = Path(base).stem
    path = out_dir / f"{base}.html"
    path.write_text(html, encoding="utf-8")
    return str(path)


# ---------------------------------------------------------------------------
# HTML generation helpers
# ---------------------------------------------------------------------------

def _escape_html(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _refresh_indicator_html(config: DashboardConfig) -> str:
    if config.refresh_interval:
        return f'<span id="refresh-indicator" class="refresh-indicator">Auto-refresh: {config.refresh_interval}s</span>'
    return ""


def _generate_css(config: DashboardConfig) -> str:
    return """
        :root {
            --transition-speed: 0.3s;
        }

        body.theme-light {
            --bg-primary: #f5f7fa;
            --bg-card: #ffffff;
            --bg-header: #ffffff;
            --text-primary: #1a1a2e;
            --text-secondary: #6c757d;
            --accent: #4361ee;
            --border: #e0e0e0;
            --shadow: 0 2px 8px rgba(0,0,0,0.08);
            --kpi-bg: #ffffff;
        }

        body.theme-dark {
            --bg-primary: #1a1a2e;
            --bg-card: #16213e;
            --bg-header: #0f3460;
            --text-primary: #e0e0e0;
            --text-secondary: #a0a0a0;
            --accent: #4cc9f0;
            --border: #2a2a4a;
            --shadow: 0 2px 8px rgba(0,0,0,0.3);
            --kpi-bg: #16213e;
        }

        * { margin: 0; padding: 0; box-sizing: border-box; }

        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: var(--bg-primary);
            color: var(--text-primary);
            transition: background var(--transition-speed), color var(--transition-speed);
        }

        .dashboard-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 16px 24px;
            background: var(--bg-header);
            border-bottom: 1px solid var(--border);
            box-shadow: var(--shadow);
        }

        .dashboard-header h1 {
            font-size: 1.5rem;
            font-weight: 600;
        }

        .header-controls {
            display: flex;
            align-items: center;
            gap: 12px;
        }

        #theme-toggle {
            padding: 8px 16px;
            border: 1px solid var(--border);
            border-radius: 6px;
            background: var(--bg-card);
            color: var(--text-primary);
            cursor: pointer;
            font-size: 0.85rem;
            transition: all var(--transition-speed);
        }

        #theme-toggle:hover {
            background: var(--accent);
            color: #fff;
            border-color: var(--accent);
        }

        .refresh-indicator {
            font-size: 0.8rem;
            color: var(--text-secondary);
            padding: 4px 10px;
            border-radius: 12px;
            background: var(--bg-card);
            border: 1px solid var(--border);
        }

        .filter-bar {
            display: flex;
            flex-wrap: wrap;
            gap: 12px;
            padding: 12px 24px;
            background: var(--bg-card);
            border-bottom: 1px solid var(--border);
            align-items: center;
        }

        .filter-group {
            display: flex;
            align-items: center;
            gap: 6px;
        }

        .filter-group label {
            font-size: 0.85rem;
            font-weight: 500;
            color: var(--text-secondary);
        }

        .filter-group select,
        .filter-group input {
            padding: 6px 10px;
            border: 1px solid var(--border);
            border-radius: 6px;
            background: var(--bg-primary);
            color: var(--text-primary);
            font-size: 0.85rem;
        }

        .filter-reset {
            padding: 6px 12px;
            border: 1px solid var(--border);
            border-radius: 6px;
            background: var(--bg-primary);
            color: var(--text-secondary);
            cursor: pointer;
            font-size: 0.8rem;
        }

        .kpi-row {
            display: flex;
            gap: 16px;
            padding: 16px 24px;
            overflow-x: auto;
        }

        .kpi-card {
            flex: 1;
            min-width: 180px;
            padding: 16px 20px;
            background: var(--kpi-bg);
            border-radius: 10px;
            border: 1px solid var(--border);
            box-shadow: var(--shadow);
            transition: all var(--transition-speed);
        }

        .kpi-label {
            font-size: 0.8rem;
            color: var(--text-secondary);
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-bottom: 4px;
        }

        .kpi-value {
            font-size: 1.8rem;
            font-weight: 700;
            color: var(--accent);
        }

        .dashboard-grid {
            display: grid;
            gap: 16px;
            padding: 16px 24px;
        }

        .panel-card {
            background: var(--bg-card);
            border-radius: 10px;
            border: 1px solid var(--border);
            box-shadow: var(--shadow);
            overflow: hidden;
            transition: all var(--transition-speed);
        }

        .panel-card.full-width {
            grid-column: 1 / -1;
        }

        .panel-title {
            padding: 12px 16px;
            font-size: 0.95rem;
            font-weight: 600;
            border-bottom: 1px solid var(--border);
            color: var(--text-primary);
        }

        .panel-chart {
            width: 100%;
            min-height: 350px;
        }

        .panel-chart.table-chart {
            min-height: 300px;
        }
    """


def _generate_filter_html(config: DashboardConfig) -> str:
    if not config.filters:
        return ""

    filter_items = []
    for f in config.filters:
        if f.filter_type == "dropdown":
            options_html = '<option value="">All</option>'
            for opt in f.options:
                options_html += f'<option value="{_escape_html(str(opt))}">{_escape_html(str(opt))}</option>'
            filter_items.append(
                f'<div class="filter-group">'
                f'<label>{_escape_html(f.label)}:</label>'
                f'<select id="filter-{f.column}" onchange="applyFilters()">{options_html}</select>'
                f'</div>'
            )
        elif f.filter_type == "date_range":
            filter_items.append(
                f'<div class="filter-group">'
                f'<label>{_escape_html(f.label)}:</label>'
                f'<input type="date" id="filter-{f.column}-start" onchange="applyFilters()">'
                f'<span>to</span>'
                f'<input type="date" id="filter-{f.column}-end" onchange="applyFilters()">'
                f'</div>'
            )

    filter_items.append('<button class="filter-reset" onclick="resetFilters()">Reset</button>')

    return f'<div class="filter-bar">{"".join(filter_items)}</div>'


def _generate_kpi_html(config: DashboardConfig) -> str:
    if not config.kpis:
        return ""

    cards = []
    for i, kpi in enumerate(config.kpis):
        cards.append(
            f'<div class="kpi-card">'
            f'<div class="kpi-label">{_escape_html(kpi["label"])}</div>'
            f'<div class="kpi-value" id="kpi-{i}">--</div>'
            f'</div>'
        )

    return f'<div class="kpi-row">{"".join(cards)}</div>'


def _generate_panel_html(config: DashboardConfig) -> str:
    panels = []
    for p in config.panels:
        extra_class = " full-width" if p.panel_type == "table" else ""
        chart_class = "panel-chart table-chart" if p.panel_type == "table" else "panel-chart"
        panels.append(
            f'<div class="panel-card{extra_class}">'
            f'<div class="panel-title">{_escape_html(p.title)}</div>'
            f'<div id="{p.panel_id}" class="{chart_class}"></div>'
            f'</div>'
        )
    return "\n        ".join(panels)


def _generate_javascript(config: DashboardConfig) -> str:
    """Generate the client-side JavaScript for the dashboard."""
    # Build panel config as JSON for JS consumption
    panels_js = []
    for p in config.panels:
        panels_js.append({
            "id": p.panel_id,
            "type": p.panel_type,
            "chartType": p.chart_type,
            "title": p.title,
            "config": p.config,
        })

    kpis_js = config.kpis
    filters_js = [{"column": f.column, "type": f.filter_type, "label": f.label} for f in config.filters]

    return f"""
    // Dashboard configuration
    var DASHBOARD_CONFIG = {{
        panels: {json.dumps(panels_js)},
        kpis: {json.dumps(kpis_js, default=str)},
        filters: {json.dumps(filters_js)},
        theme: "{config.theme}",
        refreshInterval: {json.dumps(config.refresh_interval)}
    }};

    // Dashboard state
    var DashboardState = {{
        rawData: [],
        filteredData: [],
        crossFilter: null,
        charts: {{}}
    }};

    function initDashboard() {{
        // Load embedded data
        var dataEl = document.getElementById('dashboard-data');
        DashboardState.rawData = JSON.parse(dataEl.textContent);
        DashboardState.filteredData = DashboardState.rawData.slice();

        // Render everything
        updateKPIs();
        renderAllCharts();
        setupCrossFilter();

        // Start polling if configured
        if (DASHBOARD_CONFIG.refreshInterval && DASHBOARD_CONFIG.refreshInterval > 0) {{
            startPolling(DASHBOARD_CONFIG.refreshInterval);
        }}
    }}

    function getPlotlyTemplate() {{
        var isDark = document.body.classList.contains('theme-dark');
        return isDark ? 'plotly_dark' : 'plotly_white';
    }}

    function getPlotlyLayout(title) {{
        var isDark = document.body.classList.contains('theme-dark');
        return {{
            template: getPlotlyTemplate(),
            title: {{ text: title, font: {{ size: 14 }} }},
            margin: {{ l: 50, r: 30, t: 40, b: 50 }},
            paper_bgcolor: 'rgba(0,0,0,0)',
            plot_bgcolor: 'rgba(0,0,0,0)',
            font: {{ color: isDark ? '#e0e0e0' : '#1a1a2e' }}
        }};
    }}

    function updateKPIs() {{
        var data = DashboardState.filteredData;
        DASHBOARD_CONFIG.kpis.forEach(function(kpi, i) {{
            var el = document.getElementById('kpi-' + i);
            if (!el) return;
            var sum = 0;
            var count = 0;
            data.forEach(function(row) {{
                var v = parseFloat(row[kpi.column]);
                if (!isNaN(v)) {{ sum += v; count++; }}
            }});
            // Format the value
            if (Math.abs(sum) >= 1000) {{
                el.textContent = sum.toLocaleString(undefined, {{maximumFractionDigits: 0}});
            }} else {{
                el.textContent = sum.toLocaleString(undefined, {{maximumFractionDigits: 2}});
            }}
        }});
    }}

    function renderAllCharts() {{
        DASHBOARD_CONFIG.panels.forEach(function(panel) {{
            renderPanel(panel);
        }});
    }}

    function renderPanel(panel) {{
        var data = DashboardState.filteredData;
        var el = document.getElementById(panel.id);
        if (!el) return;
        var layout = getPlotlyLayout(panel.title);
        var plotlyConfig = {{ responsive: true, displayModeBar: false }};

        if (panel.type === 'time_series') {{
            var traces = [];
            var yCols = panel.config.y_columns || [];
            var xCol = panel.config.x_column;
            var xVals = data.map(function(r) {{ return r[xCol]; }});
            yCols.forEach(function(yCol) {{
                traces.push({{
                    x: xVals,
                    y: data.map(function(r) {{ return r[yCol]; }}),
                    type: 'scatter',
                    mode: panel.config.mode || 'lines+markers',
                    name: yCol
                }});
            }});
            Plotly.react(el, traces, layout, plotlyConfig);

        }} else if (panel.type === 'bar') {{
            var xCol = panel.config.x_column;
            var yCol = panel.config.y_column;
            // Aggregate by x column
            var agg = {{}};
            data.forEach(function(r) {{
                var key = String(r[xCol]);
                agg[key] = (agg[key] || 0) + (parseFloat(r[yCol]) || 0);
            }});
            var keys = Object.keys(agg);
            Plotly.react(el, [{{
                x: keys,
                y: keys.map(function(k) {{ return agg[k]; }}),
                type: 'bar',
                marker: {{ color: getComputedStyle(document.body).getPropertyValue('--accent').trim() }}
            }}], layout, plotlyConfig);

        }} else if (panel.type === 'pie') {{
            var labelsCol = panel.config.labels_column;
            var valuesCol = panel.config.values_column;
            var agg = {{}};
            data.forEach(function(r) {{
                var key = String(r[labelsCol]);
                agg[key] = (agg[key] || 0) + (parseFloat(r[valuesCol]) || 0);
            }});
            var keys = Object.keys(agg);
            Plotly.react(el, [{{
                labels: keys,
                values: keys.map(function(k) {{ return agg[k]; }}),
                type: 'pie'
            }}], layout, plotlyConfig);

        }} else if (panel.type === 'histogram') {{
            var xCol = panel.config.x_column;
            Plotly.react(el, [{{
                x: data.map(function(r) {{ return r[xCol]; }}),
                type: 'histogram'
            }}], layout, plotlyConfig);

        }} else if (panel.type === 'table') {{
            var maxRows = panel.config.max_rows || 100;
            var subset = data.slice(0, maxRows);
            if (subset.length === 0) {{
                Plotly.react(el, [], layout, plotlyConfig);
                return;
            }}
            var cols = Object.keys(subset[0]);
            var headerValues = cols.map(function(c) {{ return '<b>' + c + '</b>'; }});
            var cellValues = cols.map(function(c) {{
                return subset.map(function(r) {{ return r[c]; }});
            }});
            var isDark = document.body.classList.contains('theme-dark');
            Plotly.react(el, [{{
                type: 'table',
                header: {{
                    values: headerValues,
                    fill: {{ color: isDark ? '#0f3460' : '#4361ee' }},
                    font: {{ color: '#ffffff', size: 12 }},
                    align: 'left'
                }},
                cells: {{
                    values: cellValues,
                    fill: {{ color: isDark ? '#16213e' : '#f8f9fa' }},
                    font: {{ color: isDark ? '#e0e0e0' : '#1a1a2e', size: 11 }},
                    align: 'left'
                }}
            }}], {{ ...layout, margin: {{ l: 10, r: 10, t: 40, b: 10 }} }}, plotlyConfig);
        }}

        DashboardState.charts[panel.id] = true;
    }}

    function setupCrossFilter() {{
        DASHBOARD_CONFIG.panels.forEach(function(panel) {{
            if (panel.type === 'bar' || panel.type === 'pie') {{
                var el = document.getElementById(panel.id);
                if (!el) return;
                el.on('plotly_click', function(eventData) {{
                    if (!eventData || !eventData.points || !eventData.points.length) return;
                    var point = eventData.points[0];
                    var value;
                    if (panel.type === 'pie') {{
                        value = point.label;
                    }} else {{
                        value = point.x;
                    }}
                    var col = panel.config.x_column || panel.config.labels_column;
                    // Toggle: if same value clicked, clear filter
                    if (DashboardState.crossFilter &&
                        DashboardState.crossFilter.column === col &&
                        DashboardState.crossFilter.value === value) {{
                        DashboardState.crossFilter = null;
                    }} else {{
                        DashboardState.crossFilter = {{ column: col, value: value }};
                    }}
                    applyFilters();
                }});
            }}
        }});
    }}

    function applyFilters() {{
        var data = DashboardState.rawData.slice();

        // Apply dropdown filters
        DASHBOARD_CONFIG.filters.forEach(function(f) {{
            if (f.type === 'dropdown') {{
                var sel = document.getElementById('filter-' + f.column);
                if (sel && sel.value) {{
                    data = data.filter(function(r) {{ return String(r[f.column]) === sel.value; }});
                }}
            }} else if (f.type === 'date_range') {{
                var startEl = document.getElementById('filter-' + f.column + '-start');
                var endEl = document.getElementById('filter-' + f.column + '-end');
                if (startEl && startEl.value) {{
                    var startDate = new Date(startEl.value);
                    data = data.filter(function(r) {{ return new Date(r[f.column]) >= startDate; }});
                }}
                if (endEl && endEl.value) {{
                    var endDate = new Date(endEl.value);
                    endDate.setHours(23, 59, 59);
                    data = data.filter(function(r) {{ return new Date(r[f.column]) <= endDate; }});
                }}
            }}
        }});

        // Apply cross-filter
        if (DashboardState.crossFilter) {{
            var cf = DashboardState.crossFilter;
            data = data.filter(function(r) {{ return String(r[cf.column]) === String(cf.value); }});
        }}

        DashboardState.filteredData = data;
        updateKPIs();
        renderAllCharts();
    }}

    function resetFilters() {{
        // Reset dropdowns
        DASHBOARD_CONFIG.filters.forEach(function(f) {{
            if (f.type === 'dropdown') {{
                var sel = document.getElementById('filter-' + f.column);
                if (sel) sel.value = '';
            }} else if (f.type === 'date_range') {{
                var startEl = document.getElementById('filter-' + f.column + '-start');
                var endEl = document.getElementById('filter-' + f.column + '-end');
                if (startEl) startEl.value = '';
                if (endEl) endEl.value = '';
            }}
        }});
        DashboardState.crossFilter = null;
        applyFilters();
    }}

    function toggleTheme() {{
        var body = document.body;
        if (body.classList.contains('theme-light')) {{
            body.classList.replace('theme-light', 'theme-dark');
        }} else {{
            body.classList.replace('theme-dark', 'theme-light');
        }}
        // Re-render all charts with updated theme
        renderAllCharts();
    }}

    function startPolling(intervalSeconds) {{
        setInterval(function() {{
            fetch('/api/data')
                .then(function(response) {{ return response.json(); }})
                .then(function(newData) {{
                    DashboardState.rawData = newData;
                    applyFilters();
                    // Flash the refresh indicator
                    var ind = document.getElementById('refresh-indicator');
                    if (ind) {{
                        ind.style.color = getComputedStyle(document.body).getPropertyValue('--accent').trim();
                        setTimeout(function() {{ ind.style.color = ''; }}, 500);
                    }}
                }})
                .catch(function(err) {{
                    console.warn('Refresh failed:', err);
                }});
        }}, intervalSeconds * 1000);
    }}

    // Initialize on DOM ready
    document.addEventListener('DOMContentLoaded', initDashboard);
    """
