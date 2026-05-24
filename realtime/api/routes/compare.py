"""GET /compare — picker; GET /compare/{session_id} — residuals page."""
from __future__ import annotations

import math

import pandas as pd
import plotly.graph_objects as go
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from realtime.compare.residuals import compute_and_save
from realtime.db import engine, read_df

router = APIRouter()
templates = Jinja2Templates(directory="realtime/api/templates")

_COMPOUND_COLOR = {
    "SOFT":   "#e8002d",   # Pirelli red
    "MEDIUM": "#ffd100",   # Pirelli yellow
    "HARD":   "#ebebeb",   # Pirelli white
}


def _build_scatter(df: pd.DataFrame, sigma_mean: float | None) -> str:
    """Build the residual × lap_number scatter, returning the HTML div."""
    fig = go.Figure()

    if sigma_mean is not None and not df.empty:
        max_lap = int(df["lap_number"].max())
        fig.add_trace(
            go.Scatter(
                x=[1, max_lap, max_lap, 1],
                y=[sigma_mean, sigma_mean, -sigma_mean, -sigma_mean],
                fill="toself",
                fillcolor="rgba(120,120,120,0.12)",
                line=dict(color="rgba(0,0,0,0)"),
                showlegend=False,
                hoverinfo="skip",
                name="±1σ",
            )
        )

    fig.add_hline(y=0, line=dict(color="#888", width=1, dash="dash"))

    for driver in sorted(df["driver"].unique()):
        df_d = df[df["driver"] == driver]
        colors = [_COMPOUND_COLOR.get(c, "#999") for c in df_d["compound"]]
        fig.add_trace(
            go.Scatter(
                x=df_d["lap_number"].tolist(),
                y=[float(r) for r in df_d["residual_s"].tolist()],
                mode="markers",
                name=driver,
                marker=dict(size=6, color=colors, line=dict(width=0)),
                customdata=list(
                    zip(
                        df_d["compound"].tolist(),
                        df_d["tyre_life"].tolist(),
                        [f"{float(s):.3f}s" if pd.notna(s) else "—" for s in df_d["stddev_s"]],
                    )
                ),
                hovertemplate=(
                    f"<b>{driver}</b><br>Lap %{{x}}<br>"
                    "Residual: %{y:.3f}s<br>"
                    "Compound: %{customdata[0]}<br>"
                    "Tyre life: %{customdata[1]}<br>"
                    "σ: %{customdata[2]}<extra></extra>"
                ),
            )
        )

    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="#0f1117",
        plot_bgcolor="#0f1117",
        font=dict(color="#e0e0e0"),
        xaxis=dict(title="Lap number", gridcolor="#2a2a2a"),
        yaxis=dict(title="Residual (actual − predicted, s)", gridcolor="#2a2a2a"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=40, r=20, t=30, b=40),
        height=480,
    )
    return fig.to_html(full_html=False, include_plotlyjs=False)


def _aggregate_by_compound(df: pd.DataFrame) -> list[dict]:
    """Return per-compound stats ordered SOFT → MEDIUM → HARD."""
    if df.empty:
        return []
    rows = []
    for compound, df_c in df.groupby("compound"):
        residuals = df_c["residual_s"].astype(float)
        rmse = float(math.sqrt((residuals ** 2).mean()))
        rows.append(
            {
                "compound":        compound,
                "count":           int(len(df_c)),
                "mean_residual_s": float(residuals.mean()),
                "rmse_s":          rmse,
                "mean_tyre_life":  float(df_c["tyre_life"].astype(float).mean()),
            }
        )
    order = {"SOFT": 0, "MEDIUM": 1, "HARD": 2}
    rows.sort(key=lambda g: order.get(g["compound"], 9))
    return rows


def _total_laps_in_session(session_id: str) -> int:
    with engine.connect() as conn:
        n = conn.execute(
            text("SELECT COUNT(*) FROM live.lap WHERE session_id = :sid"),
            {"sid": session_id},
        ).scalar()
    return int(n or 0)


