import QtQuick 2.15
import "." as Components

// Material Icons Round glyph by name (font bundled in fonts/, loaded in
// main.py). Codepoints from MaterialIconsRound-Regular.codepoints - add
// entries here as needed; names match the Material set.
Text {
    id: icon

    property string name: ""
    property real size: 22

    readonly property var _glyphs: ({
        "add": "\ue145",
        "adjust": "\ue39e",
        "arrow_back": "\ue2ea",
        "brightness": "\ue3ab",
        "check": "\ue5ca",
        "circle": "\uef4a",
        "close": "\ue5cd",
        "delete": "\ue872",
        "expand_more": "\ue5cf",
        "home": "\ue88a",
        "light_mode": "\ue518",
        "lightbulb": "\ue0f0",
        "music_note": "\ue405",
        "pause": "\ue034",
        "play_arrow": "\ue037",
        "play_circle": "\ue1c4",
        "playlist_play": "\ue05f",
        "power": "\ue8ac",
        "queue_music": "\ue03d",
        "radio_unchecked": "\ue836",
        "refresh": "\ue5d5",
        "restart": "\uf053",
        "search": "\ue8b6",
        "shuffle": "\ue043",
        "skip_next": "\ue044",
        "stop": "\ue047",
        "tune": "\ue429",
        "wifi": "\ue63e"
    })

    text: _glyphs[name] || ""
    font.family: Components.ThemeManager.fontIcon
    font.pixelSize: size
    color: Components.ThemeManager.textPrimary
    verticalAlignment: Text.AlignVCenter
    horizontalAlignment: Text.AlignHCenter
}
