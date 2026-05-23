-- Migration 001: schema predictions
-- Armazena predições geradas antes do evento (pré-corrida)
-- Rodar uma vez por ambiente: psql -U airflow -d f1 -h localhost -f migrations/001_predictions_schema.sql

CREATE SCHEMA IF NOT EXISTS predictions;

CREATE TABLE IF NOT EXISTS predictions.race_forecast (
    forecast_id             UUID PRIMARY KEY,
    year                    INT NOT NULL,
    round_number            INT NOT NULL,
    event_name              TEXT NOT NULL,
    generated_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    forecast_track_temp_c   NUMERIC,
    forecast_rainfall_prob  NUMERIC,    -- 0..1
    pirelli_c_soft          TEXT,       -- ex: 'C4'
    pirelli_c_medium        TEXT,
    pirelli_c_hard          TEXT,
    UNIQUE (year, round_number, generated_at)
);

CREATE TABLE IF NOT EXISTS predictions.compound_curve (
    forecast_id             UUID NOT NULL REFERENCES predictions.race_forecast (forecast_id),
    compound                TEXT NOT NULL,      -- SOFT / MEDIUM / HARD
    tyre_life               INT NOT NULL,       -- volta dentro do stint (1..N)
    predicted_laptime_s     NUMERIC NOT NULL,
    predicted_deg_per_lap_s NUMERIC,
    stddev_s                NUMERIC,            -- desvio-padrão histórico dos resíduos
    PRIMARY KEY (forecast_id, compound, tyre_life)
);

CREATE INDEX IF NOT EXISTS idx_race_forecast_year_round
    ON predictions.race_forecast (year, round_number);
