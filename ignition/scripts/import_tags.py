# Run in the Ignition Designer Script Console after creating the device and DB.
# This script creates a new folder only; it refuses to replace an existing one.
ROOT = "[default]TemaTraining"
if system.tag.exists(ROOT):
    raise ValueError("TemaTraining already exists; inspect it before importing")
json_path = system.file.openFile("json")
if json_path:
    document = system.util.jsonDecode(system.file.readFileAsString(json_path))
    results = system.tag.configure("[default]", document["tags"], "a")
    if any(not result.isGood() for result in results):
        raise ValueError("Tag configuration failed: %s" % results)
    print("TemaTraining tags configured. Verify device quality before using the view.")
