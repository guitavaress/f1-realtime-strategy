-- Migration 002: schema live
-- Armazena laps capturados pelo livetiming_worker durante sessões ao vivo
-- Rodar uma vez por ambiente: psql -U airflow -d f1 -h localhost -f migrations/002_live_schema.sql

CREATE SCHEMA IF NOT EXISTS live;

CREATE TABLE IF NOT EXISTS live.session (
    session_id      UUID PRIMARY KEY,
    year            INT NOT NULL,
    round_number    INT NOT NULL,
    session_type    TEXT NOT NULL,      -- 'R' race / 'Q' qualifying / 'S' sprint
    started_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS live.lap (
    session_id      UUID NOT NULL REFERENCES live.session (session_id),
    driver          TEXT NOT NULL,
    lap_number      INT NOT NULL,
    laptime_s       NUMERIC,
    compound        TEXT,               -- SOFT / MEDIUM / HARD / INTERMEDIATE / WET
    tyre_life       INT,
    stint           INT,
    received_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (session_id, driver, lap_number)
);

CREATE INDEX IF NOT EXISTS idx_live_lap_session_driver
    ON live.lap (session_id, driver);
