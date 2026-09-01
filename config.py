"""
Romax Digital – Wallet Pass Creator
config.py – App configuration, folder layout, secret key management
"""

import os
import secrets

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INSTANCE_DIR = os.path.join(BASE_DIR, "instance")
os.makedirs(INSTANCE_DIR, exist_ok=True)

PASSES_DIR = os.path.join(BASE_DIR, "passes")
os.makedirs(PASSES_DIR, exist_ok=True)

APPLE_CERTS_DIR = os.path.join(INSTANCE_DIR, "apple_certs")
os.makedirs(APPLE_CERTS_DIR, exist_ok=True)

GOOGLE_CERTS_DIR = os.path.join(INSTANCE_DIR, "google_certs")
os.makedirs(GOOGLE_CERTS_DIR, exist_ok=True)


def _load_or_create_secret_key() -> str:
    """Persist a random secret key across restarts instead of hardcoding one."""
    key_path = os.path.join(INSTANCE_DIR, "secret_key.txt")
    if os.path.exists(key_path):
        with open(key_path, "r") as f:
            existing = f.read().strip()
            if existing:
                return existing
    key = secrets.token_hex(32)
    with open(key_path, "w") as f:
        f.write(key)
    return key


class Config:
    SECRET_KEY = os.environ.get("ROMAX_SECRET_KEY") or _load_or_create_secret_key()
    SQLALCHEMY_DATABASE_URI = "sqlite:///" + os.path.join(INSTANCE_DIR, "romax.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    MAX_CONTENT_LENGTH = 8 * 1024 * 1024  # 8MB upload limit (cert / logo uploads)


def apple_cert_dir(user_id: int) -> str:
    path = os.path.join(APPLE_CERTS_DIR, str(user_id))
    os.makedirs(path, exist_ok=True)
    return path


def google_cert_dir(user_id: int) -> str:
    path = os.path.join(GOOGLE_CERTS_DIR, str(user_id))
    os.makedirs(path, exist_ok=True)
    return path
