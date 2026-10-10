from __future__ import annotations

from contextlib import asynccontextmanager
import ipaddress
import re
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from .credentials import save_camera_password
from .database import Database
from .engine import CameraEngine


PROJECT_ROOT = Path(__file__).resolve().parents[2]
WEB_DIR = PROJECT_ROOT / "web"


class CameraPayload(BaseModel):
    host: str = Field(min_length=1, max_length=255)
    port: int = Field(default=554, ge=1, le=65535)
    stream_name: str = Field(default="stream2", pattern="^stream[12]$")
    username: str = Field(min_length=1, max_length=128)
    password: str | None = Field(default=None, max_length=512)

    @field_validator("host")
    @classmethod
    def validate_host(cls, value: str) -> str:
        host = value.strip()
        try:
            ipaddress.ip_address(host)
            return host
        except ValueError:
            pass
        if len(host) > 253 or not re.fullmatch(
            r"(?=.{1,253}$)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)*"
            r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?",
            host,
        ):
            raise ValueError("Ingresá una dirección IP o nombre de host válido")
        return host


class PointPayload(BaseModel):
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)


class ZonePayload(BaseModel):
    points: list[PointPayload] = Field(min_length=3, max_length=32)
    frame_width: int = Field(ge=1)
    frame_height: int = Field(ge=1)


class AdjustmentPayload(BaseModel):
    delta: int
    reason: str = Field(min_length=1, max_length=500)


class InstallationSettingsPayload(BaseModel):
    max_concurrent_vehicles: int = Field(ge=1)


def create_app(database_path: Path | None = None, start_engine: bool = True) -> FastAPI:
    database = Database(database_path or PROJECT_ROOT / "data" / "detecta_images.db")
    database.migrate()
    engine = CameraEngine(database)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        if start_engine:
            engine.start()
        yield
        engine.stop()

    app = FastAPI(title="DetectaImages", version="0.1.0", lifespan=lifespan)
    app.state.database = database
    app.state.engine = engine

    @app.get("/")
    def index():
        return FileResponse(WEB_DIR / "index.html")

    @app.get("/api/status")
    def status():
        return engine.status()

    @app.get("/api/summary")
    def summary(date: str | None = Query(default=None)):
        return database.daily_summary(date)

    @app.get("/api/activity")
    def activity(date: str | None = Query(default=None)):
        return {
            "services": database.list_services(date),
            "adjustments": database.list_adjustments(date),
        }

    @app.get("/api/camera")
    def get_camera():
        config = database.get_camera_config()
        if config is None:
            return None
        config.pop("credential_key", None)
        return config

    @app.get("/api/settings")
    def get_settings():
        return {
            "max_concurrent_vehicles": database.get_max_concurrent_vehicles()
        }

    @app.put("/api/settings")
    def save_settings(payload: InstallationSettingsPayload):
        value = database.save_max_concurrent_vehicles(
            payload.max_concurrent_vehicles
        )
        if start_engine:
            engine.restart()
        return {"max_concurrent_vehicles": value, "saved": True}

    @app.put("/api/camera")
    def save_camera(payload: CameraPayload):
        existing = database.get_camera_config()
        credential_key = str(existing["credential_key"]) if existing else "tapo-main"
        if payload.password:
            save_camera_password(credential_key, payload.password)
        elif existing is None:
            raise HTTPException(422, "La contraseña es obligatoria al configurar la cámara")
        database.save_camera_config(
            payload.host, payload.port, payload.stream_name, payload.username, credential_key
        )
        if start_engine:
            engine.restart()
        return {"saved": True}

    @app.get("/api/zone")
    def get_zone():
        return database.get_active_zone()

    @app.put("/api/zone")
    def save_zone(payload: ZonePayload):
        camera = database.get_camera_config()
        if camera is None:
            raise HTTPException(409, "Configurá la cámara antes de guardar la zona")
        zone_id = database.replace_active_zone(
            int(camera["id"]),
            [(point.x, point.y) for point in payload.points],
            None,
            payload.frame_width,
            payload.frame_height,
        )
        if start_engine:
            engine.restart()
        return {"id": zone_id, "saved": True}

    @app.post("/api/adjustments", status_code=201)
    def create_adjustment(payload: AdjustmentPayload):
        try:
            adjustment_id = database.create_adjustment(payload.delta, payload.reason)
        except ValueError as error:
            raise HTTPException(422, str(error)) from error
        return {"id": adjustment_id, "summary": database.daily_summary()}

    @app.get("/api/video")
    def video():
        def frames():
            import time

            while True:
                jpeg = engine.latest_jpeg()
                if jpeg:
                    yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n"
                time.sleep(0.1)

        return StreamingResponse(
            frames(), media_type="multipart/x-mixed-replace; boundary=frame"
        )

    @app.get("/api/evidence/{service_id}/{evidence_type}")
    def evidence(service_id: int, evidence_type: str):
        if evidence_type not in {"vehicle", "plate"}:
            raise HTTPException(404, "Evidencia no encontrada")
        relative_path = database.get_evidence_path(service_id, evidence_type)
        if relative_path is None:
            raise HTTPException(404, "Evidencia no encontrada")
        path = (PROJECT_ROOT / relative_path).resolve()
        data_root = (PROJECT_ROOT / "data" / "evidence").resolve()
        if data_root not in path.parents or not path.is_file():
            raise HTTPException(404, "Evidencia no encontrada")
        return FileResponse(path)

    app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")
    return app
