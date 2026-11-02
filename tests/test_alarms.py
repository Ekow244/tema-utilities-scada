import unittest
from scada.alarms import Alarms
from scada.controller import Controller, State


class AlarmTests(unittest.TestCase):
    def test_sensor_trip_acknowledgement_and_no_p1_shelving(self):
        c, alarms = Controller(), Alarms()
        c.plant.sensor_failed = True
        alarms.update(c, 0.5, now=100)
        self.assertTrue(alarms.items['SENSOR']['active'])
        alarms.command('SENSOR', 'acknowledge', now=101)
        self.assertTrue(alarms.items['SENSOR']['acknowledged'])
        with self.assertRaises(ValueError):
            alarms.command('SENSOR', 'shelve', now=102)
        c.plant.sensor_failed = False
        alarms.update(c, 0.5, now=103)
        self.assertFalse(alarms.items['SENSOR']['active'])
        self.assertEqual([e['action'] for e in alarms.audit], ['RAISED','ACKNOWLEDGED','CLEARED'])

    def test_deviation_delay_deadband_and_shelf_expiry(self):
        c, alarms = Controller(), Alarms()
        c.state = State.HOLD
        c.plant.temperature = 64
        for _ in range(19):
            alarms.update(c, 0.5, now=100)
        self.assertNotIn('DEVIATION', alarms.items)
        alarms.update(c, 0.5, now=100)
        alarms.command('DEVIATION', 'shelve', now=100)
        self.assertEqual(alarms.items['DEVIATION']['shelved_until'], 160)
        c.plant.temperature = 61.5
        alarms.update(c, 0.5, now=161)
        self.assertTrue(alarms.items['DEVIATION']['active'])
        self.assertEqual(alarms.items['DEVIATION']['shelved_until'], 0)
        c.plant.temperature = 60.8
        alarms.update(c, 0.5, now=162)
        self.assertFalse(alarms.items['DEVIATION']['active'])

    def test_pump_timeout_has_response(self):
        c, alarms = Controller(), Alarms()
        c.state, c.reason = State.FAULTED, 'DISCHARGE step timeout'
        alarms.update(c, .5, now=100)
        self.assertEqual(alarms.items['TIMEOUT']['priority'], 'P2')
        self.assertIn('pump', alarms.items['TIMEOUT']['response'])
