-- Rollback: restore the SQLite backup created before applying this migration.
PRAGMA foreign_keys = OFF;
BEGIN IMMEDIATE;

CREATE TABLE services_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    work_zone_id INTEGER NOT NULL,
    camera_session_id TEXT NOT NULL CHECK (length(camera_session_id) > 0),
    tracker_id INTEGER NOT NULL CHECK (tracker_id >= 0),
    confirmed_at TEXT NOT NULL,
    dwell_seconds INTEGER NOT NULL CHECK (dwell_seconds >= 1),
    vehicle_class TEXT NOT NULL CHECK (length(vehicle_class) > 0),
    color_name TEXT,
    plate_text TEXT,
    detection_confidence REAL NOT NULL CHECK (detection_confidence BETWEEN 0 AND 1),
    plate_confidence REAL CHECK (plate_confidence BETWEEN 0 AND 1),
    logical_vehicle_id TEXT NOT NULL CHECK (length(trim(logical_vehicle_id)) > 0),
    FOREIGN KEY (work_zone_id) REFERENCES work_zones(id),
    UNIQUE (camera_session_id, logical_vehicle_id)
);

INSERT INTO services_new (
    id, work_zone_id, camera_session_id, tracker_id, confirmed_at,
    dwell_seconds, vehicle_class, color_name, plate_text,
    detection_confidence, plate_confidence, logical_vehicle_id
)
SELECT
    id, work_zone_id, camera_session_id, tracker_id, confirmed_at,
    dwell_seconds, vehicle_class, color_name, plate_text,
    detection_confidence, plate_confidence, logical_vehicle_id
FROM services;

DROP TABLE services;
ALTER TABLE services_new RENAME TO services;

CREATE INDEX ix_services_confirmed_at ON services(confirmed_at);
CREATE INDEX ix_services_work_zone_id ON services(work_zone_id);

COMMIT;
PRAGMA foreign_keys = ON;
