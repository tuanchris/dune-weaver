import os
import time
import threading
import subprocess
import platform
import logging
import json
from datetime import datetime
from pathlib import Path

# Configure logging
logger = logging.getLogger(__name__)

class WebcamController:
    def __init__(self):
        self.timelapse_dir = './timelapses'
        self.current_session_dir = None
        self.is_capturing = False
        self.capture_thread = None
        self.interval = 5  # Default interval in seconds
        self.auto_mode = False  # Auto start/stop with patterns
        self.selected_camera = '/dev/video0'  # Default camera
        self.available_cameras = []
        self.lock = threading.Lock()
        
        # Create timelapses directory if it doesn't exist
        os.makedirs(self.timelapse_dir, exist_ok=True)
        
        # Detect platform
        self.platform = platform.system()
        logger.info(f"Detected platform: {self.platform}")
        
        # Scan for available cameras
        self.scan_cameras()
    
    def scan_cameras(self):
        """Scan for available camera devices based on platform"""
        self.available_cameras = []
        
        try:
            if self.platform == 'Linux':
                # On Linux, look for video devices in /dev
                video_devices = [f"/dev/video{i}" for i in range(10) if os.path.exists(f"/dev/video{i}")]
                self.available_cameras = video_devices
            elif self.platform == 'Windows':
                # On Windows, use more reliable method to detect cameras
                try:
                    # First try using ffmpeg to list devices
                    result = subprocess.run(
                        ['ffmpeg', '-list_devices', 'true', '-f', 'dshow', '-i', 'dummy'],
                        stderr=subprocess.PIPE,
                        stdout=subprocess.PIPE,
                        text=True,
                        encoding='utf-8',
                        errors='replace',
                        creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
                    )
                    
                    lines = result.stderr.split('\n')
                    in_video_devices = False
                    for line in lines:
                        if 'DirectShow video devices' in line:
                            in_video_devices = True
                            continue
                        if in_video_devices and 'DirectShow audio devices' in line:
                            in_video_devices = False
                            break
                        if in_video_devices and '"' in line:
                            try:
                                camera_name = line.split('"')[1]
                                if camera_name and camera_name.strip():
                                    self.available_cameras.append(camera_name)
                            except IndexError:
                                pass
                except Exception as e:
                    logger.warning(f"Error using ffmpeg to list devices: {str(e)}")
                    
                # If no cameras found, try alternative method
                if not self.available_cameras:
                    try:
                        # Try using PowerShell to get camera info
                        ps_command = "Get-CimInstance Win32_PnPEntity | Where-Object {$_.PNPClass -eq 'Camera'} | Select-Object Name | ConvertTo-Json"
                        result = subprocess.run(
                            ['powershell', '-Command', ps_command],
                            capture_output=True,
                            text=True
                        )
                        
                        if result.stdout.strip():
                            try:
                                cameras_data = json.loads(result.stdout)
                                # Handle both single camera and multiple cameras
                                if isinstance(cameras_data, dict):
                                    camera_name = cameras_data.get('Name')
                                    if camera_name:
                                        self.available_cameras.append(camera_name)
                                elif isinstance(cameras_data, list):
                                    for camera in cameras_data:
                                        camera_name = camera.get('Name')
                                        if camera_name:
                                            self.available_cameras.append(camera_name)
                            except json.JSONDecodeError:
                                pass
                    except Exception as e:
                        logger.warning(f"Error using PowerShell to list cameras: {str(e)}")
            elif self.platform == 'Darwin':  # macOS
                # On macOS, use ffmpeg with AVFoundation
                result = subprocess.run(
                    ['ffmpeg', '-f', 'avfoundation', '-list_devices', 'true', '-i', ''],
                    stderr=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    text=True,
                    encoding='utf-8',
                    errors='replace'
                )
                
                lines = result.stderr.split('\n')
                for line in lines:
                    if '[AVFoundation input device]' in line and 'video' in line.lower():
                        parts = line.split(']')
                        if len(parts) > 1:
                            camera_name = parts[1].strip()
                            self.available_cameras.append(camera_name)
        except Exception as e:
            logger.error(f"Error scanning for cameras: {str(e)}")
        
        # If no cameras found, add a default one
        if not self.available_cameras:
            if self.platform == 'Linux':
                self.available_cameras = ['/dev/video0']
            elif self.platform == 'Windows':
                self.available_cameras = ['0']  # Use index instead of name for Windows
            elif self.platform == 'Darwin':
                self.available_cameras = ['0']  # Use index for macOS too
        
        logger.info(f"Available cameras: {self.available_cameras}")
        return self.available_cameras
    
    def start_timelapse(self, camera=None, interval=None, auto_mode=None):
        """Start timelapse capture"""
        with self.lock:
            if self.is_capturing:
                logger.warning("Timelapse already running")
                return False
            
            # Update settings if provided
            if camera is not None:
                self.selected_camera = camera
            if interval is not None:
                self.interval = float(interval)
            if auto_mode is not None:
                self.auto_mode = bool(auto_mode)
            
            # Create a new session directory with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            self.current_session_dir = os.path.join(self.timelapse_dir, f"timelapse_{timestamp}")
            os.makedirs(self.current_session_dir, exist_ok=True)
            
            # Save session info
            session_info = {
                'start_time': timestamp,
                'camera': self.selected_camera,
                'interval': self.interval,
                'auto_mode': self.auto_mode,
                'platform': self.platform
            }
            
            with open(os.path.join(self.current_session_dir, 'session_info.json'), 'w') as f:
                json.dump(session_info, f)
            
            # Start capture thread
            self.is_capturing = True
            self.capture_thread = threading.Thread(target=self._capture_loop)
            self.capture_thread.daemon = True
            self.capture_thread.start()
            
            logger.info(f"Started timelapse capture with camera {self.selected_camera}, interval {self.interval}s")
            return True
    
    def stop_timelapse(self):
        """Stop timelapse capture"""
        with self.lock:
            if not self.is_capturing:
                logger.warning("No timelapse running")
                return False
            
            self.is_capturing = False
            if self.capture_thread:
                self.capture_thread.join(timeout=2.0)
            
            logger.info("Stopped timelapse capture")
            return True
    
    def _capture_loop(self):
        """Background thread for capturing images at intervals"""
        frame_count = 0
        
        while self.is_capturing:
            try:
                frame_count += 1
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                output_file = os.path.join(self.current_session_dir, f"frame_{frame_count:06d}_{timestamp}.jpg")
                
                self._capture_frame(output_file)
                
                # Sleep for the interval
                time.sleep(self.interval)
            except Exception as e:
                logger.error(f"Error in capture loop: {str(e)}")
                time.sleep(1)  # Sleep briefly to avoid tight loop on error
    
    def _capture_frame(self, output_file):
        """Capture a single frame using the appropriate method for the platform"""
        try:
            if self.platform == 'Linux':
                # Try v4l2-ctl first (for Raspberry Pi)
                try:
                    subprocess.run([
                        'v4l2-ctl',
                        '--device', self.selected_camera,
                        '--set-fmt-video=width=1280,height=720,pixelformat=MJPG',
                        '--stream-mmap',
                        '--stream-count=1',
                        f'--stream-to={output_file}'
                    ], check=True, timeout=5)
                    return
                except (subprocess.SubprocessError, FileNotFoundError) as e:
                    logger.warning(f"v4l2-ctl failed, falling back to ffmpeg: {str(e)}")
                
                # Fallback to ffmpeg
                subprocess.run([
                    'ffmpeg',
                    '-f', 'v4l2',
                    '-i', self.selected_camera,
                    '-frames:v', '1',
                    '-y',
                    output_file
                ], check=True, timeout=5, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                
            elif self.platform == 'Windows':
                # On Windows, try multiple approaches
                try:
                    # First try with DirectShow using camera name
                    if self.selected_camera.isdigit():
                        # If it's just a number, use it as an index
                        video_input = f"video={self.selected_camera}"
                    else:
                        # Otherwise use the full name
                        video_input = f"video={self.selected_camera}"
                    
                    # Create directory if it doesn't exist
                    os.makedirs(os.path.dirname(output_file), exist_ok=True)
                    
                    # Use subprocess with shell=True for Windows
                    cmd = [
                        'ffmpeg',
                        '-f', 'dshow',
                        '-i', video_input,
                        '-frames:v', '1',
                        '-y',
                        output_file
                    ]
                    
                    # Add creation flags to hide console window
                    creation_flags = 0
                    if hasattr(subprocess, 'CREATE_NO_WINDOW'):
                        creation_flags = subprocess.CREATE_NO_WINDOW
                    
                    process = subprocess.run(
                        cmd,
                        check=True,
                        timeout=5,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        creationflags=creation_flags
                    )
                    
                    # Check if file was created
                    if not os.path.exists(output_file) or os.path.getsize(output_file) == 0:
                        raise Exception("Failed to capture frame - output file is empty or missing")
                    
                except Exception as e:
                    logger.warning(f"DirectShow capture failed: {str(e)}, trying alternative method")
                    
                    # Try using index-based approach
                    try:
                        # Try using index-based approach with vfwcap
                        index = "0"
                        if self.selected_camera.isdigit():
                            index = self.selected_camera
                        
                        subprocess.run([
                            'ffmpeg',
                            '-f', 'vfwcap',
                            '-i', index,
                            '-frames:v', '1',
                            '-y',
                            output_file
                        ], check=True, timeout=5, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                        creationflags=creation_flags)
                    except Exception as e2:
                        logger.error(f"All Windows capture methods failed: {str(e2)}")
                        raise
                
            elif self.platform == 'Darwin':  # macOS
                # On macOS, use ffmpeg with AVFoundation
                device_index = self.selected_camera.split(':')[0] if ':' in self.selected_camera else '0'
                subprocess.run([
                    'ffmpeg',
                    '-f', 'avfoundation',
                    '-i', f'{device_index}',
                    '-frames:v', '1',
                    '-y',
                    output_file
                ], check=True, timeout=5, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            logger.debug(f"Captured frame to {output_file}")
        except Exception as e:
            logger.error(f"Error capturing frame: {str(e)}")
            raise
    
    def create_video(self, session_dir=None, fps=10):
        """Create a video from the captured frames"""
        if session_dir is None:
            session_dir = self.current_session_dir
        
        if not session_dir or not os.path.exists(session_dir):
            logger.error(f"Session directory does not exist: {session_dir}")
            return False
        
        try:
            # Get all jpg files in the directory
            frames = sorted([f for f in os.listdir(session_dir) if f.endswith('.jpg')])
            
            if not frames:
                logger.error(f"No frames found in {session_dir}")
                return False
            
            # Create output video filename
            output_video = os.path.join(session_dir, f"timelapse_{Path(session_dir).name}.mp4")
            
            # Use ffmpeg to create video
            subprocess.run([
                'ffmpeg',
                '-framerate', str(fps),
                '-pattern_type', 'glob',
                '-i', os.path.join(session_dir, 'frame_*.jpg'),
                '-c:v', 'libx264',
                '-pix_fmt', 'yuv420p',
                '-y',
                output_video
            ], check=True, timeout=60)
            
            logger.info(f"Created timelapse video: {output_video}")
            return {
                'success': True,
                'video_path': output_video,
                'frame_count': len(frames)
            }
        except Exception as e:
            logger.error(f"Error creating video: {str(e)}")
            return False
    
    def list_sessions(self):
        """List all timelapse sessions"""
        sessions = []
        
        try:
            for item in os.listdir(self.timelapse_dir):
                session_path = os.path.join(self.timelapse_dir, item)
                if os.path.isdir(session_path) and item.startswith('timelapse_'):
                    # Get session info
                    info_file = os.path.join(session_path, 'session_info.json')
                    info = {}
                    if os.path.exists(info_file):
                        with open(info_file, 'r') as f:
                            info = json.load(f)
                    
                    # Count frames
                    frames = [f for f in os.listdir(session_path) if f.endswith('.jpg')]
                    frame_count = len(frames)
                    
                    # Check if video exists
                    video_file = os.path.join(session_path, f"timelapse_{item}.mp4")
                    has_video = os.path.exists(video_file)
                    
                    # Get thumbnail (first frame)
                    thumbnail = None
                    if frames:
                        thumbnail = os.path.join(item, sorted(frames)[0])
                    
                    sessions.append({
                        'id': item,
                        'path': session_path,
                        'info': info,
                        'frame_count': frame_count,
                        'has_video': has_video,
                        'thumbnail': thumbnail
                    })
        except Exception as e:
            logger.error(f"Error listing sessions: {str(e)}")
        
        # Sort by start time (newest first)
        sessions.sort(key=lambda x: x['id'], reverse=True)
        return sessions
    
    def get_session_frames(self, session_id):
        """Get all frames for a session"""
        session_path = os.path.join(self.timelapse_dir, session_id)
        if not os.path.exists(session_path):
            return []
        
        frames = []
        try:
            for item in os.listdir(session_path):
                if item.endswith('.jpg') and item.startswith('frame_'):
                    frames.append({
                        'path': os.path.join(session_id, item),
                        'filename': item
                    })
        except Exception as e:
            logger.error(f"Error getting session frames: {str(e)}")
        
        # Sort by frame number
        frames.sort(key=lambda x: x['filename'])
        return frames
    
    def get_status(self):
        """Get current timelapse status"""
        with self.lock:
            return {
                'is_capturing': self.is_capturing,
                'current_session': self.current_session_dir.split('/')[-1] if self.current_session_dir else None,
                'interval': self.interval,
                'auto_mode': self.auto_mode,
                'selected_camera': self.selected_camera,
                'available_cameras': self.available_cameras
            }
    
    def pattern_started(self):
        """Notify that a pattern has started (for auto mode)"""
        if self.auto_mode and not self.is_capturing:
            logger.info("Auto-starting timelapse due to pattern start")
            self.start_timelapse()
    
    def pattern_stopped(self):
        """Notify that a pattern has stopped (for auto mode)"""
        if self.auto_mode and self.is_capturing:
            logger.info("Auto-stopping timelapse due to pattern stop")
            self.stop_timelapse()

# Create a singleton instance
webcam_controller = WebcamController() 