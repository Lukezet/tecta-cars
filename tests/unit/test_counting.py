import unittest

from detecta_images.counting import CountingEngine, point_in_polygon


ZONE = [(0.1, 0.1), (0.9, 0.1), (0.9, 0.9), (0.1, 0.9)]


class CountingEngineTests(unittest.TestCase):
    def test_point_in_polygon_distinguishes_inside_and_outside(self) -> None:
        self.assertTrue(point_in_polygon((0.5, 0.5), ZONE))
        self.assertFalse(point_in_polygon((0.95, 0.5), ZONE))

    def test_vehicle_is_counted_once_at_threshold(self) -> None:
        engine = CountingEngine(dwell_seconds=900, absence_grace_seconds=10)

        self.assertEqual(engine.update(1, (0.5, 0.5), 100.0, ZONE), [])
        events = engine.update(1, (0.5, 0.5), 1000.0, ZONE)
        repeated = engine.update(1, (0.5, 0.5), 1100.0, ZONE)

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].logical_vehicle_id, 1)
        self.assertEqual(events[0].dwell_seconds, 900)
        self.assertEqual(repeated, [])

    def test_two_vehicles_have_independent_timers(self) -> None:
        engine = CountingEngine(dwell_seconds=900, absence_grace_seconds=10)
        engine.update(1, (0.4, 0.5), 0.0, ZONE)
        engine.update(2, (0.6, 0.5), 300.0, ZONE)

        first = engine.update(1, (0.4, 0.5), 900.0, ZONE)
        second_early = engine.update(2, (0.6, 0.5), 900.0, ZONE)
        second = engine.update(2, (0.6, 0.5), 1200.0, ZONE)

        self.assertEqual([event.logical_vehicle_id for event in first], [1])
        self.assertEqual(second_early, [])
        self.assertEqual([event.logical_vehicle_id for event in second], [2])

    def test_long_absence_resets_continuous_dwell(self) -> None:
        engine = CountingEngine(dwell_seconds=900, absence_grace_seconds=10)
        engine.update(1, (0.5, 0.5), 0.0, ZONE)
        engine.mark_frame_complete(seen_vehicle_ids=set(), now=500.0)
        engine.mark_frame_complete(seen_vehicle_ids=set(), now=511.0)

        engine.update(1, (0.5, 0.5), 600.0, ZONE)
        events = engine.update(1, (0.5, 0.5), 1400.0, ZONE)

        self.assertEqual(events, [])

    def test_short_absence_preserves_timer(self) -> None:
        engine = CountingEngine(dwell_seconds=900, absence_grace_seconds=10)
        engine.update(1, (0.5, 0.5), 0.0, ZONE)
        engine.mark_frame_complete(seen_vehicle_ids=set(), now=500.0)
        engine.update(1, (0.5, 0.5), 505.0, ZONE)

        events = engine.update(1, (0.5, 0.5), 900.0, ZONE)

        self.assertEqual(len(events), 1)

    def test_paused_time_is_not_added_to_dwell(self) -> None:
        engine = CountingEngine(dwell_seconds=900, absence_grace_seconds=10)
        engine.update(1, (0.5, 0.5), 0.0, ZONE)
        engine.pause(300.0)
        engine.resume(600.0)

        early = engine.update(1, (0.5, 0.5), 900.0, ZONE)
        on_time = engine.update(1, (0.5, 0.5), 1200.0, ZONE)

        self.assertEqual(early, [])
        self.assertEqual(len(on_time), 1)


if __name__ == "__main__":
    unittest.main()
