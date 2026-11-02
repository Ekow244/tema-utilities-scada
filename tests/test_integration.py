import socket
import unittest

try:
    from scada.integration import Runtime
except ModuleNotFoundError:
    Runtime = None


@unittest.skipIf(Runtime is None, 'Install requirements.txt for Modbus integration tests')
class ModbusTests(unittest.TestCase):
    def setUp(self):
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        self.runtime = Runtime(port)
        self.runtime.server.start()

    def tearDown(self):
        self.runtime.client.close()
        self.runtime.server.stop()

    def test_register_scaling_and_quality_over_tcp(self):
        r = self.runtime
        r.command(dict(request_id='start', action='start'))
        for _ in range(70):
            r.tick()
        snapshot = r.snapshot()
        self.assertEqual(snapshot['tags']['volume']['value'], r.c.plant.volume)
        self.assertAlmostEqual(snapshot['tags']['temperature']['value'], r.c.plant.temperature, places=2)
        r.command(dict(request_id='fault', action='sensor-fault'))
        r.tick()
        snapshot = r.snapshot()
        self.assertEqual(snapshot['state'], 'FAULTED')
        self.assertEqual(snapshot['tags']['temperature']['quality'], 'BAD')
        self.assertEqual(snapshot['tags']['heater']['value'], 0)

    def test_idempotent_command_and_rejected_transition(self):
        r = self.runtime
        request = dict(request_id='one', action='start')
        self.assertTrue(r.command(request)['accepted'])
        self.assertTrue(r.command(request)['accepted'])
        self.assertEqual(len(r.c.events), 1)
        self.assertFalse(r.command(dict(request_id='two', action='start'))['accepted'])
        with self.assertRaises(ValueError):
            r.command(dict(request_id='one', action='abort'))

    def test_modbus_failure_does_not_publish_good_data(self):
        self.runtime.server.stop()
        with self.assertRaises(ConnectionError):
            self.runtime.snapshot()
