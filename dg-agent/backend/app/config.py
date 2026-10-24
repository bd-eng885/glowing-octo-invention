"""Environment-based configuration. No secrets are hard-coded here."""
from __future__ import annotations

import os
import secrets
from dataclasses import dataclass, field
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _bool(name: str, default: bool) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class Settings:
    database_url: str = field(default_factory=lambda: os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'dg_agent.db'}"))
    # A random secret is generated per process if none is configured. This is safe
    # (tokens just stop validating on restart) but production MUST set JWT_SECRET.
    jwt_secret: str = field(default_factory=lambda: os.getenv("JWT_SECRET") or secrets.token_urlsafe(48))
    jwt_ttl_minutes: int = field(default_factory=lambda: int(os.getenv("JWT_TTL_MINUTES", "480")))
    storage_dir: Path = field(default_factory=lambda: Path(os.getenv("STORAGE_DIR", str(BASE_DIR / "storage"))))
    max_upload_mb: int = field(default_factory=lambda: int(os.getenv("MAX_UPLOAD_MB", "20")))
    ocr_enabled: bool = field(default_factory=lambda: _bool("OCR_ENABLED", True))
    llm_provider: str = field(default_factory=lambda: os.getenv("LLM_PROVIDER", "none"))  # none | anthropic
    llm_model: str = field(default_factory=lambda: os.getenv("LLM_MODEL", "claude-opus-5-5"))
    seed_demo_data: bool = field(default_factory=lambda: _bool("SEED_DEMO_DATA", True))
    demo_users_password: str | None = field(default_factory=lambda: os.getenv("DEMO_USERS_PASSWORD"))
    initial_admin_email: str | None = field(default_factory=lambda: os.getenv("INITIAL_ADMIN_EMAIL"))
    initial_admin_password: str | None = field(default_factory=lambda: os.getenv("INITIAL_ADMIN_PASSWORD"))
    frontend_dist: Path = field(default_factory=lambda: Path(os.getenv("FRONTEND_DIST", str(BASE_DIR.parent / "frontend" / "dist"))))
    # Only the automated test suite sets this: it lets TEST FIXTURE data exercise the
    # "verified" code paths. Never enable it in a deployment.
    test_mode: bool = field(default_factory=lambda: _bool("DG_TEST_MODE", False))
    cors_origins: list[str] = field(default_factory=lambda: [o for o in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",") if o])


settings = Settings()
