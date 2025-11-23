import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import QtQuick.Dialogs
import "../components"
import "../components" as Components

Page {
    id: page
    property var backend: null

    // Local state
    property bool ledPowerOn: false
    property int ledBrightness: 100
    property string ledProvider: "none"
    property bool ledConnected: false
    property int currentEffectIndex: 0
    property int currentPaletteIndex: 0
    property var effectsList: []
    property var palettesList: []

    // Predefined colors for quick selection (muted tones to fit dark UI)
    property var presetColors: [
        {"name": "White", "color": "#e8e8e8", "sendColor": "#ffffff"},
        {"name": "Warm", "color": "#d4a574", "sendColor": "#ffaa55"},
        {"name": "Red", "color": "#c45c5c", "sendColor": "#ff0000"},
        {"name": "Orange", "color": "#d4875c", "sendColor": "#ff8800"},
        {"name": "Yellow", "color": "#c9b95c", "sendColor": "#ffff00"},
        {"name": "Green", "color": "#5cb85c", "sendColor": "#00ff00"},
        {"name": "Cyan", "color": "#5cb8b8", "sendColor": "#00ffff"},
        {"name": "Blue", "color": "#5c7cc4", "sendColor": "#0000ff"},
        {"name": "Purple", "color": "#8b5cc4", "sendColor": "#8800ff"},
        {"name": "Pink", "color": "#c45c99", "sendColor": "#ff00ff"}
    ]

    // Backend signal connections
    Connections {
        target: backend

        function onLedStatusChanged() {
            if (backend) {
                ledPowerOn = backend.ledPowerOn
                ledBrightness = backend.ledBrightness
                ledProvider = backend.ledProvider
                ledConnected = backend.ledConnected
                currentEffectIndex = backend.ledCurrentEffect
                currentPaletteIndex = backend.ledCurrentPalette
            }
        }

        function onLedEffectsLoaded(effects) {
            effectsList = effects
        }

        function onLedPalettesLoaded(palettes) {
            palettesList = palettes
        }
    }

    // Load LED config on page load
    Component.onCompleted: {
        if (backend) {
            backend.loadLedConfig()
        }
    }

    Rectangle {
        anchors.fill: parent
        color: Components.ThemeManager.backgroundColor
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        // Header
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 50
            color: Components.ThemeManager.surfaceColor

            Rectangle {
                anchors.bottom: parent.bottom
                width: parent.width
                height: 1
                color: Components.ThemeManager.borderColor
            }

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 15
                anchors.rightMargin: 10

                ConnectionStatus {
                    backend: page.backend
                    Layout.rightMargin: 8
                }

                Label {
                    text: "LED Control"
                    font.pixelSize: 18
                    font.bold: true
                    color: Components.ThemeManager.textPrimary
                }

                Item {
                    Layout.fillWidth: true
                }
            }
        }

        // Main Content
        ScrollView {
            Layout.fillWidth: true
            Layout.fillHeight: true
            contentWidth: availableWidth

            ColumnLayout {
                width: parent.width
                anchors.margins: 5
                spacing: 2

                // Provider Info & Power/Brightness Section
                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: ledProvider === "none" ? 100 : (ledProvider === "wled" ? 90 : 110)
                    Layout.margins: 5
                    radius: 8
                    color: Components.ThemeManager.surfaceColor

                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: 15
                        spacing: 10

                        // Not configured message
                        ColumnLayout {
                            visible: ledProvider === "none"
                            Layout.fillWidth: true
                            spacing: 8

                            Label {
                                text: "LED Not Configured"
                                font.pixelSize: 14
                                font.bold: true
                                color: Components.ThemeManager.textPrimary
                            }

                            Label {
                                text: "Configure LED settings in the main Dune Weaver web interface"
                                font.pixelSize: 12
                                color: Components.ThemeManager.textSecondary
                                wrapMode: Text.WordWrap
                                Layout.fillWidth: true
                            }
                        }

                        // DW LEDs Controls - Power and Brightness in same section
                        ColumnLayout {
                            visible: ledProvider === "dw_leds"
                            Layout.fillWidth: true
                            spacing: 8

                            // Power row with status and toggle
                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 12

                                // Status indicator with label
                                RowLayout {
                                    spacing: 6

                                    Rectangle {
                                        width: 12
                                        height: 12
                                        radius: 6
                                        color: ledPowerOn ? "#4CAF50" : "#6b7280"
                                    }

                                    Label {
                                        text: ledPowerOn ? "On" : "Off"
                                        font.pixelSize: 13
                                        font.bold: true
                                        color: Components.ThemeManager.textPrimary
                                    }
                                }

                                // Toggle button
                                ModernControlButton {
                                    Layout.preferredWidth: 100
                                    Layout.preferredHeight: 36
                                    text: ledPowerOn ? "Turn Off" : "Turn On"
                                    icon: ""
                                    buttonColor: ledPowerOn ? "#6b7280" : "#4CAF50"
                                    fontSize: 11

                                    onClicked: {
                                        if (backend) {
                                            backend.toggleLedPower()
                                        }
                                    }
                                }

                                Item { Layout.fillWidth: true }

                                // Connection status (smaller, secondary)
                                RowLayout {
                                    spacing: 4

                                    Rectangle {
                                        width: 8
                                        height: 8
                                        radius: 4
                                        color: ledConnected ? "#4CAF50" : "#ef4444"
                                    }

                                    Label {
                                        text: ledConnected ? "Connected" : "Disconnected"
                                        font.pixelSize: 10
                                        color: Components.ThemeManager.textTertiary
                                    }
                                }
                            }

                            // Brightness row
                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 10

                                Label {
                                    text: "Brightness"
                                    font.pixelSize: 12
                                    color: Components.ThemeManager.textSecondary
                                }

                                Slider {
                                    id: brightnessSlider
                                    Layout.fillWidth: true
                                    from: 0
                                    to: 100
                                    stepSize: 5
                                    value: ledBrightness

                                    onMoved: {
                                        if (backend) {
                                            backend.setLedBrightness(Math.round(value))
                                        }
                                    }
                                }

                                Label {
                                    text: Math.round(brightnessSlider.value) + "%"
                                    font.pixelSize: 12
                                    font.bold: true
                                    color: Components.ThemeManager.textPrimary
                                    Layout.preferredWidth: 35
                                    horizontalAlignment: Text.AlignRight
                                }
                            }
                        }

                        // WLED Info
                        ColumnLayout {
                            visible: ledProvider === "wled"
                            Layout.fillWidth: true
                            spacing: 8

                            Label {
                                text: "WLED Mode"
                                font.pixelSize: 14
                                font.bold: true
                                color: Components.ThemeManager.textPrimary
                            }

                            Label {
                                text: "Use the main Dune Weaver web interface for WLED controls"
                                font.pixelSize: 12
                                color: Components.ThemeManager.textSecondary
                                wrapMode: Text.WordWrap
                                Layout.fillWidth: true
                            }
                        }
                    }
                }

                // Effects Section (only for dw_leds)
                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: effectsList.length > 0 ? 180 : 80
                    Layout.margins: 5
                    radius: 8
                    color: Components.ThemeManager.surfaceColor
                    visible: ledProvider === "dw_leds"

                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: 15
                        spacing: 10

                        Label {
                            text: "Effects"
                            font.pixelSize: 14
                            font.bold: true
                            color: Components.ThemeManager.textPrimary
                        }

                        // Show loading or no effects message
                        Label {
                            visible: effectsList.length === 0
                            text: "No effects available"
                            font.pixelSize: 12
                            color: Components.ThemeManager.textSecondary
                        }

                        // Effects grid
                        GridLayout {
                            Layout.fillWidth: true
                            columns: 4
                            rowSpacing: 6
                            columnSpacing: 6
                            visible: effectsList.length > 0

                            Repeater {
                                model: effectsList.slice(0, 12) // Show first 12 effects

                                Rectangle {
                                    property int effectId: modelData.id !== undefined ? modelData.id : index
                                    property bool isSelected: effectId === currentEffectIndex

                                    Layout.fillWidth: true
                                    Layout.preferredHeight: 35
                                    radius: 6
                                    color: isSelected ?
                                           Components.ThemeManager.selectedBackground :
                                           Components.ThemeManager.buttonBackground
                                    border.color: isSelected ?
                                                  Components.ThemeManager.selectedBorder :
                                                  Components.ThemeManager.buttonBorder
                                    border.width: 1

                                    Label {
                                        anchors.centerIn: parent
                                        anchors.leftMargin: 4
                                        anchors.rightMargin: 4
                                        width: parent.width - 8
                                        text: modelData.name || ("Effect " + effectId)
                                        font.pixelSize: 10
                                        color: isSelected ? "white" : Components.ThemeManager.textPrimary
                                        elide: Text.ElideRight
                                        horizontalAlignment: Text.AlignHCenter
                                    }

                                    MouseArea {
                                        anchors.fill: parent
                                        onClicked: {
                                            if (backend) {
                                                backend.setLedEffect(effectId)
                                                currentEffectIndex = effectId
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }

                // Palettes Section (only for dw_leds)
                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: palettesList.length > 0 ? 140 : 80
                    Layout.margins: 5
                    radius: 8
                    color: Components.ThemeManager.surfaceColor
                    visible: ledProvider === "dw_leds"

                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: 15
                        spacing: 10

                        Label {
                            text: "Palettes"
                            font.pixelSize: 14
                            font.bold: true
                            color: Components.ThemeManager.textPrimary
                        }

                        // Show loading or no palettes message
                        Label {
                            visible: palettesList.length === 0
                            text: "No palettes available"
                            font.pixelSize: 12
                            color: Components.ThemeManager.textSecondary
                        }

                        // Palettes grid
                        GridLayout {
                            Layout.fillWidth: true
                            columns: 4
                            rowSpacing: 6
                            columnSpacing: 6
                            visible: palettesList.length > 0

                            Repeater {
                                model: palettesList.slice(0, 8) // Show first 8 palettes

                                Rectangle {
                                    property int paletteId: modelData.id !== undefined ? modelData.id : index
                                    property bool isSelected: paletteId === currentPaletteIndex

                                    Layout.fillWidth: true
                                    Layout.preferredHeight: 35
                                    radius: 6
                                    color: isSelected ?
                                           Components.ThemeManager.selectedBackground :
                                           Components.ThemeManager.buttonBackground
                                    border.color: isSelected ?
                                                  Components.ThemeManager.selectedBorder :
                                                  Components.ThemeManager.buttonBorder
                                    border.width: 1

                                    Label {
                                        anchors.centerIn: parent
                                        anchors.leftMargin: 4
                                        anchors.rightMargin: 4
                                        width: parent.width - 8
                                        text: modelData.name || ("Palette " + paletteId)
                                        font.pixelSize: 10
                                        color: isSelected ? "white" : Components.ThemeManager.textPrimary
                                        elide: Text.ElideRight
                                        horizontalAlignment: Text.AlignHCenter
                                    }

                                    MouseArea {
                                        anchors.fill: parent
                                        onClicked: {
                                            if (backend) {
                                                backend.setLedPalette(paletteId)
                                                currentPaletteIndex = paletteId
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }

                // Quick Colors Section - MOVED TO BOTTOM (only for dw_leds)
                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 160
                    Layout.margins: 5
                    radius: 8
                    color: Components.ThemeManager.surfaceColor
                    visible: ledProvider === "dw_leds"

                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: 15
                        spacing: 10

                        Label {
                            text: "Quick Colors"
                            font.pixelSize: 14
                            font.bold: true
                            color: Components.ThemeManager.textPrimary
                        }

                        GridLayout {
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            columns: 5
                            rowSpacing: 8
                            columnSpacing: 8

                            Repeater {
                                model: presetColors

                                Rectangle {
                                    Layout.fillWidth: true
                                    Layout.fillHeight: true
                                    Layout.minimumHeight: 50
                                    radius: 6
                                    color: Components.ThemeManager.buttonBackground
                                    border.color: Components.ThemeManager.buttonBorder
                                    border.width: 1

                                    RowLayout {
                                        anchors.centerIn: parent
                                        spacing: 6

                                        // Color indicator circle
                                        Rectangle {
                                            width: 14
                                            height: 14
                                            radius: 7
                                            color: modelData.color
                                            border.color: Qt.darker(modelData.color, 1.2)
                                            border.width: 1
                                        }

                                        Label {
                                            text: modelData.name
                                            font.pixelSize: 11
                                            color: Components.ThemeManager.textPrimary
                                        }
                                    }

                                    MouseArea {
                                        anchors.fill: parent
                                        onClicked: {
                                            if (backend) {
                                                backend.setLedColorHex(modelData.sendColor)
                                            }
                                        }
                                    }

                                    // Touch feedback
                                    Rectangle {
                                        id: colorTouchFeedback
                                        anchors.fill: parent
                                        color: Components.ThemeManager.darkMode ? "#ffffff" : "#000000"
                                        opacity: 0
                                        radius: 6

                                        NumberAnimation {
                                            id: colorTouchAnimation
                                            target: colorTouchFeedback
                                            property: "opacity"
                                            from: 0.15
                                            to: 0
                                            duration: 200
                                        }
                                    }
                                }
                            }
                        }
                    }
                }

                // Add some bottom spacing for better scrolling
                Item {
                    Layout.preferredHeight: 20
                }
            }
        }
    }
}
