from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlparse

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


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if value is None or not value.strip():
        raise RuntimeError(f'Missing required environment variable: {name}')
    return value


SECRET_KEY = _required_env('SECRET_KEY')
FLASK_DEBUG = _env_bool('FLASK_DEBUG', True)
FLASK_HOST = os.getenv('FLASK_HOST', '0.0.0.0')
FLASK_PORT = int(os.getenv('FLASK_PORT', '5000'))

DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_PORT = int(os.getenv('DB_PORT', '3306'))
DB_USER = _required_env('DB_USER')
DB_PASSWORD = _required_env('DB_PASSWORD')
DB_NAME = os.getenv('DB_NAME', 'cast_project')

PANEL_PUBLIC_BASE = os.getenv('PANEL_PUBLIC_BASE', 'http://localhost:5007').rstrip('/')
PANEL_SERVE_PREFIX = urlparse(PANEL_PUBLIC_BASE).path.rstrip('/')
PANEL_HOST = os.getenv('PANEL_HOST', '0.0.0.0')
PANEL_PORT = int(os.getenv('PANEL_PORT', '5007'))
PANEL_ALLOW_ORIGINS = _env_csv(
    'PANEL_ALLOW_ORIGINS',
    'localhost:5007,127.0.0.1:5007,localhost:5000,127.0.0.1:5000',
)

MF6_EXE = os.getenv('MF6_EXE', '')
NUMERICAL_MAX_CELLS = int(os.getenv('NUMERICAL_MAX_CELLS', os.getenv('MAX_GRID_CELLS', '40000')))
NUMERICAL_SOLVER_TIMEOUT_S = float(
    os.getenv('NUMERICAL_SOLVER_TIMEOUT_S', os.getenv('SOLVER_TIMEOUT_SECONDS', '120'))
)
NUMERICAL_HK_MIN_M_PER_DAY = float(os.getenv('NUMERICAL_HK_MIN_M_PER_DAY', '0.000001'))
NUMERICAL_HK_MAX_M_PER_DAY = float(os.getenv('NUMERICAL_HK_MAX_M_PER_DAY', '1000'))
if NUMERICAL_MAX_CELLS <= 0 or NUMERICAL_SOLVER_TIMEOUT_S <= 0:
    raise RuntimeError('NUMERICAL_MAX_CELLS and NUMERICAL_SOLVER_TIMEOUT_S must be positive')
if NUMERICAL_HK_MIN_M_PER_DAY <= 0 or NUMERICAL_HK_MAX_M_PER_DAY < NUMERICAL_HK_MIN_M_PER_DAY:
    raise RuntimeError('NUMERICAL_HK_MIN_M_PER_DAY and NUMERICAL_HK_MAX_M_PER_DAY define an invalid range')
