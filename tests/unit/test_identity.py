import unittest

from detecta_images.identity import LogicalVehicleManager, VehicleObservation


def observation(
    tracker_id: int,
    bounds: tuple[float, float, float, float],
    *,
    plate: str | None = None,
    color: str = "gris",
) -> VehicleObservation:
    x1, _, x2, y2 = bounds
    return VehicleObservation(
        tracker_id=tracker_id,
        bounds=bounds,
        point=((x1 + x2) / 2, y2),
        confidence=0.9,
        vehicle_class="car",
        color_name=color,
        plate_text=plate,
    )


class LogicalVehicleManagerTests(unittest.TestCase):
    def test_overlapping_duplicate_boxes_create_one_vehicle(self) -> None:
        manager = LogicalVehicleManager(max_vehicles=2)

        matches = manager.match_frame(
            [
                observation(10, (0.20, 0.20, 0.60, 0.80)),
                observation(11, (0.22, 0.22, 0.62, 0.80)),
            ],
            now=0.0,
        )

        self.assertEqual([match.logical_vehicle_id for match in matches], [1])
        self.assertEqual(manager.active_ids(), {1})

    def test_changed_tracker_near_same_position_keeps_logical_identity(self) -> None:
        manager = LogicalVehicleManager(max_vehicles=2)
        first = manager.match_frame(
            [observation(82, (0.20, 0.20, 0.60, 0.80))], now=0.0
        )
        changed = manager.match_frame(
            [observation(2341, (0.16, 0.18, 0.66, 0.81))], now=5.0
        )

        self.assertEqual(first[0].logical_vehicle_id, 1)
        self.assertEqual(changed[0].logical_vehicle_id, 1)

    def test_matching_plate_preserves_identity_after_large_shape_change(self) -> None:
        manager = LogicalVehicleManager(max_vehicles=2)
        manager.match_frame(
            [observation(1, (0.10, 0.20, 0.40, 0.75), plate="AB 123 CD")], now=0.0
        )

        changed = manager.match_frame(
            [observation(99, (0.30, 0.15, 0.80, 0.82), plate="AB123CD")], now=5.0
        )

        self.assertEqual(changed[0].logical_vehicle_id, 1)

    def test_two_separated_vehicles_have_independent_identities(self) -> None:
        manager = LogicalVehicleManager(max_vehicles=2)

        matches = manager.match_frame(
            [
                observation(1, (0.05, 0.15, 0.40, 0.65)),
                observation(2, (0.55, 0.35, 0.92, 0.90), color="blanco"),
            ],
            now=0.0,
        )

        self.assertEqual({match.logical_vehicle_id for match in matches}, {1, 2})

    def test_two_vehicles_in_line_are_not_merged_when_boxes_overlap(self) -> None:
        manager = LogicalVehicleManager(max_vehicles=2)

        matches = manager.match_frame(
            [
                observation(1, (0.15, 0.10, 0.80, 0.95), color="rojo"),
                observation(2, (0.25, 0.12, 0.55, 0.48), color="azul"),
            ],
            now=0.0,
        )

        self.assertEqual({match.logical_vehicle_id for match in matches}, {1, 2})

    def test_swapped_tracker_ids_do_not_swap_logical_vehicles(self) -> None:
        manager = LogicalVehicleManager(max_vehicles=2)
        first = manager.match_frame(
            [
                observation(10, (0.20, 0.05, 0.45, 0.35), color="negro"),
                observation(20, (0.25, 0.25, 0.85, 0.95), color="rojo"),
            ],
            now=0.0,
        )
        initial_by_tracker = {
            match.observation.tracker_id: match.logical_vehicle_id for match in first
        }

        swapped = manager.match_frame(
            [
                observation(10, (0.25, 0.25, 0.85, 0.95), color="rojo"),
                observation(20, (0.20, 0.05, 0.45, 0.35), color="negro"),
            ],
            now=5.0,
        )
        swapped_by_tracker = {
            match.observation.tracker_id: match.logical_vehicle_id for match in swapped
        }

        self.assertEqual(swapped_by_tracker[10], initial_by_tracker[20])
        self.assertEqual(swapped_by_tracker[20], initial_by_tracker[10])

    def test_capacity_two_never_creates_third_identity(self) -> None:
        manager = LogicalVehicleManager(max_vehicles=2)

        matches = manager.match_frame(
            [
                observation(1, (0.02, 0.10, 0.25, 0.50)),
                observation(2, (0.38, 0.30, 0.62, 0.70)),
                observation(3, (0.73, 0.50, 0.98, 0.95)),
            ],
            now=0.0,
        )

        self.assertEqual(len(matches), 2)
        self.assertEqual(manager.active_ids(), {1, 2})


if __name__ == "__main__":
    unittest.main()
