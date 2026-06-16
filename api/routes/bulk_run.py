"""
api/routes/bulk_run.py — Start, stop, and monitor bulk generation runs.

The bulk run executes as a decoupled background subprocess (python bulk_run.py).
"""

import asyncio
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel

from api.auth import require_auth
from api.websocket import broadcaster
from config import DATA_DIR, CHANNEL_NAMES

router = APIRouter()

# ─── Global state for the running process ─────────────────────────────────────
_bulk_process: subprocess.Popen | None = None

# ─── Models ───────────────────────────────────────────────────────────────────
class GenerateRequest(BaseModel):
    month: str | None = None
    custom_count: int | None = None

# ─── Helpers ──────────────────────────────────────────────────────────────────
def _state_path() -> Path:
    return DATA_DIR / "run_state.json"

def _load_state() -> dict:
    p = _state_path()
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:
            pass
    return {}

def _save_state(state: dict):
    _state_path().write_text(json.dumps(state, indent=2))

async def _tail_process_logs(proc: subprocess.Popen):
    """Wait for the process to finish and broadcast status"""
    global _bulk_process
    
    # Non-blocking wait using asyncio
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, proc.wait)
    
    state = _load_state()
    if proc.returncode == 0:
        state["status"] = "complete"
        await broadcaster.broadcast_status("complete")
    elif proc.returncode == -15: # Terminated
        state["status"] = "stopped"
        await broadcaster.broadcast_status("stopped")
    else:
        state["status"] = "error"
        await broadcaster.broadcast_status("error")
        
    _save_state(state)
    _bulk_process = None

def _start_generation(month: str, count: int | None, resume: bool, background_tasks: BackgroundTasks):
    global _bulk_process
    state = _load_state()

    if _bulk_process and _bulk_process.poll() is None:
        raise HTTPException(status_code=409, detail="A bulk run is already in progress.")

    cmd = ["python", "bulk_run.py", "--month", month]
    if resume:
        cmd.append("--resume")
    elif count is not None:
        cmd.extend(["--count", str(count)])

    # Initialize state if not resuming
    if not resume:
        state = {
            "month": month,
            "stage": 0,
            "completed_stages": [],
            "completed_shorts": {ch: 0 for ch in CHANNEL_NAMES},
            "total_shorts": (count or 60) * len(CHANNEL_NAMES),
            "started_at": datetime.now(timezone.utc).isoformat(),
            "last_checkpoint": None,
            "status": "running",
            "errors": [],
        }
    else:
        state["status"] = "running"

    _save_state(state)

    try:
        # We run it in the workspace root, which is the parent of api
        workspace_dir = Path(__file__).resolve().parent.parent.parent
        _bulk_process = subprocess.Popen(
            cmd,
            cwd=workspace_dir,
            stdout=subprocess.DEVNULL, # Could pipe to log file later
            stderr=subprocess.DEVNULL
        )
        background_tasks.add_task(_tail_process_logs, _bulk_process)
    except Exception as e:
        state["status"] = "error"
        _save_state(state)
        raise HTTPException(status_code=500, detail=f"Failed to start bulk run: {e}")

# ─── Routes ───────────────────────────────────────────────────────────────────

@router.post("/generate/{size}")
async def generate_content(size: str, body: GenerateRequest, background_tasks: BackgroundTasks, user: dict = Depends(require_auth)):
    month = body.month or datetime.now(timezone.utc).strftime("%Y_%m")
    
    size_map = {
        "test3": 1,
        "test10": 4,   # 12 shorts total
        "test25": 9,   # 27 shorts total
        "month": 60,   # 180 shorts total
    }
    
    if size == "custom":
        if not body.custom_count:
            raise HTTPException(status_code=400, detail="custom_count required for custom size")
        count = body.custom_count
    elif size in size_map:
        count = size_map[size]
    else:
        raise HTTPException(status_code=400, detail="Invalid size parameter")

    _start_generation(month, count, resume=False, background_tasks=background_tasks)
    return {"message": f"Started generating {size} shorts for {month}"}

@router.post("/bulk-run/resume")
async def resume_bulk_run(body: GenerateRequest, background_tasks: BackgroundTasks, user: dict = Depends(require_auth)):
    state = _load_state()
    month = body.month or state.get("month") or datetime.now(timezone.utc).strftime("%Y_%m")
    _start_generation(month, None, resume=True, background_tasks=background_tasks)
    return {"message": "Resumed bulk run"}

@router.post("/bulk-run/stop")
async def stop_bulk_run(user: dict = Depends(require_auth)):
    global _bulk_process
    if _bulk_process and _bulk_process.poll() is None:
        _bulk_process.terminate()
        try:
            _bulk_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _bulk_process.kill()
        
    state = _load_state()
    state["status"] = "stopped"
    _save_state(state)
    await broadcaster.broadcast_status("stopped")
    return {"message": "Bulk run stop signal sent"}

@router.get("/bulk-run/status")
async def get_bulk_run_status(user: dict = Depends(require_auth)):
    return _load_state()

# Keep legacy start/retry routes for backwards compatibility just in case
@router.post("/bulk-run/start")
async def legacy_start(body: GenerateRequest, background_tasks: BackgroundTasks, user: dict = Depends(require_auth)):
    month = body.month or datetime.now(timezone.utc).strftime("%Y_%m")
    _start_generation(month, 60, resume=False, background_tasks=background_tasks)
    return {"message": "Started bulk run"}

@router.post("/bulk-run/retry")
async def legacy_retry(background_tasks: BackgroundTasks, user: dict = Depends(require_auth)):
    state = _load_state()
    month = state.get("month") or datetime.now(timezone.utc).strftime("%Y_%m")
    _start_generation(month, None, resume=True, background_tasks=background_tasks)
    return {"message": "Resumed bulk run"}
