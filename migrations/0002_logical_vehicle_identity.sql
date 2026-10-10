-- Rollback: restore the pre-migration SQLite backup. SQLite cannot remove the
-- added column without rebuilding the services table.
BEGIN IMMEDIATE;

CREATE TABLE installation_settings (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    max_concurrent_vehicles INTEGER NOT NULL
        CHECK (max_concurrent_vehicles >= 1),
    updated_at TEXT NOT NULL
);

INSERT INTO installation_settings (id, max_concurrent_vehicles, updated_at)
VALUES (1, 2, datetime('now'));

ALTER TABLE services ADD COLUMN logical_vehicle_id TEXT;

UPDATE services
SET logical_vehicle_id = 'legacy-' || id
WHERE logical_vehicle_id IS NULL;

CREATE UNIQUE INDEX ux_services_session_logical_vehicle
    ON services(camera_session_id, logical_vehicle_id);

CREATE TRIGGER services_logical_vehicle_required
BEFORE INSERT ON services
WHEN NEW.logical_vehicle_id IS NULL OR length(trim(NEW.logical_vehicle_id)) = 0
BEGIN
    SELECT RAISE(ABORT, 'logical_vehicle_id is required');
END;

COMMIT;
