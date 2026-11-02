# Ignition integration · source package

**Target: Ignition Standard 8.1.48. Status: source and contract checks only; native runtime acceptance is pending.** This directory is not a Gateway backup, a Designer-exported project, or evidence of completed Ignition commissioning. [Exact validation status](evidence/validation-status.json).

The package mirrors the existing thermal skid with:

- Eleven read-only Modbus input-register tags and engineering-unit expression tags.
- One native Perspective view with state/measurement labels, validated HTTP batch controls, a Power Chart and an Alarm Status Table.
- A native alarm-pipeline assembly specification and tested Script-block helper for local SQL audit.
- SQL Tag Historian settings for the engineering tags and a dedicated PostgreSQL database.

This is separate from the public GitHub Pages browser simulation. Ignition cannot run on GitHub Pages. No vendor installation files, credentials or licence keys are included in GitHub.

## Contents

| Path | Purpose |
|---|---|
| `tags/tema-tags.json` | Tag configuration for Designer import |
| `tags/modbus-map.csv` | Register offset, Ignition address and scale |
| `project/TemaIgnition/` | Filesystem project source: view, page route and `tema` script library |
| `pipelines/LocalAudit.json` | Designer block/connection specification; not a native export |
| `sql/001_pipeline.sql` | SQL table for local pipeline audit; separate from native historian tables |
| `scripts/import_tags.py` | Designer-console import that refuses an existing training folder |
| `scripts/verify_gateway.py` | Actual Gateway acceptance checks to run after setup |

## Local services

From the repository root:

```sh
docker compose -f compose.yaml -f ignition/compose.ignition.yaml up -d ignition ignition-db
```

Open http://localhost:9088/. Select Standard Edition, review/accept the vendor licence yourself and create your administrator credentials. The Compose file explicitly does not accept the licence or seed a password. Use the evaluation/trial controls provided by Ignition; no trial-expiry workaround is included. Decline the unrelated Quick Start project when offered.

The Gateway is bound to localhost. Its database is private to the Compose network. The database password is an explicit local-demo placeholder; it is not a Gateway administrator credential. Named volumes preserve Gateway/database state. To stop just these services:

```sh
docker compose -f compose.yaml -f ignition/compose.ignition.yaml stop ignition ignition-db
```

Existing Gateway: use the same 8.1 source package, but adapt device/database hostnames. A non-Docker Gateway cannot resolve `simulator` or `ignition-db`. This package does not publish their ports by default.

## Gateway configuration

Required modules: OPC UA with Modbus driver, Perspective, Tag Historian and Alarm Notification. Keep the project name **TemaIgnition**, default tag provider **default**, Gateway name **TemaIgnition**, Modbus device **TemaSim** and PostgreSQL connection **TemaHistory** for the supplied paths.

1. Add a **Modbus TCP** device named `TemaSim`: host `simulator`, port `1502`. **Uncheck Zero-based Addressing**: item `1.IRUS1` then maps to protocol offset 0. Unit ID is 1. The explicit unsigned `IRUS` designator avoids signed-word interpretation. At idle, verify raw temperature 2000, setpoint 6000 (standard recipe), and supply volume 20000. If values are shifted, resolve addressing before proceeding.
2. Add a PostgreSQL database connection named `TemaHistory`: JDBC host `ignition-db`, port `5432`, database `tema_ignition`, user `ignition`, password from the local Compose file. Confirm the connection is valid. The dedicated database isolates Ignition's native history/journal tables from the original application historian.
3. Ensure the SQL Tag History provider associated with `TemaHistory` is available. Ignition manages its `sqlth_*` tables; do not create replacement time-series tables manually.
4. Add a database Alarm Journal profile named `TemaJournal` using `TemaHistory` if you want native active/clear/ack history. Pipeline SQL records are a separate audit of pipeline traversal, not a substitute for the native journal.

## Install the project source

Generate a source archive and fresh tag configuration:

```sh
python3 scripts/build_ignition.py
```

`ignition/dist/TemaIgnition-source.zip` is a source bundle, **not** a Designer-generated export. Prefer loading `project/TemaIgnition/` into a new development Gateway project using the documented filesystem layout. Do not overwrite an existing project with this name. For the supplied container, after commissioning:

```sh
docker compose -f compose.yaml -f ignition/compose.ignition.yaml cp ignition/project/TemaIgnition ignition:/usr/local/bin/ignition/data/projects/
docker compose -f compose.yaml -f ignition/compose.ignition.yaml exec -u 0 ignition sh -c 'chown -R ignition:ignition /usr/local/bin/ignition/data/projects/TemaIgnition'
```

Open `TemaIgnition` in Designer and verify its resources are recognized. If the filesystem change is not detected, use Gateway project scanning/restart in this development environment. A Designer import/render check remains required: static JSON checks do not prove that every component property is accepted by the target build.