@router.get("/compare", response_class=HTMLResponse)
def compare_index(request: Request):
    """Picker page: list recent sessions in live.session with links to /compare/{sid}.

    Joined with COUNT(live.lap) so the user can see which sessions actually
    have data to compare. Newest first, capped at 50.
    """
    try:
        sessions = read_df(
            """
            SELECT s.session_id::text       AS session_id,
                   s.year,
                   s.round_number,
                   s.session_type,
                   s.started_at,
                   COUNT(l.lap_number)      AS lap_count
            FROM live.session s
            LEFT JOIN live.lap l ON l.session_id = s.session_id
            GROUP BY s.session_id, s.year, s.round_number, s.session_type, s.started_at
            ORDER BY s.started_at DESC NULLS LAST
            LIMIT 50
            """
        )
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail=f"Database unavailable: {exc}")

    rows = sessions.to_dict(orient="records") if not sessions.empty else []
    return templates.TemplateResponse(
        request,
        "compare_index.html",
        {"sessions": rows},
    )


@router.get("/compare/{session_id}", response_class=HTMLResponse)
def compare_page(
    request: Request,
    session_id: str,
    refresh: bool = False,
    driver: str | None = None,
):
    """Render the residuals page for a session.

    Query params:
        refresh: if true, DELETE + recompute residuals (force=True in compute_and_save).
        driver: optional 3-letter code to filter the scatter chart only. KPIs and
            the aggregated table remain global to the session.

    Sync ``def`` (not ``async def``) so Starlette runs it in a threadpool — the
    DB work inside ``compute_and_save`` is blocking and would otherwise stall
    the event loop, freezing concurrent WS feeds on /ws/live.
    """
    try:
        df = compute_and_save(session_id, force=refresh)
    except ValueError as exc:
        msg = str(exc)
        # "Session not found" → 404; "No forecast for year=..." → 424 (failed dependency)
        status = 404 if msg.startswith("Session not found") else 424
        raise HTTPException(status_code=status, detail=msg)
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail=f"Database error: {exc}")

    driver_norm = driver.upper() if driver else None
    df_chart    = df if driver_norm is None else df[df["driver"] == driver_norm]
    driver_empty = bool(driver_norm) and df_chart.empty and not df.empty

    total_laps      = _total_laps_in_session(session_id)
    laps_compared   = int(len(df))
    drivers_compared = int(df["driver"].nunique()) if laps_compared else 0

    if laps_compared:
        residuals = df["residual_s"].astype(float)
        stddevs   = df["stddev_s"].astype(float)
        mean_residual = float(residuals.mean())
        rmse          = float(math.sqrt((residuals ** 2).mean()))
        valid_sigma   = stddevs.notna() & (stddevs > 0)
        if valid_sigma.any():
            within   = (residuals[valid_sigma].abs() <= stddevs[valid_sigma]).mean()
            pct_within = float(within * 100)
            sigma_mean = float(stddevs[valid_sigma].mean())
        else:
            pct_within = None
            sigma_mean = None
    else:
        mean_residual = rmse = pct_within = sigma_mean = None

    aggregates = _aggregate_by_compound(df)
    chart_html = (
        _build_scatter(df_chart, sigma_mean)
        if laps_compared and not df_chart.empty
        else ""
    )

    return templates.TemplateResponse(
        request,
        "compare.html",
        {
            "session_id":        session_id,
            "driver_filter":     driver_norm,
            "driver_empty":      driver_empty,
            "total_laps":        total_laps,
            "laps_compared":     laps_compared,
            "drivers_compared":  drivers_compared,
            "mean_residual_s":   mean_residual,
            "rmse_s":            rmse,
            "pct_within_1sigma": pct_within,
            "aggregates":        aggregates,
            "chart_html":        chart_html,
        },
    )
