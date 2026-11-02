"""Exercise the HMI API against a fresh local Compose simulator."""
import json
from pathlib import Path
import time
import urllib.error
import urllib.request
import uuid


def api(path, body=None, reject=False):
    request = urllib.request.Request('http://127.0.0.1:8080' + path,
        data=json.dumps(body).encode() if body else None,
        headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(request, timeout=6) as response:
            result = json.load(response)
        assert not reject, 'Expected request rejection'
        return result
    except urllib.error.HTTPError as error:
        if not reject:
            raise
        assert error.code in (400, 409)
        return json.load(error)


def wait_state(state):
    deadline = time.monotonic() + 100
    while time.monotonic() < deadline:
        snapshot = api('/telemetry')
        if snapshot['state'] == state:
            return snapshot
        if snapshot['state'] == 'FAULTED' and state != 'FAULTED':
            raise AssertionError(snapshot['events'][-1])
        time.sleep(0.2)
    raise AssertionError('State timeout: ' + state)


def command(action):
    return api('/commands', dict(batch_id=api('/telemetry')['batch_id'],
                                request_id=str(uuid.uuid4()), action=action))


def prepare(recipe_id):
    return api('/configure', dict(batch_id=api('/telemetry')['batch_id'], recipe_id=recipe_id))


def main():
    assert api('/telemetry')['state'] == 'IDLE', 'Use a fresh IDLE simulator'
    recipe = dict(name='Tema · verification training', volume=20, setpoint=35,
                  hold_seconds=10, rinse_volume=10, rinse_seconds=5)
    api('/recipes', {**recipe, 'volume': 150}, reject=True)
    saved = api('/recipes', recipe)
    assert any(r['id'] == saved['id'] for r in api('/recipes'))
    old = api('/telemetry')['batch_id']
    first = prepare(saved['id'])['batch_id']
    api('/commands', dict(batch_id=old, request_id='stale', action='start'), reject=True)
    command('start')
    api('/configure', dict(batch_id=first, recipe_id=saved['id']), reject=True)
    command('pause')
    wait_state('PAUSED')
    command('resume')
    command('sensor-fault')
    fault = wait_state('FAULTED')
    assert fault['tags']['heater']['value'] == 0
    assert fault['tags']['temperature']['quality'] == 'BAD'
    api('/alarms', dict(batch_id=first, alarm_id='SENSOR', action='shelve'), reject=True)
    api('/alarms', dict(batch_id=first, alarm_id='SENSOR', action='acknowledge'))
    second = prepare(saved['id'])['batch_id']
    archive = api('/history?batch=' + first)
    assert any(a['action'] == 'ACKNOWLEDGED' for a in archive['alarms'])
    assert archive['events'][-1]['state'] == 'FAULTED'
    command('start')
    command('pump-fault')
    timeout = wait_state('FAULTED')
    assert any(a['id'] == 'TIMEOUT' and a['priority'] == 'P2' for a in timeout['alarms'])
    for action in ('shelve', 'acknowledge', 'unshelve'):
        api('/alarms', dict(batch_id=second, alarm_id='TIMEOUT', action=action))
    third = prepare(saved['id'])['batch_id']
    assert any(a['action'] == 'SHELVED_60S' for a in api('/history?batch='+second)['alarms'])
    command('start')
    wait_state('COMPLETE')
    prepare(saved['id'])  # archive final batch and leave dashboard ready
    normal = api('/history?batch=' + third)
    assert normal['events'][-1]['state'] == 'COMPLETE'
    assert len(normal['samples']) > 2
    report = dict(result='PASS', sensor_batch=first, pump_timeout_batch=second,
                  completed_batch=third, recipe_id=saved['id'],
                  checks=['recipe save and validation', 'reject stale batch command',
                          'block active recipe change', 'pause/resume', 'sensor trip',
                          'P1 shelving prohibited', 'alarm acknowledgement archived',
                          'P2 shelving and unshelving', 'normal full batch',
                          'final history committed before batch rollover'])
    Path('runs/hmi-verification.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
