from __future__ import annotations

from dataclasses import dataclass


Point = tuple[float, float]


def point_in_polygon(point: Point, polygon: list[Point]) -> bool:
    if len(polygon) < 3:
        return False
    x, y = point
    inside = False
    previous = polygon[-1]
    for current in polygon:
        x1, y1 = previous
        x2, y2 = current
        crosses_ray = (y1 > y) != (y2 > y)
        if crosses_ray:
            intersection_x = (x2 - x1) * (y - y1) / (y2 - y1) + x1
            if x < intersection_x:
                inside = not inside
        previous = current
    return inside


@dataclass(frozen=True)
class ServiceReady:
    logical_vehicle_id: int
    dwell_seconds: int


@dataclass
class TrackState:
    logical_vehicle_id: int
    entered_at: float
    last_seen_at: float
    counted: bool = False
    missing_since: float | None = None


class CountingEngine:
    def __init__(self, dwell_seconds: int = 900, absence_grace_seconds: int = 10):
        if dwell_seconds < 1:
            raise ValueError("dwell_seconds debe ser positivo")
        if absence_grace_seconds < 0:
            raise ValueError("absence_grace_seconds no puede ser negativo")
        self.dwell_seconds = dwell_seconds
        self.absence_grace_seconds = absence_grace_seconds
        self._tracks: dict[int, TrackState] = {}
        self._paused_at: float | None = None

    def update(
        self, logical_vehicle_id: int, point: Point, now: float, polygon: list[Point]
    ) -> list[ServiceReady]:
        if not point_in_polygon(point, polygon):
            self._tracks.pop(logical_vehicle_id, None)
            return []

        state = self._tracks.get(logical_vehicle_id)
        if state is None:
            state = TrackState(logical_vehicle_id, entered_at=now, last_seen_at=now)
            self._tracks[logical_vehicle_id] = state
        else:
            state.last_seen_at = now
            state.missing_since = None

        elapsed = max(0, int(now - state.entered_at))
        if not state.counted and elapsed >= self.dwell_seconds:
            state.counted = True
            return [ServiceReady(logical_vehicle_id, self.dwell_seconds)]
        return []

    def mark_frame_complete(self, seen_vehicle_ids: set[int], now: float) -> None:
        expired: list[int] = []
        for logical_vehicle_id, state in self._tracks.items():
            if logical_vehicle_id in seen_vehicle_ids:
                continue
            if state.missing_since is None:
                state.missing_since = now
            elif now - state.missing_since > self.absence_grace_seconds:
                expired.append(logical_vehicle_id)
        for logical_vehicle_id in expired:
            del self._tracks[logical_vehicle_id]

    def active_tracks(self, now: float) -> list[dict[str, object]]:
        effective_now = self._paused_at if self._paused_at is not None else now
        return [
            {
                "logical_vehicle_id": state.logical_vehicle_id,
                "tracker_id": state.logical_vehicle_id,
                "elapsed_seconds": max(0, int(effective_now - state.entered_at)),
                "target_seconds": self.dwell_seconds,
                "counted": state.counted,
                "temporarily_missing": state.missing_since is not None,
            }
            for state in sorted(
                self._tracks.values(), key=lambda item: item.logical_vehicle_id
            )
        ]

    def pause(self, now: float) -> None:
        if self._paused_at is None:
            self._paused_at = now

    def resume(self, now: float) -> None:
        if self._paused_at is None:
            return
        paused_duration = max(0.0, now - self._paused_at)
        for state in self._tracks.values():
            state.entered_at += paused_duration
            state.last_seen_at += paused_duration
            if state.missing_since is not None:
                state.missing_since += paused_duration
        self._paused_at = None
