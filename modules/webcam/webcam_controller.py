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
        last_capture_time = 0
        
        while self.is_capturing:
            try:
                # Get current time
                current_time = time.time()
                
                # Check if it's time for the next capture
                # This prevents double captures if the previous capture took longer than expected
                if current_time - last_capture_time < self.interval:
                    # Not time yet, sleep a bit and continue
                    time.sleep(0.1)
                    continue
                
                # Update last capture time
                last_capture_time = current_time
                
                # Increment frame count
                frame_count += 1
                
                # Generate timestamp and output filename
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                output_file = os.path.join(self.current_session_dir, f"frame_{frame_count:06d}_{timestamp}.jpg")
                
                # Small delay before capture to ensure camera is ready
                time.sleep(0.2)
                
                # Capture the frame
                logger.debug(f"Capturing frame {frame_count} at {timestamp}")
                self._capture_frame(output_file)
                
                # Small delay after capture to allow camera to reset
                time.sleep(0.2)
                
                # Calculate time elapsed during capture
                elapsed = time.time() - current_time
                
                # Calculate remaining sleep time
                sleep_time = max(0, self.interval - elapsed)
                
                logger.debug(f"Frame {frame_count} captured in {elapsed:.2f}s, sleeping for {sleep_time:.2f}s")
                
                # Sleep for the remaining interval
                if sleep_time > 0:
                    time.sleep(sleep_time)
                
            except Exception as e:
                logger.error(f"Error in capture loop: {str(e)}")
                # Sleep briefly to avoid tight loop on error
                time.sleep(max(1, self.interval / 2))  # Sleep at least 1 second, or half the interval
    
    def _capture_frame(self, output_file):
        """Capture a single frame using the appropriate method for the platform"""
        try:
            if self.platform == 'Linux':
                # On Linux, use v4l2-ctl
                subprocess.run([
                    'v4l2-ctl',
                    '--device', self.selected_camera,
                    '--set-fmt-video=width=1280,height=720,pixelformat=MJPG',
                    '--stream-mmap',
                    '--stream-count=1',
                    '--stream-to=' + output_file
                ], check=True, timeout=10)
            elif self.platform == 'Windows':
                print("Capturing on Windows...")
                # On Windows, use a more direct approach with minimal camera access
                # Set creation flags to avoid console window
                creation_flags = 0x08000000 if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
                
                # Determine the camera index (use 0 as default)
                index = "0"
                if self.selected_camera.isdigit():
                    index = self.selected_camera
                elif ':' in self.selected_camera and self.selected_camera.split(':')[0].isdigit():
                    index = self.selected_camera.split(':')[0]
                
                # Use a single command with explicit options to minimize camera initialization
                # Disable audio to prevent extra device access
                # Use -loglevel quiet to minimize unnecessary operations
                subprocess.run([
                    'ffmpeg',
                    '-loglevel', 'quiet',
                    '-f', 'vfwcap',
                    '-i', index,
                    '-frames:v', '1',
                    '-an',  # Disable audio
                    '-y',
                    output_file
                ], check=True, timeout=15, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                creationflags=creation_flags)
            elif self.platform == 'Darwin':  # macOS
                # On macOS, use ffmpeg with AVFoundation
                device_index = self.selected_camera.split(':')[0] if ':' in self.selected_camera else '0'
                subprocess.run([
                    'ffmpeg',
                    '-loglevel', 'quiet',
                    '-f', 'avfoundation',
                    '-i', f'{device_index}',
                    '-frames:v', '1',
                    '-an',  # Disable audio
                    '-y',
                    output_file
                ], check=True, timeout=15, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            # Verify the file was created successfully
            if not os.path.exists(output_file) or os.path.getsize(output_file) == 0:
                raise Exception(f"Failed to capture frame - output file is empty or missing: {output_file}")
                
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
            
            # Create a temporary file list for ffmpeg
            temp_list_file = os.path.join(session_dir, "frames_list.txt")
            with open(temp_list_file, 'w') as f:
                for frame in frames:
                    # Write just the filename, not the full path
                    f.write(f"file '{frame}'\n")
            
            # Change working directory to the session directory before running ffmpeg
            current_dir = os.getcwd()
            os.chdir(session_dir)
            
            try:
                # Use ffmpeg with the concat demuxer instead of glob patterns
                # Using -r instead of -framerate for better compatibility
                subprocess.run([
                    'ffmpeg',
                    '-f', 'concat',
                    '-safe', '0',
                    '-i', 'frames_list.txt',
                    '-r', str(fps),  # Use -r instead of -framerate
                    '-c:v', 'libx264',
                    '-pix_fmt', 'yuv420p',
                    '-y',
                    Path(output_video).name
                ], check=True, timeout=60)
            finally:
                # Restore the original working directory
                os.chdir(current_dir)
            
            # Clean up the temporary file
            try:
                os.remove(temp_list_file)
            except:
                pass
            
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
            
    def delete_session(self, session_id):
        """Delete a timelapse session"""
        try:
            # Validate session_id to prevent directory traversal
            if not session_id or '..' in session_id or not session_id.startswith('timelapse_'):
                logger.error(f"Invalid session ID: {session_id}")
                return False
            
            session_dir = os.path.join(self.timelapse_dir, session_id)
            
            # Check if directory exists
            if not os.path.exists(session_dir) or not os.path.isdir(session_dir):
                logger.error(f"Session not found: {session_id}")
                return False
            
            # Delete all files in the directory
            for file in os.listdir(session_dir):
                file_path = os.path.join(session_dir, file)
                try:
                    if os.path.isfile(file_path):
                        os.unlink(file_path)
                except Exception as e:
                    logger.error(f"Error deleting file {file_path}: {str(e)}")
            
            # Delete the directory
            os.rmdir(session_dir)
            
            return True
        except Exception as e:
            logger.error(f"Error deleting session {session_id}: {str(e)}")
            return False

# Create a singleton instance
webcam_controller = WebcamController() 