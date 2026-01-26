pragma Singleton
import QtQuick 2.15
import Qt.labs.settings 1.0

QtObject {
    id: themeManager

    // Theme state - loaded from settings
    property bool darkMode: settings.darkMode

    // Background colors
    property color backgroundColor: darkMode ? "#1a1a1a" : "#f5f5f5"
    property color surfaceColor: darkMode ? "#2d2d2d" : "#ffffff"
    property color cardColor: darkMode ? "#3d3d3d" : "#f8f9fa"

    // Text colors
    property color textPrimary: darkMode ? "#ffffff" : "#333333"
    property color textSecondary: darkMode ? "#b0b0b0" : "#666666"
    property color textTertiary: darkMode ? "#808080" : "#999999"

    // Border colors
    property color borderColor: darkMode ? "#4d4d4d" : "#e5e7eb"
    property color borderLight: darkMode ? "#3d3d3d" : "#f0f0f0"

    // Accent colors (consistent in both themes)
    property color accentBlue: "#2563eb"
    property color accentBlueHover: "#1e40af"
    property color accentRed: "#dc2626"
    property color accentRedHover: "#b91c1c"
    property color accentGray: "#6b7280"
    property color accentGrayHover: "#525252"
    property color accentGrayDisabled: "#9ca3af"

    // Control colors
    property color buttonBackground: darkMode ? "#3d3d3d" : "#f0f0f0"
    property color buttonBackgroundHover: darkMode ? "#4d4d4d" : "#e0e0e0"
    property color buttonBorder: darkMode ? "#5d5d5d" : "#cccccc"

    // Selected/Active colors
    property color selectedBackground: "#2196F3"
    property color selectedBorder: "#1976D2"

    // Placeholder colors
    property color placeholderBackground: darkMode ? "#2d2d2d" : "#f0f0f0"
    property color placeholderText: darkMode ? "#606060" : "#cccccc"

    // Preview background - lighter in dark mode for better pattern visibility
    property color previewBackground: darkMode ? "#707070" : "#f8f9fa"

    // Shadow colors
    property color shadowColor: darkMode ? "#000000" : "#00000020"

    // Navigation colors
    property color navBackground: darkMode ? "#1f1f1f" : "#ffffff"
    property color navBorder: darkMode ? "#3d3d3d" : "#e5e7eb"
    property color navIconActive: "#2196F3"
    property color navIconInactive: darkMode ? "#808080" : "#9ca3af"
    property color navTextActive: darkMode ? "#ffffff" : "#333333"
    property color navTextInactive: darkMode ? "#808080" : "#666666"

    // Persistent settings
    property Settings settings: Settings {
        category: "Appearance"
        property bool darkMode: false  // Default to light mode
    }

    onDarkModeChanged: {
        // Save preference
        settings.darkMode = darkMode
    }

    // Helper function to get contrast color
    function getContrastColor(baseColor) {
        return darkMode ? Qt.lighter(baseColor, 1.2) : Qt.darker(baseColor, 1.1)
    }
}
