"""Live simulation and HTTP-to-Modbus polling bridge for the private demo network."""
from dataclasses import asdict
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import threading
import time
import uuid
from pathlib import Path
from urllib.parse import urlsplit, parse_qs

from pyModbusTCP.server import ModbusServer, DataBank
from pyModbusTCP.client import ModbusClient
from .controller import Controller, State
from .alarms import Alarms
from .repository import Repository

STATES = list(State)
TAGS = [('volume', 'L', 100), ('temperature', 'degC', 100),
        ('setpoint', 'degC', 100), ('heater', '%', 100), ('hold', 's', 10)]


def utc():
    return datetime.now(timezone.utc).isoformat()


def encode(c):
    s = c.sample()
    return [round(s['volume'] * 100), round(s['temperature'] * 100),
            round(s['setpoint'] * 100), round(s['heater'] * 10000),
            round(s['hold'] * 10), STATES.index(c.state), int(c.plant.sensor_failed),
            int(c.plant.inlet), int(c.plant.outlet), int(c.plant.rinse), round(c.plant.supply * 100)]


class Runtime:
    def __init__(self, port=1502):
        self.lock = threading.RLock()
        self.c = Controller()
        self.batch_id = str(uuid.uuid4())
        self.created = utc()
        self.started = self.ended = None
        self.commands = {}
        self.sequence = 0
        self.alarms = Alarms()
        self.repository = Repository()
        self.bank = DataBank()
        self.server = ModbusServer(host='0.0.0.0', port=port, no_block=True, data_bank=self.bank)
        self.client = ModbusClient(host='127.0.0.1', port=port, unit_id=1, timeout=2)
        self.update_registers()

    def update_registers(self):
        self.bank.set_input_registers(0, encode(self.c))

    def command(self, body):
        request_id, action = body.get('request_id'), body.get('action')
        if not isinstance(request_id, str) or not 1 <= len(request_id) <= 80:
            raise ValueError('request_id must contain 1..80 characters')
        if action not in ('start', 'pause', 'resume', 'abort', 'sensor-fault', 'pump-fault', 'heat-loss'):
            raise ValueError('Unknown action')
        with self.lock:
            if body.get('batch_id', self.batch_id) != self.batch_id:
                raise ValueError('Batch changed; refresh before sending a command')
            if request_id in self.commands:
                previous = self.commands[request_id]
                if previous['action'] != action:
                    raise ValueError('request_id already used for another action')
                return previous
            ack = dict(request_id=request_id, action=action, timestamp=utc(), sim_time=self.c.time)
            try:
                if action in ('sensor-fault', 'pump-fault', 'heat-loss'):
                    if self.c.state.value not in self.c.limits:
                        raise ValueError('Fault injection requires an active batch')
                    if action == 'sensor-fault':
                        self.c.plant.sensor_failed = True
                    elif action == 'pump-fault':
                        self.c.plant.pump_failed = True
                    else:
                        self.c.plant.heat_loss = 0.12
                else:
                    self.c.command(action)
                if action == 'start':
                    self.started = utc()
                ack.update(accepted=True, reason='Accepted', state=self.c.state.value)
            except ValueError as e:
                ack.update(accepted=False, reason=str(e), state=self.c.state.value)
            self.commands[request_id] = ack
            self.update_registers()
            return ack

    def configure(self, body):
        with self.lock:
            if body.get('batch_id') != self.batch_id:
                raise ValueError('Batch changed; refresh before configuring')
            if self.c.state not in (State.IDLE, State.COMPLETE, State.FAULTED, State.ABORTED):
                raise ValueError('Finish or abort the batch before preparing another')
            recipe = self.repository.recipe(body['recipe_id'])
            # Commit the old batch before replacing its in-memory event log.
            # If SQL is unavailable the rollover fails without losing the batch.
            self.repository.flush(self.snapshot())
            self.c = Controller(recipe)
            self.batch_id, self.created = str(uuid.uuid4()), utc()
            self.started = self.ended = None
            self.commands, self.sequence, self.alarms = {}, 0, Alarms()
            self.update_registers()
            return dict(batch_id=self.batch_id, state='IDLE')

    def alarm_command(self, body):
        with self.lock:
            if body.get('batch_id') != self.batch_id:
                raise ValueError('Batch changed; refresh before acknowledging')
            self.alarms.command(body['alarm_id'], body['action'])
            return dict(accepted=True)

    def tick(self):
        with self.lock:
            if self.c.state not in (State.IDLE, State.COMPLETE, State.ABORTED, State.FAULTED):
                self.c.tick()
                if self.c.state in (State.COMPLETE, State.ABORTED, State.FAULTED):
                    self.ended = utc()
            self.update_registers()
            self.alarms.update(self.c, 0.5)

    def snapshot(self):
        with self.lock:
            # Read actual Modbus TCP, not an in-memory shortcut. Hold the scan
            # lock so the register block and batch metadata belong to one scan.
            registers = self.client.read_input_registers(0, 11)
            if registers is None:
                raise ConnectionError('Modbus I/O unavailable; snapshot not published')
            self.sequence += 1
            timestamp = utc()
            tags = {name: dict(value=registers[i] / scale, units=units,
                               quality='BAD' if name == 'temperature' and registers[6] else 'GOOD')
                    for i, (name, units, scale) in enumerate(TAGS)}
            for i, name in enumerate(('inlet', 'outlet', 'rinse'), 7):
                tags[name] = dict(value=bool(registers[i]), units='bool', quality='GOOD')
            tags['supply'] = dict(value=registers[10] / 100, units='L', quality='GOOD')
            return dict(schema_version=1, batch_id=self.batch_id, sequence=self.sequence,
                        timestamp=timestamp, sim_time=self.c.time, state=STATES[registers[5]].value,
                        created_at=self.created, started_at=self.started, ended_at=self.ended,
                        recipe=asdict(self.c.recipe), tags=tags, events=self.c.events[:],
                        commands=list(self.commands.values()), alarms=list(self.alarms.items.values()),
                        alarm_audit=self.alarms.audit[:], sim_speed=float(os.getenv('SIM_SPEED', '20')))


