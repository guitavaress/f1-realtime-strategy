-- Migration 004: stddev_s em comparisons.lap_residual
-- Persiste o desvio-padrao da curva de predicao ao lado de cada residual,
-- evitando re-join com predictions.compound_curve em runtime para normalizar
-- residuais (|residual| / stddev) ou montar bandas +/-1 sigma na UI.
-- Idempotente: usa ADD COLUMN IF NOT EXISTS.

ALTER TABLE comparisons.lap_residual
    ADD COLUMN IF NOT EXISTS stddev_s NUMERIC;
