"""Short-lived SQL connections for HMI reads and versioned recipe storage."""
from dataclasses import asdict
import json
import os
import uuid
import psycopg
from psycopg.types.json import Jsonb
from .controller import Recipe


class Repository:
    def connect(self):
        return psycopg.connect(os.environ['DATABASE_URL'], connect_timeout=3)

    def recipes(self):
        with self.connect() as conn:
            rows = conn.execute('SELECT recipe_id, created_at, recipe FROM recipes ORDER BY created_at').fetchall()
        return [dict(id=str(r[0]), created_at=str(r[1]), recipe=r[2]) for r in rows]

    def save_recipe(self, body):
        recipe = Recipe(**body)
        if not isinstance(recipe.name, str) or not 1 <= len(recipe.name.strip()) <= 80:
            raise ValueError('Recipe name must be 1..80 characters')
        if recipe.hold_seconds > 1200 or recipe.rinse_seconds > 300:
            raise ValueError('Demo limits: hold ≤1200 s; rinse ≤300 s')
        key = uuid.uuid4()
        with self.connect() as conn:
            conn.execute('INSERT INTO recipes (recipe_id,recipe) VALUES (%s,%s)', (key, Jsonb(asdict(recipe))))
        return dict(id=str(key), recipe=asdict(recipe))

    def recipe(self, key):
        key = uuid.UUID(key)
        with self.connect() as conn:
            row = conn.execute('SELECT recipe FROM recipes WHERE recipe_id=%s', (key,)).fetchone()
        if not row:
            raise ValueError('Recipe not found')
        return Recipe(**row[0])

    def history(self, batch=None):
        with self.connect() as conn:
            if batch:
                batch = uuid.UUID(batch)
                events = conn.execute('SELECT sim_time,previous,state,reason FROM events WHERE batch_id=%s ORDER BY event_index', (batch,)).fetchall()
                samples = conn.execute('SELECT sim_time,state,tags FROM samples WHERE batch_id=%s ORDER BY sequence DESC LIMIT 2000', (batch,)).fetchall()
                commands = conn.execute('SELECT detail FROM commands WHERE batch_id=%s ORDER BY timestamp', (batch,)).fetchall()
                alarms = conn.execute('SELECT detail FROM alarm_events WHERE batch_id=%s ORDER BY event_index', (batch,)).fetchall()
                return dict(events=[dict(time=e[0], previous=e[1], state=e[2], reason=e[3]) for e in events],
                            samples=[dict(time=s[0], state=s[1], tags=s[2]) for s in reversed(samples)],
                            commands=[c[0] for c in commands], alarms=[a[0] for a in alarms])
            rows = conn.execute('SELECT batch_id,state,started_at,ended_at,recipe FROM batches ORDER BY created_at DESC LIMIT 30').fetchall()
        return [dict(id=str(r[0]), state=r[1], started_at=str(r[2]) if r[2] else None,
                     ended_at=str(r[3]) if r[3] else None, recipe=r[4]) for r in rows]

    def flush(self, snapshot):
        from .historian import store
        with self.connect() as conn:
            store(conn, snapshot)
