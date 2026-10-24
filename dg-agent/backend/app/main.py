from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from .db import SessionLocal, init_db
from .engines.documents import ocr_available
from .routers import analysis, auth_users, reports, sources
from .seed import seed

log = logging.getLogger("dg")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    with SessionLocal() as db:
        seed(db)
    if not os.getenv("JWT_SECRET"):
        log.warning("JWT_SECRET not set: using an ephemeral secret (tokens invalid after restart).")
    yield


app = FastAPI(title="DG Compliance, Segregation & Emergency Response Assistant", version="0.1.0-mvp", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])
for r in (auth_users.router, sources.router, analysis.router, reports.router):
    app.include_router(r)


@app.get("/api/health")
def health():
    return {"status": "ok", "database": settings.database_url.split(":")[0], "ocr_available": ocr_available(),
            "llm_provider": settings.llm_provider,
            "notice": "Decision-support system. Outputs require review by qualified DG personnel."}


if settings.frontend_dist.is_dir():
    app.mount("/assets", StaticFiles(directory=settings.frontend_dist / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path.startswith("api/"):
            raise HTTPException(404, "Not found")
        f = settings.frontend_dist / path
        if path and f.is_file() and settings.frontend_dist in f.resolve().parents:
            return FileResponse(f)
        return FileResponse(settings.frontend_dist / "index.html")
