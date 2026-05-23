-- Migration 003: schema comparisons
-- Delta entre laps reais (live) e predição pré-evento; alimenta calibração futura
-- Rodar uma vez por ambiente: psql -U airflow -d f1 -h localhost -f migrations/003_comparisons_schema.sql

CREATE SCHEMA IF NOT EXISTS comparisons;

CREATE TABLE IF NOT EXISTS comparisons.lap_residual (
    session_id              UUID NOT NULL,
    forecast_id             UUID NOT NULL,
    driver                  TEXT NOT NULL,
    lap_number              INT NOT NULL,
    compound                TEXT NOT NULL,
    tyre_life               INT NOT NULL,
    actual_laptime_s        NUMERIC NOT NULL,
    predicted_laptime_s     NUMERIC NOT NULL,
    residual_s              NUMERIC GENERATED ALWAYS AS (actual_laptime_s - predicted_laptime_s) STORED,
    recorded_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (session_id, driver, lap_number)
);

CREATE INDEX IF NOT EXISTS idx_lap_residual_forecast
    ON comparisons.lap_residual (forecast_id);

CREATE INDEX IF NOT EXISTS idx_lap_residual_compound
    ON comparisons.lap_residual (compound, tyre_life);
