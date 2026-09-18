from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


def history_with_rolling_figure(frame: pd.DataFrame, rolling: list[dict]) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=frame["ds"], y=frame["y"], name="факт", mode="lines"))
    if rolling:
        roll_df = pd.DataFrame(rolling)
        roll_df["ds"] = pd.to_datetime(roll_df["ds"], utc=True)
        fig.add_trace(
            go.Scatter(x=roll_df["ds"], y=roll_df["rolling_mean"], name="скользящее среднее", mode="lines")
        )
    fig.update_layout(margin=dict(l=10, r=10, t=30, b=10), legend_title_text="")
    return fig


def profile_bar_figure(points: list[dict], title: str) -> go.Figure:
    if not points:
        fig = go.Figure()
        fig.update_layout(title=title, margin=dict(l=10, r=10, t=40, b=10))
        return fig
    df = pd.DataFrame(points)
    fig = px.bar(df, x="key", y="value", title=title)
    fig.update_layout(margin=dict(l=10, r=10, t=40, b=10), xaxis_title="", yaxis_title="среднее")
    return fig


def anomalies_figure(frame: pd.DataFrame, anomaly_points: list[dict]) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=frame["ds"], y=frame["y"], name="ряд", mode="lines"))
    if anomaly_points:
        adf = pd.DataFrame(anomaly_points)
        adf["ds"] = pd.to_datetime(adf["ds"], utc=True)
        fig.add_trace(
            go.Scatter(
                x=adf["ds"],
                y=adf["y"],
                name="аномалии",
                mode="markers",
                marker=dict(size=10, color="red"),
            )
        )
    fig.update_layout(margin=dict(l=10, r=10, t=30, b=10), legend_title_text="")
    return fig


def contribution_figure(points: list[dict]) -> go.Figure:
    if not points:
        return go.Figure()
    df = pd.DataFrame(points)
    fig = px.bar(df, x="category", y="share_pct", title="Вклад категорий, %")
    fig.update_layout(margin=dict(l=10, r=10, t=40, b=10), xaxis_title="", yaxis_title="%")
    return fig


def forecast_figure(
    history: pd.DataFrame,
    forecast_points: list[dict],
    *,
    title: str = "История и прогноз",
) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=history["ds"], y=history["y"], name="факт", mode="lines"))
    if forecast_points:
        fdf = pd.DataFrame(forecast_points)
        fdf["ds"] = pd.to_datetime(fdf["ds"], utc=True)
        if "yhat_lower" in fdf.columns and "yhat_upper" in fdf.columns:
            fig.add_trace(
                go.Scatter(
                    x=list(fdf["ds"]) + list(fdf["ds"][::-1]),
                    y=list(fdf["yhat_upper"]) + list(fdf["yhat_lower"][::-1]),
                    fill="toself",
                    fillcolor="rgba(31, 119, 180, 0.15)",
                    line=dict(color="rgba(255,255,255,0)"),
                    name="интервал",
                    hoverinfo="skip",
                )
            )
        fig.add_trace(go.Scatter(x=fdf["ds"], y=fdf["yhat"], name="прогноз", mode="lines"))
    fig.update_layout(title=title, margin=dict(l=10, r=10, t=40, b=10), legend_title_text="")
    return fig


def scenarios_compare_figure(series: list[dict]) -> go.Figure:
    """series: [{name, points: [{ds,yhat}, ...]}, ...]"""
    fig = go.Figure()
    for item in series:
        pts = item.get("points") or []
        if not pts:
            continue
        df = pd.DataFrame(pts)
        df["ds"] = pd.to_datetime(df["ds"], utc=True)
        fig.add_trace(go.Scatter(x=df["ds"], y=df["yhat"], name=item.get("name", "?"), mode="lines"))
    fig.update_layout(
        title="Сравнение сценариев",
        margin=dict(l=10, r=10, t=40, b=10),
        legend_title_text="",
    )
    return fig
