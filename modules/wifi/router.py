"""
FastAPI router for WiFi management endpoints.
"""

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import Optional
import logging

from . import manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/wifi", tags=["wifi"])

# Separate router for the captive portal handler (no prefix)
captive_portal_router = APIRouter(tags=["wifi"])


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


# --- Captive portal detection endpoints ---
# These handle the well-known URLs that phones/tablets probe to detect captive portals.
# In hotspot mode, DNS redirects all domains to the Pi, so these probes arrive here.
# We serve a minimal HTML page that redirects to the WiFi setup page.

CAPTIVE_PORTAL_HTML = """<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Dune Weaver - WiFi Setup</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
               display: flex; justify-content: center; align-items: center;
               min-height: 100vh; background: #f8fafc; color: #0f172a; padding: 1rem; }
        .card { background: #ffffff; border: 1px solid #e2e8f0; border-radius: 12px;
                padding: 2rem; max-width: 400px; width: 100%; text-align: center;
                box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
        h1 { font-size: 1.5rem; margin-bottom: 0.5rem; font-weight: 600; }
        p { color: #64748b; margin-bottom: 1.5rem; font-size: 0.9rem; }
        a { display: inline-block; background: #2563eb; color: white; padding: 0.75rem 2rem;
            border-radius: 8px; text-decoration: none; font-weight: 500; }
        a:hover { background: #1d4ed8; }
    </style>
</head>
<body>
    <div class="card">
        <h1>Welcome to Dune Weaver</h1>
        <p>Connect to your home WiFi to get started.</p>
        <a href="/wifi-setup">Set Up WiFi</a>
    </div>
</body>
</html>"""


@captive_portal_router.get("/hotspot-detect.html", response_class=HTMLResponse)
@captive_portal_router.get("/generate_204", response_class=HTMLResponse)
@captive_portal_router.get("/connecttest.txt", response_class=HTMLResponse)
@captive_portal_router.get("/ncsi.txt", response_class=HTMLResponse)
@captive_portal_router.get("/redirect", response_class=HTMLResponse)
@captive_portal_router.get("/canonical.html", response_class=HTMLResponse)
async def captive_portal_detect():
    """Handle captive portal detection probes.

    Phones and tablets check these well-known URLs after connecting to WiFi.
    In hotspot mode, DNS resolves all domains to the Pi, so these probes
    arrive at our server. Returning anything other than the expected response
    triggers the OS to show a captive portal browser.
    """
    return HTMLResponse(content=CAPTIVE_PORTAL_HTML, status_code=200)