def handler(runtime):
    class Handler(BaseHTTPRequestHandler):
        def reply(self, status, body):
            data = json.dumps(body, allow_nan=False).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            try:
                path = urlsplit(self.path).path
                assets = {'/': ('index.html', 'text/html'), '/app.js': ('app.js', 'text/javascript'),
                          '/style.css': ('style.css', 'text/css'), '/plc-engine.js': ('plc-engine.js', 'text/javascript'),
                          '/plc-panel.js': ('plc-panel.js', 'text/javascript'), '/plc-program.json': ('plc-program.json', 'application/json')}
                for asset, mime in [('io-list.csv', 'text/csv'), ('wiring.svg', 'image/svg+xml'),
                                    ('ladder.svg', 'image/svg+xml'), ('fault-report.md', 'text/plain'),
                                    ('ladder-program.json', 'application/json'), ('open-wire-diagnosis.json', 'application/json')]:
                    assets['/training/' + asset] = ('training/' + asset, mime)
                if path in assets:
                    name, mime = assets[path]
                    data = (Path(__file__).parent / 'web' / name).read_bytes()
                    self.send_response(200)
                    self.send_header('Content-Type', mime + '; charset=utf-8')
                    self.send_header('Content-Length', str(len(data)))
                    self.send_header('Cache-Control', 'no-cache')
                    self.end_headers()
                    self.wfile.write(data)
                elif path == '/telemetry':
                    self.reply(200, runtime.snapshot())
                elif path == '/recipes':
                    self.reply(200, runtime.repository.recipes())
                elif path == '/history':
                    batch = parse_qs(urlsplit(self.path).query).get('batch', [None])[0]
                    self.reply(200, runtime.repository.history(batch))
                elif path == '/health':
                    self.reply(200, dict(status='ok'))
                else:
                    self.reply(404, dict(error='Not found'))
            except ConnectionError as e:
                self.reply(503, dict(error=str(e)))
            except (ValueError, TypeError) as e:
                self.reply(400, dict(error=str(e)))
            except Exception:
                self.reply(503, dict(error='Service unavailable; check container logs'))

        def do_POST(self):
            if self.path not in ('/commands', '/recipes', '/configure', '/alarms'):
                return self.reply(404, dict(error='Not found'))
            try:
                size = int(self.headers.get('Content-Length', 0))
                if not 0 < size <= 4096:
                    raise ValueError('Body must be 1..4096 bytes')
                body = json.loads(self.rfile.read(size))
                if not isinstance(body, dict):
                    raise ValueError('JSON object required')
                if self.path == '/commands':
                    ack = runtime.command(body)
                    self.reply(200 if ack['accepted'] else 409, ack)
                elif self.path == '/recipes':
                    self.reply(201, runtime.repository.save_recipe(body))
                elif self.path == '/configure':
                    self.reply(200, runtime.configure(body))
                else:
                    self.reply(200, runtime.alarm_command(body))
            except (ValueError, TypeError, KeyError) as e:
                self.reply(400, dict(error=str(e)))
            except Exception:
                self.reply(503, dict(error='Service unavailable; check container logs'))

        def log_message(self, *_):
            pass
    return Handler


def main():
    runtime = Runtime(int(os.getenv('MODBUS_PORT', '1502')))
    speed = float(os.getenv('SIM_SPEED', '20'))
    if not 0 < speed <= 100:
        raise ValueError('SIM_SPEED must be in (0, 100]')
    runtime.server.start()
    stop = threading.Event()
    def scan():
        while not stop.wait(0.5 / speed):
            runtime.tick()
    thread = threading.Thread(target=scan, daemon=True)
    thread.start()
    http = ThreadingHTTPServer(('0.0.0.0', 8080), handler(runtime))
    print(f'Batch {runtime.batch_id}; simulation speed {speed}x', flush=True)
    try:
        http.serve_forever()
    finally:
        stop.set()
        http.server_close()
        runtime.client.close()
        runtime.server.stop()


if __name__ == '__main__':
    main()
