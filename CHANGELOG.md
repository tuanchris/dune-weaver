# Changelog

All notable changes to this project will be documented in this file.

## [1.1.0] - Default Pattern functionality

### Added
- **Default Pattern Feature:**
    - Added a "Set as Default Pattern" button in the UI.
    - Implemented the `/set_default_pattern` endpoint to allow users to set a selected `.thr` file as the default pattern.
    - Automatically runs the `custom_patterns/default_pattern.thr` file upon establishing a serial connection, if the file exists.
- **Auto-connect Serial Connection when app is started**
- **Retry Logic for Serial Connection:**
    - Introduced retry functionality for serial connections with configurable retry intervals and maximum retries.
    - Automatically selected the first available serial port if none was specified.
- **Added Footer with:**
  - Links to github 
  - Toggle button to show/hide the debug log

### Changed
- **Improved UI**
  - Certain buttons are now only visible when it's applicable for the current state.
  - Moved Stop button and Speed input to Quick Actions**
- **Pattern file prioritization:**
    - Updated the `/list_theta_rho_files` endpoint to:
        - Only display files with the `.thr` extension.
        - Include `custom_patterns/default_pattern.thr` at the top of the list if it exists.
        - Prioritize files in the `custom_patterns/` folder over other files.

## [1.0.0] - Initial Version
- Initial implementation of the Flask application to control the Dune Weaver sand table.
- Added core functionality for:
    - Serial port connection and management.
    - Parsing `.thr` files (theta-rho format).
    - Executing patterns via Arduino.
    - Basic Flask endpoints for listing, uploading, and running `.thr` files.
