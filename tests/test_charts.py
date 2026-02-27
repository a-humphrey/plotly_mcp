"""Tests for charts.py — generic trace engine, dashboard builder, and save logic."""

import os

import plotly.graph_objects as go
import pytest

from plotly_mcp.charts import (
    DASHBOARD_PRESETS,
    LEGACY_ALIASES,
    SUPPORTED_CHART_TYPES,
    TRACE_TYPE_MAP,
    build_chart,
    build_chart_generic,
    build_dashboard,
    resolve_trace_class,
    save_chart,
)


# ---------------------------------------------------------------------------
# Trace type map & resolution
# ---------------------------------------------------------------------------

class TestTraceTypeMap:
    def test_map_has_many_types(self):
        # Plotly v5 has ~50 trace types
        assert len(TRACE_TYPE_MAP) >= 40

    def test_supported_list_includes_aliases(self):
        for alias in LEGACY_ALIASES:
            assert alias in SUPPORTED_CHART_TYPES

    def test_common_types_present(self):
        for t in ("scatter", "bar", "pie", "histogram", "heatmap", "box",
                   "violin", "funnel", "treemap", "sunburst", "scatter3d",
                   "candlestick", "sankey", "indicator", "waterfall",
                   "choropleth", "table"):
            assert t in TRACE_TYPE_MAP, f"{t} missing from TRACE_TYPE_MAP"

    def test_resolve_direct(self):
        cls, defaults = resolve_trace_class("bar")
        assert cls is go.Bar
        assert defaults == {}

    def test_resolve_case_insensitive(self):
        cls, _ = resolve_trace_class("Bar")
        assert cls is go.Bar

    def test_resolve_alias_line(self):
        cls, defaults = resolve_trace_class("line")
        assert cls is go.Scatter
        assert defaults == {"mode": "lines"}

    def test_resolve_alias_area(self):
        cls, defaults = resolve_trace_class("area")
        assert cls is go.Scatter
        assert defaults == {"fill": "tozeroy"}

    def test_resolve_alias_scatter_3d(self):
        cls, defaults = resolve_trace_class("scatter_3d")
        assert cls is go.Scatter3d
        assert defaults == {}

    def test_resolve_unknown_raises(self):
        with pytest.raises(ValueError, match="Unknown trace type"):
            resolve_trace_class("totally_fake_type")

    def test_resolve_suggests_similar(self):
        with pytest.raises(ValueError, match="Did you mean"):
            resolve_trace_class("scater")  # typo


# ---------------------------------------------------------------------------
# Backward-compatible build_chart (single-trace, old API)
# ---------------------------------------------------------------------------

