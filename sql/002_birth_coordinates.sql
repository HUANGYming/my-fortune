-- Existing installations only. New installations use 001_schema.sql.
ALTER TABLE fortune_patron_source ADD COLUMN birth_minute INTEGER;
ALTER TABLE fortune_patron_source ADD COLUMN birth_timezone VARCHAR(64);
ALTER TABLE fortune_patron_source ADD COLUMN longitude DOUBLE PRECISION;
