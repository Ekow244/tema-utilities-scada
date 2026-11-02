"""Run against an already-started, fresh local Compose stack."""
import json
import os
from pathlib import Path
import subprocess
import time
import urllib.request
import uuid


def compose(*args):
    command = ['docker']
    if os.getenv('SCADA_DOCKER_CONFIG'):
        command += ['--config', os.environ['SCADA_DOCKER_CONFIG']]
    return subprocess.check_output([*command, 'compose', *args], text=True).strip()


def telemetry():
    with urllib.request.urlopen('http://127.0.0.1:8080/telemetry', timeout=3) as response:
        return json.load(response)


def sql(query):
    code = ('import os,json,psycopg; '
            'c=psycopg.connect(os.environ["DATABASE_URL"]); '
            f'print(json.dumps(c.execute({query!r}).fetchall(),default=str))')
    return json.loads(compose('exec', '-T', 'historian', 'python', '-c', code))


def wait_for(fn, timeout=90):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = fn()
        if result:
            return result
        time.sleep(0.5)
    raise AssertionError('Timed out waiting for verification condition')


def command(action, request_id=None):
    request_id = request_id or str(uuid.uuid4())
    payload = json.dumps(dict(request_id=request_id, action=action))
    compose('exec', '-T', 'mqtt', 'mosquitto_pub', '-h', 'localhost', '-q', '1',
            '-t', 'scada/v1/commands', '-m', payload)
    return request_id


def main():
    first = telemetry()
    assert first['state'] == 'IDLE', 'Use a fresh simulator for verification'
    batch = first['batch_id']
    # A stored idle sample proves Node-RED, MQTT and historian are connected.
    wait_for(lambda: sql(f"SELECT count(*) FROM samples WHERE batch_id='{batch}'")[0][0] > 0)
    request = command('start')
    wait_for(lambda: telemetry()['state'] != 'IDLE')
    command('start', request)  # QoS redelivery / repeated command simulation
    command('pause')
    wait_for(lambda: telemetry()['state'] == 'PAUSED')
    command('resume')
    wait_for(lambda: telemetry()['state'] not in ('PAUSED', 'IDLE'))
    wait_for(lambda: telemetry()['state'] == 'COMPLETE')
    wait_for(lambda: sql(f"SELECT state FROM batches WHERE batch_id='{batch}'")[0][0] == 'COMPLETE')
    events = sql(f"SELECT state FROM events WHERE batch_id='{batch}' ORDER BY event_index")
    assert sum(e[0] == 'PRECHECK' for e in events) == 1
    assert any(e[0] == 'PAUSED' for e in events)
    count = sql(f"SELECT count(*) FROM commands WHERE batch_id='{batch}'")[0][0]
    assert count == 3, count
    samples = sql(f"SELECT count(*) FROM samples WHERE batch_id='{batch}'")[0][0]
    assert samples > 20
    # Restart simulator only: PostgreSQL history survives and the next batch
    # has a new UUID. Do not remove the database volume.
    compose('restart', 'simulator')
    time.sleep(2)
    second = telemetry()
    assert second['batch_id'] != batch
    command('start')
    wait_for(lambda: telemetry()['state'] != 'IDLE')
    command('sensor-fault')
    wait_for(lambda: telemetry()['state'] == 'FAULTED')
    new_batch = second['batch_id']
    wait_for(lambda: sql(f"SELECT state FROM batches WHERE batch_id='{new_batch}'") == [['FAULTED']])
    assert telemetry()['tags']['temperature']['quality'] == 'BAD'
    assert telemetry()['tags']['heater']['value'] == 0
    assert sql(f"SELECT state FROM batches WHERE batch_id='{batch}'") == [['COMPLETE']]
    report = dict(result='PASS', normal_batch=batch, fault_batch=new_batch,
                  normal_samples=samples, distinct_normal_commands=count,
                  normal_states=[e[0] for e in events],
                  checks=['MQTT command routing', 'duplicate command suppression',
                          'pause/resume', 'complete batch historian', 'sensor fault quality',
                          'safe heater output', 'history survives simulator restart'])
    Path('runs').mkdir(exist_ok=True)
    Path('runs/phase2-verification.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
