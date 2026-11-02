"""Source/contract checks only; these do not substitute for Gateway acceptance."""
import importlib.util
import json
import re
from pathlib import Path
from types import SimpleNamespace
import unittest

from scada.controller import Controller, State

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'ignition'


class IgnitionSourceTests(unittest.TestCase):
    def setUp(self):
        self.tags = json.loads((BASE / 'tags/tema-tags.json').read_text())['tags'][0]['tags']
        self.by_name = {tag['name']: tag for tag in self.tags}

    def test_modbus_mapping_matches_real_simulator_and_unsigned_scaling(self):
        try:
            from scada.integration import encode
        except ModuleNotFoundError:
            self.skipTest("Install requirements.txt for the Modbus mapping test")
        controller = Controller()
        controller.plant.supply = 200
        registers = encode(controller)
        raw = self.by_name['Raw']['tags']
        self.assertEqual(len(raw), len(registers))
        for offset, tag in enumerate(raw):
            self.assertEqual(tag['opcItemPath'], '[TemaSim]1.IRUS%d' % (offset+1))
            self.assertEqual(tag['accessRights'], 'Read_Only')
        self.assertEqual(registers[10], 20000)
        self.assertIn('/ 100.0', self.by_name['SupplyVolume']['expression'])
        self.assertIn('/ 100.0', self.by_name['HeaterPercent']['expression'])

    def test_alarm_state_and_historian_use_actual_enum_and_named_provider(self):
        alarm = self.by_name['StateCode']['alarms'][0]
        self.assertEqual(alarm['setpointA'], list(State).index(State.FAULTED))
        for tag in self.tags:
            if tag.get('historyEnabled'):
                self.assertEqual(tag['historyProvider'], 'TemaHistory')
                self.assertEqual(tag['sampleMode'], 'Periodic')
                self.assertEqual(tag['historySampleRateUnits'], 'SEC')
        pipeline = json.loads((BASE / 'pipelines/LocalAudit.json').read_text())
        for attachment in pipeline['attach_to']:
            name = attachment['tag'].split('/')[-1]
            self.assertIn(attachment['alarm'], [a['name'] for a in self.by_name[name]['alarms']])
        self.assertFalse(pipeline['external_notifications'])

    def test_resource_manifests_and_bindings_resolve_source_files(self):
        project = BASE / 'project/TemaIgnition'
        for path in project.rglob('resource.json'):
            for filename in json.loads(path.read_text())['files']:
                self.assertTrue((path.parent / filename).is_file(), path)
        view = json.loads((project / 'com.inductiveautomation.perspective/views/Overview/view.json').read_text())
        references = []
        def walk(node):
            for setting in node.get('propConfig', {}).values():
                binding = setting['binding']
                if binding['type'] == 'expr':
                    names = re.findall(r'\{\[default\]TemaTraining/([^}]+)\}', binding['config']['expression'])
                    for name in names:
                        references.append(name)
                        self.assertIn(name, self.by_name)
                if binding['type'] == 'tag':
                    self.assertIn(binding['config']['tagPath'].split('/')[-1], self.by_name)
            for child in node.get('children', []):
                walk(child)
            for action in node.get('events', {}).get('component', {}).values():
                self.assertIsInstance(action, dict)
                self.assertEqual(action['type'], 'script')
                self.assertEqual(action['scope'], 'G')
        walk(view['root'])
        self.assertGreater(len(references), 5)
        self.assertEqual(view['root']['type'], 'ia.container.flex')

    def module(self):
        path = BASE / 'project/TemaIgnition/ignition/script-python/tema/code.py'
        spec = importlib.util.spec_from_file_location('tema_ignition_test', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_command_carries_batch_uuid_and_handles_http_rejection(self):
        module = self.module()
        calls = []
        class Response:
            def __init__(self, status, data): self.status, self.data = status, data
            def getStatusCode(self): return self.status
            def getJson(self): return self.data
        class Client:
            reject = False
            def get(self, url): return Response(200, dict(batch_id='test-batch'))
            def post(self, url, json):
                calls.append((url, json))
                return Response(409 if self.reject else 200, dict(accepted=True))
        client = Client()
        module.system = SimpleNamespace(net=SimpleNamespace(httpClient=lambda **kw: client))
        self.assertTrue(module.command('start')['accepted'])
        self.assertEqual(calls[0][1]['batch_id'], 'test-batch')
        self.assertTrue(calls[0][1]['request_id'])
        client.reject = True
        with self.assertRaises(ValueError): module.command('start')
        with self.assertRaises(ValueError): module.command('write-register')

    def test_pipeline_helper_uses_parameterized_idempotent_sql(self):
        module = self.module()
        calls = []
        event = SimpleNamespace(getId=lambda:'alarm-uuid', getSource=lambda:'prov:default:/tag:SensorFault',
            getName=lambda:'TemperatureSignalInvalid', getPriority=lambda:SimpleNamespace(intValue=lambda:4))
        module.system = SimpleNamespace(db=SimpleNamespace(runPrepUpdate=lambda *args:calls.append(args)),
            util=SimpleNamespace(getLogger=lambda name:SimpleNamespace(info=lambda text:None)))
        module.record_alarm(event, 'active')
        query, arguments, database = calls[0]
        self.assertIn('ON CONFLICT', query)
        self.assertEqual(query.count('?'), len(arguments))
        self.assertEqual(arguments, ['alarm-uuid','active','prov:default:/tag:SensorFault','TemperatureSignalInvalid',4])
        self.assertEqual(database, 'TemaHistory')
        with self.assertRaises(ValueError): module.record_alarm(event, 'email')


if __name__ == '__main__':
    unittest.main()
