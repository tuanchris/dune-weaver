from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from typing import List, Optional
import os
import logging
from datetime import datetime
from modules.connection import connection_manager
from modules.core import pattern_manager
from modules.core.pattern_manager import parse_theta_rho_file, THETA_RHO_DIR
from modules.core import playlist_manager
from modules.update import update_manager
from modules.core.state import state
from modules import mqtt
import signal
import asyncio
from contextlib import asynccontextmanager
from modules.led.led_interface import LEDInterface
from modules.screen.screen_controller import ScreenController
from modules.led.idle_timeout_manager import idle_timeout_manager
from modules.core.cache_manager import get_cache_path, generate_image_preview, get_pattern_metadata
from modules.core.version_manager import version_manager
from modules.core.log_handler import init_memory_handler, get_memory_handler
from modules.wifi.router import router as wifi_router, captive_portal_router
import json
import base64
import hashlib
import time
import subprocess

# Get log level from environment variable, default to INFO
log_level_str = os.getenv('LOG_LEVEL', 'INFO').upper()
log_level = getattr(logging, log_level_str, logging.INFO)

logging.basicConfig(
    level=log_level,
    format='%(asctime)s - %(name)s:%(lineno)d - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
    ]
)

# Initialize memory log handler for web UI log viewer
# Increased to 5000 entries to support lazy loading in the UI
init_memory_handler(max_entries=5000)

logger = logging.getLogger(__name__)


async def _check_table_is_idle() -> bool:
    """Helper function to check if table is idle."""
    return not state.current_playing_file or state.pause_requested


def _start_idle_led_timeout():
    """Start idle LED timeout if enabled."""
    if not state.dw_led_idle_timeout_enabled or state.dw_led_idle_timeout_minutes <= 0:
        return

    logger.debug(f"Starting idle LED timeout: {state.dw_led_idle_timeout_minutes} minutes")
    idle_timeout_manager.start_idle_timeout(
        timeout_minutes=state.dw_led_idle_timeout_minutes,
        state=state,
        check_idle_callback=_check_table_is_idle
    )


def check_homing_in_progress():
    """Check if homing is in progress and raise exception if so."""
    if state.is_homing:
        raise HTTPException(status_code=409, detail="Cannot perform this action while homing is in progress")


