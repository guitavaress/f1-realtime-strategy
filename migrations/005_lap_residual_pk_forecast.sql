-- Migration 005: incluir forecast_id na PK de comparisons.lap_residual
-- Motivacao: a PK original (session_id, driver, lap_number) impedia comparar a mesma
-- sessao contra mais de um forecast — INSERT...ON CONFLICT DO NOTHING dropava silenciosamente
-- as linhas do segundo forecast. Inclui forecast_id pra permitir reaproveitar a mesma
-- session_id com forecasts distintos (ex: clima muda e /next-event roda de novo).
-- Idempotente: DROP IF EXISTS + ADD sempre — se rodada mais de uma vez, recria a mesma PK.

ALTER TABLE comparisons.lap_residual
    DROP CONSTRAINT IF EXISTS lap_residual_pkey;

ALTER TABLE comparisons.lap_residual
    ADD PRIMARY KEY (session_id, forecast_id, driver, lap_number);
