import os
import time
import threading
import subprocess
import platform
import logging
import json
from datetime import datetime
from pathlib import Path
import numpy as np
import cv2  # Import OpenCV globally

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
        
        # Default camera settings
        self.camera_settings = {
            'brightness': 0.4,
            'contrast': 1.2,
            'exposure': 0.1
        }
        
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
                self.capture_single_frame(output_file)
                
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
    
    def capture_single_frame(self, output_file=None, camera=None, return_base64=False):
        """Capture a single frame using OpenCV - can be used for both test captures and timelapse captures
        
        Args:
            output_file: Path to save the captured frame (optional if return_base64=True)
            camera: Camera identifier (index, string, or device path)
            return_base64: If True, return the frame as a base64 encoded string instead of saving to disk
            
        Returns:
            True if saved to disk successfully, or base64 encoded string if return_base64=True
        """
        try:
            # Convert camera identifier to integer index if needed
            camera_index = None
            
            # If camera is provided, convert it to an index
            if camera is not None:
                if isinstance(camera, int):
                    camera_index = camera
                elif isinstance(camera, str):
                    if camera.isdigit():
                        camera_index = int(camera)
                    elif ':' in camera and camera.split(':')[0].isdigit():
                        camera_index = int(camera.split(':')[0])
                    elif self.platform == 'Linux' and camera.startswith('/dev/video'):
                        try:
                            camera_index = int(camera.replace('/dev/video', ''))
                        except ValueError:
                            camera_index = 0
            
            # If no camera index was determined, use the selected camera
            if camera_index is None:
                # Convert selected_camera to integer index if possible
                camera_index = 0  # Default to first camera
                if self.selected_camera.isdigit():
                    camera_index = int(self.selected_camera)
                elif ':' in self.selected_camera and self.selected_camera.split(':')[0].isdigit():
                    camera_index = int(self.selected_camera.split(':')[0])
                elif self.platform == 'Linux' and self.selected_camera.startswith('/dev/video'):
                    # Extract number from /dev/videoX
                    try:
                        camera_index = int(self.selected_camera.replace('/dev/video', ''))
                    except ValueError:
                        camera_index = 0
            
            logger.debug(f"Capturing with camera index: {camera_index} and settings: {self.camera_settings}")
            
            # Initialize the camera
            cam = cv2.VideoCapture(camera_index)
            
            # Set camera properties for better image quality
            cam.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
            cam.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
            
            # Try to apply user-defined camera settings to hardware
            brightness_result = cam.set(cv2.CAP_PROP_BRIGHTNESS, self.camera_settings['brightness'])
            contrast_result = cam.set(cv2.CAP_PROP_CONTRAST, self.camera_settings['contrast'])
            auto_exposure_result = cam.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.25)  # Manual exposure
            exposure_result = cam.set(cv2.CAP_PROP_EXPOSURE, self.camera_settings['exposure'])
            
            # Log whether the settings were applied successfully
            logger.debug(f"Camera property set results - brightness: {brightness_result}, contrast: {contrast_result}, auto_exposure: {auto_exposure_result}, exposure: {exposure_result}")
            
            # Wait a moment for camera to adjust
            time.sleep(0.5)
            
            # Capture frame
            ret, frame = cam.read()
            
            # Release the camera
            cam.release()
            
            if not ret or frame is None:
                raise Exception("Failed to capture frame from camera")
            
            # Apply post-processing adjustments in software
            # This ensures the settings have an effect even if the camera hardware controls don't work
            
            # Convert brightness from 0-1 to -1 to 1 range (0.5 is neutral)
            brightness_adjust = (self.camera_settings['brightness'] - 0.5) * 2.0
            
            # Apply brightness adjustment
            if brightness_adjust > 0:
                # Increase brightness
                frame = cv2.addWeighted(frame, 1, np.zeros(frame.shape, frame.dtype), 0, brightness_adjust * 100)
            else:
                # Decrease brightness
                frame = cv2.addWeighted(frame, 1, np.zeros(frame.shape, frame.dtype), 0, brightness_adjust * 100)
            
            # Apply contrast adjustment
            # Convert to float and normalize to 0-1
            f = frame.astype(np.float32) / 255.0
            # Apply contrast adjustment (contrast_factor of 1.0 is neutral)
            contrast_factor = self.camera_settings['contrast']
            f = (f - 0.5) * contrast_factor + 0.5
            # Clip to 0-1 range
            f = np.clip(f, 0, 1)
            # Convert back to 8-bit
            frame = (f * 255).astype(np.uint8)
            
            # If return_base64 is True, return the frame as a base64 encoded string
            if return_base64:
                # Encode the frame as JPEG
                success, buffer = cv2.imencode('.jpg', frame)
                if not success:
                    raise Exception("Failed to encode image")
                
                # Convert to base64
                import base64
                jpg_as_text = base64.b64encode(buffer).decode('utf-8')
                
                # Return the base64 encoded image with MIME type
                return f"data:image/jpeg;base64,{jpg_as_text}"
            
            # Otherwise save the processed frame to disk
            else:
                if output_file is None:
                    raise ValueError("output_file must be provided when return_base64 is False")
                
                # Save the processed frame
                cv2.imwrite(output_file, frame)
                
                # Verify the file was created successfully
                if not os.path.exists(output_file) or os.path.getsize(output_file) == 0:
                    raise Exception(f"Failed to save frame - output file is empty or missing: {output_file}")
                    
                logger.debug(f"Captured and processed frame to {output_file}")
                return True
                
        except Exception as e:
            logger.error(f"Error capturing frame: {str(e)}")
            raise

    def test_capture(self, camera=None, output_dir=None, return_base64=True):
        """Take a test capture with the specified camera
        
        Args:
            camera: Camera identifier (index, string, or device path)
            output_dir: Directory to save the captured frame (only used if return_base64=False)
            return_base64: If True, return the frame as a base64 encoded string instead of saving to disk
            
        Returns:
            Base64 encoded string if return_base64=True, or relative path to the saved image if return_base64=False
        """
        try:
            # If returning base64, just use the capture_single_frame method directly
            if return_base64:
                return self.capture_single_frame(camera=camera, return_base64=True)
            
            # Otherwise, save to disk
            # Create test directory if it doesn't exist
            if output_dir is None:
                output_dir = os.path.join(self.timelapse_dir, 'test_captures')
            os.makedirs(output_dir, exist_ok=True)
            
            # Generate a unique filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = os.path.join(output_dir, f"test_capture_{timestamp}.jpg")
            
            # Capture the frame using the common method
            # The camera conversion is handled inside capture_single_frame
            success = self.capture_single_frame(output_file=output_file, camera=camera, return_base64=False)
            
            if success:
                # Return the relative path to the image
                return os.path.join('test_captures', f"test_capture_{timestamp}.jpg")
            else:
                return None
        except Exception as e:
            logger.error(f"Error in test capture: {str(e)}")
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

    def capture_frame_to_base64(self, camera=None):
        """Capture a single frame and return it as a base64 encoded string without saving to disk"""
        return self.capture_single_frame(camera=camera, return_base64=True)

# Create a singleton instance
webcam_controller = WebcamController() 