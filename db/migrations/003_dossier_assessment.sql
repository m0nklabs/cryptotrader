-- Add structured LLM assessment fields to coin_dossier_entries
-- Depends on: 002_coin_dossier.sql
--
-- These columns store the structured trading recommendation from the LLM,
-- separate from the narrative prediction section.

BEGIN;

-- Add assessment fields to coin_dossier_entries
ALTER TABLE coin_dossier_entries
    ADD COLUMN IF NOT EXISTS assessment_action TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS assessment_confidence INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS assessment_risk TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS assessment_entry_low DOUBLE PRECISION NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS assessment_entry_high DOUBLE PRECISION NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS assessment_stop_loss DOUBLE PRECISION NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS assessment_take_profit_1 DOUBLE PRECISION NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS assessment_take_profit_2 DOUBLE PRECISION NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS assessment_reasoning TEXT NOT NULL DEFAULT '';

-- Add index on assessment_action for filtering by recommendation type
CREATE INDEX IF NOT EXISTS idx_dossier_assessment_action
    ON coin_dossier_entries (assessment_action, entry_date DESC);

COMMIT;
