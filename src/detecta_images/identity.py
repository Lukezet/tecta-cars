from __future__ import annotations

from dataclasses import dataclass, field
from math import hypot
import re
import uuid


Bounds = tuple[float, float, float, float]
Point = tuple[float, float]


def normalize_plate(value: str | None) -> str | None:
    normalized = re.sub(r"[^A-Z0-9]", "", (value or "").upper())
    return normalized if len(normalized) >= 5 else None


def intersection_over_union(first: Bounds, second: Bounds) -> float:
    x1 = max(first[0], second[0])
    y1 = max(first[1], second[1])
    x2 = min(first[2], second[2])
    y2 = min(first[3], second[3])
    intersection = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    first_area = max(0.0, first[2] - first[0]) * max(0.0, first[3] - first[1])
    second_area = max(0.0, second[2] - second[0]) * max(0.0, second[3] - second[1])
    union = first_area + second_area - intersection
    return intersection / union if union else 0.0


def intersection_over_smaller(first: Bounds, second: Bounds) -> float:
    x1 = max(first[0], second[0])
    y1 = max(first[1], second[1])
    x2 = min(first[2], second[2])
    y2 = min(first[3], second[3])
    intersection = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    first_area = max(0.0, first[2] - first[0]) * max(0.0, first[3] - first[1])
    second_area = max(0.0, second[2] - second[0]) * max(0.0, second[3] - second[1])
    smaller = min(first_area, second_area)
    return intersection / smaller if smaller else 0.0


def core_bounds(bounds: Bounds) -> Bounds:
    x1, y1, x2, y2 = bounds
    width = x2 - x1
    height = y2 - y1
    return (x1 + width * 0.2, y1 + height * 0.1, x2 - width * 0.2, y2)


@dataclass(frozen=True)
class VehicleObservation:
    tracker_id: int
    bounds: Bounds
    point: Point
    confidence: float
    vehicle_class: str
    color_name: str
    plate_text: str | None = None
    related_tracker_ids: tuple[int, ...] = ()


@dataclass(frozen=True)
class LogicalMatch:
    logical_vehicle_id: int
    identity_key: str
    observation: VehicleObservation


@dataclass
class LogicalVehicleState:
    logical_vehicle_id: int
    identity_key: str
    last_observation: VehicleObservation
    last_seen_at: float
    tracker_ids: set[int] = field(default_factory=set)
    plate_text: str | None = None


