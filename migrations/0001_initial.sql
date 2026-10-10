BEGIN IMMEDIATE;

CREATE TABLE camera_configs (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    host TEXT NOT NULL CHECK (length(trim(host)) > 0),
    port INTEGER NOT NULL CHECK (port BETWEEN 1 AND 65535),
    stream_name TEXT NOT NULL CHECK (stream_name IN ('stream1', 'stream2')),
    username TEXT NOT NULL CHECK (length(trim(username)) > 0),
    credential_key TEXT NOT NULL CHECK (length(trim(credential_key)) > 0),
    updated_at TEXT NOT NULL
);

CREATE TABLE work_zones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    camera_config_id INTEGER NOT NULL,
    polygon_json TEXT NOT NULL CHECK (json_valid(polygon_json)),
    reference_image_path TEXT,
    frame_width INTEGER NOT NULL CHECK (frame_width > 0),
    frame_height INTEGER NOT NULL CHECK (frame_height > 0),
    is_active INTEGER NOT NULL CHECK (is_active IN (0, 1)),
    created_at TEXT NOT NULL,
    deactivated_at TEXT,
    FOREIGN KEY (camera_config_id) REFERENCES camera_configs(id)
);

CREATE UNIQUE INDEX ux_work_zones_one_active
    ON work_zones(camera_config_id)
    WHERE is_active = 1;

CREATE TABLE services (
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
    FOREIGN KEY (work_zone_id) REFERENCES work_zones(id),
    UNIQUE (camera_session_id, tracker_id)
);

CREATE INDEX ix_services_confirmed_at ON services(confirmed_at);
CREATE INDEX ix_services_work_zone_id ON services(work_zone_id);

CREATE TABLE evidence_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    service_id INTEGER NOT NULL,
    evidence_type TEXT NOT NULL CHECK (evidence_type IN ('vehicle', 'plate')),
    relative_path TEXT NOT NULL CHECK (length(relative_path) > 0),
    created_at TEXT NOT NULL,
    FOREIGN KEY (service_id) REFERENCES services(id) ON DELETE CASCADE
);

CREATE INDEX ix_evidence_files_service_id ON evidence_files(service_id);

CREATE TABLE manual_adjustments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    occurred_at TEXT NOT NULL,
    delta INTEGER NOT NULL CHECK (delta IN (-1, 1)),
    reason TEXT NOT NULL CHECK (length(trim(reason)) > 0)
);

CREATE INDEX ix_manual_adjustments_occurred_at
    ON manual_adjustments(occurred_at);

COMMIT;
