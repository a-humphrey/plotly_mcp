"""Tests for auto_layout.py — DataFrame analysis and dashboard spec generation."""

import pandas as pd
import pytest

from plotly_mcp.auto_layout import (
    analyze_columns,
    build_auto_layout,
    select_kpi_metrics,
)


@pytest.fixture
def sales_df():
    return pd.DataFrame({
        "date": pd.to_datetime(["2024-01-01", "2024-02-01", "2024-03-01", "2024-04-01"]),
        "revenue": [100, 150, 200, 175],
        "profit": [20, 35, 50, 40],
        "region": ["East", "West", "East", "West"],
        "product": ["A", "B", "A", "B"],
    })


@pytest.fixture
def numeric_only_df():
    return pd.DataFrame({
        "x": [1, 2, 3, 4, 5],
        "y": [10, 20, 30, 40, 50],
        "z": [5, 15, 25, 35, 45],
    })


@pytest.fixture
def high_cardinality_df():
    return pd.DataFrame({
        "id": [f"ID_{i}" for i in range(50)],
        "value": range(50),
        "category": ["A", "B"] * 25,
    })


class TestAnalyzeColumns:
    def test_detects_numeric(self, sales_df):
        info = analyze_columns(sales_df)
        assert "revenue" in info["numeric"]
        assert "profit" in info["numeric"]

    def test_detects_categorical(self, sales_df):
        info = analyze_columns(sales_df)
        assert "region" in info["categorical"]
        assert "product" in info["categorical"]

    def test_detects_datetime(self, sales_df):
        info = analyze_columns(sales_df)
        assert "date" in info["datetime"]

    def test_detects_id_like_high_cardinality(self, high_cardinality_df):
        info = analyze_columns(high_cardinality_df)
        assert "id" in info["id_like"]
        assert "id" not in info["categorical"]

    def test_string_dates_detected(self):
        df = pd.DataFrame({
            "date_str": ["2024-01-01", "2024-02-01", "2024-03-01"],
            "value": [1, 2, 3],
        })
        info = analyze_columns(df)
        assert "date_str" in info["datetime"]

    def test_empty_dataframe(self):
        df = pd.DataFrame()
        info = analyze_columns(df)
        assert info["numeric"] == []
        assert info["categorical"] == []
        assert info["datetime"] == []
        assert info["id_like"] == []

    def test_all_types_present(self, sales_df):
        info = analyze_columns(sales_df)
        for key in ("numeric", "categorical", "datetime", "id_like"):
            assert key in info


class TestSelectKpiMetrics:
    def test_prefers_kpi_named_columns(self, sales_df):
        kpis = select_kpi_metrics(sales_df, ["revenue", "profit"])
        # revenue and profit match KPI patterns
        assert len(kpis) >= 1
        labels = [k["column"] for k in kpis]
        assert "revenue" in labels

    def test_respects_hints(self, sales_df):
        kpis = select_kpi_metrics(sales_df, ["revenue", "profit"], hints=["profit"])
        assert len(kpis) == 1
        assert kpis[0]["column"] == "profit"

    def test_caps_at_4(self):
        df = pd.DataFrame({f"metric_{i}": [i * 10] for i in range(10)})
        kpis = select_kpi_metrics(df, [f"metric_{i}" for i in range(10)])
        assert len(kpis) <= 4

    def test_no_numeric_returns_empty(self):
        df = pd.DataFrame({"name": ["a", "b"]})
        kpis = select_kpi_metrics(df, [])
        assert kpis == []

    def test_kpi_has_required_fields(self, sales_df):
        kpis = select_kpi_metrics(sales_df, ["revenue"])
        assert len(kpis) >= 1
        kpi = kpis[0]
        assert "column" in kpi
        assert "label" in kpi
        assert "value" in kpi
        assert "format_str" in kpi


class TestBuildAutoLayout:
    def test_returns_required_keys(self, sales_df):
        layout = build_auto_layout(sales_df)
        assert "title" in layout
        assert "kpis" in layout
        assert "panels" in layout
        assert "filters" in layout
        assert "grid_cols" in layout

    def test_generates_time_series_panel(self, sales_df):
        layout = build_auto_layout(sales_df)
        types = [p["type"] for p in layout["panels"]]
        assert "time_series" in types

    def test_generates_bar_panel(self, sales_df):
        layout = build_auto_layout(sales_df)
        types = [p["type"] for p in layout["panels"]]
        assert "bar" in types

    def test_generates_data_table(self, sales_df):
        layout = build_auto_layout(sales_df)
        types = [p["type"] for p in layout["panels"]]
        assert "table" in types

    def test_generates_filters_for_categorical(self, sales_df):
        layout = build_auto_layout(sales_df)
        filter_cols = [f["column"] for f in layout["filters"]]
        assert "region" in filter_cols

    def test_generates_date_filter(self, sales_df):
        layout = build_auto_layout(sales_df)
        date_filters = [f for f in layout["filters"] if f["type"] == "date_range"]
        assert len(date_filters) >= 1

    def test_custom_title(self, sales_df):
        layout = build_auto_layout(sales_df, title="Sales Report")
        assert layout["title"] == "Sales Report"

    def test_numeric_only_gets_histogram(self, numeric_only_df):
        layout = build_auto_layout(numeric_only_df)
        types = [p["type"] for p in layout["panels"]]
        assert "histogram" in types
        # Should not have bar or pie without categorical
        assert "bar" not in types
        assert "pie" not in types

    def test_user_hints_override_detection(self, sales_df):
        layout = build_auto_layout(
            sales_df,
            metrics=["profit"],
            time_column="date",
            category_column="region",
        )
        kpi_cols = [k["column"] for k in layout["kpis"]]
        assert kpi_cols == ["profit"]

    def test_grid_cols_scales_with_panels(self, sales_df):
        layout = build_auto_layout(sales_df)
        chart_panels = [p for p in layout["panels"] if p["type"] != "table"]
        if len(chart_panels) <= 1:
            assert layout["grid_cols"] == 1
        elif len(chart_panels) <= 2:
            assert layout["grid_cols"] == 2
        else:
            assert layout["grid_cols"] <= 3

    def test_empty_dataframe(self):
        df = pd.DataFrame()
        layout = build_auto_layout(df)
        assert layout["kpis"] == []
        # Should at least have the table panel
        assert len(layout["panels"]) >= 1
