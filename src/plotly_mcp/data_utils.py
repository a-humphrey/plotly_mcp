"""Data file loading, summarization, and chart suggestion heuristics."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd


def load_dataframe(file_path: str) -> pd.DataFrame:
    """Load a file into a DataFrame based on its extension."""
    p = Path(file_path)
    if not p.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    ext = p.suffix.lower()
    if ext == ".csv":
        return pd.read_csv(p)
    elif ext == ".tsv":
        return pd.read_csv(p, sep="\t")
    elif ext in (".xls", ".xlsx"):
        return pd.read_excel(p)
    elif ext == ".json":
        return pd.read_json(p)
    else:
        raise ValueError(f"Unsupported file extension '{ext}'. Supported: .csv, .tsv, .xls, .xlsx, .json")


def summarize_dataframe(df: pd.DataFrame) -> dict[str, Any]:
    """Return a summary dict describing the DataFrame."""
    numeric_cols = df.select_dtypes(include="number").columns.tolist()
    categorical_cols = df.select_dtypes(include=["object", "category", "str"]).columns.tolist()
    datetime_cols = df.select_dtypes(include="datetime").columns.tolist()

    stats = {}
    if numeric_cols:
        stats = df[numeric_cols].describe().to_dict()

    return {
        "rows": len(df),
        "columns": len(df.columns),
        "column_names": df.columns.tolist(),
        "column_types": {col: str(dtype) for col, dtype in df.dtypes.items()},
        "null_counts": df.isnull().sum().to_dict(),
        "numeric_columns": numeric_cols,
        "categorical_columns": categorical_cols,
        "datetime_columns": datetime_cols,
        "numeric_stats": stats,
        "sample_rows": df.head(5).to_dict(orient="records"),
        "suggested_charts": _suggest_charts(df, numeric_cols, categorical_cols, datetime_cols),
    }


def _suggest_charts(
    df: pd.DataFrame,
    numeric_cols: list[str],
    categorical_cols: list[str],
    datetime_cols: list[str],
) -> list[dict[str, str]]:
    """Heuristic chart suggestions based on column types."""
    suggestions: list[dict[str, str]] = []

    if datetime_cols and numeric_cols:
        suggestions.append({
            "chart_type": "line",
            "reason": f"Time series: '{datetime_cols[0]}' vs numeric columns",
            "x_column": datetime_cols[0],
            "y_column": numeric_cols[0],
        })

    if categorical_cols and numeric_cols:
        suggestions.append({
            "chart_type": "bar",
            "reason": f"Compare '{numeric_cols[0]}' across '{categorical_cols[0]}' categories",
            "x_column": categorical_cols[0],
            "y_column": numeric_cols[0],
        })
        suggestions.append({
            "chart_type": "waterfall",
            "reason": f"Show cumulative effect of '{numeric_cols[0]}' across '{categorical_cols[0]}'",
            "x_column": categorical_cols[0],
            "y_column": numeric_cols[0],
        })

    if len(numeric_cols) >= 2:
        suggestions.append({
            "chart_type": "scatter",
            "reason": f"Relationship between '{numeric_cols[0]}' and '{numeric_cols[1]}'",
            "x_column": numeric_cols[0],
            "y_column": numeric_cols[1],
        })

    if categorical_cols and numeric_cols:
        suggestions.append({
            "chart_type": "pie",
            "reason": f"Distribution of '{numeric_cols[0]}' by '{categorical_cols[0]}'",
            "x_column": categorical_cols[0],
            "y_column": numeric_cols[0],
        })

    if numeric_cols:
        suggestions.append({
            "chart_type": "histogram",
            "reason": f"Distribution of '{numeric_cols[0]}'",
            "x_column": numeric_cols[0],
        })
        suggestions.append({
            "chart_type": "indicator",
            "reason": f"Single-value display of '{numeric_cols[0]}' (sum, mean, latest)",
        })

    if numeric_cols and categorical_cols:
        suggestions.append({
            "chart_type": "box",
            "reason": f"Spread of '{numeric_cols[0]}' by '{categorical_cols[0]}'",
            "x_column": categorical_cols[0],
            "y_column": numeric_cols[0],
        })

    # OHLC / candlestick — if columns look like financial data
    ohlc_names = {"open", "high", "low", "close"}
    col_lower = {c.lower() for c in df.columns}
    if ohlc_names.issubset(col_lower) and datetime_cols:
        suggestions.append({
            "chart_type": "candlestick",
            "reason": "OHLC columns detected — financial candlestick chart",
            "x_column": datetime_cols[0],
        })

    return suggestions