class LogicalVehicleManager:
    def __init__(self, max_vehicles: int, absence_grace_seconds: int = 60):
        if max_vehicles < 1:
            raise ValueError("La capacidad debe ser al menos 1")
        if absence_grace_seconds < 0:
            raise ValueError("La tolerancia de ausencia no puede ser negativa")
        self.max_vehicles = max_vehicles
        self.absence_grace_seconds = absence_grace_seconds
        self._vehicles: dict[int, LogicalVehicleState] = {}
        self._tracker_to_logical: dict[int, int] = {}

    def active_ids(self) -> set[int]:
        return set(self._vehicles)

    def _expire(self, now: float) -> None:
        expired = [
            logical_id
            for logical_id, state in self._vehicles.items()
            if now - state.last_seen_at > self.absence_grace_seconds
        ]
        for logical_id in expired:
            del self._vehicles[logical_id]
        if expired:
            active = set(self._vehicles)
            self._tracker_to_logical = {
                tracker_id: logical_id
                for tracker_id, logical_id in self._tracker_to_logical.items()
                if logical_id in active
            }

    @staticmethod
    def _duplicates(first: VehicleObservation, second: VehicleObservation) -> bool:
        iou = intersection_over_union(first.bounds, second.bounds)
        contained = intersection_over_smaller(first.bounds, second.bounds)
        point_distance = hypot(
            first.point[0] - second.point[0], first.point[1] - second.point[1]
        )
        baseline_distance = abs(first.point[1] - second.point[1])
        horizontal_overlap = max(
            0.0, min(first.bounds[2], second.bounds[2]) - max(first.bounds[0], second.bounds[0])
        )
        smaller_width = min(
            first.bounds[2] - first.bounds[0], second.bounds[2] - second.bounds[0]
        )
        horizontal_ratio = horizontal_overlap / smaller_width if smaller_width > 0 else 0.0
        same_vehicle_depth = baseline_distance <= 0.12
        return same_vehicle_depth and (
            iou >= 0.35
            or contained >= 0.75
            or (point_distance <= 0.10 and horizontal_ratio >= 0.60)
        )

    def consolidate(
        self, observations: list[VehicleObservation]
    ) -> list[VehicleObservation]:
        groups: list[list[VehicleObservation]] = []
        for observation in sorted(
            observations, key=lambda item: item.confidence, reverse=True
        ):
            group = next(
                (
                    existing
                    for existing in groups
                    if any(self._duplicates(observation, item) for item in existing)
                ),
                None,
            )
            if group is None:
                groups.append([observation])
            else:
                group.append(observation)

        consolidated: list[VehicleObservation] = []
        for group in groups:
            primary = max(group, key=lambda item: item.confidence)
            plate = next(
                (
                    normalize_plate(item.plate_text)
                    for item in group
                    if normalize_plate(item.plate_text)
                ),
                None,
            )
            related = tuple(
                sorted(
                    {
                        tracker_id
                        for item in group
                        for tracker_id in (item.tracker_id, *item.related_tracker_ids)
                    }
                )
            )
            consolidated.append(
                VehicleObservation(
                    tracker_id=primary.tracker_id,
                    bounds=primary.bounds,
                    point=primary.point,
                    confidence=primary.confidence,
                    vehicle_class=primary.vehicle_class,
                    color_name=primary.color_name,
                    plate_text=plate,
                    related_tracker_ids=related,
                )
            )
        return consolidated

    @staticmethod
    def _association_score(
        observation: VehicleObservation, state: LogicalVehicleState
    ) -> float | None:
        previous = state.last_observation
        current_plate = normalize_plate(observation.plate_text)
        previous_plate = normalize_plate(state.plate_text)
        plate_match = bool(current_plate and previous_plate and current_plate == previous_plate)
        iou = intersection_over_union(
            core_bounds(observation.bounds), core_bounds(previous.bounds)
        )
        distance = hypot(
            observation.point[0] - previous.point[0],
            observation.point[1] - previous.point[1],
        )
        if not plate_match and iou < 0.08 and distance > 0.18:
            return None
        score = iou * 4 + max(0.0, 1 - distance / 0.25) * 2
        if plate_match:
            score += 100
        if observation.color_name == previous.color_name:
            score += 0.2
        return score

    def match_frame(
        self, observations: list[VehicleObservation], now: float
    ) -> list[LogicalMatch]:
        self._expire(now)
        observations = self.consolidate(observations)
        assigned_observations: set[int] = set()
        assigned_vehicles: set[int] = set()
        assignments: dict[int, int] = {}

        for index, observation in enumerate(observations):
            tracker_ids = (observation.tracker_id, *observation.related_tracker_ids)
            logical_id = next(
                (
                    self._tracker_to_logical[tracker_id]
                    for tracker_id in tracker_ids
                    if tracker_id in self._tracker_to_logical
                    and self._tracker_to_logical[tracker_id] in self._vehicles
                    and self._tracker_to_logical[tracker_id] not in assigned_vehicles
                    and self._association_score(
                        observation,
                        self._vehicles[self._tracker_to_logical[tracker_id]],
                    )
                    is not None
                ),
                None,
            )
            if logical_id is not None:
                assignments[index] = logical_id
                assigned_observations.add(index)
                assigned_vehicles.add(logical_id)

        candidates: list[tuple[float, int, int]] = []
        for index, observation in enumerate(observations):
            if index in assigned_observations:
                continue
            for logical_id, state in self._vehicles.items():
                if logical_id in assigned_vehicles:
                    continue
                score = self._association_score(observation, state)
                if score is not None:
                    candidates.append((score, index, logical_id))
        for _, index, logical_id in sorted(candidates, reverse=True):
            if index in assigned_observations or logical_id in assigned_vehicles:
                continue
            assignments[index] = logical_id
            assigned_observations.add(index)
            assigned_vehicles.add(logical_id)

        available_ids = [
            logical_id
            for logical_id in range(1, self.max_vehicles + 1)
            if logical_id not in self._vehicles
        ]
        for index in range(len(observations)):
            if index in assigned_observations or not available_ids:
                continue
            logical_id = available_ids.pop(0)
            assignments[index] = logical_id
            assigned_observations.add(index)
            assigned_vehicles.add(logical_id)

        matches: list[LogicalMatch] = []
        for index, logical_id in sorted(assignments.items()):
            observation = observations[index]
            tracker_ids = {
                observation.tracker_id,
                *observation.related_tracker_ids,
            }
            state = self._vehicles.get(logical_id)
            plate = normalize_plate(observation.plate_text)
            if state is None:
                state = LogicalVehicleState(
                    logical_vehicle_id=logical_id,
                    identity_key=uuid.uuid4().hex,
                    last_observation=observation,
                    last_seen_at=now,
                    tracker_ids=tracker_ids,
                    plate_text=plate,
                )
                self._vehicles[logical_id] = state
            else:
                state.last_observation = observation
                state.last_seen_at = now
                state.tracker_ids.update(tracker_ids)
                if plate:
                    state.plate_text = plate
            for tracker_id in tracker_ids:
                self._tracker_to_logical[tracker_id] = logical_id
            matches.append(LogicalMatch(logical_id, state.identity_key, observation))
        return matches
