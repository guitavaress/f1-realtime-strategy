"""GET /next-event — pre-race prediction page."""
from __future__ import annotations

import plotly.graph_objects as go
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates


def _hex_rgba(hex_color: str, alpha: float = 0.15) -> str:
    """Convert '#rrggbb' to 'rgba(r,g,b,alpha)' for Plotly fillcolor."""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"

from realtime.ingest.schedule import next_event as get_next_event
from realtime.predict.model import generate_forecast, get_latest_forecast

router = APIRouter()
templates = Jinja2Templates(directory="realtime/api/templates")

_COMPOUND_COLOR = {
    "SOFT":   "#e8002d",   # Pirelli red
    "MEDIUM": "#ffd100",   # Pirelli yellow
    "HARD":   "#ebebeb",   # Pirelli white
}


def _build_chart(curves_df) -> str:
    """Build a Plotly degradation curve chart and return the HTML div string."""
    fig = go.Figure()

    for compound, color in _COMPOUND_COLOR.items():
        df = curves_df[curves_df["compound"] == compound].sort_values("tyre_life")
        if df.empty:
            continue

        x = df["tyre_life"].tolist()
        y = df["predicted_laptime_s"].tolist()
        stddev = df["stddev_s"].tolist()

        # Confidence band (±1σ) if stddev available
        has_std = any(s is not None and s == s for s in stddev)  # NaN check
        if has_std:
            std_vals = [float(s or 0) for s in stddev]
            fig.add_trace(
                go.Scatter(
                    x=x + x[::-1],
                    y=[yi + si for yi, si in zip(y, std_vals)]
                     + [yi - si for yi, si in zip(y[::-1], std_vals[::-1])],
                    fill="toself",
                    fillcolor=_hex_rgba(color),
                    line=dict(color="rgba(0,0,0,0)"),
                    showlegend=False,
                    hoverinfo="skip",
                )
            )

        fig.add_trace(
            go.Scatter(
                x=x,
                y=y,
                mode="lines",
                name=compound,
                line=dict(color=color, width=2.5),
                hovertemplate=(
                    f"<b>{compound}</b><br>"
                    "Lap %{x}: %{y:.3f}s<extra></extra>"
                ),
            )
        )

    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="#0f1117",
        plot_bgcolor="#0f1117",
        font=dict(color="#e0e0e0"),
        xaxis=dict(title="Tyre Life (laps)", gridcolor="#2a2a2a"),
        yaxis=dict(title="Predicted Lap Time (s)", gridcolor="#2a2a2a"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=40, r=20, t=30, b=40),
        height=380,
    )

    return fig.to_html(full_html=False, include_plotlyjs=False)


@router.get("/next-event", response_class=HTMLResponse)
async def next_event_page(request: Request, refresh: bool = False):
    """Render the pre-race prediction page for the upcoming F1 event.

    Generates a new forecast if none exists or if ?refresh=true is passed.
    """
    event = get_next_event()
    if event is None:
        return HTMLResponse("<h1>No upcoming F1 events found.</h1>", status_code=404)

    round_number = int(event["RoundNumber"])
    event_name   = str(event["EventName"])
    race_date    = str(event["EventDate"])[:10]  # YYYY-MM-DD
    year         = int(race_date[:4])

    # Generate or reuse forecast
    forecast = None if refresh else get_latest_forecast(year, round_number)
    if forecast is None:
        try:
            fid = generate_forecast(year, round_number, event_name, race_date)
            forecast = get_latest_forecast(year, round_number)
        except Exception as exc:
            return HTMLResponse(
                f"<h1>Forecast generation failed</h1><pre>{exc}</pre>",
                status_code=500,
            )

    chart_html = _build_chart(forecast["curves"]) if forecast and not forecast["curves"].empty else ""

    return templates.TemplateResponse(
        request,
        "next_event.html",
        {
            "year":         year,
            "round_number": round_number,
            "event_name":   event_name,
            "race_date":    race_date,
            "forecast":     {
                "track_temp_c":  forecast["track_temp_c"],
                "rainfall_prob": round(forecast["rainfall_prob"] * 100, 0),
            },
            "allocation":   forecast["allocation"],
            "chart_html":   chart_html,
            "generated_at": forecast["generated_at"],
        },
    )


