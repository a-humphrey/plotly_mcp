"""Auto-layout engine: analyze a DataFrame and produce a dashboard specification."""

from __future__ import annotations

import warnings
from typing import Any

import pandas as pd

# Column name patterns that suggest KPI-worthy metrics
_KPI_PATTERNS = ("revenue", "total", "count", "amount", "sales", "profit", "cost", "price")

# Maximum unique values for a categorical column to be used in charts/filters
_MAX_CATEGORICAL_UNIQUE = 20

# Maximum KPI cards to show
_MAX_KPIS = 4

# Maximum chart panels (excluding KPI row and data table)
_MAX_CHART_PANELS = 4


def analyze_columns(df: pd.DataFrame) -> dict[str, list[str]]:
    """Classify DataFrame columns by type.

    Returns dict with keys: numeric, categorical, datetime, id_like.
    High-cardinality categoricals (>20 unique) are classified as id_like.
    """
    numeric = df.select_dtypes(include="number").columns.tolist()
    datetime_cols = df.select_dtypes(include="datetime").columns.tolist()

    # Also detect string columns that look like dates
    object_cols = df.select_dtypes(include=["object", "category", "string"]).columns.tolist()
    detected_datetime: list[str] = []
    categorical: list[str] = []
    id_like: list[str] = []

    for col in object_cols:
        # Try to parse as datetime
        if len(df) > 0:
            sample = df[col].dropna().head(20)
            if len(sample) > 0:
                try:
                    with warnings.catch_warnings():
                        warnings.simplefilter("ignore", UserWarning)
                        pd.to_datetime(sample)
                    detected_datetime.append(col)
                    continue
                except (ValueError, TypeError):
                    pass

        nunique = df[col].nunique()
        if nunique > _MAX_CATEGORICAL_UNIQUE:
            id_like.append(col)
        else:
            categorical.append(col)

    return {
        "numeric": numeric,
        "categorical": categorical,
        "datetime": datetime_cols + detected_datetime,
        "id_like": id_like,
    }


def select_kpi_metrics(
    df: pd.DataFrame,
    numeric_cols: list[str],
    hints: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Select columns for KPI indicator cards.

    Returns list of dicts with: column, label, value, format_str.
    Prefers columns whose names match common KPI patterns.
    """
    if not numeric_cols:
        return []

    if hints:
        # Use only valid hints that exist in numeric_cols
        selected = [c for c in hints if c in numeric_cols]
    else:
        # Score columns by KPI-likeness
        scored: list[tuple[str, int]] = []
        for col in numeric_cols:
            col_lower = col.lower()
            score = sum(1 for p in _KPI_PATTERNS if p in col_lower)
            scored.append((col, score))
        # Sort by score descending, then by original order
        scored.sort(key=lambda x: -x[1])
        selected = [col for col, _ in scored]

    selected = selected[:_MAX_KPIS]

    kpis: list[dict[str, Any]] = []
    for col in selected:
        series = df[col].dropna()
        if len(series) == 0:
            continue
        value = float(series.sum())
        # Format large numbers with commas, small with 2 decimals
        if abs(value) >= 1000:
            fmt = ",.0f"
        elif abs(value) >= 1:
            fmt = ",.2f"
        else:
            fmt = ".4f"
        kpis.append({
            "column": col,
            "label": col.replace("_", " ").title(),
            "value": value,
            "format_str": fmt,
        })

    return kpis


def build_auto_layout(
    df: pd.DataFrame,
    title: str = "Dashboard",
    metrics: list[str] | None = None,
    time_column: str | None = None,
    category_column: str | None = None,
    max_panels: int = _MAX_CHART_PANELS,
) -> dict[str, Any]:
    """Build a complete dashboard layout specification from a DataFrame.

    Returns a dict with: title, panels, filters, kpis, grid_cols.
    """
    col_info = analyze_columns(df)
    numeric_cols = col_info["numeric"]
    categorical_cols = col_info["categorical"]
    datetime_cols = col_info["datetime"]

    # Override auto-detected columns with user hints
    if time_column and time_column not in datetime_cols:
        datetime_cols = [time_column] + datetime_cols
    if category_column and category_column not in categorical_cols:
        categorical_cols = [category_column] + categorical_cols

    # --- KPIs ---
    kpis = select_kpi_metrics(df, numeric_cols, hints=metrics)

    # --- Panels ---
    panels: list[dict[str, Any]] = []
    panel_id = 0

    # 1. Time series panel
    if datetime_cols and numeric_cols and panel_id < max_panels:
        dt_col = datetime_cols[0]
        y_cols = numeric_cols[:3]  # up to 3 lines
        panels.append({
            "id": f"panel_{panel_id}",
            "type": "time_series",
            "chart_type": "scatter",
            "title": f"{', '.join(y_cols)} over Time",
            "x_column": dt_col,
            "y_columns": y_cols,
            "mode": "lines+markers",
        })
        panel_id += 1

    # 2. Categorical breakdown (bar chart)
    if categorical_cols and numeric_cols and panel_id < max_panels:
        cat_col = categorical_cols[0]
        num_col = numeric_cols[0]
        panels.append({
            "id": f"panel_{panel_id}",
            "type": "bar",
            "chart_type": "bar",
            "title": f"{num_col.replace('_', ' ').title()} by {cat_col.replace('_', ' ').title()}",
            "x_column": cat_col,
            "y_column": num_col,
            "aggregate": "sum",
        })
        panel_id += 1

    # 3. Distribution (pie chart for categorical+numeric, histogram for numeric)
    if categorical_cols and numeric_cols and panel_id < max_panels:
        cat_col = categorical_cols[0]
        num_col = numeric_cols[0]
        panels.append({
            "id": f"panel_{panel_id}",
            "type": "pie",
            "chart_type": "pie",
            "title": f"{num_col.replace('_', ' ').title()} Distribution",
            "labels_column": cat_col,
            "values_column": num_col,
        })
        panel_id += 1
    elif numeric_cols and panel_id < max_panels:
        panels.append({
            "id": f"panel_{panel_id}",
            "type": "histogram",
            "chart_type": "histogram",
            "title": f"{numeric_cols[0].replace('_', ' ').title()} Distribution",
            "x_column": numeric_cols[0],
        })
        panel_id += 1

    # 4. Data table (always last)
    panels.append({
        "id": f"panel_{panel_id}",
        "type": "table",
        "chart_type": "table",
        "title": "Data Preview",
        "max_rows": 100,
    })

    # --- Filters ---
    filters: list[dict[str, Any]] = []
    for col in categorical_cols:
        if df[col].nunique() <= _MAX_CATEGORICAL_UNIQUE:
            unique_vals = sorted(df[col].dropna().unique().tolist(), key=str)
            filters.append({
                "column": col,
                "type": "dropdown",
                "label": col.replace("_", " ").title(),
                "options": unique_vals,
            })
    for col in datetime_cols:
        filters.append({
            "column": col,
            "type": "date_range",
            "label": col.replace("_", " ").title(),
        })

    # --- Grid columns ---
    # Chart panels (excluding table) determine grid layout
    chart_panel_count = len([p for p in panels if p["type"] != "table"])
    if chart_panel_count <= 1:
        grid_cols = 1
    elif chart_panel_count <= 2:
        grid_cols = 2
    else:
        grid_cols = min(chart_panel_count, 3)

    return {
        "title": title,
        "kpis": kpis,
        "panels": panels,
        "filters": filters,
        "grid_cols": grid_cols,
        "column_info": col_info,
    }
