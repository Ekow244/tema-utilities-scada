A deterministic, accelerated Python simulation for demonstrating industrial automation concepts. Uses only the Python standard library (Python 3.10+). No installation of third-party packages is required.

## Run

From this folder:

```sh
python3 -m scada --output runs/normal
python3 -m scada --scenario heat-loss --output runs/heat-loss
python3 -m scada --scenario sensor-fault --output runs/sensor-fault
python3 -m scada --scenario pump-fault --output runs/pump-fault
python3 -m unittest discover -s tests -v
```

Each run produces `samples.csv`, `events.json`, `summary.json`, and `trend.svg`. Open the SVG in a browser. Time is simulated: a 16.5-minute batch executes in a fraction of a second.

## Process and sequence

200 L supply → fill valve → 120 L heated vessel → discharge pump. Separate fresh-water inlet provides a simplified rinse.

`IDLE → PRECHECK → FILL → HEAT → HOLD → DISCHARGE → CIP_FILL → CIP_RINSE → CIP_DRAIN → COMPLETE`

Default recipe: 60 L water, 60°C target, 120 continuous seconds within ±1°C, then discharge and a 20 L / 30-second rinse. HEAT transitions to HOLD within ±0.5°C. Leaving the hold tolerance resets the qualification timer. The rinse is an ambient-water dwell and drain; it does not model circulation, chemicals, hygienic efficacy, or validated CIP.

| Step | Action | Completion | Timeout |
|---|---|---|---|
| PRECHECK | Validate empty vessel and supply | Checks pass | 5 s |
| FILL | Open supply inlet | Recipe volume reached | 120 s |
| HEAT | Automatic temperature control | Within 0.5°C of target | 1800 s |
| HOLD | Continue temperature control | Continuous qualified hold | 1800 s |
| DISCHARGE | Run discharge pump | Vessel ≤0.1 L | 120 s |
| CIP_FILL | Open fresh-water inlet | Rinse volume reached | 120 s |
| CIP_RINSE | Retain water | Rinse duration reached | 600 s |
| CIP_DRAIN | Run discharge pump | Vessel ≤0.1 L | 120 s |

Pause closes valves, stops the pump and disables heat. Resume restores the step timer and tracks the PID to zero output before re-entering automatic control. Hold qualification remains subject to temperature tolerance on the next scan. Abort retains contents and de-energizes outputs. Faults latch; create a fresh controller to reset this MVP. No automatic fault restart is provided.

## Controls and model

- A 500 ms simulation scan validates inputs, evaluates transitions, assigns outputs, then advances the plant.
- Water has density 1 kg/L and heat capacity 4.186 kJ/(kg·K); heater rating is 30 kW. Nominal heat loss is 0.025 kW/K to 20°C ambient. Inlet and discharge rates are 2 L/s. Perfect mixing is assumed.
- PID uses proportional error, integral action and derivative on measurement. Current tuning is PI: Kp=0.12 output/°C, Ki=0.0015 output/(°C·s), Kd=0. Output is limited to 0–100%, with conditional-integration anti-windup and output tracking.
- Heat is inhibited below 10 L. Invalid temperature, injected sensor failure, temperature ≥85°C, or volume >110 L faults an active/paused batch. Step timeouts detect failures such as a blocked discharge.
- The recipe is immutable during a run and copied to the summary. `Recipe` in `scada/controller.py` exposes the initial parameters for programmatic use.

These are IEC 61131-3-inspired sequencing concepts implemented in Python, not IEC code or a certified PLC runtime. These software checks are educational; this project does not operate physical equipment.

## Recorded verification

| Scenario | Result | Simulated duration | Peak temperature |
|---|---|---|---|
| Normal | COMPLETE | 990 s | 62.194°C |
| Heat loss increased to 0.12 kW/K at HOLD entry | COMPLETE | 773 s | 61.582°C |
| Sensor failure at HOLD entry | FAULTED; outputs off | 395 s | 59.555°C |
| Failed discharge pump | FAULTED on discharge timeout | 1030.5 s | 62.194°C |

Normal overshoot is 2.194°C above target. This initial tuning completes the required uninterrupted hold; it is not an optimized tune. The heat-loss case completes sooner because the extra cooling reduces overshoot. It demonstrates disturbance behavior at HOLD entry, not a separate steady-state recovery benchmark.

Six tests cover the full state sequence, qualified hold completion, safe terminal outputs, sensor failure, pump timeout, pause/resume/abort, recipe/precheck validation, PID saturation and tracking.

## Interview walkthrough

1. Explain the equipment, recipe and state transitions.
2. Run the normal scenario and open its temperature trend.
3. Show the HOLD timer rule and discuss measured overshoot and tuning tradeoffs.
4. Run the sensor and pump faults; show the event reasons and final actuator states.
5. Explain how the controller's `command`, `tick`, and `sample` interface can support a future browser HMI.

## Next milestone

Add a local web dashboard with live state, tank level, temperature trend and start/pause/resume/abort controls, then a WebGL scene driven by the same telemetry. Modbus, MQTT, Node-RED, SQL historian, Docker and public hosting are not implemented in Phase 1. CSV/JSON outputs are local run evidence rather than a production historian.
