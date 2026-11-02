-- Separate from Ignition-managed sqlth_* historian and alarm journal tables.
CREATE TABLE IF NOT EXISTS training_alarm_pipeline (
    event_id text NOT NULL,
    stage text NOT NULL,
    recorded_at timestamptz NOT NULL DEFAULT now(),
    source text NOT NULL,
    alarm_name text NOT NULL,
    priority integer NOT NULL,
    PRIMARY KEY (event_id, stage)
);
