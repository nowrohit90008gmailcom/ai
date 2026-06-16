"""
api/routes/library.py — Content library endpoints.

Search, filter, preview, and edit metadata for all generated shorts.
"""

import json
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel

from api.auth import require_auth
from config import CHANNELS, GDRIVE_BASE

router = APIRouter()

# ─── Models ───────────────────────────────────────────────────────────────────
class MetadataUpdateRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[list[str]] = None

# ─── Helpers ──────────────────────────────────────────────────────────────────
def _load_seo(short_dir: Path) -> dict:
    seo_path = short_dir / "seo.json"
    if seo_path.exists():
        return json.loads(seo_path.read_text())
    return {}

def _load_script(short_dir: Path) -> str:
    script_path = short_dir / "script.txt"
    if script_path.exists():
        return script_path.read_text()
    return ""

def _short_info(month: str, channel: str, day: int, short_num: int) -> dict:
    short_dir = GDRIVE_BASE / f"month_{month}" / channel / f"day_{day:02d}_short_{short_num:02d}"
    seo = _load_seo(short_dir)
    has_video = (short_dir / "final_short.mp4").exists()
    has_audio = (short_dir / "audio.mp3").exists()
    has_thumb = (short_dir / "thumbnail.png").exists()

    return {
        "id": f"{month}_{channel}_d{day:02d}_s{short_num:02d}",
        "month": month,
        "channel": channel,
        "channel_name": CHANNELS.get(channel, {}).get("name", channel),
        "day": day,
        "short_num": short_num,
        "title": seo.get("title_clickbait", f"Short {day}-{short_num}"),
        "description": seo.get("description", ""),
        "tags": seo.get("tags", []),
        "hashtags": seo.get("hashtags", []),
        "has_video": has_video,
        "has_audio": has_audio,
        "has_thumbnail": has_thumb,
        "status": "ready" if has_video else "pending",
        "path": str(short_dir),
    }

# ─── Routes ───────────────────────────────────────────────────────────────────
@router.get("/library/{month}")
async def list_library(
    month: str,
    channel: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, le=60),
    user: dict = Depends(require_auth),
):
    """List all shorts for a month with optional filters."""
    channels = [channel] if channel else list(CHANNELS.keys())
    all_shorts = []

    for ch in channels:
        ch_dir = GDRIVE_BASE / f"month_{month}" / ch
        if not ch_dir.exists():
            continue
        for short_dir in sorted(ch_dir.iterdir()):
            if not short_dir.is_dir():
                continue
            try:
                parts = short_dir.name.split("_")  # day_DD_short_NN
                day = int(parts[1])
                short_num = int(parts[3])
                info = _short_info(month, ch, day, short_num)
                if status and info["status"] != status:
                    continue
                all_shorts.append(info)
            except (ValueError, IndexError):
                pass

    total = len(all_shorts)
    start = (page - 1) * per_page
    end   = start + per_page

    return {
        "month": month,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page,
        "shorts": all_shorts[start:end],
    }

@router.get("/library/{month}/{channel}/{day}/{short_num}")
async def get_short_detail(
    month: str, channel: str, day: int, short_num: int,
    user: dict = Depends(require_auth),
):
    """Get full detail for a single short including script."""
    info = _short_info(month, channel, day, short_num)
    short_dir = Path(info["path"])
    info["script"] = _load_script(short_dir)
    return info

@router.patch("/library/{month}/{channel}/{day}/{short_num}/metadata")
async def update_metadata(
    month: str, channel: str, day: int, short_num: int,
    body: MetadataUpdateRequest,
    user: dict = Depends(require_auth),
):
    """Update title / description / tags before posting."""
    short_dir = GDRIVE_BASE / f"month_{month}" / channel / f"day_{day:02d}_short_{short_num:02d}"
    seo_path = short_dir / "seo.json"
    if not seo_path.exists():
        raise HTTPException(status_code=404, detail="SEO file not found for this short")

    seo = json.loads(seo_path.read_text())
    if body.title:
        seo["title_clickbait"] = body.title
    if body.description:
        seo["description"] = body.description
    if body.tags is not None:
        seo["tags"] = body.tags

    seo_path.write_text(json.dumps(seo, indent=2))
    return {"message": "Metadata updated", "seo": seo}
