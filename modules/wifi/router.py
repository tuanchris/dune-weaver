"""
FastAPI router for WiFi management endpoints.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
import logging

from . import manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/wifi", tags=["wifi"])


class WiFiConnectRequest(BaseModel):
    ssid: str
    password: Optional[str] = ""


class WiFiForgetRequest(BaseModel):
    ssid: str


@router.get("/status")
async def wifi_status():
    """Get current WiFi mode, connection, and IP."""
    return manager.get_wifi_status()


@router.get("/networks")
async def wifi_networks():
    """Scan for available WiFi networks."""
    return manager.scan_networks()


@router.post("/connect")
async def wifi_connect(req: WiFiConnectRequest):
    """Connect to a WiFi network and reboot."""
    if not req.ssid:
        raise HTTPException(status_code=400, detail="SSID is required")

    result = await manager.connect_to_network(req.ssid, req.password or "")
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return result


@router.post("/forget")
async def wifi_forget(req: WiFiForgetRequest):
    """Forget a saved WiFi network."""
    if not req.ssid:
        raise HTTPException(status_code=400, detail="SSID is required")

    result = manager.forget_network(req.ssid)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return result


@router.get("/saved")
async def wifi_saved():
    """Get list of saved WiFi connections."""
    return manager.get_saved_connections()
