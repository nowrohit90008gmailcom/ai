"""
api/websocket.py — WebSocket endpoint for live bulk-run log streaming.

The frontend connects to ws://<host>/ws/logs and receives JSON messages
as the bulk run progresses. The broadcaster is a simple async pub/sub queue.
"""

import asyncio
import json
from datetime import datetime
from typing import Set

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()

# ─── Connection Manager ───────────────────────────────────────────────────────
class LogBroadcaster:
    def __init__(self):
        self._connections: Set[WebSocket] = set()
        self._history: list[dict] = []   # last 200 messages kept for reconnects

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self._connections.add(ws)
        # Replay recent history to newly connected client
        for msg in self._history[-200:]:
            try:
                await ws.send_json(msg)
            except Exception:
                break

    def disconnect(self, ws: WebSocket):
        self._connections.discard(ws)

    async def broadcast(self, message: dict):
        """Send a message to all connected clients."""
        self._history.append(message)
        if len(self._history) > 500:
            self._history = self._history[-200:]

        dead = set()
        for ws in self._connections:
            try:
                await ws.send_json(message)
            except Exception:
                dead.add(ws)
        for ws in dead:
            self._connections.discard(ws)

    async def broadcast_log(self, level: str, message: str, channel: str = None, stage: int = None):
        """Convenience method to broadcast a structured log entry."""
        payload = {
            "type": "log",
            "level": level,
            "message": message,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "channel": channel,
            "stage": stage,
        }
        await self.broadcast(payload)

    async def broadcast_progress(self, stage: int, stage_name: str, percent: float,
                                  completed: int, total: int):
        """Broadcast a progress update."""
        payload = {
            "type": "progress",
            "stage": stage,
            "stage_name": stage_name,
            "percent": round(percent, 1),
            "completed": completed,
            "total": total,
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }
        await self.broadcast(payload)

    async def broadcast_status(self, status: str):
        """Broadcast overall run status change."""
        payload = {
            "type": "status",
            "status": status,
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }
        await self.broadcast(payload)

# ─── Global singleton ─────────────────────────────────────────────────────────
broadcaster = LogBroadcaster()

# ─── WebSocket endpoint ───────────────────────────────────────────────────────
@router.websocket("/ws/logs")
async def websocket_logs(websocket: WebSocket):
    await broadcaster.connect(websocket)
    try:
        while True:
            # Keep connection alive; client can send ping/pong
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        broadcaster.disconnect(websocket)
    except Exception:
        broadcaster.disconnect(websocket)
