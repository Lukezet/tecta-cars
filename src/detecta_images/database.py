from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS_DIR = PROJECT_ROOT / "migrations"


class Database:
    def __init__(self, path: Path):
        self.path = Path(path)

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    @contextmanager
    def connection(self):
        connection = self._connect()
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def migrate(self) -> None:
        with self.connection() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version TEXT PRIMARY KEY,
                    applied_at TEXT NOT NULL
                )
                """
            )
            applied = {
                row["version"]
                for row in connection.execute(
                    "SELECT version FROM schema_migrations"
                ).fetchall()
            }
            for migration_path in sorted(MIGRATIONS_DIR.glob("*.sql")):
                version = migration_path.stem
                if version in applied:
                    continue
                connection.executescript(migration_path.read_text(encoding="utf-8"))
                connection.execute(
                    "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
                    (version, datetime.now().astimezone().isoformat()),
                )

    def save_camera_config(
        self,
        host: str,
        port: int,
        stream_name: str,
        username: str,
        credential_key: str,
    ) -> int:
        if not host.strip() or not username.strip() or not credential_key.strip():
            raise ValueError("Host, usuario y referencia de credencial son obligatorios")
        if not 1 <= port <= 65535:
            raise ValueError("Puerto invalido")
        if stream_name not in {"stream1", "stream2"}:
            raise ValueError("Flujo invalido")
        with self.connection() as connection:
            connection.execute(
                """
                INSERT INTO camera_configs (
                    id, host, port, stream_name, username, credential_key, updated_at
                ) VALUES (1, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    host = excluded.host,
                    port = excluded.port,
                    stream_name = excluded.stream_name,
                    username = excluded.username,
                    credential_key = excluded.credential_key,
                    updated_at = excluded.updated_at
                """,
                (
                    host.strip(),
                    port,
                    stream_name,
                    username.strip(),
                    credential_key.strip(),
                    datetime.now().astimezone().isoformat(),
                ),
            )
        return 1

    def get_camera_config(self) -> dict[str, object] | None:
        with self.connection() as connection:
            row = connection.execute(
                """
                SELECT id, host, port, stream_name, username, credential_key, updated_at
                FROM camera_configs WHERE id = 1
                """
            ).fetchone()
        return dict(row) if row else None

    def get_max_concurrent_vehicles(self) -> int:
        with self.connection() as connection:
            row = connection.execute(
                """
                SELECT max_concurrent_vehicles
                FROM installation_settings
                WHERE id = 1
                """
            ).fetchone()
        if row is None:
            raise RuntimeError("Falta la configuración de la instalación")
        return int(row["max_concurrent_vehicles"])

    def save_max_concurrent_vehicles(self, value: int) -> int:
        if value < 1:
            raise ValueError("La capacidad debe ser al menos 1")
        with self.connection() as connection:
            connection.execute(
                """
                UPDATE installation_settings
                SET max_concurrent_vehicles = ?, updated_at = ?
                WHERE id = 1
                """,
                (value, datetime.now().astimezone().isoformat()),
            )
        return value

    def replace_active_zone(
        self,
        camera_id: int,
        polygon: Iterable[tuple[float, float]],
        reference_image_path: str | None,
        frame_width: int,
        frame_height: int,
    ) -> int:
        points = [(float(x), float(y)) for x, y in polygon]
        if len(points) < 3 or any(
            not 0 <= coordinate <= 1 for point in points for coordinate in point
        ):
            raise ValueError("La zona requiere al menos tres puntos entre 0 y 1")
        if frame_width < 1 or frame_height < 1:
            raise ValueError("Las dimensiones del cuadro deben ser positivas")
        timestamp = datetime.now().astimezone().isoformat()
        with self.connection() as connection:
            connection.execute(
                """
                UPDATE work_zones
                SET is_active = 0, deactivated_at = ?
                WHERE camera_config_id = ? AND is_active = 1
                """,
                (timestamp, camera_id),
            )
            cursor = connection.execute(
                """
                INSERT INTO work_zones (
                    camera_config_id, polygon_json, reference_image_path,
                    frame_width, frame_height, is_active, created_at, deactivated_at
                ) VALUES (?, ?, ?, ?, ?, 1, ?, NULL)
                """,
                (
                    camera_id,
                    json.dumps(points, separators=(",", ":")),
                    reference_image_path,
                    frame_width,
                    frame_height,
                    timestamp,
                ),
            )
            return int(cursor.lastrowid)

    def get_active_zone(self) -> dict[str, object] | None:
        with self.connection() as connection:
            row = connection.execute(
                """
                SELECT id, camera_config_id, polygon_json, reference_image_path,
                       frame_width, frame_height, created_at
                FROM work_zones WHERE is_active = 1
                """
            ).fetchone()
        if row is None:
            return None
        result = dict(row)
        result["polygon"] = json.loads(str(result.pop("polygon_json")))
        return result

    def create_service(
        self,
        work_zone_id: int,
        camera_session_id: str,
        logical_vehicle_id: str,
        tracker_id: int,
        confirmed_at: datetime,
        dwell_seconds: int,
        vehicle_class: str,
        color_name: str | None,
        plate_text: str | None,
        detection_confidence: float,
        plate_confidence: float | None,
    ) -> int:
        try:
            with self.connection() as connection:
                cursor = connection.execute(
                    """
                    INSERT INTO services (
                        work_zone_id, camera_session_id, logical_vehicle_id,
                        tracker_id, confirmed_at, dwell_seconds, vehicle_class,
                        color_name, plate_text, detection_confidence, plate_confidence
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        work_zone_id,
                        camera_session_id,
                        logical_vehicle_id,
                        tracker_id,
                        confirmed_at.astimezone().isoformat(),
                        dwell_seconds,
                        vehicle_class,
                        color_name,
                        plate_text,
                        detection_confidence,
                        plate_confidence,
                    ),
                )
                return int(cursor.lastrowid)
        except sqlite3.IntegrityError as error:
            if "services.camera_session_id, services.logical_vehicle_id" in str(error):
                raise ValueError("El vehiculo ya fue contabilizado") from error
            raise

    def _day(self, date_value: str | None) -> str:
        return date_value or datetime.now().astimezone().date().isoformat()

    def daily_summary(self, date_value: str | None = None) -> dict[str, int | str]:
        day = self._day(date_value)
        with self.connection() as connection:
            automatic = int(
                connection.execute(
                    "SELECT COUNT(*) FROM services WHERE substr(confirmed_at, 1, 10) = ?",
                    (day,),
                ).fetchone()[0]
            )
            adjustment = int(
                connection.execute(
                    """
                    SELECT COALESCE(SUM(delta), 0) FROM manual_adjustments
                    WHERE substr(occurred_at, 1, 10) = ?
                    """,
                    (day,),
                ).fetchone()[0]
            )
        return {
            "date": day,
            "automatic_count": automatic,
            "adjustment_total": adjustment,
            "final_total": automatic + adjustment,
        }

    def create_adjustment(self, delta: int, reason: str) -> int:
        if delta not in {-1, 1}:
            raise ValueError("El ajuste debe ser +1 o -1")
        if not reason.strip():
            raise ValueError("El motivo es obligatorio")
        occurred_at = datetime.now().astimezone().isoformat()
        day = occurred_at[:10]
        with self.connection() as connection:
            automatic = int(
                connection.execute(
                    "SELECT COUNT(*) FROM services WHERE substr(confirmed_at, 1, 10) = ?",
                    (day,),
                ).fetchone()[0]
            )
            adjustment = int(
                connection.execute(
                    """
                    SELECT COALESCE(SUM(delta), 0) FROM manual_adjustments
                    WHERE substr(occurred_at, 1, 10) = ?
                    """,
                    (day,),
                ).fetchone()[0]
            )
            if automatic + adjustment + delta < 0:
                raise ValueError("El total no puede quedar debajo de cero")
            cursor = connection.execute(
                """
                INSERT INTO manual_adjustments (occurred_at, delta, reason)
                VALUES (?, ?, ?)
                """,
                (occurred_at, delta, reason.strip()),
            )
            return int(cursor.lastrowid)

    def add_evidence(
        self,
        service_id: int,
        evidence_type: str,
        relative_path: str,
        created_at: datetime,
    ) -> int:
        if evidence_type not in {"vehicle", "plate"}:
            raise ValueError("Tipo de evidencia invalido")
        if not relative_path.strip():
            raise ValueError("La ruta de evidencia es obligatoria")
        with self.connection() as connection:
            cursor = connection.execute(
                """
                INSERT INTO evidence_files (
                    service_id, evidence_type, relative_path, created_at
                ) VALUES (?, ?, ?, ?)
                """,
                (
                    service_id,
                    evidence_type,
                    relative_path,
                    created_at.astimezone().isoformat(),
                ),
            )
            return int(cursor.lastrowid)

    def delete_service(self, service_id: int) -> None:
        with self.connection() as connection:
            connection.execute("DELETE FROM services WHERE id = ?", (service_id,))

    def list_services(self, date_value: str | None = None) -> list[dict[str, object]]:
        day = self._day(date_value)
        with self.connection() as connection:
            rows = connection.execute(
                """
                SELECT s.id, s.confirmed_at, s.dwell_seconds, s.vehicle_class,
                       s.color_name, s.plate_text, s.detection_confidence,
                       s.plate_confidence,
                       (
                           SELECT e.relative_path FROM evidence_files e
                           WHERE e.service_id = s.id AND e.evidence_type = 'vehicle'
                           ORDER BY e.id LIMIT 1
                       ) AS vehicle_image_path,
                       (
                           SELECT e.relative_path FROM evidence_files e
                           WHERE e.service_id = s.id AND e.evidence_type = 'plate'
                           ORDER BY e.id LIMIT 1
                       ) AS plate_image_path
                FROM services s
                WHERE substr(s.confirmed_at, 1, 10) = ?
                ORDER BY s.confirmed_at DESC
                """,
                (day,),
            ).fetchall()
        return [dict(row) for row in rows]

    def list_adjustments(self, date_value: str | None = None) -> list[dict[str, object]]:
        day = self._day(date_value)
        with self.connection() as connection:
            rows = connection.execute(
                """
                SELECT id, occurred_at, delta, reason
                FROM manual_adjustments
                WHERE substr(occurred_at, 1, 10) = ?
                ORDER BY occurred_at DESC
                """,
                (day,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_evidence_path(self, service_id: int, evidence_type: str) -> str | None:
        if evidence_type not in {"vehicle", "plate"}:
            return None
        with self.connection() as connection:
            row = connection.execute(
                """
                SELECT relative_path FROM evidence_files
                WHERE service_id = ? AND evidence_type = ?
                ORDER BY id LIMIT 1
                """,
                (service_id, evidence_type),
            ).fetchone()
        return str(row["relative_path"]) if row else None
