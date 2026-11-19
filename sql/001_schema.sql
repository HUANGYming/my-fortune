-- Reference source table. Replace with a view mapping existing Patron columns.
CREATE TABLE fortune_patron_source (
    patron_id VARCHAR(128) NOT NULL,
    birth_date DATE,
    birth_hour INTEGER,
    gender VARCHAR(16),
    birth_minute INTEGER,
    birth_timezone VARCHAR(64),
    longitude DOUBLE PRECISION,
    preferences_json VARCHAR(64000)
);

CREATE TABLE fortune_catalog (
    kind VARCHAR(16) NOT NULL,
    entry_id VARCHAR(128) NOT NULL,
    name VARCHAR(256) NOT NULL,
    metadata_json VARCHAR(64000),
    active BOOLEAN NOT NULL
);

-- Full five-field public document is published in one transaction.
-- JSON is serialized as VARCHAR for Yellowbrick compatibility.
CREATE TABLE my_fortunes (
    patron_id VARCHAR(128) NOT NULL,
    fortune_date DATE NOT NULL,
    generated_at TIMESTAMPTZ NOT NULL,
    payload VARCHAR(64000) NOT NULL,
    audit_json VARCHAR(64000) NOT NULL
);
