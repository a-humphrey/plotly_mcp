"""Tests for live_dashboard.py — HTML dashboard generation."""

import json

import pandas as pd
import pytest

from plotly_mcp.live_dashboard import (
    DashboardConfig,
    FilterConfig,
    PanelConfig,
    build_live_dashboard,
    generate_dashboard_html,
    save_live_dashboard,
)


@pytest.fixture
def sample_csv(tmp_path):
    p = tmp_path / "sales.csv"
    p.write_text(
        "date,revenue,profit,region\n"
        "2024-01-01,100,20,East\n"
        "2024-02-01,150,35,West\n"
        "2024-03-01,200,50,East\n"
        "2024-04-01,175,40,West\n"
    )
    return str(p)


@pytest.fixture
def output_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("PLOTLY_MCP_OUTPUT_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def minimal_config():
    return DashboardConfig(
        title="Test Dashboard",
        theme="light",
        refresh_interval=None,
        data_json='[{"x": 1, "y": 2}]',
        columns=["x", "y"],
        kpis=[{"column": "y", "label": "Total Y", "value": 2, "format_str": ".2f"}],
        panels=[
            PanelConfig(
                panel_id="panel_0",
                panel_type="bar",
                chart_type="bar",
                title="Test Bar",
                config={"x_column": "x", "y_column": "y"},
            ),
        ],
        filters=[
            FilterConfig(column="x", filter_type="dropdown", label="X", options=["1", "2"]),
        ],
        grid_cols=1,
    )


class TestBuildLiveDashboard:
    def test_returns_html_and_config(self, sample_csv):
        html, config = build_live_dashboard(sample_csv)
        assert isinstance(html, str)
        assert isinstance(config, DashboardConfig)

    def test_html_contains_plotly_js(self, sample_csv):
        html, _ = build_live_dashboard(sample_csv)
        assert "plotly" in html.lower()
        assert "<script src=" in html

    def test_html_contains_title(self, sample_csv):
        html, _ = build_live_dashboard(sample_csv, title="Sales Report")
        assert "Sales Report" in html

    def test_html_contains_theme_class(self, sample_csv):
        html, _ = build_live_dashboard(sample_csv, theme="dark")
        assert 'class="theme-dark"' in html

    def test_config_has_panels(self, sample_csv):
        _, config = build_live_dashboard(sample_csv)
        assert len(config.panels) >= 1

    def test_config_has_filters(self, sample_csv):
        _, config = build_live_dashboard(sample_csv)
        assert len(config.filters) >= 1

    def test_custom_metrics(self, sample_csv):
        _, config = build_live_dashboard(sample_csv, metrics=["profit"])
        kpi_cols = [k["column"] for k in config.kpis]
        assert kpi_cols == ["profit"]

    def test_refresh_interval_in_html(self, sample_csv):
        html, _ = build_live_dashboard(sample_csv, refresh_interval=5)
        assert "Auto-refresh: 5s" in html
        assert "startPolling" in html

    def test_no_refresh_when_none(self, sample_csv):
        html, _ = build_live_dashboard(sample_csv, refresh_interval=None)
        assert "Auto-refresh" not in html


class TestGenerateDashboardHtml:
    def test_has_doctype(self, minimal_config):
        html = generate_dashboard_html(minimal_config)
        assert html.startswith("<!DOCTYPE html>")

    def test_has_embedded_data(self, minimal_config):
        html = generate_dashboard_html(minimal_config)
        assert 'id="dashboard-data"' in html
        assert minimal_config.data_json in html

    def test_has_filter_controls(self, minimal_config):
        html = generate_dashboard_html(minimal_config)
        assert 'filter-bar' in html
        assert '<select' in html
        assert 'applyFilters()' in html

    def test_has_kpi_cards(self, minimal_config):
        html = generate_dashboard_html(minimal_config)
        assert 'kpi-card' in html
        assert 'Total Y' in html

    def test_has_panel_divs(self, minimal_config):
        html = generate_dashboard_html(minimal_config)
        assert 'panel_0' in html
        assert 'panel-card' in html

    def test_has_theme_toggle(self, minimal_config):
        html = generate_dashboard_html(minimal_config)
        assert 'theme-toggle' in html
        assert 'toggleTheme()' in html

    def test_has_javascript_functions(self, minimal_config):
        html = generate_dashboard_html(minimal_config)
        assert "initDashboard" in html
        assert "applyFilters" in html
        assert "renderAllCharts" in html
        assert "setupCrossFilter" in html
        assert "toggleTheme" in html
        assert "resetFilters" in html

    def test_has_css_themes(self, minimal_config):
        html = generate_dashboard_html(minimal_config)
        assert "theme-light" in html
        assert "theme-dark" in html
        assert "--bg-primary" in html

    def test_dark_theme_body_class(self, minimal_config):
        minimal_config.theme = "dark"
        html = generate_dashboard_html(minimal_config)
        assert 'class="theme-dark"' in html

    def test_grid_template(self, minimal_config):
        minimal_config.grid_cols = 2
        html = generate_dashboard_html(minimal_config)
        assert "repeat(2, 1fr)" in html

    def test_no_filters_when_empty(self, minimal_config):
        minimal_config.filters = []
        html = generate_dashboard_html(minimal_config)
        # CSS class still in stylesheet, but no filter-bar div should be emitted
        assert '<div class="filter-bar">' not in html

    def test_no_kpis_when_empty(self, minimal_config):
        minimal_config.kpis = []
        html = generate_dashboard_html(minimal_config)
        # CSS class still in stylesheet, but no kpi-row div should be emitted
        assert '<div class="kpi-row">' not in html

    def test_date_range_filter(self):
        config = DashboardConfig(
            title="Test",
            theme="light",
            refresh_interval=None,
            data_json="[]",
            columns=[],
            kpis=[],
            panels=[],
            filters=[FilterConfig(column="date", filter_type="date_range", label="Date")],
            grid_cols=1,
        )
        html = generate_dashboard_html(config)
        assert 'type="date"' in html
        assert "filter-date-start" in html
        assert "filter-date-end" in html


class TestSaveLiveDashboard:
    def test_saves_to_output_dir(self, output_dir):
        html = "<html><body>test</body></html>"
        path = save_live_dashboard(html, filename="test_dash")
        assert path.endswith("test_dash.html")
        assert (output_dir / "test_dash.html").exists()
        assert (output_dir / "test_dash.html").read_text() == html

    def test_auto_generates_filename(self, output_dir):
        html = "<html><body>test</body></html>"
        path = save_live_dashboard(html)
        assert "dashboard_" in path
        assert path.endswith(".html")
