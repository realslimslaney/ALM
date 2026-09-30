"""Tests for alm.plot module (line_chart, bar_chart, area_chart)."""

import plotly.graph_objects as go
import plotly.io as pio
import polars as pl

from alm.plot import (
    PALETTE,
    QUARTO_RENDERER,
    area_chart,
    bar_chart,
    line_chart,
    use_quarto_renderer,
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
# area_chart
# ---------------------------------------------------------------------------


class TestAreaChart:
    """Tests for area_chart."""

    def test_returns_figure(self, sample_df: pl.DataFrame):
        fig = area_chart(sample_df, x="year", y=["assets", "liabilities"])
        assert isinstance(fig, go.Figure)

    def test_trace_count_matches_y(self, sample_df: pl.DataFrame):
        fig = area_chart(sample_df, x="year", y=["assets", "liabilities"])
        assert len(fig.data) == 2

    def test_stacked_sets_stackgroup(self, sample_df: pl.DataFrame):
        fig = area_chart(sample_df, x="year", y=["assets", "liabilities"], stacked=True)
        for trace in fig.data:
            assert trace.stackgroup == "one"

    def test_unstacked_no_stackgroup(self, sample_df: pl.DataFrame):
        fig = area_chart(sample_df, x="year", y=["assets", "liabilities"], stacked=False)
        for trace in fig.data:
            assert trace.stackgroup is None

    def test_title_propagates(self, sample_df: pl.DataFrame):
        fig = area_chart(sample_df, x="year", y=["assets"], title="Area Title")
        assert fig.layout.title.text == "Area Title"

    def test_currency_format(self, sample_df: pl.DataFrame):
        fig = area_chart(sample_df, x="year", y=["assets"], yformat="$")
        assert fig.layout.yaxis.tickprefix == "$"


# ---------------------------------------------------------------------------
# PALETTE
# ---------------------------------------------------------------------------


def test_palette_has_enough_colors():
    assert len(PALETTE) >= 10


# ---------------------------------------------------------------------------
# use_quarto_renderer
# ---------------------------------------------------------------------------


class TestQuartoRenderer:
    """The shared Quarto renderer embeds no MathJax and switches to png for PDF."""

    def test_html_mode_selects_shared_renderer(self, sample_df: pl.DataFrame):
        previous = pio.renderers.default
        try:
            assert use_quarto_renderer(pdf=False) == QUARTO_RENDERER
            assert pio.renderers.default == QUARTO_RENDERER
            fig = line_chart(sample_df, x="year", y="assets")
            bundle = pio.renderers["notebook_nomathjax"].to_mimebundle(fig.to_dict())
            assert (
                "mathjax/" not in bundle["text/html"].lower()
            )  # no CDN script; inline config is fine
            assert "plotly" in bundle["text/html"].lower()
        finally:
            pio.renderers.default = previous

    def test_pdf_mode_selects_png(self):
        previous = pio.renderers.default
        try:
            assert use_quarto_renderer(pdf=True) == "png"
        finally:
            pio.renderers.default = previous

    def test_reads_quarto_environment(self, monkeypatch):
        previous = pio.renderers.default
        try:
            monkeypatch.setenv("QUARTO_PROJECT_OUTPUT_FORMAT", "pdf")
            assert use_quarto_renderer() == "png"
            monkeypatch.setenv("QUARTO_PROJECT_OUTPUT_FORMAT", "html")
            assert use_quarto_renderer() == QUARTO_RENDERER
        finally:
            pio.renderers.default = previous