def normalize_file_path(file_path: str) -> str:
    """Normalize file path separators for consistent cross-platform handling."""
    if not file_path:
        return ''
    
    # First normalize path separators
    normalized = file_path.replace('\\', '/')
    
    # Remove only the patterns directory prefix from the beginning, not patterns within the path
    if normalized.startswith('./patterns/'):
        normalized = normalized[11:]
    elif normalized.startswith('patterns/'):
        normalized = normalized[9:]
    
    return normalized

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting Dune Weaver application...")

    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Connect device in background so the web server starts immediately
    async def connect_and_home():
        """Connect to device and perform homing in background."""
        try:
            # Connect without homing first (fast)
            await asyncio.to_thread(connection_manager.connect_device, False)

            # If connected, perform homing in background (unless disabled)
            if state.conn and state.conn.is_connected():
                if not state.home_on_connect:
                    logger.info("Device connected. Home-on-connect is disabled — skipping automatic homing.")
                else:
                    logger.info("Device connected, starting homing in background...")
                    state.is_homing = True
                    try:
                        success = await asyncio.to_thread(connection_manager.home)
                        if not success:
                            logger.warning("Background homing failed or was skipped")
                            # If sensor homing failed, close connection and wait for user action
                            if state.sensor_homing_failed:
                                logger.error("Sensor homing failed - closing connection. User must check sensor or switch to crash homing.")
                                if state.conn:
                                    await asyncio.to_thread(state.conn.close)
                                    state.conn = None
                                return  # Don't proceed with auto-play
                    finally:
                        state.is_homing = False
                        logger.info("Background homing completed")

                # After homing (or skip), check for auto_play mode
                if state.auto_play_enabled and state.auto_play_playlist:
                    logger.info(f"Homing complete, checking auto_play playlist: {state.auto_play_playlist}")
                    try:
                        playlist_exists = playlist_manager.get_playlist(state.auto_play_playlist) is not None
                        if not playlist_exists:
                            logger.warning(f"Auto-play playlist '{state.auto_play_playlist}' not found. Clearing invalid reference.")
                            state.auto_play_playlist = None
                            state.save()
                        elif state.conn and state.conn.is_connected():
                            logger.info(f"Starting auto-play playlist: {state.auto_play_playlist}")
                            asyncio.create_task(playlist_manager.run_playlist(
                                state.auto_play_playlist,
                                pause_time=state.auto_play_pause_time,
                                clear_pattern=state.auto_play_clear_pattern,
                                run_mode=state.auto_play_run_mode,
                                shuffle=state.auto_play_shuffle
                            ))
                    except Exception as e:
                        logger.error(f"Failed to auto-play playlist: {str(e)}")
        except Exception as e:
            logger.warning(f"Failed to auto-connect to serial port: {str(e)}")

    # Start connection/homing in background - doesn't block server startup
    asyncio.create_task(connect_and_home())

    # Initialize LED controller based on saved configuration
    try:
        # Auto-detect provider for backward compatibility with existing installations
        if not state.led_provider or state.led_provider == "none":
            if state.wled_ip:
                state.led_provider = "wled"
                logger.info("Auto-detected WLED provider from existing configuration")

        # Initialize the appropriate controller
        if state.led_provider == "wled" and state.wled_ip:
            state.led_controller = LEDInterface("wled", state.wled_ip)
            logger.info(f"LED controller initialized: WLED at {state.wled_ip}")
        elif state.led_provider == "dw_leds":
            state.led_controller = LEDInterface(
                "dw_leds",
                num_leds=state.dw_led_num_leds,
                gpio_pin=state.dw_led_gpio_pin,
                pixel_order=state.dw_led_pixel_order,
                brightness=state.dw_led_brightness / 100.0,
                speed=state.dw_led_speed,
                intensity=state.dw_led_intensity
            )
            logger.info(f"LED controller initialized: DW LEDs ({state.dw_led_num_leds} LEDs on GPIO{state.dw_led_gpio_pin}, pixel order: {state.dw_led_pixel_order})")

            # Initialize hardware and start idle effect (matches behavior of /set_led_config)
            status = state.led_controller.check_status()
            if status.get("connected", False):
                if state.led_automation_enabled:
                    state.led_controller.effect_idle(state.dw_led_idle_effect)
                    _start_idle_led_timeout()
                    logger.info("DW LEDs hardware initialized and idle effect started")
                else:
                    logger.info("DW LEDs hardware initialized (manual mode, no auto-effect)")
            else:
                error_msg = status.get("error", "Unknown error")
                logger.warning(f"DW LED hardware initialization failed: {error_msg}")
        else:
            state.led_controller = None
            logger.info("LED controller not configured")

        # Save if provider was auto-detected
        if state.led_provider and state.wled_ip:
            state.save()
    except Exception as e:
        logger.warning(f"Failed to initialize LED controller: {str(e)}")
        state.led_controller = None

    # Initialize screen controller for LCD backlight control
    try:
        state.screen_controller = ScreenController()
        if state.screen_controller.available:
            logger.info("Screen controller initialized (backlight control available)")
        else:
            logger.info("Screen controller initialized (no backlight device found)")
    except Exception as e:
        logger.warning(f"Failed to initialize screen controller: {e}")
        state.screen_controller = None

    # Note: auto_play is now handled in connect_and_home() after homing completes

    try:
        mqtt.init_mqtt()
    except Exception as e:
        logger.warning(f"Failed to initialize MQTT: {str(e)}")
    
    # Schedule cache generation check for later (non-blocking startup)
    async def delayed_cache_check():
        """Check and generate cache in background."""
        try:
            logger.info("Starting cache check...")

            from modules.core.cache_manager import is_cache_generation_needed_async, generate_cache_background

            if await is_cache_generation_needed_async():
                logger.info("Cache generation needed, starting background task...")
                asyncio.create_task(generate_cache_background())  # Don't await - run in background
            else:
                logger.info("Cache is up to date, skipping generation")
        except Exception as e:
            logger.warning(f"Failed during cache generation: {str(e)}")

    # Start cache check in background immediately
    asyncio.create_task(delayed_cache_check())

    yield

    # Shutdown
    logger.info("Shutting down Dune Weaver application...")


# NOTE: This is a partial content marker — the tool call had to elide the full body.
