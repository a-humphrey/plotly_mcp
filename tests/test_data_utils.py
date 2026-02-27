"""Tests for data_utils.py — loading and summarization."""

import json
import tempfile
from pathlib import Path

import pandas as pd
import pytest

from plotly_mcp.data_utils import load_dataframe, summarize_dataframe


@pytest.fixture
def sample_csv(tmp_path):
    p = tmp_path / "data.csv"
    p.write_text("name,value,score\nAlice,10,3.5\nBob,20,7.2\nCarol,30,9.1\n")
    return str(p)


@pytest.fixture
def sample_json(tmp_path):
    p = tmp_path / "data.json"
    data = [{"x": 1, "y": 2}, {"x": 3, "y": 4}]
    p.write_text(json.dumps(data))
    return str(p)


@pytest.fixture
def sample_tsv(tmp_path):
    p = tmp_path / "data.tsv"
    p.write_text("col_a\tcol_b\n1\t2\n3\t4\n")
    return str(p)


class TestLoadDataframe:
    def test_load_csv(self, sample_csv):
        df = load_dataframe(sample_csv)
        assert len(df) == 3
        assert list(df.columns) == ["name", "value", "score"]

    def test_load_json(self, sample_json):
        df = load_dataframe(sample_json)
        assert len(df) == 2

    def test_load_tsv(self, sample_tsv):
        df = load_dataframe(sample_tsv)
        assert len(df) == 2

    def test_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            load_dataframe("/nonexistent/file.csv")

    def test_unsupported_extension(self, tmp_path):
        p = tmp_path / "data.xyz"
        p.write_text("hello")
        with pytest.raises(ValueError, match="Unsupported file extension"):
            load_dataframe(str(p))


class TestSummarizeDataframe:
    def test_summary_structure(self, sample_csv):
        df = load_dataframe(sample_csv)
        summary = summarize_dataframe(df)

        assert summary["rows"] == 3
        assert summary["columns"] == 3
        assert "name" in summary["column_names"]
        assert len(summary["sample_rows"]) == 3
        assert isinstance(summary["suggested_charts"], list)

    def test_numeric_stats(self, sample_csv):
        df = load_dataframe(sample_csv)
        summary = summarize_dataframe(df)
        assert "value" in summary["numeric_columns"]
        assert "value" in summary["numeric_stats"]

    def test_categorical_detected(self, sample_csv):
        df = load_dataframe(sample_csv)
        summary = summarize_dataframe(df)
        assert "name" in summary["categorical_columns"]

    def test_suggestions_not_empty(self, sample_csv):
        df = load_dataframe(sample_csv)
        summary = summarize_dataframe(df)
        assert len(summary["suggested_charts"]) > 0
        types = {s["chart_type"] for s in summary["suggested_charts"]}
        # With categorical + numeric columns, expect bar and pie at minimum
        assert "bar" in types
