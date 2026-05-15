import os
from dotenv import load_dotenv
load_dotenv(override=True)

import json
import logging
from datetime import datetime
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from backend.scheduler import start_scheduler, stop_scheduler, force_check
from backend.memory_store import get_history, get_flagged_log, get_source_status, save_result
from backend.nlp_connector import run_nlp_check, parse_voice_query, build_voice_response, verify_image
from backend.sms import send_sms_alert

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger("API")

app = FastAPI(title="VoiceGuard AI API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WebSocket connected. Total: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
        logger.info(f"WebSocket disconnected. Total: {len(self.active_connections)}")

    async def broadcast(self, data: dict):
        for connection in self.active_connections.copy():
            try:
                await connection.send_text(json.dumps(data))
            except Exception as e:
                logger.warning(f"Failed to send to WS client, removing: {e}")
                self.active_connections.remove(connection)

manager = ConnectionManager()

@app.on_event("startup")
async def startup_event():
    logger.info("Starting API server...")
    start_scheduler(app, manager)

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Shutting down API server...")
    stop_scheduler()

@app.get("/")
async def root():
    return {
        "project": "VoiceGuard AI",
        "endpoints": [
            "/check-now", "/voice-check", "/history", "/status",
            "/sources-status", "/misinformation-log", "/verify-image",
            "/manual-alert"
        ]
    }

@app.get("/check-now")
async def check_now_route():
    try:
        result = await force_check()
        severity = result.get("severity", "LOW")
        if severity in ["MEDIUM", "HIGH"]:
            send_sms_alert(result)
        return result
    except Exception as e:
        logger.error(f"/check-now failed: {e}")
        return {"error": str(e)}

class VoiceQuery(BaseModel):
    query: str

@app.post("/voice-check")
async def voice_check_route(request: VoiceQuery):
    try:
        result = await run_nlp_check(source="voice")
        intent = await parse_voice_query(request.query)
        voice_response = await build_voice_response(result, intent)
        return {
            "result": result,
            "voice_response": voice_response,
            "intent": intent
        }
    except Exception as e:
        logger.error(f"/voice-check failed: {e}")
        return {"error": str(e)}

@app.get("/history")
async def history_route():
    return get_history()

@app.get("/status")
async def status_route():
    history = get_history()
    last_check = history[0].get("timestamp") if history else None
    current_severity = history[0].get("severity", "LOW") if history else "LOW"
    
    return {
        "server": "running",
        "last_check": last_check,
        "current_severity": current_severity,
        "scheduler": "running",
        "sources": get_source_status()
    }

@app.get("/sources-status")
async def sources_status_route():
    return get_source_status()

@app.get("/misinformation-log")
async def misinformation_log_route():
    return get_flagged_log()

class ImageVerifyReq(BaseModel):
    image_url: str

@app.post("/verify-image")
async def verify_image_route(req: ImageVerifyReq):
    return await verify_image(req.image_url)

class ManualAlertReq(BaseModel):
    disaster_type: str
    location: str
    severity: str

@app.post("/manual-alert")
async def manual_alert_route(req: ManualAlertReq):
    try:
        mock_result = {
            "disaster_type": req.disaster_type,
            "location": req.location,
            "severity": req.severity,
            "advice": "Demo alert triggered manually. Evacuate if necessary.",
            "posts_analyzed": 99,
            "posts_flagged": 0,
            "all_locations": [req.location],
            "sources": {"simulated": 99},
            "timestamp": datetime.now().isoformat(),
            "source": "manual_trigger"
        }
        save_result(mock_result)
        await manager.broadcast({"type": "manual_update", "result": mock_result})
        send_sms_alert(mock_result)
        return {"message": "Alert triggered successfully"}
    except Exception as e:
        logger.error(f"/manual-alert failed: {e}")
        return {"error": str(e)}

@app.websocket("/ws/dashboard")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            # keep alive
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(websocket)