Import `tags/tema-tags.json` with Designer's tag import, or run `scripts/import_tags.py` in its Script Console and select that file. The helper refuses to overwrite `[default]TemaTraining`. Check raw and engineering values, Good communication quality, the configured history provider and sample mode before starting a batch.

## Perspective screen

The route `/` points to `Overview`. After the project is loaded, open:

`http://localhost:9088/data/perspective/client/TemaIgnition/`

The view reads native tags through Ignition. Start/pause/resume/abort, prepare-standard and sensor-fault actions call the existing simulator's validated HTTP API from the project script library. No Modbus writes are made to read-only input registers. Native alarm acknowledgement stays within Ignition; acknowledging an alarm does not reset the Python fault.

Power Chart pens use `TemaHistory`, Gateway `TemaIgnition`, provider `default` and the historical tag paths. If a pen path is unresolved on the installed build, browse the corresponding saved tag from the native chart and retain its generated path. The chart defaults to a five-minute wall-time window.

The Alarm Status Table uses its native defaults and can show all Gateway alarms. On a shared Gateway, set a source filter for `TemaTraining` in Designer. The sensor-fault flag is historized separately: a simulated sensor failure is not the same as an OPC communication-quality failure. The screen explicitly identifies that flag; raw numeric temperature should not be treated as valid while it is true.

## Native alarm pipeline

Create **LocalAudit** under Alarm Notification Pipelines in project `TemaIgnition`. Assemble the blocks from `pipelines/LocalAudit.json`:

```text
Start → Script (record active) → Delay (10 s) → Script (record unacknowledged) → end
```

The first Script block body is:

```python
tema.record_alarm(event, 'active')
```

The second Script block body is:

```python
tema.record_alarm(event, 'unacknowledged_10s')
```

Enable the pipeline's acknowledged, cleared and shelved dropout conditions. Select the pipeline through each supplied alarm's **Active Pipeline** dropdown; do this in Designer so its project-qualified reference is generated correctly. Tags initially omit that reference rather than pointing to a nonexistent pipeline.

The SQL table is initialized for a fresh `ignition-db` volume. For an existing database, apply `sql/001_pipeline.sql` before triggering alarms. Script calls use prepared queries and `(event_id, stage)` uniqueness. No email/SMS profile or external recipient is configured, and no notifications are sent outside the local project.

Native tags define sensor-invalid (Critical), batch-faulted (High) and high-temperature (High, 80°C with 2°C deadband and a delay) alarms. The StateCode alarm is generated from the Python enum, not a hand-maintained number. Source checks caught and corrected the older register-map documentation's off-by-one state-range description.

## Runtime acceptance still required

1. Confirm the device is connected and engineering tag quality is Good.
2. Start a batch; verify fill, heating and state transitions on the native view.
3. Confirm history in the native Power Chart and native `sqlth_*` tables. Refresh the session and query saved history.
4. Inject sensor failure after the pipeline is attached. Confirm native alarm activation and one `active` SQL audit row.
5. Acknowledge within 10 seconds: verify dropout prevents a delayed row. Repeat without acknowledging: verify `unacknowledged_10s` is inserted once.
6. Stop the simulator service: verify bad OPC quality is visible and controls disable. Restore it and prepare a fresh batch.
7. Run `scripts/verify_gateway.py` in the Designer Script Console. Save its actual output in a local evidence file, then review it before publishing. Do not replace `NOT_RUN` with PASS until the relevant native behavior is observed.

The verification script checks tag quality, recent native history and pipeline audit rows. It does not automatically prove layout quality, dropout timing or all manual acceptance steps.

## Sources

- [Official Docker image and commissioning](https://www.docs.inductiveautomation.com/docs/8.1/platform/docker-image)
- [Modbus address syntax](https://www.docs.inductiveautomation.com/docs/8.1/ignition-modules/opc-ua/opc-ua-drivers/modbus/modbus-addressing) and [connection addressing option](https://www.docs.inductiveautomation.com/docs/8.1/ignition-modules/opc-ua/opc-ua-drivers/modbus/connecting-to-modbus-device)
- [Tag properties and history](https://www.docs.inductiveautomation.com/docs/8.1/platform/tags/tag-properties)
- [Project resource manifests](https://www.docs.inductiveautomation.com/docs/8.1/appendix/reference-pages/resource-json-file)
- [Pipeline blocks](https://www.docs.inductiveautomation.com/docs/8.1/ignition-modules/alarm-notification/alarm-notification-pipelines/pipeline-blocks)
- [Native history queries](https://docs.inductiveautomation.com/docs/8.1/appendix/scripting-functions/system-tag/system-tag-queryTagHistory)
