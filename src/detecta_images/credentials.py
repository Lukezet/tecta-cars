from __future__ import annotations

import keyring


SERVICE_NAME = "DetectaImages"


def save_camera_password(credential_key: str, password: str) -> None:
    if not password:
        raise ValueError("La contraseña no puede estar vacia")
    keyring.set_password(SERVICE_NAME, credential_key, password)


def get_camera_password(credential_key: str) -> str | None:
    return keyring.get_password(SERVICE_NAME, credential_key)

