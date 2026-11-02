import argparse
import csv
import json
from pathlib import Path
from dataclasses import asdict
from .controller import Controller, State


def main():
    parser = argparse.ArgumentParser(description='Accelerated batch simulation (no physical I/O)')
    parser.add_argument('--scenario', choices=['normal', 'heat-loss', 'sensor-fault', 'pump-fault'], default='normal')
    parser.add_argument('--output', default='runs/normal')
    args = parser.parse_args()
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    c = Controller()
    c.command('start')
    rows = [c.sample()]
    injected = False
    while c.time < 4000 and c.state not in (State.COMPLETE, State.FAULTED, State.ABORTED):
        if not injected and c.state == State.HOLD and args.scenario in ('heat-loss', 'sensor-fault'):
            if args.scenario == 'sensor-fault':
                c.plant.sensor_failed = True
            else:
                c.plant.heat_loss = 0.12
            c.events.append(dict(time=c.time, previous=c.state.value, state=c.state.value,
                                 reason=f'Injected {args.scenario}'))
            injected = True
        if args.scenario == 'pump-fault' and c.state == State.DISCHARGE:
            c.plant.pump_failed = True
        c.tick()
        rows.append(c.sample())
    with (out / 'samples.csv').open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    (out / 'events.json').write_text(json.dumps(c.events, indent=2))
    summary = dict(scenario=args.scenario, final_state=c.state.value, seconds=c.time,
                   max_temperature=max(row['temperature'] for row in rows),
                   reason=c.reason, recipe=asdict(c.recipe))
    (out / 'summary.json').write_text(json.dumps(summary, indent=2))
    # Standalone SVG: no plotting packages or network dependencies.
    def points(key):
        return ' '.join(f"{60 + row['time']/max(c.time,1)*880:.1f},{300-row[key]/100*250:.1f}" for row in rows[::4] + rows[-1:])
    svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1000 380"><rect width="1000" height="380" fill="#101c2a"/>'
    svg += '<g fill="#e1ebf5" font-family="sans-serif"><text x="60" y="28" font-size="20">Batch temperature — ' + args.scenario + '</text>'
    for temp in range(0, 101, 20):
        y = 300-temp*2.5
        svg += f'<path d="M60 {y} H940" stroke="#304256"/><text x="15" y="{y+5}">{temp}</text>'
    svg += f'<text x="60" y="335">0 s</text><text x="850" y="335">{c.time:.0f} s</text><text x="60" y="363">°C · cyan: temperature · amber: setpoint · final state: {c.state.value}</text></g>'
    svg += f'<polyline points="{points("setpoint")}" fill="none" stroke="#ffbd69" stroke-dasharray="6 4"/><polyline points="{points("temperature")}" fill="none" stroke="#44ded0" stroke-width="2"/></svg>'
    (out / 'trend.svg').write_text(svg)
    print(json.dumps(summary, indent=2))
    if c.state not in (State.COMPLETE, State.FAULTED):
        raise SystemExit('Simulation did not reach an expected terminal state')


if __name__ == '__main__':
    main()
