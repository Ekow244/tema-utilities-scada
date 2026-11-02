from dataclasses import dataclass, asdict
from enum import Enum
import math
from .model import Plant, PID


class State(str, Enum):
    IDLE = 'IDLE'
    PRECHECK = 'PRECHECK'
    FILL = 'FILL'
    HEAT = 'HEAT'
    HOLD = 'HOLD'
    DISCHARGE = 'DISCHARGE'
    CIP_FILL = 'CIP_FILL'
    CIP_RINSE = 'CIP_RINSE'
    CIP_DRAIN = 'CIP_DRAIN'
    COMPLETE = 'COMPLETE'
    PAUSED = 'PAUSED'
    ABORTING = 'ABORTING'
    ABORTED = 'ABORTED'
    FAULTED = 'FAULTED'


@dataclass(frozen=True)
class Recipe:
    name: str = 'Demo water batch'
    volume: float = 60.0
    setpoint: float = 60.0
    hold_seconds: float = 120.0
    rinse_volume: float = 20.0
    rinse_seconds: float = 30.0

    def __post_init__(self):
        for key, value in asdict(self).items():
            if key != 'name' and (not math.isfinite(value) or value <= 0):
                raise ValueError(f'{key} must be positive and finite')
        if not 10 <= self.volume <= 100 or not 25 <= self.setpoint <= 75 or self.rinse_volume > 100:
            raise ValueError('Recipe exceeds demo operating limits')


class Controller:
    """Scan-based sequence: input checks, transition evaluation, output assignment."""
    limits = {'PRECHECK': 5, 'FILL': 120, 'HEAT': 1800, 'HOLD': 1800,
              'DISCHARGE': 120, 'CIP_FILL': 120, 'CIP_RINSE': 600, 'CIP_DRAIN': 120}

    def __init__(self, recipe=None):
        self.recipe = recipe or Recipe()
        self.plant = Plant()
        self.pid = PID()
        self.state = State.IDLE
        self.time = self.elapsed = self.hold = 0.0
        self.events = []
        self.saved = None
        self.reason = ''

    def safe(self):
        self.plant.heater = 0.0
        self.plant.inlet = self.plant.outlet = self.plant.rinse = False

    def transition(self, state, reason=''):
        self.events.append(dict(time=round(self.time, 2), previous=self.state.value,
                                state=state.value, reason=reason))
        self.state, self.elapsed, self.reason = state, 0.0, reason
        self.safe()

    def command(self, action):
        if action == 'start' and self.state == State.IDLE:
            self.transition(State.PRECHECK)
        elif action == 'pause' and self.state.value in self.limits:
            self.saved = (self.state, self.elapsed)
            self.transition(State.PAUSED, 'Operator pause')
        elif action == 'resume' and self.state == State.PAUSED:
            state, elapsed = self.saved
            self.transition(state, 'Operator resume')
            self.elapsed = elapsed
            self.pid.track(0, self.recipe.setpoint, self.plant.temperature)
        elif action == 'abort' and self.state not in (State.COMPLETE, State.ABORTED):
            self.transition(State.ABORTING, 'Operator abort; contents retained')
        else:
            raise ValueError(f'Command {action} invalid in {self.state.value}')

    def tick(self, dt=0.5):
        if not math.isfinite(dt) or not 0 < dt <= 1:
            raise ValueError('Scan timestep must be in (0, 1] seconds')
        p, r = self.plant, self.recipe
        self.time += dt
        self.elapsed += dt
        active = self.state.value in self.limits or self.state == State.PAUSED
        if active and (p.sensor_failed or not math.isfinite(p.temperature) or p.temperature >= 85 or p.volume > 110):
            self.transition(State.FAULTED, 'Sensor invalid or process safety limit exceeded')
        elif self.state.value in self.limits and self.elapsed > self.limits[self.state.value]:
            self.transition(State.FAULTED, f'{self.state.value} step timeout')
        s = self.state
        if s == State.PRECHECK:
            if p.supply < r.volume or p.volume > 0.1:
                self.transition(State.FAULTED, 'Precheck: supply insufficient or vessel not empty')
            else:
                self.transition(State.FILL)
        elif s == State.FILL and p.volume >= r.volume:
            self.pid.track(0, r.setpoint, p.temperature)
            self.transition(State.HEAT)
        elif s == State.HEAT and abs(p.temperature - r.setpoint) <= 0.5:
            self.transition(State.HOLD)
        elif s == State.HOLD:
            self.hold = self.hold + dt if abs(p.temperature - r.setpoint) <= 1 else 0
            if self.hold >= r.hold_seconds:
                self.transition(State.DISCHARGE)
        elif s == State.DISCHARGE and p.volume <= 0.1:
            self.transition(State.CIP_FILL)
        elif s == State.CIP_FILL and p.volume >= r.rinse_volume:
            self.transition(State.CIP_RINSE)
        elif s == State.CIP_RINSE and self.elapsed >= r.rinse_seconds:
            self.transition(State.CIP_DRAIN)
        elif s == State.CIP_DRAIN and p.volume <= 0.1:
            self.transition(State.COMPLETE)
        elif s == State.ABORTING:
            self.transition(State.ABORTED, 'Outputs de-energized; contents retained')
        self.safe()
        p.inlet = self.state == State.FILL
        p.rinse = self.state == State.CIP_FILL
        p.outlet = self.state in (State.DISCHARGE, State.CIP_DRAIN)
        if self.state in (State.HEAT, State.HOLD) and p.volume >= 10:
            p.heater = self.pid.update(r.setpoint, p.temperature, dt)
        p.step(dt)

    def sample(self):
        return dict(time=round(self.time, 2), state=self.state.value,
                    volume=round(self.plant.volume, 3), temperature=round(self.plant.temperature, 3),
                    setpoint=self.recipe.setpoint, heater=round(self.plant.heater, 4),
                    hold=round(self.hold, 2))
