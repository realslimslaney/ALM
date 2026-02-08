"""Tests for alm.plot module (line_chart, bar_chart)."""

import plotly.graph_objects as go
import polars as pl
import pytest

from alm.plot import PALETTE, bar_chart, line_chart


@pytest.fixture()
def sample_df() -> pl.DataFrame:
    """Simple DataFrame for chart tests."""
    return pl.DataFrame(
        {
            "year": [1, 2, 3, 4],
            "assets": [100.0, 105.0, 110.0, 115.0],
            "liabilities": [90.0, 92.0, 95.0, 98.0],
            "group": ["A", "A", "B", "B"],
        }
    )


# ---------------------------------------------------------------------------
# line_chart
# ---------------------------------------------------------------------------


class TestLineChart:
    """Tests for line_chart."""

    def test_returns_figure(self, sample_df: pl.DataFrame):
        fig = line_chart(sample_df, x="year", y="assets")
        assert isinstance(fig, go.Figure)

    def test_single_y_trace(self, sample_df: pl.DataFrame):
        fig = line_chart(sample_df, x="year", y="assets")
        assert len(fig.data) == 1

    def test_multi_y_traces(self, sample_df: pl.DataFrame):
        fig = line_chart(sample_df, x="year", y=["assets", "liabilities"])
        assert len(fig.data) == 2
        names = {t.name for t in fig.data}
        assert names == {"assets", "liabilities"}

    def test_color_grouping(self, sample_df: pl.DataFrame):
        fig = line_chart(sample_df, x="year", y="assets", color="group")
        assert len(fig.data) == 2

    def test_title_applied(self, sample_df: pl.DataFrame):
        fig = line_chart(sample_df, x="year", y="assets", title="My Chart")
        assert fig.layout.title.text == "My Chart"

    def test_axis_labels(self, sample_df: pl.DataFrame):
        fig = line_chart(sample_df, x="year", y="assets", xlab="Year", ylab="Value ($)")
        assert fig.layout.xaxis.title.text == "Year"
        assert fig.layout.yaxis.title.text == "Value ($)"

    def test_currency_format(self, sample_df: pl.DataFrame):
        fig = line_chart(sample_df, x="year", y="assets", yformat="$")
        assert fig.layout.yaxis.tickprefix == "$"

    def test_percent_format(self, sample_df: pl.DataFrame):
        fig = line_chart(sample_df, x="year", y="assets", yformat="%")
        assert fig.layout.yaxis.tickformat == ".1%"


# ---------------------------------------------------------------------------
# bar_chart
# ---------------------------------------------------------------------------


class TestBarChart:
    """Tests for bar_chart."""

    def test_returns_figure(self, sample_df: pl.DataFrame):
        fig = bar_chart(sample_df, x="year", y="assets")
        assert isinstance(fig, go.Figure)

    def test_single_y_trace(self, sample_df: pl.DataFrame):
        fig = bar_chart(sample_df, x="year", y="assets")
        assert len(fig.data) == 1

    def test_multi_y_traces(self, sample_df: pl.DataFrame):
        fig = bar_chart(sample_df, x="year", y=["assets", "liabilities"])
        assert len(fig.data) == 2

    def test_color_grouping(self, sample_df: pl.DataFrame):
        fig = bar_chart(sample_df, x="year", y="assets", color="group")
        assert len(fig.data) == 2

    def test_barmode_default(self, sample_df: pl.DataFrame):
        fig = bar_chart(sample_df, x="year", y=["assets", "liabilities"])
        assert fig.layout.barmode == "group"

    def test_barmode_stack(self, sample_df: pl.DataFrame):
        fig = bar_chart(sample_df, x="year", y=["assets", "liabilities"], barmode="stack")
        assert fig.layout.barmode == "stack"


# ---------------------------------------------------------------------------
# PALETTE
# ---------------------------------------------------------------------------


def test_palette_has_enough_colors():
    assert len(PALETTE) >= 10
