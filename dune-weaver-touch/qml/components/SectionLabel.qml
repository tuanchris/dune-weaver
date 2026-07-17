import QtQuick 2.15
import QtQuick.Controls 2.15
import "." as Components

// Uppercase eyebrow used as a section title on settings-style pages.
Label {
    font.family: Components.ThemeManager.fontDisplay
    font.pixelSize: 11
    font.letterSpacing: 1.4
    font.capitalization: Font.AllUppercase
    color: Components.ThemeManager.textTertiary
}
