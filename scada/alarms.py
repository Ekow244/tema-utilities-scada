"""Small rationalized alarm set; illustrative ISA-18.2 concepts, not certification."""
import time


class Alarms:
    definitions = {
        'SENSOR': ('P1', 'Temperature signal invalid', 'Inspect TT-101 before preparing a fresh simulation.'),
        'TRIP': ('P1', 'Process limit trip', 'Inspect temperature and vessel level before restarting.'),
        'TIMEOUT': ('P2', 'Sequence step timeout', 'Check commanded flow and pump operation; inspect the failed step.'),
        'DEVIATION': ('P2', 'Hold temperature deviation', 'Inspect heater output and heat loss; hold qualification resets.'),
    }

    def __init__(self):
        self.items = {}
        self.audit = []
        self.deviation_time = 0

    def event(self, key, action, now):
        self.audit.append(dict(alarm=key, action=action, timestamp=now))

    def update(self, controller, dt, now=None):
        now = time.time() if now is None else now
        p, c = controller.plant, controller
        deviation = abs(p.temperature - c.recipe.setpoint)
        previous = self.items.get('DEVIATION', {}).get('active', False)
        bad = c.state.value == 'HOLD' and deviation > (1 if previous else 3)
        self.deviation_time = self.deviation_time + dt if bad else 0
        conditions = dict(SENSOR=p.sensor_failed,
                          TRIP=c.state.value == 'FAULTED' and 'safety limit' in c.reason and not p.sensor_failed,
                          TIMEOUT=c.state.value == 'FAULTED' and 'timeout' in c.reason,
                          DEVIATION=bad and (previous or self.deviation_time >= 10))
        for key, active in conditions.items():
            alarm = self.items.get(key)
            if active and (not alarm or not alarm['active']):
                priority, title, response = self.definitions[key]
                alarm = dict(id=key, priority=priority, title=title, response=response,
                             active=True, acknowledged=False, raised_at=now, shelved_until=0)
                self.items[key] = alarm
                self.event(key, 'RAISED', now)
            elif alarm and alarm['active'] and not active:
                alarm['active'] = False
                self.event(key, 'CLEARED', now)
            if alarm and alarm['shelved_until'] and now >= alarm['shelved_until']:
                alarm['shelved_until'] = 0
                self.event(key, 'SHELF_EXPIRED', now)

    def command(self, key, action, now=None):
        now = time.time() if now is None else now
        if key not in self.items:
            raise ValueError('Unknown alarm')
        alarm = self.items[key]
        if action == 'acknowledge':
            if not alarm['acknowledged']:
                alarm['acknowledged'] = True
                self.event(key, 'ACKNOWLEDGED', now)
        elif action == 'shelve':
            if alarm['priority'] == 'P1':
                raise ValueError('P1 alarms cannot be shelved in this demo')
            alarm['shelved_until'] = now + 60
            self.event(key, 'SHELVED_60S', now)
        elif action == 'unshelve':
            alarm['shelved_until'] = 0
            self.event(key, 'UNSHELVED', now)
        else:
            raise ValueError('Unknown alarm action')