class TestBuildChart:
    """Test that the backward-compatible build_chart API still works."""

    def test_line(self):
        fig = build_chart("line", {"x": [1, 2, 3], "y": [10, 20, 30]})
        assert isinstance(fig, go.Figure)
        assert len(fig.data) == 1
        assert fig.data[0].mode == "lines"

    def test_bar(self):
        fig = build_chart("bar", {"x": ["Q1", "Q2", "Q3"], "y": [100, 150, 200]})
        assert isinstance(fig, go.Figure)

    def test_scatter(self):
        fig = build_chart("scatter", {"x": [1, 2, 3], "y": [4, 5, 6], "mode": "markers"})
        assert isinstance(fig, go.Figure)

    def test_pie(self):
        fig = build_chart("pie", {"labels": ["A", "B", "C"], "values": [30, 50, 20]})
        assert isinstance(fig, go.Figure)

    def test_histogram(self):
        fig = build_chart("histogram", {"x": [1, 2, 2, 3, 3, 3, 4]})
        assert isinstance(fig, go.Figure)

    def test_heatmap(self):
        fig = build_chart("heatmap", {"z": [[1, 2], [3, 4]]})
        assert isinstance(fig, go.Figure)

    def test_box(self):
        fig = build_chart("box", {"y": [1, 2, 3, 4, 5]})
        assert isinstance(fig, go.Figure)

    def test_area(self):
        fig = build_chart("area", {"x": [1, 2, 3], "y": [10, 20, 30]})
        assert isinstance(fig, go.Figure)
        assert fig.data[0].fill == "tozeroy"

    def test_violin(self):
        fig = build_chart("violin", {"y": [1, 2, 3, 4, 5]})
        assert isinstance(fig, go.Figure)

    def test_funnel(self):
        fig = build_chart("funnel", {"y": ["Visit", "Cart", "Buy"], "x": [100, 50, 20]})
        assert isinstance(fig, go.Figure)

    def test_scatter_3d(self):
        fig = build_chart("scatter_3d", {"x": [1, 2], "y": [3, 4], "z": [5, 6]})
        assert isinstance(fig, go.Figure)

    def test_treemap(self):
        fig = build_chart("treemap", {
            "labels": ["Root", "A", "B"],
            "parents": ["", "Root", "Root"],
            "values": [0, 10, 20],
        })
        assert isinstance(fig, go.Figure)

    def test_sunburst(self):
        fig = build_chart("sunburst", {
            "labels": ["Root", "A", "B"],
            "parents": ["", "Root", "Root"],
            "values": [0, 10, 20],
        })
        assert isinstance(fig, go.Figure)

    def test_with_layout(self):
        fig = build_chart("bar", {"x": ["a"], "y": [1]}, layout={"title": "Test"})
        assert fig.layout.title.text == "Test"

    def test_unsupported_type_raises(self):
        with pytest.raises(ValueError, match="Unknown trace type"):
            build_chart("unknown_type", {})

    # --- Style pass-through tests ---

    def test_bar_style_marker_color(self):
        fig = build_chart("bar", {
            "x": ["Q1", "Q2", "Q3"],
            "y": [100, 150, 200],
            "style": {"marker_color": "red"},
        })
        assert fig.data[0].marker.color == "red"

    def test_line_style_dash(self):
        fig = build_chart("line", {
            "x": [1, 2, 3],
            "y": [10, 20, 30],
            "style": {"line": {"dash": "dash"}},
        })
        assert fig.data[0].line.dash == "dash"

    def test_pie_style_colors(self):
        colors = ["red", "blue", "green"]
        fig = build_chart("pie", {
            "labels": ["A", "B", "C"],
            "values": [30, 50, 20],
            "style": {"marker": {"colors": colors}},
        })
        assert list(fig.data[0].marker.colors) == colors

    def test_empty_style_no_regression(self):
        fig = build_chart("bar", {
            "x": ["a", "b"],
            "y": [1, 2],
            "style": {},
        })
        assert isinstance(fig, go.Figure)
        assert len(fig.data) == 1

    # --- New trace types (previously unsupported) ---

    def test_candlestick(self):
        fig = build_chart("candlestick", {
            "x": ["2024-01-01", "2024-01-02"],
            "open": [10, 12],
            "high": [15, 14],
            "low": [9, 11],
            "close": [13, 12],
        })
        assert isinstance(fig, go.Figure)
        assert isinstance(fig.data[0], go.Candlestick)

    def test_indicator(self):
        fig = build_chart("indicator", {
            "mode": "number+delta",
            "value": 450,
            "delta": {"reference": 400},
        })
        assert isinstance(fig, go.Figure)
        assert isinstance(fig.data[0], go.Indicator)

    def test_waterfall(self):
        fig = build_chart("waterfall", {
            "x": ["Start", "A", "B", "Total"],
            "y": [100, -20, 30, 110],
            "measure": ["absolute", "relative", "relative", "total"],
        })
        assert isinstance(fig, go.Figure)
        assert isinstance(fig.data[0], go.Waterfall)


# ---------------------------------------------------------------------------
# build_chart_generic (multi-trace)
# ---------------------------------------------------------------------------

class TestBuildChartGeneric:
    def test_single_trace(self):
        fig = build_chart_generic([{"type": "bar", "x": ["a"], "y": [1]}])
        assert len(fig.data) == 1

    def test_multi_trace(self):
        fig = build_chart_generic([
            {"type": "scatter", "x": [1, 2], "y": [3, 4], "mode": "lines", "name": "A"},
            {"type": "bar", "x": [1, 2], "y": [5, 6], "name": "B"},
        ])
        assert len(fig.data) == 2

    def test_with_layout(self):
        fig = build_chart_generic(
            [{"type": "bar", "x": [1], "y": [2]}],
            layout={"title": "Multi"},
        )
        assert fig.layout.title.text == "Multi"

    def test_missing_type_raises(self):
        with pytest.raises(ValueError, match="missing a 'type' key"):
            build_chart_generic([{"x": [1], "y": [2]}])

    def test_legacy_alias_in_traces(self):
        fig = build_chart_generic([{"type": "line", "x": [1, 2], "y": [3, 4]}])
        assert fig.data[0].mode == "lines"

    @pytest.mark.parametrize("trace_type,kwargs", [
        ("scatter", {"x": [1], "y": [2], "mode": "markers"}),
        ("bar", {"x": ["a"], "y": [1]}),
        ("pie", {"labels": ["a", "b"], "values": [1, 2]}),
        ("heatmap", {"z": [[1, 2], [3, 4]]}),
        ("scatter3d", {"x": [1], "y": [2], "z": [3]}),
        ("indicator", {"mode": "number", "value": 42}),
        ("sankey", {
            "node": {"label": ["A", "B", "C"]},
            "link": {"source": [0, 0], "target": [1, 2], "value": [10, 20]},
        }),
    ])
    def test_various_trace_types(self, trace_type, kwargs):
        fig = build_chart_generic([{"type": trace_type, **kwargs}])
        assert isinstance(fig, go.Figure)
        assert len(fig.data) == 1


# ---------------------------------------------------------------------------
# build_dashboard
# ---------------------------------------------------------------------------

