import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import "." as Components

// Connection dot + the connected table's name (firmware hostname), shown in
// every page header. Tapping it opens the table switcher: a dropdown of the
// tables discovered on the network, one tap to jump between them.
Rectangle {
    id: connectionStatus

    property var backend: null

    readonly property bool connected: backend && backend.serialConnected
    readonly property string tableName: connected ? (backend.tableName || "Table") : "No table"

    implicitHeight: 40
    implicitWidth: statusRow.implicitWidth + 2 * Components.ThemeManager.spaceMd
    radius: height / 2
    color: switchArea.pressed || tablePopup.opened
           ? Components.ThemeManager.pressedColor : "transparent"

    Row {
        id: statusRow
        anchors.centerIn: parent
        spacing: 6

        Rectangle {
            width: 9
            height: 9
            radius: 4.5
            anchors.verticalCenter: parent.verticalCenter
            color: connectionStatus.connected ? Components.ThemeManager.ok
                                              : Components.ThemeManager.danger

            Behavior on color {
                ColorAnimation {
                    duration: 300
                    easing.type: Easing.OutQuart
                }
            }
        }

        Text {
            anchors.verticalCenter: parent.verticalCenter
            text: connectionStatus.tableName
            font.family: Components.ThemeManager.fontMedium
            font.pixelSize: Components.ThemeManager.fontSizeCaption
            color: Components.ThemeManager.textSecondary
        }

        Components.Icon {
            anchors.verticalCenter: parent.verticalCenter
            name: "expand_more"
            size: 16
            color: Components.ThemeManager.textTertiary
        }
    }

    MouseArea {
        id: switchArea
        anchors.fill: parent
        onClicked: {
            if (!backend)
                return
            backend.refreshSerialPorts()  // fresh mDNS browse while the list shows
            tablePopup.open()
        }
    }

    Popup {
        id: tablePopup
        y: parent.height + Components.ThemeManager.spaceSm
        x: 0
        width: 300
        padding: Components.ThemeManager.spaceMd
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside

        background: Rectangle {
            color: Components.ThemeManager.surfaceColor
            radius: Components.ThemeManager.radiusMd
            border.color: Components.ThemeManager.borderColor
            border.width: 1
        }

        contentItem: ColumnLayout {
            spacing: Components.ThemeManager.spaceSm

            SectionLabel {
                text: "Switch table"
                Layout.leftMargin: Components.ThemeManager.spaceXs
            }

            Repeater {
                model: backend ? backend.discoveredTables : []

                delegate: Rectangle {
                    required property var modelData
                    readonly property bool isCurrent:
                        connectionStatus.connected && modelData.url === backend.currentPort

                    Layout.fillWidth: true
                    Layout.preferredHeight: 56
                    radius: Components.ThemeManager.radiusSm
                    color: isCurrent ? Components.ThemeManager.accentSoft
                                     : (rowArea.pressed ? Components.ThemeManager.pressedColor
                                                        : Components.ThemeManager.cardColor)
                    border.width: 1
                    border.color: isCurrent ? Components.ThemeManager.accent
                                            : Components.ThemeManager.borderLight

                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: Components.ThemeManager.spaceMd
                        anchors.rightMargin: Components.ThemeManager.spaceMd
                        spacing: Components.ThemeManager.spaceSm

                        Column {
                            Layout.fillWidth: true
                            spacing: 1

                            Label {
                                text: modelData.name || modelData.url
                                font.family: Components.ThemeManager.fontMedium
                                font.pixelSize: Components.ThemeManager.fontSizeBody
                                color: Components.ThemeManager.textPrimary
                                elide: Text.ElideRight
                                width: parent.width
                            }

                            Label {
                                text: modelData.url
                                font.family: Components.ThemeManager.fontBody
                                font.pixelSize: 11
                                color: Components.ThemeManager.textTertiary
                                elide: Text.ElideRight
                                width: parent.width
                            }
                        }

                        Components.Icon {
                            visible: parent.parent.isCurrent
                            name: "check"
                            size: 18
                            color: Components.ThemeManager.accent
                        }
                    }

                    MouseArea {
                        id: rowArea
                        anchors.fill: parent
                        enabled: !parent.isCurrent
                        onClicked: {
                            if (backend)
                                backend.connectSerial(parent.modelData.url)
                            tablePopup.close()
                        }
                    }
                }
            }

            Label {
                visible: !backend || backend.discoveredTables.length === 0
                text: "Searching your network for tables..."
                font.family: Components.ThemeManager.fontBody
                font.pixelSize: Components.ThemeManager.fontSizeCaption
                color: Components.ThemeManager.textTertiary
                Layout.fillWidth: true
                Layout.margins: Components.ThemeManager.spaceXs
                wrapMode: Text.WordWrap
            }
        }
    }
}
