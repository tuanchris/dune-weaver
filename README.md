# Dune Weaver

[!["Buy Me A Coffee"](https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png)](https://buymeacoffee.com/tuanchris)

![Dune Weaver Gif](./static/IMG_7404.gif)

Dune Weaver is a web-controlled kinetic sand table system that creates mesmerizing patterns in sand using a steel ball guided by magnets beneath the surface. This project seamlessly integrates hardware control with a modern web interface, featuring real-time pattern execution, playlist management, and synchronized lighting effects.

## 🌟 Key Features

- **Web-Based Control Interface**: Modern, responsive web UI for pattern management and table control
- **Real-Time Pattern Execution**: Live preview and control of pattern drawing with progress tracking
- **Playlist System**: Queue multiple patterns for continuous execution
- **WLED Integration**: Synchronized lighting effects during pattern execution
- **Pattern Library**: Browse, upload, and manage custom patterns with preview generation
- **Polar Coordinate System**: Specialized θ-ρ coordinate system optimized for radial designs
- **Auto-Update System**: GitHub-integrated version management with update notifications

### **📚 Complete Documentation: [Dune Weaver Wiki](https://github.com/tuanchris/dune-weaver/wiki)**

---

The Dune Weaver comes in two versions:

1. **Small Version (Mini Dune Weaver)**:
   - Uses two **28BYJ-48 DC 5V stepper motors**.
   - Controlled via **ULN2003 motor drivers**.
   - Powered by an **ESP32**.

2. **Larger Version (Dune Weaver)**:
   - Uses two **NEMA 17 or NEMA 23 stepper motors**.
   - Controlled via **TMC2209 or DRV8825 motor drivers**.
   - Powered by an **Arduino UNO with a CNC shield**.

Each version operates similarly but differs in power, precision, and construction cost.

The sand table consists of two main bases:
1. **Lower Base**: Houses all the electronic components, including motor drivers, and power connections.
2. **Upper Base**: Contains the sand and the marble, which is moved by a magnet beneath.

Both versions of the table use two stepper motors:

- **Radial Axis Motor**: Controls the in-and-out movement of the arm.
- **Angular Axis Motor**: Controls the rotational movement of the arm.

The small version uses **28BYJ-48 motors** driven by **ULN2003 drivers**, while the larger version uses **NEMA 17 or NEMA 23 motors** with **TMC2209 or DRV8825 drivers**.: Controls the in-and-out movement of the arm.
- **Angular Axis Motor**: Controls the rotational movement of the arm.

Each motor is connected to a motor driver that dictates step and direction. The motor drivers are, in turn, connected to the ESP32 board, which serves as the system's main controller. The entire table is powered by a single USB cable attached to the ESP32.

---

## Coordinate System
Unlike traditional CNC machines that use an **X-Y coordinate system**, the sand table operates on a **theta-rho (θ, ρ) coordinate system**:
- **Theta (θ)**: Represents the angular position of the arm, with **2π radians (360 degrees) for one full revolution**.
- **Rho (ρ)**: Represents the radial distance of the marble from the center, with **0 at the center and 1 at the perimeter**.

This system allows the table to create intricate radial designs that differ significantly from traditional Cartesian-based CNC machines.

---

## Homing and Position Tracking
Unlike conventional CNC machines, the sand table **does not have a limit switch** for homing. Instead, it uses a **crash-homing method**:
1. Upon power-on, the radial axis moves inward to its physical limit, ensuring the marble is positioned at the center.
2. The software then assumes this as the **home position (0,0 in polar coordinates)**.
3. The system continuously tracks all executed coordinates to maintain an accurate record of the marble’s position.

---

## Mechanical Constraints and Software Adjustments
### Coupled Angular and Radial Motion
Due to the **hardware design choice**, the angular axis **does not move independently**. This means that when the angular motor moves one full revolution, the radial axis **also moves slightly**—either inwards or outwards, depending on the rotation direction.

To counteract this behavior, the software:
- Monitors how many revolutions the angular axis has moved.
- Applies an offset to the radial axis to compensate for unintended movements.

This correction ensures that the table accurately follows the intended path without accumulating errors over time.

---

Each pattern file consists of lines with theta and rho values (in degrees and normalized units, respectively), separated by a space. Comments start with #.

Example:

```
# Example pattern
0 0.5
90 0.7
180 0.5
270 0.7
```

## API Endpoints

The project exposes RESTful APIs for various actions. Here are some key endpoints:
 • List Serial Ports: /list_serial_ports (GET)
 • Connect to Serial: /connect (POST)
 • Upload Pattern: /upload_theta_rho (POST)
 • Run Pattern: /run_theta_rho (POST)
 • Stop Execution: /stop_execution (POST)

## 🚀 Quick Start

1. **Clone the repository**:
   ```bash
   git clone https://github.com/tuanchris/dune-weaver.git
   cd dune-weaver
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   npm install
   ```

3. **Build CSS**:
   ```bash
   npm run build-css
   ```

4. **Start the application**:
   ```bash
   python main.py
   ```

5. **Open your browser** and navigate to `http://localhost:8080`

## 📁 Project Structure

```
dune-weaver/
├── main.py                     # FastAPI application entry point
├── VERSION                     # Current software version
├── modules/
│   ├── connection/             # Serial & WebSocket connection management
│   ├── core/                   # Core business logic
│   │   ├── cache_manager.py    # Pattern preview caching
│   │   ├── pattern_manager.py  # Pattern file handling
│   │   ├── playlist_manager.py # Playlist system
│   │   ├── state.py           # Global state management
│   │   └── version_manager.py  # GitHub version checking
│   ├── led/                    # WLED integration
│   ├── mqtt/                   # MQTT support
│   └── update/                 # Software update management
├── patterns/                   # Pattern files (.thr format)
├── static/                     # Web assets (CSS, JS, images)
├── templates/                  # HTML templates
├── firmware/                   # Hardware controller firmware
└── requirements.txt            # Python dependencies
```

## 🔧 Configuration

The application uses several configuration methods:
- **Environment Variables**: `LOG_LEVEL`, connection settings
- **State Persistence**: Settings saved to `state.json`
- **Version Management**: Automatic GitHub release checking

## 🌐 API Endpoints

Core API endpoints for integration:

- **Pattern Management**: `/upload_theta_rho`, `/list_theta_rho_files`
- **Execution Control**: `/run_theta_rho`, `/pause_execution`, `/stop_execution`
- **Hardware Control**: `/connect`, `/send_home`, `/set_speed`
- **Version Management**: `/api/version`, `/api/update`
- **Real-time Updates**: WebSocket at `/ws/status`

## 🤝 Contributing

We welcome contributions! Please check out our [Contributing Guide](https://github.com/tuanchris/dune-weaver/wiki/Contributing) for details.

## 📖 Documentation

For detailed setup instructions, hardware assembly, and advanced configuration:

**🔗 [Visit the Complete Wiki](https://github.com/tuanchris/dune-weaver/wiki)**

---

**Happy sand drawing with Dune Weaver! ✨**

