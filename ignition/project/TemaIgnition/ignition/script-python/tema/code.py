"""Jython 2.7-compatible project script. Run inside Ignition, not CPython."""
import uuid

SIMULATOR_URL = "http://simulator:8080"
DATABASE = "TemaHistory"
TAG_ROOT = "[default]TemaTraining/"


def _request(path, body=None):
    client = system.net.httpClient(timeout=5000)
    if body is None:
        response = client.get(SIMULATOR_URL + path)
    else:
        response = client.post(SIMULATOR_URL + path, json=body)
    if response.getStatusCode() < 200 or response.getStatusCode() >= 300:
        raise ValueError("Simulator request rejected: HTTP %s" % response.getStatusCode())
    return response.getJson()


def command(action):
    allowed = ("start", "pause", "resume", "abort", "sensor-fault", "pump-fault", "heat-loss")
    if action not in allowed:
        raise ValueError("Unsupported command")
    snapshot = _request("/telemetry")
    acknowledgement = _request("/commands", {
        "batch_id": snapshot["batch_id"],
        "request_id": str(uuid.uuid4()),
        "action": action
    })
    if not acknowledgement.get("accepted"):
        raise ValueError(acknowledgement.get("reason", "Command rejected"))
    return acknowledgement


def prepare_standard():
    snapshot = _request("/telemetry")
    return _request("/configure", {
        "batch_id": snapshot["batch_id"],
        "recipe_id": "00000000-0000-4000-8000-000000000001"
    })


def record_alarm(event, stage):
    """Called only by the native pipeline's Script blocks. No email/SMS."""
    if stage not in ("active", "unacknowledged_10s"):
        raise ValueError("Unsupported pipeline stage")
    query = """INSERT INTO training_alarm_pipeline
        (event_id,stage,source,alarm_name,priority) VALUES (?,?,?,?,?)
        ON CONFLICT (event_id,stage) DO NOTHING"""
    priority = event.getPriority().intValue
    # Accommodate the Jython property accessor and Java method exposure.
    priority = priority() if callable(priority) else priority
    system.db.runPrepUpdate(query, [str(event.getId()), stage, str(event.getSource()),
                                   str(event.getName()), int(priority)], DATABASE)
    system.util.getLogger("TemaTraining.AlarmPipeline").info(
        "%s: %s" % (stage, str(event.getSource())))


def recent_history(minutes=5):
    if minutes < 1 or minutes > 60:
        raise ValueError("History window must be 1..60 minutes")
    end = system.date.now()
    return system.tag.queryTagHistory(
        paths=[TAG_ROOT + "Temperature", TAG_ROOT + "Setpoint", TAG_ROOT + "Volume"],
        startDate=system.date.addMinutes(end, -minutes), endDate=end,
        returnSize=-1, returnFormat="Wide", noInterpolation=True,
        includeBoundingValues=False)
