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
    property string ledColor: "#ffffff"
    property var effectsList: []
    property var palettesList: []

    readonly property bool hasRing: ledProvider === "dw_leds"

    // 'ball' tracker state (firmware-native effect that follows the sand ball)
    property string ballColor2: "#000000"
    property int ballFgBright: 255
    property int ballBgBright: 255
    property int ballSize: 3
    property string ballBg: "static"
    property string ballDirection: "cw"
    property int ballAlign: 0

    // Resolve the 'ball' effect id from the catalogue (id 38 today).
    property int ballEffectId: {
        for (var i = 0; i < effectsList.length; i++)
            if (effectsList[i].name === "ball")
                return effectsList[i].id
        return 38
    }
    property bool ballActive: currentEffectIndex === ballEffectId

    // The ball tracker has its own card (matching the web UI), so it is not
    // offered as a plain effect chip.
    property var selectableEffects: effectsList.filter(function(e) {
        return e.name !== "ball"
    })

    // Background options for the ball: solid colour, off, or any other effect.
    property var ballBgOptions: {
        var opts = [
            {"label": "Solid", "value": "static"},
            {"label": "Off", "value": "off"}
        ]
        for (var i = 0; i < effectsList.length; i++) {
            var n = effectsList[i].name
            if (n !== "ball" && n !== "off" && n !== "static")
                opts.push({"label": n.charAt(0).toUpperCase() + n.slice(1), "value": n})
        }
        return opts
    }

    // Predefined colors for quick selection (muted tones to fit the dark UI)
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
                ledColor = backend.ledColor
                ballColor2 = backend.ledColor2
                ballFgBright = backend.ledBallFgBright
                ballBgBright = backend.ledBallBgBright
                ballSize = backend.ledBallSize
                ballBg = backend.ledBallBg
                ballDirection = backend.ledBallDirection
                ballAlign = backend.ledBallAlign
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
            Layout.preferredHeight: Components.ThemeManager.headerHeight
            color: Components.ThemeManager.surfaceColor

            Rectangle {
                anchors.bottom: parent.bottom
                width: parent.width
                height: 1
                color: Components.ThemeManager.borderColor
            }

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: Components.ThemeManager.spaceLg
                anchors.rightMargin: Components.ThemeManager.spaceLg

                ConnectionStatus {
                    backend: page.backend
                    Layout.rightMargin: Components.ThemeManager.spaceSm
                }

                Label {
                    text: "Light"
                    font.family: Components.ThemeManager.fontDisplay
                    font.pixelSize: Components.ThemeManager.fontSizeTitle
                    color: Components.ThemeManager.textPrimary
                }

                Item {
                    Layout.fillWidth: true
                }
            }
        }

        // Content — the light's state stays pinned on the left (power and
        // brightness never scroll away); the right column scrolls through
        // every effect, the ball tracker, every palette, and quick colors.
        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 0

            // ---- Left: state panel (fits without scrolling in most
            // setups; scrolls independently when the backlight card is
            // present on the Pi) ----
            ScrollView {
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.maximumWidth: hasRing ? Math.round(page.width * 0.42) : page.width
                contentWidth: availableWidth

                ColumnLayout {
                    width: parent.width
                    spacing: 0

                // Table light: power + brightness (or provider notices)
                SettingsCard {
                    Layout.rightMargin: hasRing ? Components.ThemeManager.spaceSm
                                                : Components.ThemeManager.spaceLg
                    Layout.preferredHeight: providerColumn.implicitHeight + 2 * Components.ThemeManager.spaceLg

                    ColumnLayout {
                        id: providerColumn
                        anchors.fill: parent
                        anchors.margins: Components.ThemeManager.spaceLg
                        spacing: Components.ThemeManager.spaceMd

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: Components.ThemeManager.spaceSm

                            SectionLabel {
                                text: "Table light"
                                Layout.fillWidth: true
                            }

                            Rectangle {
                                visible: hasRing
                                width: 8
                                height: 8
                                radius: 4
                                color: ledConnected ? Components.ThemeManager.ok
                                                    : Components.ThemeManager.danger
                            }

                            Label {
                                visible: hasRing
                                text: ledConnected ? "Connected" : "Disconnected"
                                font.family: Components.ThemeManager.fontBody
                                font.pixelSize: Components.ThemeManager.fontSizeCaption
                                color: Components.ThemeManager.textTertiary
                            }
                        }

                        // Not configured message
                        Label {
                            visible: ledProvider === "none"
                            text: "No light ring is set up for this table. Configure one in the Dune Weaver web interface."
                            font.family: Components.ThemeManager.fontBody
                            font.pixelSize: Components.ThemeManager.fontSizeBody
                            color: Components.ThemeManager.textSecondary
                            wrapMode: Text.WordWrap
                            Layout.fillWidth: true
                        }

                        // WLED notice
                        Label {
                            visible: ledProvider === "wled"
                            text: "This table's light is driven by WLED — use the Dune Weaver web interface to control it."
                            font.family: Components.ThemeManager.fontBody
                            font.pixelSize: Components.ThemeManager.fontSizeBody
                            color: Components.ThemeManager.textSecondary
                            wrapMode: Text.WordWrap
                            Layout.fillWidth: true
                        }

                        // Power row
                        RowLayout {
                            visible: hasRing
                            Layout.fillWidth: true
                            spacing: Components.ThemeManager.spaceMd

                            Label {
                                text: ledPowerOn ? "On" : "Off"
                                font.family: Components.ThemeManager.fontDisplay
                                font.pixelSize: Components.ThemeManager.fontSizeBody
                                color: Components.ThemeManager.textPrimary
                                Layout.fillWidth: true
                            }

                            DwSwitch {
                                id: powerSwitch
                                checked: ledPowerOn
                                onToggled: {
                                    if (backend) {
                                        backend.toggleLedPower()
                                    }
                                }

                                // A user toggle breaks the declarative binding;
                                // this keeps the switch following backend state.
                                Binding {
                                    target: powerSwitch
                                    property: "checked"
                                    value: ledPowerOn
                                }
                            }
                        }

                        // Brightness row
                        RowLayout {
                            visible: hasRing
                            Layout.fillWidth: true
                            spacing: Components.ThemeManager.spaceMd

                            Label {
                                text: "Brightness"
                                font.family: Components.ThemeManager.fontBody
                                font.pixelSize: Components.ThemeManager.fontSizeCaption
                                color: Components.ThemeManager.textSecondary
                                Layout.preferredWidth: 76
                            }

                            DwSlider {
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
                                font.family: Components.ThemeManager.fontMedium
                                font.pixelSize: Components.ThemeManager.fontSizeCaption
                                color: Components.ThemeManager.textPrimary
                                Layout.preferredWidth: 36
                                horizontalAlignment: Text.AlignRight
                            }
                        }
                    }
                }

                // Screen brightness (always visible, controls Pi LCD backlight)
                SettingsCard {
                    Layout.rightMargin: hasRing ? Components.ThemeManager.spaceSm
                                                : Components.ThemeManager.spaceLg
                    Layout.preferredHeight: lcdColumn.implicitHeight + 2 * Components.ThemeManager.spaceLg
                    visible: backend && backend.lcdMaxBrightness > 0

                    ColumnLayout {
                        id: lcdColumn
                        anchors.fill: parent
                        anchors.margins: Components.ThemeManager.spaceLg
                        spacing: Components.ThemeManager.spaceSm

                        SectionLabel {
                            text: "Screen brightness"
                        }

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: Components.ThemeManager.spaceMd

                            Components.Icon {
                                name: "brightness"
                                size: 20
                                color: Components.ThemeManager.textSecondary
                            }

                            DwSlider {
                                id: lcdBrightnessSlider
                                Layout.fillWidth: true
                                from: 0
                                to: backend ? backend.lcdMaxBrightness : 255
                                stepSize: 1
                                value: backend ? backend.lcdBrightness : 255

                                onMoved: {
                                    if (backend) {
                                        backend.setLcdBrightness(Math.round(value))
                                    }
                                }
                            }

                            Label {
                                text: {
                                    var max = backend ? backend.lcdMaxBrightness : 255
                                    if (max <= 0) return "0%"
                                    return Math.round(lcdBrightnessSlider.value / max * 100) + "%"
                                }
                                font.family: Components.ThemeManager.fontMedium
                                font.pixelSize: Components.ThemeManager.fontSizeCaption
                                color: Components.ThemeManager.textPrimary
                                Layout.preferredWidth: 36
                                horizontalAlignment: Text.AlignRight
                            }
                        }
                    }
                }

                // Quick colors — set the whole ring to one plain colour
                SettingsCard {
                    Layout.rightMargin: Components.ThemeManager.spaceSm
                    Layout.preferredHeight: quickColumn.implicitHeight + 2 * Components.ThemeManager.spaceLg
                    visible: hasRing

                    ColumnLayout {
                        id: quickColumn
                        anchors.fill: parent
                        anchors.margins: Components.ThemeManager.spaceLg
                        spacing: Components.ThemeManager.spaceMd

                        SectionLabel {
                            text: "Quick colors"
                        }

                        GridLayout {
                            Layout.fillWidth: true
                            columns: 5
                            rowSpacing: Components.ThemeManager.spaceSm
                            columnSpacing: Components.ThemeManager.spaceSm

                            Repeater {
                                model: presetColors

                                Rectangle {
                                    property bool isSel: ledColor.toLowerCase() === modelData.sendColor.toLowerCase()
                                    Layout.fillWidth: true
                                    Layout.preferredHeight: 40
                                    radius: 20
                                    color: modelData.color
                                    border.color: isSel ? Components.ThemeManager.textPrimary
                                                        : Qt.darker(modelData.color, 1.2)
                                    border.width: isSel ? 2 : 1

                                    MouseArea {
                                        anchors.fill: parent
                                        onClicked: {
                                            if (backend) {
                                                backend.setLedColorHex(modelData.sendColor)
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }

                }
            }

            // ---- Right: everything the ring can do (scrolls) ----
            ScrollView {
                Layout.fillWidth: true
                Layout.fillHeight: true
                contentWidth: availableWidth
                visible: hasRing

                ColumnLayout {
                    width: parent.width
                    spacing: 0

                    // Effects — the full firmware catalogue
                    SettingsCard {
                        Layout.leftMargin: Components.ThemeManager.spaceSm
                        Layout.preferredHeight: effectsColumn.implicitHeight + 2 * Components.ThemeManager.spaceLg

                        ColumnLayout {
                            id: effectsColumn
                            anchors.fill: parent
                            anchors.margins: Components.ThemeManager.spaceLg
                            spacing: Components.ThemeManager.spaceMd

                            SectionLabel {
                                text: "Effect"
                            }

                            Label {
                                visible: selectableEffects.length === 0
                                text: "No effects available"
                                font.family: Components.ThemeManager.fontBody
                                font.pixelSize: Components.ThemeManager.fontSizeCaption
                                color: Components.ThemeManager.textSecondary
                            }

                            GridLayout {
                                Layout.fillWidth: true
                                columns: 3
                                rowSpacing: Components.ThemeManager.spaceSm
                                columnSpacing: Components.ThemeManager.spaceSm
                                visible: selectableEffects.length > 0

                                Repeater {
                                    model: selectableEffects

                                    ChoiceChip {
                                        property int effectId: modelData.id !== undefined ? modelData.id : index
                                        property string effectName: modelData.name || ("Effect " + effectId)

                                        Layout.fillWidth: true
                                        label: effectName.charAt(0).toUpperCase() + effectName.slice(1)
                                        selected: effectId === currentEffectIndex

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

                    // Ball Tracker — firmware-native effect (id 38) that
                    // follows the sand ball, so it lives with the effects.
                    SettingsCard {
                        Layout.leftMargin: Components.ThemeManager.spaceSm
                        Layout.preferredHeight: ballCol.implicitHeight + 2 * Components.ThemeManager.spaceLg

                        ColumnLayout {
                            id: ballCol
                            anchors.fill: parent
                            anchors.margins: Components.ThemeManager.spaceLg
                            spacing: Components.ThemeManager.spaceMd

                            // Header row: title + enable toggle
                            RowLayout {
                                Layout.fillWidth: true
                                spacing: Components.ThemeManager.spaceSm

                                ColumnLayout {
                                    Layout.fillWidth: true
                                    spacing: 2
                                    SectionLabel {
                                        text: "Ball tracker"
                                    }
                                    Label {
                                        text: ballActive
                                              ? "Following the sand ball — replaces the effect above."
                                              : "A glowing dot that follows the sand ball."
                                        font.family: Components.ThemeManager.fontBody
                                        font.pixelSize: Components.ThemeManager.fontSizeCaption
                                        color: Components.ThemeManager.textSecondary
                                        wrapMode: Text.WordWrap
                                        Layout.fillWidth: true
                                    }
                                }

                                DwSwitch {
                                    id: ballSwitch
                                    checked: ballActive
                                    onToggled: {
                                        if (backend)
                                            backend.setBallTracker(!ballActive)
                                    }

                                    Binding {
                                        target: ballSwitch
                                        property: "checked"
                                        value: ballActive
                                    }
                                }
                            }

                            // Controls (only meaningful while the ball effect is on)
                            ColumnLayout {
                                Layout.fillWidth: true
                                visible: ballActive
                                spacing: Components.ThemeManager.spaceMd

                                // ---- Blob ----
                                Label {
                                    text: "The dot"
                                    font.family: Components.ThemeManager.fontMedium
                                    font.pixelSize: Components.ThemeManager.fontSizeCaption
                                    color: Components.ThemeManager.textSecondary
                                }

                                // Blob colour swatches
                                GridLayout {
                                    Layout.fillWidth: true
                                    columns: 10
                                    rowSpacing: Components.ThemeManager.spaceSm
                                    columnSpacing: Components.ThemeManager.spaceSm
                                    Repeater {
                                        model: presetColors
                                        Rectangle {
                                            property bool isSel: ledColor.toLowerCase() === modelData.sendColor.toLowerCase()
                                            Layout.fillWidth: true
                                            Layout.preferredHeight: 32
                                            radius: 16
                                            color: modelData.color
                                            border.color: isSel ? Components.ThemeManager.textPrimary
                                                                : Qt.darker(modelData.color, 1.2)
                                            border.width: isSel ? 2 : 1
                                            MouseArea {
                                                anchors.fill: parent
                                                onClicked: { if (backend) backend.setLedColorHex(modelData.sendColor) }
                                            }
                                        }
                                    }
                                }

                                // Blob brightness
                                RowLayout {
                                    Layout.fillWidth: true
                                    spacing: Components.ThemeManager.spaceMd
                                    Label {
                                        text: "Brightness"
                                        font.family: Components.ThemeManager.fontBody
                                        font.pixelSize: Components.ThemeManager.fontSizeCaption
                                        color: Components.ThemeManager.textSecondary
                                        Layout.preferredWidth: 84
                                    }
                                    DwSlider {
                                        id: ballFgSlider
                                        Layout.fillWidth: true
                                        from: 0; to: 255; stepSize: 1
                                        value: ballFgBright
                                        onMoved: { if (backend) backend.setLedBallFgBright(Math.round(value)) }
                                    }
                                    Label {
                                        text: Math.round(ballFgSlider.value)
                                        font.family: Components.ThemeManager.fontMedium
                                        font.pixelSize: Components.ThemeManager.fontSizeCaption
                                        color: Components.ThemeManager.textPrimary
                                        Layout.preferredWidth: 36
                                        horizontalAlignment: Text.AlignRight
                                    }
                                }

                                // Direction
                                RowLayout {
                                    Layout.fillWidth: true
                                    spacing: Components.ThemeManager.spaceMd
                                    Label {
                                        text: "Direction"
                                        font.family: Components.ThemeManager.fontBody
                                        font.pixelSize: Components.ThemeManager.fontSizeCaption
                                        color: Components.ThemeManager.textSecondary
                                        Layout.preferredWidth: 84
                                    }
                                    Repeater {
                                        model: [
                                            {"label": "Clockwise", "value": "cw"},
                                            {"label": "Counter-CW", "value": "ccw"}
                                        ]
                                        ChoiceChip {
                                            Layout.fillWidth: true
                                            label: modelData.label
                                            selected: ballDirection === modelData.value
                                            onClicked: { if (backend) backend.setLedBallDirection(modelData.value) }
                                        }
                                    }
                                }

                                // Glow size
                                RowLayout {
                                    Layout.fillWidth: true
                                    spacing: Components.ThemeManager.spaceMd
                                    Label {
                                        text: "Glow size"
                                        font.family: Components.ThemeManager.fontBody
                                        font.pixelSize: Components.ThemeManager.fontSizeCaption
                                        color: Components.ThemeManager.textSecondary
                                        Layout.preferredWidth: 84
                                    }
                                    DwSlider {
                                        id: ballSizeSlider
                                        Layout.fillWidth: true
                                        from: 1; to: 30; stepSize: 1
                                        value: ballSize
                                        onMoved: { if (backend) backend.setLedBallSize(Math.round(value)) }
                                    }
                                    Label {
                                        text: Math.round(ballSizeSlider.value)
                                        font.family: Components.ThemeManager.fontMedium
                                        font.pixelSize: Components.ThemeManager.fontSizeCaption
                                        color: Components.ThemeManager.textPrimary
                                        Layout.preferredWidth: 36
                                        horizontalAlignment: Text.AlignRight
                                    }
                                }

                                // Alignment
                                RowLayout {
                                    Layout.fillWidth: true
                                    spacing: Components.ThemeManager.spaceMd
                                    Label {
                                        text: "Alignment"
                                        font.family: Components.ThemeManager.fontBody
                                        font.pixelSize: Components.ThemeManager.fontSizeCaption
                                        color: Components.ThemeManager.textSecondary
                                        Layout.preferredWidth: 84
                                    }
                                    DwSlider {
                                        id: ballAlignSlider
                                        Layout.fillWidth: true
                                        from: 0; to: 359; stepSize: 1
                                        value: ballAlign
                                        onMoved: { if (backend) backend.setLedBallAlign(Math.round(value)) }
                                    }
                                    Label {
                                        text: Math.round(ballAlignSlider.value) + "°"
                                        font.family: Components.ThemeManager.fontMedium
                                        font.pixelSize: Components.ThemeManager.fontSizeCaption
                                        color: Components.ThemeManager.textPrimary
                                        Layout.preferredWidth: 36
                                        horizontalAlignment: Text.AlignRight
                                    }
                                }

                                // ---- Background ----
                                Rectangle {
                                    Layout.fillWidth: true
                                    Layout.preferredHeight: 1
                                    Layout.topMargin: Components.ThemeManager.spaceXs
                                    color: Components.ThemeManager.borderColor
                                }
                                Label {
                                    text: "Behind the dot"
                                    font.family: Components.ThemeManager.fontMedium
                                    font.pixelSize: Components.ThemeManager.fontSizeCaption
                                    color: Components.ThemeManager.textSecondary
                                }

                                // Background selector (Solid / Off / any effect)
                                GridLayout {
                                    Layout.fillWidth: true
                                    columns: 3
                                    rowSpacing: Components.ThemeManager.spaceSm
                                    columnSpacing: Components.ThemeManager.spaceSm
                                    Repeater {
                                        model: ballBgOptions
                                        ChoiceChip {
                                            Layout.fillWidth: true
                                            label: modelData.label
                                            selected: ballBg === modelData.value
                                            onClicked: { if (backend) backend.setLedBallBg(modelData.value) }
                                        }
                                    }
                                }

                                // Background colour (only for the solid background)
                                ColumnLayout {
                                    Layout.fillWidth: true
                                    visible: ballBg === "static"
                                    spacing: Components.ThemeManager.spaceSm
                                    Label {
                                        text: "Background colour"
                                        font.family: Components.ThemeManager.fontBody
                                        font.pixelSize: Components.ThemeManager.fontSizeCaption
                                        color: Components.ThemeManager.textSecondary
                                    }
                                    GridLayout {
                                        Layout.fillWidth: true
                                        columns: 10
                                        rowSpacing: Components.ThemeManager.spaceSm
                                        columnSpacing: Components.ThemeManager.spaceSm
                                        Repeater {
                                            model: presetColors
                                            Rectangle {
                                                property bool isSel: ballColor2.toLowerCase() === modelData.sendColor.toLowerCase()
                                                Layout.fillWidth: true
                                                Layout.preferredHeight: 32
                                                radius: 16
                                                color: modelData.color
                                                border.color: isSel ? Components.ThemeManager.textPrimary
                                                                    : Qt.darker(modelData.color, 1.2)
                                                border.width: isSel ? 2 : 1
                                                MouseArea {
                                                    anchors.fill: parent
                                                    onClicked: { if (backend) backend.setLedColor2Hex(modelData.sendColor) }
                                                }
                                            }
                                        }
                                    }
                                }

                                // Background brightness (hidden when background is off)
                                RowLayout {
                                    Layout.fillWidth: true
                                    visible: ballBg !== "off"
                                    spacing: Components.ThemeManager.spaceMd
                                    Label {
                                        text: "Bg brightness"
                                        font.family: Components.ThemeManager.fontBody
                                        font.pixelSize: Components.ThemeManager.fontSizeCaption
                                        color: Components.ThemeManager.textSecondary
                                        Layout.preferredWidth: 84
                                    }
                                    DwSlider {
                                        id: ballBgSlider
                                        Layout.fillWidth: true
                                        from: 0; to: 255; stepSize: 1
                                        value: ballBgBright
                                        onMoved: { if (backend) backend.setLedBallBgBright(Math.round(value)) }
                                    }
                                    Label {
                                        text: Math.round(ballBgSlider.value)
                                        font.family: Components.ThemeManager.fontMedium
                                        font.pixelSize: Components.ThemeManager.fontSizeCaption
                                        color: Components.ThemeManager.textPrimary
                                        Layout.preferredWidth: 36
                                        horizontalAlignment: Text.AlignRight
                                    }
                                }
                            }
                        }
                    }

                    // Palettes — the full firmware catalogue
                    SettingsCard {
                        Layout.leftMargin: Components.ThemeManager.spaceSm
                        Layout.bottomMargin: Components.ThemeManager.spaceLg
                        Layout.preferredHeight: palettesColumn.implicitHeight + 2 * Components.ThemeManager.spaceLg

                        ColumnLayout {
                            id: palettesColumn
                            anchors.fill: parent
                            anchors.margins: Components.ThemeManager.spaceLg
                            spacing: Components.ThemeManager.spaceMd

                            SectionLabel {
                                text: "Palette"
                            }

                            Label {
                                visible: palettesList.length === 0
                                text: "No palettes available"
                                font.family: Components.ThemeManager.fontBody
                                font.pixelSize: Components.ThemeManager.fontSizeCaption
                                color: Components.ThemeManager.textSecondary
                            }

                            GridLayout {
                                Layout.fillWidth: true
                                columns: 3
                                rowSpacing: Components.ThemeManager.spaceSm
                                columnSpacing: Components.ThemeManager.spaceSm
                                visible: palettesList.length > 0

                                Repeater {
                                    model: palettesList

                                    ChoiceChip {
                                        property int paletteId: modelData.id !== undefined ? modelData.id : index
                                        property string paletteName: modelData.name || ("Palette " + paletteId)

                                        Layout.fillWidth: true
                                        label: paletteName.charAt(0).toUpperCase() + paletteName.slice(1)
                                        selected: paletteId === currentPaletteIndex

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
            }
        }
    }
}
