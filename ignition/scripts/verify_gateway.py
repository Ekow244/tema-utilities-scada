# Run in the Designer Script Console with project TemaIgnition open.
# This records actual Gateway results only. It does not fabricate runtime evidence.
def verify_tema():
    paths = ["[default]TemaTraining/" + name for name in
             ("Volume", "Temperature", "Setpoint", "HeaterPercent", "SensorFault", "StateCode")]
    values = system.tag.readBlocking(paths)
    good = all(value.quality.isGood() for value in values)
    history = tema.recent_history(5)
    pipeline_rows = system.db.runScalarQuery(
        "SELECT count(*) FROM training_alarm_pipeline", "TemaHistory")
    report = {
        "ignition_version": system.util.getVersion(),
        "tag_quality_good": good,
        "history_rows_last_5_minutes": history.getRowCount(),
        "pipeline_audit_rows": pipeline_rows,
        "values": dict((path, str(value.value)) for path, value in zip(paths, values)),
        "result": "PASS" if good and history.getRowCount() > 0 and pipeline_rows > 0 else "INCOMPLETE"
    }
    print(system.util.jsonEncode(report, 2))
    return report

verify_tema()
