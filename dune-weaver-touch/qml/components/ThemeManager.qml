pragma Singleton
import QtQuick 2.15
import Qt.labs.settings 1.0

// Design tokens for the touch UI — "the table at night".
// Night: warm basalt ground, bone text, one amber accent (the LED glow).
// Day: warm sand ground instead of inverted gray. Same ember accent family.
// Every color, size, and spacing in the QML goes through this singleton.
QtObject {
    id: themeManager

    // Theme state - loaded from settings
    property bool darkMode: settings.darkMode

    // ---- Typography (bundled in fonts/, registered in main.py) ----
    // Static instances carry legacy family names, hence three families.
    readonly property string fontBody: "Outfit"
    readonly property string fontMedium: "Outfit Medium"
    readonly property string fontDisplay: "Outfit SemiBold"
    readonly property string fontIcon: "Material Icons Round"

    // Type scale — the panel is read at arm's length, so nothing under 12.
    readonly property int fontSizeCaption: 12   // eyebrows, meta, counts
    readonly property int fontSizeBody: 14      // controls, list rows
    readonly property int fontSizeTitle: 17     // page titles, card titles
    readonly property int fontSizeDisplay: 24   // the one big thing per page

    // ---- Layout ----
    readonly property int spaceXs: 4
    readonly property int spaceSm: 8
    readonly property int spaceMd: 12
    readonly property int spaceLg: 16
    readonly property int spaceXl: 24
    readonly property int radiusSm: 10
    readonly property int radiusMd: 14
    readonly property int radiusPill: 999       // circles/pills: the table's geometry
    readonly property int touchTarget: 48       // minimum hit size, fingertips + sand
    readonly property int controlHeight: 56     // primary transport controls
    readonly property int headerHeight: 60
    readonly property int navHeight: 64

    // ---- Surfaces ----
    property color backgroundColor: darkMode ? "#171310" : "#ece5d6"   // basalt / dune
    property color surfaceColor: darkMode ? "#201b16" : "#f5f0e5"
    property color cardColor: darkMode ? "#2a241d" : "#e4dcca"
    property color pressedColor: darkMode ? "#332c24" : "#d9cfba"

    // ---- Text ----
    property color textPrimary: darkMode ? "#ece4d3" : "#332c22"       // bone / ink
    property color textSecondary: darkMode ? "#a39885" : "#7c7161"
    property color textTertiary: darkMode ? "#6e6455" : "#a89d8a"

    // ---- Borders ----
    property color borderColor: darkMode ? "#362f26" : "#d6ccb7"
    property color borderLight: darkMode ? "#2b2620" : "#e0d8c6"

    // ---- Accent: ember (the LED ring's glow) ----
    property color accent: darkMode ? "#e2a860" : "#b0791f"
    property color accentPressed: darkMode ? "#c98f49" : "#8f6014"
    property color onAccent: darkMode ? "#241a0c" : "#fdf8ee"
    // Subtle amber-tinted fill for selected chips/rows
    property color accentSoft: darkMode ? "#3a2f1e" : "#eadfc2"

    // ---- Semantic ----
    property color ok: darkMode ? "#9db07f" : "#5f7a3f"                 // connected, running
    property color okSoft: darkMode ? "#28301f" : "#e2e6d2"
    property color danger: darkMode ? "#c65a33" : "#b0431d"             // stop, delete, alarm
    property color dangerPressed: darkMode ? "#a84a28" : "#8f3517"

    // ---- Legacy aliases (older call sites; prefer the tokens above) ----
    property color accentBlue: accent
    property color accentBlueHover: accentPressed
    property color accentRed: danger
    property color accentRedHover: dangerPressed
    property color accentGray: textSecondary
    property color accentGrayHover: textPrimary
    property color accentGrayDisabled: textTertiary
    property color buttonBackground: cardColor
    property color buttonBackgroundHover: pressedColor
    property color buttonBorder: borderColor
    property color selectedBackground: accent
    property color selectedBorder: accentPressed

    // Placeholder / preview
    property color placeholderBackground: cardColor
    property color placeholderText: textTertiary
    // Previews carry their own dark circular dish (thr_preview.py) and sit
    // directly on the page surface — no boxed backdrop.
    property color previewBackground: backgroundColor

    property color shadowColor: darkMode ? "#000000" : "#00000020"

    // Navigation
    property color navBackground: surfaceColor
    property color navBorder: borderColor
    property color navIconActive: accent
    property color navIconInactive: textSecondary
    property color navTextActive: accent
    property color navTextInactive: textSecondary

    // Persistent settings
    property Settings settings: Settings {
        category: "Appearance"
        property bool darkMode: true  // night is the default: this screen lives on furniture
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
