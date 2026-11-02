CREATE TABLE IF NOT EXISTS batches (
  batch_id uuid PRIMARY KEY,
  created_at timestamptz NOT NULL,
  started_at timestamptz,
  ended_at timestamptz,
  recipe jsonb NOT NULL,
  state text NOT NULL,
  last_sequence bigint NOT NULL
);
CREATE TABLE IF NOT EXISTS samples (
  batch_id uuid REFERENCES batches,
  sequence bigint NOT NULL,
  timestamp timestamptz NOT NULL,
  sim_time double precision NOT NULL,
  state text NOT NULL,
  tags jsonb NOT NULL,
  PRIMARY KEY (batch_id, sequence)
);
CREATE TABLE IF NOT EXISTS events (
  batch_id uuid REFERENCES batches,
  event_index integer NOT NULL,
  sim_time double precision NOT NULL,
  previous text NOT NULL,
  state text NOT NULL,
  reason text NOT NULL,
  PRIMARY KEY (batch_id, event_index)
);
CREATE TABLE IF NOT EXISTS commands (
  batch_id uuid REFERENCES batches,
  request_id text NOT NULL,
  timestamp timestamptz NOT NULL,
  detail jsonb NOT NULL,
  PRIMARY KEY (batch_id, request_id)
);
CREATE INDEX IF NOT EXISTS samples_batch_time ON samples (batch_id, sim_time);
CREATE TABLE IF NOT EXISTS recipes (
  recipe_id uuid PRIMARY KEY,
  created_at timestamptz NOT NULL DEFAULT now(),
  recipe jsonb NOT NULL
);
INSERT INTO recipes (recipe_id,recipe) VALUES
 ('00000000-0000-4000-8000-000000000001', '{"name":"Tema · standard training","volume":60,"setpoint":60,"hold_seconds":120,"rinse_volume":20,"rinse_seconds":30}'),
 ('00000000-0000-4000-8000-000000000002', '{"name":"Tema · quick demonstration","volume":40,"setpoint":50,"hold_seconds":30,"rinse_volume":15,"rinse_seconds":15}')
ON CONFLICT DO NOTHING;
CREATE TABLE IF NOT EXISTS alarm_events (
  batch_id uuid REFERENCES batches,
  event_index integer NOT NULL,
  detail jsonb NOT NULL,
  PRIMARY KEY (batch_id,event_index)
);
