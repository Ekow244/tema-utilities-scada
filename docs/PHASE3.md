# Phase 3 — Ghana-inspired browser HMI

Open **http://localhost:8080/** after `docker compose up -d --build`.

The concept is **Tema Utilities Lab**, a fictional Ghanaian industrial training facility with an independent green-and-copper visual identity and a Ghana flag accent. No company branding, employment affiliation or real operational data is represented. The supply strip's 415 V / 50 Hz values are nominal illustrative references, not measured electrical signals. See the [PLC training package](../plc/README.md) for the new fill/drain ladder station.

## Included behavior

- Responsive HMI with animated SVG tank levels, flow paths, heater coil and equipment states.
- Browser commands connected to the existing Python controller; 500 ms HTTP polling reads real simulated Modbus registers through the bridge. Node-RED/MQTT continue to feed the historian.
- Temperature, level and output trends; SQL samples hydrate the current trend after page reload. A temperature setpoint line is shown; BAD-quality temperature samples are omitted.
- Recipe creation saves immutable versions in PostgreSQL. Batch configuration is permitted only in IDLE or a terminal state. Each new batch gets a fresh UUID and its own recipe snapshot.
- Browser commands include batch UUID to reject stale commands from a page referring to a previous batch. Legacy MQTT commands can still omit the UUID for compatibility.
- Loss of HTTP/Modbus connectivity marks data unavailable and disables batch controls. Last values stay visible as stale context, rather than being replaced with fabricated readings.
- Ghana-local clock uses Africa/Accra (GMT). Simulation time is separate and labeled.
- Historian shows the latest 30 batches; detail/export includes up to the latest 2,000 recorded samples for that batch. Full underlying records remain in PostgreSQL.

## Alarm philosophy for this demo

| Alarm | Priority | Condition | Operator response |
|---|---|---|---|
| Temperature signal invalid | P1 | Injected sensor failure | Inspect TT-101; prepare a fresh simulation |
| Process limit trip | P1 | Sequence faults on process safety limits | Inspect temperature and vessel level |
| Step timeout | P2 | Sequence timer expires | Inspect step, pump and commanded flow |
| Hold temperature deviation | P2 | >3°C deviation in HOLD for 10 simulated seconds | Inspect heat loss and heater demand |

Deviation clears at ≤1°C or on leaving HOLD. P1 alarms cannot be shelved. P2 shelving lasts 60 **real** seconds, supports manual unshelving, and never bypasses a control interlock. Alarm raise, clear, acknowledgement, shelf, unshelf and expiry actions are audited. A new occurrence after a clear requires acknowledgement again.

This illustrates ISA-18.2 alarm-management concepts. It is not a claim of conformance or a replacement for alarm rationalization, site procedures or operator training. Operator authentication, alarm performance metrics and persistent restart recovery remain outside this MVP. Alarm status is in controller memory; lifecycle records are written to SQL through snapshots. Recipe preparation explicitly flushes the old batch, but abrupt service failure can still lose untransmitted actions.

## API additions

| Route | Purpose |
|---|---|
| GET / | HMI; static JS/CSS from same service |
| GET /recipes | List saved recipe versions |
| POST /recipes | Validate/save new recipe version |
| POST /configure | New batch from recipe_id; requires current batch_id |
| POST /alarms | Acknowledge/shelve/unshelve; requires batch_id, alarm_id and action |
| GET /history | Latest batches |
| GET /history?batch=UUID | Samples, events, commands and alarm audit |

Telemetry now includes current alarms, cumulative alarm audit, and simulation speed. Input register offset 10 adds supply volume (raw /100 L); offsets 0–9 are unchanged. A new `recipes` table stores versions and `alarm_events` stores lifecycle history.

## Verification

```sh
python3 -m unittest discover -s tests -v
docker compose exec -T historian python - < tests/test_historian.py
python3 verify_hmi.py
```

Install `requirements.txt` in a virtual environment to run the real Modbus tests. The database tests require DATABASE_URL and run inside the historian container. `verify_hmi.py` expects a fresh IDLE simulator; it saves `runs/hmi-verification.json` and leaves a fresh IDLE batch after checking recipe validation, active/stale command rejection, pause/resume, P1 acknowledgement, P2 shelving/unshelving and a complete normal batch.

The full-stack HMI remains local. A separate browser-only version is published on GitHub Pages, with isolated simulation state per visitor. WebGL and a hosted backend are not implemented. Browser assets require no JavaScript framework; Google Fonts are optional and fall back to system fonts if offline.
