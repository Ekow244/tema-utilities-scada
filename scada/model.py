from dataclasses import dataclass


@dataclass
class Plant:
    volume: float = 0.0  # litres; water density assumed 1 kg/L
    temperature: float = 20.0
    supply: float = 200.0
    heater: float = 0.0  # fraction, 0..1
    inlet: bool = False
    outlet: bool = False
    rinse: bool = False
    pump_failed: bool = False
    sensor_failed: bool = False
    heat_loss: float = 0.025  # kW/K

    def step(self, dt):
        incoming = min(2.0 * dt, 120.0 - self.volume,
                       1e9 if self.rinse else self.supply) if (self.inlet or self.rinse) else 0.0
        if incoming:
            self.temperature = (self.volume * self.temperature + incoming * 20) / (self.volume + incoming)
            self.volume += incoming
            if not self.rinse:
                self.supply -= incoming
        if self.volume > 0.1:
            power = 30.0 * self.heater if self.volume >= 10 else 0.0
            self.temperature += (power - self.heat_loss * (self.temperature - 20)) * dt / (self.volume * 4.186)
        if self.outlet and not self.pump_failed:
            self.volume = max(0.0, self.volume - 2.0 * dt)


class PID:
    """PI-D on measurement, clamped output, conditional-integration anti-windup."""
    def __init__(self, kp=0.12, ki=0.0015, kd=0.0):
        self.kp, self.ki, self.kd = kp, ki, kd
        self.integral = 0.0
        self.previous = None

    def track(self, output, setpoint, measurement):
        self.integral = output - self.kp * (setpoint - measurement)
        self.previous = measurement

    def update(self, setpoint, measurement, dt):
        error = setpoint - measurement
        derivative = 0 if self.previous is None else -(measurement - self.previous) / dt
        candidate = self.integral + self.ki * error * dt
        raw = self.kp * error + candidate + self.kd * derivative
        if 0 <= raw <= 1 or (raw > 1 and error < 0) or (raw < 0 and error > 0):
            self.integral = candidate
        self.previous = measurement
        return max(0.0, min(1.0, self.kp * error + self.integral + self.kd * derivative))
