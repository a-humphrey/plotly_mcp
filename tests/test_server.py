"""Integration tests for MCP server tools."""

import json
from pathlib import Path

import pytest

from plotly_mcp.server import (
    analyze_data,
    create_chart,
    create_chart_from_file,
    create_dashboard,
    create_live_dashboard,
    stop_dashboard_server,
)


@pytest.fixture
def output_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("PLOTLY_MCP_OUTPUT_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def sample_csv(tmp_path):
    p = tmp_path / "sales.csv"
    p.write_text("quarter,revenue,region\nQ1,100,East\nQ2,150,West\nQ3,200,East\nQ4,175,West\n")
    return str(p)


def _parse_result(result: list) -> dict:
    """Parse the first JSON element from tool return."""
    return json.loads(result[0])


# ---------------------------------------------------------------------------
# create_chart — structured JSON returns
# ---------------------------------------------------------------------------

class TestCreateChart:
    def test_bar_chart_html(self, output_dir):
        result = create_chart(
            chart_type="bar",
            data={"x": ["Q1", "Q2", "Q3", "Q4"], "y": [100, 150, 200, 175]},
            layout={"title": "Quarterly Revenue"},
            output_format="html",
        )
        info = _parse_result(result)
        assert info["success"] is True
        assert len(info["files"]) == 1
        assert info["files"][0].endswith(".html")
        assert info["trace_count"] == 1

    def test_pie_chart_png(self, output_dir):
        result = create_chart(
            chart_type="pie",
            data={"labels": ["A", "B", "C"], "values": [30, 50, 20]},
            output_format="png",
            filename="test_pie",
        )
        info = _parse_result(result)
        assert info["success"] is True
        assert (output_dir / "test_pie.png").exists()
        # PNG result should include Image object
        assert len(result) == 2

    def test_both_formats(self, output_dir):
        result = create_chart(
            chart_type="line",
            data={"x": [1, 2, 3], "y": [10, 20, 30]},
            output_format="both",
            filename="test_both",
        )
        info = _parse_result(result)
        assert info["success"] is True
        assert len(info["files"]) == 2
        assert (output_dir / "test_both.html").exists()
        assert (output_dir / "test_both.png").exists()

    def test_structured_error_invalid_type(self, output_dir):
        result = create_chart(chart_type="radar", data={"x": [1]})
        info = _parse_result(result)
        assert info["success"] is False
        assert "error" in info
        assert "Unknown trace type" in info["error"]["message"]

    def test_structured_error_missing_args(self, output_dir):
        result = create_chart()
        info = _parse_result(result)
        assert info["success"] is False
        assert info["error"]["type"] == "invalid_arguments"

    def test_structured_error_invalid_property(self, output_dir):
        result = create_chart(
            chart_type="bar",
            data={"x": [1], "y": [2], "style": {"nonexistent_prop": True}},
        )
        info = _parse_result(result)
        assert info["success"] is False

    # --- Multi-trace via traces param ---

    def test_multi_trace(self, output_dir):
        result = create_chart(
            traces=[
                {"type": "scatter", "x": [1, 2], "y": [3, 4], "mode": "lines", "name": "A"},
                {"type": "bar", "x": [1, 2], "y": [5, 6], "name": "B"},
            ],
            layout={"title": "Multi"},
            output_format="html",
            filename="multi_test",
        )
        info = _parse_result(result)
        assert info["success"] is True
        assert info["trace_count"] == 2
        assert info["trace_types"] == ["scatter", "bar"]

    # --- New trace types ---

    def test_candlestick(self, output_dir):
        result = create_chart(
            chart_type="candlestick",
            data={
                "x": ["2024-01-01", "2024-01-02"],
                "open": [10, 12], "high": [15, 14],
                "low": [9, 11], "close": [13, 12],
            },
            output_format="html",
            filename="candlestick_test",
        )
        info = _parse_result(result)
        assert info["success"] is True

    def test_indicator(self, output_dir):
        result = create_chart(
            chart_type="indicator",
            data={"mode": "number", "value": 42},
            output_format="html",
        )
        info = _parse_result(result)
        assert info["success"] is True


# ---------------------------------------------------------------------------
# analyze_data — with success field
# ---------------------------------------------------------------------------

class TestAnalyzeData:
    def test_returns_summary_with_success(self, sample_csv):
        result = analyze_data(file_path=sample_csv)
        summary = json.loads(result)
        assert summary["success"] is True
        assert summary["rows"] == 4
        assert "revenue" in summary["numeric_columns"]
        assert len(summary["suggested_charts"]) > 0

    def test_file_not_found_error(self):
        result = analyze_data(file_path="/nonexistent/file.csv")
        info = json.loads(result)
        assert info["success"] is False
        assert info["error"]["type"] == "file_error"


# ---------------------------------------------------------------------------
# create_chart_from_file — structured returns
# ---------------------------------------------------------------------------

class TestCreateChartFromFile:
    def test_bar_from_csv(self, output_dir, sample_csv):
        result = create_chart_from_file(
            file_path=sample_csv,
            chart_type="bar",
            x_column="quarter",
            y_column="revenue",
            output_format="html",
            filename="from_file_test",
        )
        info = _parse_result(result)
        assert info["success"] is True
        assert (output_dir / "from_file_test.html").exists()

    def test_histogram_from_csv(self, output_dir, sample_csv):
        result = create_chart_from_file(
            file_path=sample_csv,
            chart_type="histogram",
            x_column="revenue",
            output_format="html",
            filename="hist_test",
        )
        info = _parse_result(result)
        assert info["success"] is True

    def test_grouped_bar(self, output_dir, sample_csv):
        result = create_chart_from_file(
            file_path=sample_csv,
            chart_type="bar",
            x_column="quarter",
            y_column="revenue",
            group_column="region",
            output_format="html",
            filename="grouped_test",
        )
        info = _parse_result(result)
        assert info["success"] is True

    def test_trace_properties_param(self, output_dir, sample_csv):
        result = create_chart_from_file(
            file_path=sample_csv,
            chart_type="bar",
            x_column="quarter",
            y_column="revenue",
            trace_properties={"marker_color": "blue"},
            output_format="html",
            filename="styled_test",
        )
        info = _parse_result(result)
        assert info["success"] is True

    def test_file_not_found_error(self, output_dir):
        result = create_chart_from_file(
            file_path="/nonexistent/file.csv",
            chart_type="bar",
            x_column="x",
            y_column="y",
        )
        info = _parse_result(result)
        assert info["success"] is False
        assert info["error"]["type"] == "file_error"


# ---------------------------------------------------------------------------
# create_dashboard
# ---------------------------------------------------------------------------

class TestCreateDashboard:
    def test_basic_2x1(self, output_dir):
        result = create_dashboard(
            panels=[
                {"row": 1, "col": 1, "traces": [{"type": "bar", "x": ["a", "b"], "y": [1, 2]}]},
                {"row": 2, "col": 1, "traces": [{"type": "scatter", "x": [1, 2], "y": [3, 4], "mode": "markers"}]},
            ],
            preset="2x1",
            output_format="html",
            filename="dash_test",
        )
        info = _parse_result(result)
        assert info["success"] is True
        assert info["panel_count"] == 2
        assert info["trace_count"] == 2
        assert (output_dir / "dash_test.html").exists()

    def test_2x2_with_mixed_types(self, output_dir):
        result = create_dashboard(
            panels=[
                {"row": 1, "col": 1, "traces": [{"type": "bar", "x": [1], "y": [2]}]},
                {"row": 1, "col": 2, "traces": [{"type": "pie", "labels": ["a", "b"], "values": [1, 2]}]},
                {"row": 2, "col": 1, "traces": [{"type": "scatter", "x": [1], "y": [2], "mode": "markers"}]},
                {"row": 2, "col": 2, "traces": [{"type": "histogram", "x": [1, 2, 3, 3, 4]}]},
            ],
            preset="2x2",
            output_format="html",
            filename="mixed_dash",
        )
        info = _parse_result(result)
        assert info["success"] is True
        assert info["trace_count"] == 4

    def test_invalid_preset_error(self, output_dir):
        result = create_dashboard(
            panels=[{"row": 1, "col": 1, "traces": [{"type": "bar", "x": [1], "y": [2]}]}],
            preset="nonexistent",
        )
        info = _parse_result(result)
        assert info["success"] is False

    def test_with_layout(self, output_dir):
        result = create_dashboard(
            panels=[
                {"row": 1, "col": 1, "traces": [{"type": "bar", "x": [1], "y": [2]}]},
            ],
            layout={"title": "My Dashboard"},
            output_format="html",
            filename="layout_dash",
        )
        info = _parse_result(result)
        assert info["success"] is True


# ---------------------------------------------------------------------------
# create_live_dashboard
# ---------------------------------------------------------------------------

class TestCreateLiveDashboard:
    def test_basic_dashboard(self, output_dir, sample_csv):
        result = create_live_dashboard(file_path=sample_csv, filename="live_test")
        info = json.loads(result)
        assert info["success"] is True
        assert len(info["files"]) == 1
        assert info["files"][0].endswith("live_test.html")
        assert info["panel_count"] >= 1
        assert info["filter_count"] >= 0
        assert info["theme"] == "light"
        assert info["server"] is None

    def test_dark_theme(self, output_dir, sample_csv):
        result = create_live_dashboard(
            file_path=sample_csv, theme="dark", filename="dark_dash"
        )
        info = json.loads(result)
        assert info["success"] is True
        assert info["theme"] == "dark"

    def test_with_metrics_hints(self, output_dir, sample_csv):
        result = create_live_dashboard(
            file_path=sample_csv, metrics=["revenue"], filename="kpi_test"
        )
        info = json.loads(result)
        assert info["success"] is True
        assert info["kpi_count"] >= 1

    def test_file_not_found_error(self, output_dir):
        result = create_live_dashboard(file_path="/nonexistent/file.csv")
        info = json.loads(result)
        assert info["success"] is False
        assert info["error"]["type"] == "file_error"

    def test_with_serve(self, output_dir, sample_csv):
        result = create_live_dashboard(
            file_path=sample_csv, serve=True, port=9500, filename="served_dash"
        )
        info = json.loads(result)
        assert info["success"] is True
        assert info["server"] is not None
        assert info["server"]["port"] >= 9500
        # Clean up
        from plotly_mcp.dashboard_server import stop_server
        stop_server()

    def test_refresh_only_with_serve(self, output_dir, sample_csv):
        # refresh_interval without serve should not include refresh indicator
        result = create_live_dashboard(
            file_path=sample_csv,
            refresh_interval=10,
            serve=False,
            filename="no_serve_refresh",
        )
        info = json.loads(result)
        assert info["success"] is True
        assert info["server"] is None
        assert "refresh_interval" not in info


# ---------------------------------------------------------------------------
# stop_dashboard_server
# ---------------------------------------------------------------------------

class TestStopDashboardServer:
    def test_stop_when_not_running(self):
        result = stop_dashboard_server(port=9999)
        info = json.loads(result)
        assert info["success"] is False
        assert "No active server" in info["error"]["message"]

    def test_stop_running_server(self, output_dir, sample_csv):
        # Start a server first
        create_live_dashboard(
            file_path=sample_csv, serve=True, port=9510, filename="stop_test"
        )
        # Stop it
        result = stop_dashboard_server(port=9510)
        info = json.loads(result)
        assert info["success"] is True
        assert "stopped" in info["message"]
