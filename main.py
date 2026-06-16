"""
main.py — FastAPI application entry point for the YouTube Content Factory Dashboard.

Start with:  uvicorn main:app --host 0.0.0.0 --port 8000 --reload
Production:  uvicorn main:app --host 0.0.0.0 --port 8000 --workers 1
"""

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
import uvicorn

from config import HOST, PORT, DEBUG, STATIC_DIR, TEMPLATES_DIR
from api.auth import router as auth_router
from api.routes.dashboard import router as dashboard_router
from api.routes.bulk_run import router as bulk_run_router
from api.routes.calendar import router as calendar_router
from api.routes.library import router as library_router
from api.routes.analytics import router as analytics_router
from api.routes.settings import router as settings_router
from api.websocket import router as ws_router

# ─── App Init ─────────────────────────────────────────────────────────────────
app = FastAPI(
    title="YouTube Content Factory",
    description="Automated 3-channel YouTube Shorts production system",
    version="1.0.0",
    docs_url="/api/docs" if DEBUG else None,
    redoc_url=None,
)

# ─── CORS ─────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Static Files ─────────────────────────────────────────────────────────────
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# ─── Templates ────────────────────────────────────────────────────────────────
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# ─── Routers ──────────────────────────────────────────────────────────────────
app.include_router(auth_router,       prefix="/auth",      tags=["auth"])
app.include_router(dashboard_router,  prefix="/api",       tags=["dashboard"])
app.include_router(bulk_run_router,   prefix="/api",       tags=["bulk_run"])
app.include_router(calendar_router,   prefix="/api",       tags=["calendar"])
app.include_router(library_router,    prefix="/api",       tags=["library"])
app.include_router(analytics_router,  prefix="/api",       tags=["analytics"])
app.include_router(settings_router,   prefix="/api",       tags=["settings"])
app.include_router(ws_router,                              tags=["websocket"])

# ─── Page Routes (HTML) ───────────────────────────────────────────────────────
@app.get("/")
async def root():
    return RedirectResponse(url="/dashboard")

@app.get("/login")
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.get("/dashboard")
async def dashboard_page(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request})

@app.get("/bulk-run")
async def bulk_run_page(request: Request):
    return templates.TemplateResponse("bulk_run.html", {"request": request})

@app.get("/calendar")
async def calendar_page(request: Request):
    return templates.TemplateResponse("calendar.html", {"request": request})

@app.get("/analytics")
async def analytics_page(request: Request):
    return templates.TemplateResponse("analytics.html", {"request": request})

@app.get("/library")
async def library_page(request: Request):
    return templates.TemplateResponse("library.html", {"request": request})

@app.get("/settings")
async def settings_page(request: Request):
    return templates.TemplateResponse("settings.html", {"request": request})

# ─── Startup / Shutdown Events ────────────────────────────────────────────────
@app.on_event("startup")
async def on_startup():
    from modules.logger import get_logger
    log = get_logger("main")
    log.info("🎬 YouTube Content Factory Dashboard started")
    # Ensure log directories exist
    from config import LOGS_DIR, DATA_DIR
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)

@app.on_event("shutdown")
async def on_shutdown():
    from modules.logger import get_logger
    log = get_logger("main")
    log.info("Dashboard shutting down")

# ─── Entry Point ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=HOST,
        port=PORT,
        reload=DEBUG,
        workers=1,
    )