class TestBuildDashboard:
    def test_basic_2x2(self):
        panels = [
            {"row": 1, "col": 1, "traces": [{"type": "bar", "x": [1], "y": [2]}]},
            {"row": 1, "col": 2, "traces": [{"type": "scatter", "x": [1], "y": [2], "mode": "markers"}]},
            {"row": 2, "col": 1, "traces": [{"type": "bar", "x": [3], "y": [4]}]},
            {"row": 2, "col": 2, "traces": [{"type": "scatter", "x": [3], "y": [4], "mode": "lines"}]},
        ]
        fig = build_dashboard(panels, preset="2x2")
        assert isinstance(fig, go.Figure)
        assert len(fig.data) == 4

    def test_mixed_subplot_types(self):
        panels = [
            {"row": 1, "col": 1, "traces": [{"type": "pie", "labels": ["a", "b"], "values": [1, 2]}]},
            {"row": 1, "col": 2, "traces": [{"type": "bar", "x": [1], "y": [2]}]},
        ]
        fig = build_dashboard(panels, preset="1x2")
        assert isinstance(fig, go.Figure)
        assert len(fig.data) == 2

    def test_preset_sidebar(self):
        panels = [
            {"row": 1, "col": 1, "traces": [{"type": "scatter", "x": [1], "y": [2], "mode": "markers"}]},
            {"row": 1, "col": 2, "traces": [{"type": "bar", "x": [1], "y": [2]}]},
        ]
        fig = build_dashboard(panels, preset="sidebar")
        assert isinstance(fig, go.Figure)

    def test_auto_detect_grid(self):
        panels = [
            {"row": 1, "col": 1, "traces": [{"type": "bar", "x": [1], "y": [2]}]},
            {"row": 2, "col": 1, "traces": [{"type": "bar", "x": [3], "y": [4]}]},
        ]
        fig = build_dashboard(panels)
        assert isinstance(fig, go.Figure)
        assert len(fig.data) == 2

    def test_with_layout(self):
        panels = [
            {"row": 1, "col": 1, "traces": [{"type": "bar", "x": [1], "y": [2]}]},
        ]
        fig = build_dashboard(panels, layout={"title": "Dashboard"})
        assert fig.layout.title.text == "Dashboard"

    def test_unknown_preset_raises(self):
        with pytest.raises(ValueError, match="Unknown preset"):
            build_dashboard(
                [{"row": 1, "col": 1, "traces": [{"type": "bar", "x": [1], "y": [2]}]}],
                preset="nonexistent",
            )

    def test_all_presets_valid(self):
        for preset_name in DASHBOARD_PRESETS:
            config = DASHBOARD_PRESETS[preset_name]
            assert "rows" in config
            assert "cols" in config


# ---------------------------------------------------------------------------
# save_chart (unchanged logic, existing tests)
# ---------------------------------------------------------------------------

class TestSaveChart:
    def test_save_html(self, tmp_path, monkeypatch):
        monkeypatch.setenv("PLOTLY_MCP_OUTPUT_DIR", str(tmp_path))
        fig = build_chart("bar", {"x": ["a"], "y": [1]})
        paths = save_chart(fig, output_format="html", filename="test_out")
        assert len(paths) == 1
        assert paths[0].endswith(".html")
        assert os.path.exists(paths[0])

    def test_save_png(self, tmp_path, monkeypatch):
        monkeypatch.setenv("PLOTLY_MCP_OUTPUT_DIR", str(tmp_path))
        fig = build_chart("bar", {"x": ["a"], "y": [1]})
        paths = save_chart(fig, output_format="png", filename="test_out")
        assert len(paths) == 1
        assert paths[0].endswith(".png")
        assert os.path.exists(paths[0])

    def test_save_both(self, tmp_path, monkeypatch):
        monkeypatch.setenv("PLOTLY_MCP_OUTPUT_DIR", str(tmp_path))
        fig = build_chart("bar", {"x": ["a"], "y": [1]})
        paths = save_chart(fig, output_format="both", filename="test_out")
        assert len(paths) == 2
        extensions = {p.split(".")[-1] for p in paths}
        assert extensions == {"html", "png"}

    def test_invalid_format_raises(self, tmp_path, monkeypatch):
        monkeypatch.setenv("PLOTLY_MCP_OUTPUT_DIR", str(tmp_path))
        fig = build_chart("bar", {"x": ["a"], "y": [1]})
        with pytest.raises(ValueError, match="Invalid output_format"):
            save_chart(fig, output_format="pdf")

    def test_auto_filename(self, tmp_path, monkeypatch):
        monkeypatch.setenv("PLOTLY_MCP_OUTPUT_DIR", str(tmp_path))
        fig = build_chart("bar", {"x": ["a"], "y": [1]})
        paths = save_chart(fig, output_format="html")
        assert len(paths) == 1
        assert "chart_" in os.path.basename(paths[0])
