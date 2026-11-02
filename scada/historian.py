"""MQTT consumer: commit each snapshot transactionally before acknowledging."""
import json
import os
from pathlib import Path
import time
import paho.mqtt.client as mqtt
import psycopg
from psycopg.types.json import Jsonb


def store(conn, message):
    m = message
    with conn.transaction():
        conn.execute('''INSERT INTO batches VALUES (%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (batch_id) DO UPDATE SET started_at=EXCLUDED.started_at,
            ended_at=EXCLUDED.ended_at, state=EXCLUDED.state, last_sequence=EXCLUDED.last_sequence
            WHERE batches.last_sequence < EXCLUDED.last_sequence''',
            (m['batch_id'], m['created_at'], m['started_at'], m['ended_at'],
             Jsonb(m['recipe']), m['state'], m['sequence']))
        conn.execute('''INSERT INTO samples VALUES (%s,%s,%s,%s,%s,%s)
            ON CONFLICT DO NOTHING''', (m['batch_id'], m['sequence'], m['timestamp'],
                                       m['sim_time'], m['state'], Jsonb(m['tags'])))
        for index, e in enumerate(m['events']):
            conn.execute('INSERT INTO events VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING',
                         (m['batch_id'], index, e['time'], e['previous'], e['state'], e['reason']))
        for command in m['commands']:
            conn.execute('INSERT INTO commands VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING',
                         (m['batch_id'], command['request_id'], command['timestamp'], Jsonb(command)))
        for index, event in enumerate(m.get('alarm_audit', [])):
            conn.execute('INSERT INTO alarm_events VALUES (%s,%s,%s) ON CONFLICT DO NOTHING',
                         (m['batch_id'], index, Jsonb(event)))


def main():
    conn = psycopg.connect(os.environ['DATABASE_URL'], autocommit=True)
    conn.execute(Path('deploy/schema.sql').read_text())
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id='scada-historian',
                         clean_session=False, manual_ack=True)
    def connect(client, userdata, flags, reason, properties):
        if reason == 0:
            client.subscribe('scada/v1/telemetry', qos=1)
    def message(client, userdata, msg):
        try:
            store(conn, json.loads(msg.payload))
            client.ack(msg.mid, msg.qos)
        except Exception as e:
            # Exit so Docker restarts us and the persistent MQTT session
            # redelivers the unacknowledged message after DB reconnection.
            print(f'Historian failed; restarting: {e}', flush=True)
            os._exit(1)
    client.on_connect, client.on_message = connect, message
    while True:
        try:
            client.connect(os.getenv('MQTT_HOST', 'mqtt'), 1883)
            break
        except OSError:
            time.sleep(2)
    client.loop_forever()


if __name__ == '__main__':
    main()
