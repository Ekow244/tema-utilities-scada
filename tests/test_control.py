import unittest
from scada.controller import Controller, Recipe, State
from scada.model import PID


class ControlTests(unittest.TestCase):
    def run_batch(self, c):
        c.command('start')
        for _ in range(8000):
            c.tick()
            if c.state in (State.COMPLETE, State.FAULTED):
                break
        return c

    def test_complete_batch_and_sequence(self):
        c = self.run_batch(Controller())
        self.assertEqual(c.state, State.COMPLETE)
        self.assertGreaterEqual(c.hold, c.recipe.hold_seconds)
        self.assertEqual([e['state'] for e in c.events], [
            'PRECHECK', 'FILL', 'HEAT', 'HOLD', 'DISCHARGE', 'CIP_FILL',
            'CIP_RINSE', 'CIP_DRAIN', 'COMPLETE'])
        self.assertEqual(c.plant.volume, 0)
        self.assertEqual(c.plant.heater, 0)

    def test_sensor_failure_immediately_deenergizes(self):
        c = Controller()
        c.command('start')
        while c.state != State.HEAT:
            c.tick()
        c.plant.sensor_failed = True
        c.tick()
        self.assertEqual(c.state, State.FAULTED)
        self.assertEqual(c.plant.heater, 0)
        self.assertFalse(c.plant.inlet or c.plant.outlet)

    def test_pump_timeout(self):
        c = Controller()
        c.plant.pump_failed = True
        self.run_batch(c)
        self.assertEqual(c.state, State.FAULTED)
        self.assertIn('DISCHARGE', c.reason)

    def test_pause_resume_abort(self):
        c = Controller()
        c.command('start')
        c.tick()
        c.tick()
        c.command('pause')
        volume = c.plant.volume
        for _ in range(20):
            c.tick()
        self.assertEqual(c.plant.volume, volume)
        c.command('resume')
        c.tick()
        self.assertGreater(c.plant.volume, volume)
        c.command('abort')
        c.tick()
        self.assertEqual(c.state, State.ABORTED)
        self.assertFalse(c.plant.inlet)

    def test_precheck_and_recipe_validation(self):
        c = Controller()
        c.plant.supply = 1
        self.run_batch(c)
        self.assertEqual(c.state, State.FAULTED)
        with self.assertRaises(ValueError):
            Recipe(volume=150)

    def test_pid_antiwindup_and_tracking(self):
        pid = PID()
        for _ in range(1000):
            self.assertEqual(pid.update(60, 20, 0.5), 1)
        self.assertEqual(pid.integral, 0)
        pid.track(0.4, 60, 59)
        self.assertAlmostEqual(pid.update(60, 59, 0.0001), 0.4, places=5)


if __name__ == '__main__':
    unittest.main()
