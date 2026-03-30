from __future__ import annotations

import os
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None

BASE_DIR = Path(__file__).resolve().parent
if load_dotenv is not None:
    load_dotenv(BASE_DIR / '.env')


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {'1', 'true', 'yes', 'on'}


def _env_csv(name: str, default: str = '') -> list[str]:
    raw = os.getenv(name, default)
    return [item.strip() for item in raw.split(',') if item.strip()]


SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-me')
FLASK_DEBUG = _env_bool('FLASK_DEBUG', True)
FLASK_HOST = os.getenv('FLASK_HOST', '0.0.0.0')
FLASK_PORT = int(os.getenv('FLASK_PORT', '5000'))

DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_PORT = int(os.getenv('DB_PORT', '3306'))
DB_USER = os.getenv('DB_USER', 'root')
DB_PASSWORD = os.getenv('DB_PASSWORD', 'root')
DB_NAME = os.getenv('DB_NAME', 'cast_project')

PANEL_BASE_URL = os.getenv('PANEL_BASE_URL', 'http://localhost:5007').rstrip('/')
PANEL_HOST = os.getenv('PANEL_HOST', '0.0.0.0')
PANEL_PORT = int(os.getenv('PANEL_PORT', '5007'))
PANEL_ALLOW_ORIGINS = _env_csv(
    'PANEL_ALLOW_ORIGINS',
    'localhost:5007,127.0.0.1:5007,localhost:5000,127.0.0.1:5000',
)
