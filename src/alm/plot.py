"""Reusable Plotly charting functions for ALM reports."""

from __future__ import annotations

import plotly.graph_objects as go
import polars as pl

# ---------------------------------------------------------------------------
# Styling
# ---------------------------------------------------------------------------

PALETTE = [
    "#2563eb",  # blue
    "#dc2626",  # red
    "#16a34a",  # green
    "#9333ea",  # purple
    "#ea580c",  # orange
    "#0891b2",  # cyan
    "#d97706",  # amber
    "#4f46e5",  # indigo
    "#be185d",  # pink
    "#65a30d",  # lime
]

_LAYOUT = dict(
    template="plotly_white",
    font=dict(family="Segoe UI, Arial, sans-serif", size=12),
    title_font_size=16,
    legend=dict(
        orientation="h",
        yanchor="bottom",
        y=1.02,
        xanchor="right",
        x=1,
    ),
    margin=dict(l=60, r=30, t=60, b=50),
    hovermode="x unified",
)


def _fmt(fmt: str | None) -> dict:
    """Return plotly axis-formatting kwargs.

    *fmt* can be ``"$"`` (currency), ``"%"`` (percent),
    ``"#"`` (integer with commas), or ``None`` (auto).
    """
    if fmt == "$":
        return dict(tickprefix="$", tickformat=",.0f", hoverformat="$,.0f")
    if fmt == "%":
        return dict(tickformat=".1%", hoverformat=".2%")
    if fmt == "#":
        return dict(tickformat=",.0f", hoverformat=",.0f")
    return {}


# ---------------------------------------------------------------------------
# Charts
# ---------------------------------------------------------------------------


def line_chart(
    df: pl.DataFrame,
    x: str,
    y: str | list[str],
    color: str | None = None,
    title: str = "",
    xlab: str | None = None,
    ylab: str | None = None,
    yformat: str | None = None,
    xformat: str | None = None,
) -> go.Figure:
    """Professional line chart from a Polars DataFrame.

    Parameters
    ----------
    df : pl.DataFrame
    x : str
        Column for the x-axis.
    y : str or list[str]
        Column(s) for the y-axis.  A list plots multiple traces.
    color : str, optional
        Column to colour-code lines by group (mutually exclusive
        with a list *y*).
    title, xlab, ylab : str
        Chart / axis labels (axis labels default to column names).
    yformat, xformat : ``"$"`` | ``"%"`` | ``"#"`` | ``None``
    """
    fig = go.Figure()
    xvals = df[x].to_list()

    if isinstance(y, list):
        for i, col in enumerate(y):
            fig.add_trace(
                go.Scatter(
                    x=xvals,
                    y=df[col].to_list(),
                    mode="lines",
                    name=col,
                    line=dict(color=PALETTE[i % len(PALETTE)]),
                )
            )
    elif color:
        groups = df[color].unique(maintain_order=True).to_list()
        for i, grp in enumerate(groups):
            sub = df.filter(pl.col(color) == grp)
            fig.add_trace(
                go.Scatter(
                    x=sub[x].to_list(),
                    y=sub[y].to_list(),
                    mode="lines",
                    name=str(grp),
                    line=dict(color=PALETTE[i % len(PALETTE)]),
                )
            )
    else:
        fig.add_trace(
            go.Scatter(
                x=xvals,
                y=df[y].to_list(),
                mode="lines",
                name=y,
                line=dict(color=PALETTE[0]),
                showlegend=False,
            )
        )

    fig.update_layout(
        **_LAYOUT,
        title=title,
        xaxis_title=xlab if xlab is not None else x,
        yaxis_title=ylab if ylab is not None else (y if isinstance(y, str) else ""),
    )

    if f := _fmt(xformat):
        fig.update_xaxes(**f)
    if f := _fmt(yformat):
        fig.update_yaxes(**f)

    return fig


def bar_chart(
    df: pl.DataFrame,
    x: str,
    y: str | list[str],
    color: str | None = None,
    title: str = "",
    xlab: str | None = None,
    ylab: str | None = None,
    yformat: str | None = None,
    xformat: str | None = None,
    barmode: str = "group",
) -> go.Figure:
    """Professional bar chart from a Polars DataFrame.

    Same signature as :func:`line_chart` plus *barmode*
    (``"group"`` | ``"stack"`` | ``"overlay"``).
    """
    fig = go.Figure()
    xvals = df[x].to_list()

    if isinstance(y, list):
        for i, col in enumerate(y):
            fig.add_trace(
                go.Bar(
                    x=xvals,
                    y=df[col].to_list(),
                    name=col,
                    marker_color=PALETTE[i % len(PALETTE)],
                )
            )
    elif color:
        groups = df[color].unique(maintain_order=True).to_list()
        for i, grp in enumerate(groups):
            sub = df.filter(pl.col(color) == grp)
            fig.add_trace(
                go.Bar(
                    x=sub[x].to_list(),
                    y=sub[y].to_list(),
                    name=str(grp),
                    marker_color=PALETTE[i % len(PALETTE)],
                )
            )
    else:
        fig.add_trace(
            go.Bar(
                x=xvals,
                y=df[y].to_list(),
                name=y,
                marker_color=PALETTE[0],
                showlegend=False,
            )
        )

    fig.update_layout(
        **_LAYOUT,
        title=title,
        xaxis_title=xlab if xlab is not None else x,
        yaxis_title=ylab if ylab is not None else (y if isinstance(y, str) else ""),
        barmode=barmode,
    )

    if f := _fmt(xformat):
        fig.update_xaxes(**f)
    if f := _fmt(yformat):
        fig.update_yaxes(**f)

    return fig


def area_chart(
    df: pl.DataFrame,
    x: str,
    y: list[str],
    title: str = "",
    xlab: str | None = None,
    ylab: str | None = None,
    yformat: str | None = None,
    xformat: str | None = None,
    stacked: bool = True,
) -> go.Figure:
    """Stacked (or overlaid) area chart from a Polars DataFrame.

    Parameters
    ----------
    df : pl.DataFrame
    x : str
        Column for the x-axis.
    y : list[str]
        Columns to stack as areas.
    stacked : bool
        If True, areas are stacked; otherwise overlaid with opacity.
    """
    fig = go.Figure()
    xvals = df[x].to_list()

    def _hex_to_rgba(hex_color: str, opacity: float = 0.5) -> str:
        r, g, b = int(hex_color[1:3], 16), int(hex_color[3:5], 16), int(hex_color[5:7], 16)
        return f"rgba({r},{g},{b},{opacity})"

    for i, col in enumerate(y):
        color = PALETTE[i % len(PALETTE)]
        fig.add_trace(
            go.Scatter(
                x=xvals,
                y=df[col].to_list(),
                mode="lines",
                name=col,
                line=dict(color=color, width=0.5),
                stackgroup="one" if stacked else None,
                fillcolor=_hex_to_rgba(color),
                fill="tonexty" if not stacked and i > 0 else ("tozeroy" if not stacked else None),
            )
        )

    fig.update_layout(
        **_LAYOUT,
        title=title,
        xaxis_title=xlab if xlab is not None else x,
        yaxis_title=ylab if ylab is not None else "",
    )

    if f := _fmt(xformat):
        fig.update_xaxes(**f)
    if f := _fmt(yformat):
        fig.update_yaxes(**f)

    return fig
