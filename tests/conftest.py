import os


# Test-only defaults keep collection deterministic without weakening production settings.
os.environ.setdefault("SECRET_KEY", "pytest-only-secret-key")
os.environ.setdefault("DB_USER", "pytest-only-database-user")
os.environ.setdefault("DB_PASSWORD", "pytest-only-database-password")
