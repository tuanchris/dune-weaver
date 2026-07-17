import QtQuick 2.15
import QtQuick.Layouts 1.15
import "." as Components

// Surface card for one settings section; meant to sit in a ColumnLayout.
Rectangle {
    Layout.fillWidth: true
    Layout.leftMargin: Components.ThemeManager.spaceLg
    Layout.rightMargin: Components.ThemeManager.spaceLg
    Layout.topMargin: Components.ThemeManager.spaceMd
    radius: Components.ThemeManager.radiusMd
    color: Components.ThemeManager.surfaceColor
    border.width: 1
    border.color: Components.ThemeManager.borderLight
}
