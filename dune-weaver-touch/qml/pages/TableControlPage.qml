import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import "../components"
import "../components" as Components

Page {
    id: page
    property var backend: null
    property string selectedPort: ""
    property bool isSerialConnected: false
    property bool autoPlayOnBoot: false

    // Backend signal connections
    Connections {
        target: backend

        function onSerialConnectionChanged(connected) {
            isSerialConnected = connected
        }

        function onCurrentPortChanged(port) {
            if (port) {
                selectedPort = port
            }
        }

        function onSettingsLoaded() {
            if (backend) {
                autoPlayOnBoot = backend.autoPlayOnBoot
                isSerialConnected = backend.serialConnected
                if (backend.currentPort) {
                    selectedPort = backend.currentPort
                }
            }
        }
    }

    // backend is injected by the Loader after creation, so kick off the
    // initial mDNS browse (and settings load) when it arrives — at
    // Component.onCompleted it is still null and these would be no-ops.
    onBackendChanged: {
        if (backend) {
            refreshSerialPorts()
            loadSettings()
        }
    }

    function refreshSerialPorts() {
        if (backend) {
            backend.refreshSerialPorts()
        }
    }

    function loadSettings() {
        if (backend) {
            backend.loadControlSettings()
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
                    text: "Control"
                    font.family: Components.ThemeManager.fontDisplay
                    font.pixelSize: Components.ThemeManager.fontSizeTitle
                    color: Components.ThemeManager.textPrimary
                }

                Item {
                    Layout.fillWidth: true
                }
            }
        }

        // Main content — two columns: the landscape panel wastes half its
        // width on full-page cards, so connection lives left and the
        // movement/device settings live right; both scroll together.
        ScrollView {
            Layout.fillWidth: true
            Layout.fillHeight: true
            contentWidth: availableWidth

            RowLayout {
                width: parent.width
                spacing: 0

                // ---- Left column: table connection ----
                ColumnLayout {
                    Layout.fillWidth: true
                    Layout.maximumWidth: Math.round(page.width * 0.47)
                    Layout.alignment: Qt.AlignTop
                    spacing: 0

                    SettingsCard {
                        Layout.rightMargin: Components.ThemeManager.spaceSm
                        Layout.bottomMargin: Components.ThemeManager.spaceLg
                        Layout.preferredHeight: connectionColumn.implicitHeight + 2 * Components.ThemeManager.spaceLg

                        ColumnLayout {
                            id: connectionColumn
                            anchors.fill: parent
                            anchors.margins: Components.ThemeManager.spaceLg
                            spacing: Components.ThemeManager.spaceMd

                            SectionLabel {
                                text: "Table connection"
                            }

                            // Connection status row — info rect + button as
                            // siblings, so the button column lines up with
                            // every other row's (Save, Refresh, Connect).
                            RowLayout {
                                Layout.fillWidth: true
                                spacing: Components.ThemeManager.spaceSm

                                Rectangle {
                                    Layout.fillWidth: true
                                    Layout.preferredHeight: 60
                                    radius: Components.ThemeManager.radiusSm
                                    color: isSerialConnected ? Components.ThemeManager.okSoft
                                                             : Components.ThemeManager.cardColor
                                    border.color: isSerialConnected ? Components.ThemeManager.ok
                                                                    : Components.ThemeManager.borderColor
                                    border.width: 1

                                    Column {
                                        anchors.verticalCenter: parent.verticalCenter
                                        anchors.left: parent.left
                                        anchors.right: parent.right
                                        anchors.leftMargin: Components.ThemeManager.spaceLg
                                        anchors.rightMargin: Components.ThemeManager.spaceMd
                                        spacing: 2

                                        Label {
                                            text: isSerialConnected
                                                  ? (backend && backend.tableName ? backend.tableName : "Connected")
                                                  : "Not connected"
                                            color: isSerialConnected ? Components.ThemeManager.ok
                                                                     : Components.ThemeManager.textSecondary
                                            font.family: Components.ThemeManager.fontDisplay
                                            font.pixelSize: Components.ThemeManager.fontSizeBody
                                            elide: Text.ElideRight
                                            width: parent.width
                                        }

                                        Label {
                                            text: isSerialConnected
                                                  ? selectedPort
                                                  : (backend ? backend.reconnectStatus : "")
                                            visible: text !== ""
                                            color: Components.ThemeManager.textSecondary
                                            font.family: Components.ThemeManager.fontBody
                                            font.pixelSize: Components.ThemeManager.fontSizeCaption
                                            elide: Text.ElideRight
                                            width: parent.width
                                        }
                                    }
                                }

                                ModernControlButton {
                                    Layout.preferredWidth: 116
                                    Layout.preferredHeight: 44
                                    visible: isSerialConnected
                                    text: "Disconnect"
                                    outlined: true
                                    buttonColor: Components.ThemeManager.danger
                                    fontSize: 12

                                    onClicked: {
                                        if (backend) backend.disconnectSerial()
                                    }
                                }
                            }

                            // Table password ($Sand/Password, sent as X-Sand-Key).
                            // Empty + Save clears a stored password.
                            RowLayout {
                                Layout.fillWidth: true
                                spacing: Components.ThemeManager.spaceSm

                                TextField {
                                    id: tablePasswordField
                                    Layout.fillWidth: true
                                    Layout.preferredHeight: 44
                                    echoMode: TextInput.Password
                                    placeholderText: backend && backend.hasTablePassword
                                                     ? "Table password (saved)"
                                                     : "Table password (if set)"
                                    placeholderTextColor: Components.ThemeManager.textTertiary
                                    font.family: Components.ThemeManager.fontBody
                                    font.pixelSize: Components.ThemeManager.fontSizeBody
                                    color: Components.ThemeManager.textPrimary
                                    verticalAlignment: TextInput.AlignVCenter
                                    leftPadding: Components.ThemeManager.spaceLg
                                    rightPadding: Components.ThemeManager.spaceLg

                                    background: Rectangle {
                                        color: Components.ThemeManager.backgroundColor
                                        radius: 22
                                        border.color: tablePasswordField.activeFocus ? Components.ThemeManager.accent
                                                                                     : Components.ThemeManager.borderColor
                                        border.width: 1
                                    }
                                }

                                ModernControlButton {
                                    Layout.preferredWidth: 116
                                    Layout.preferredHeight: 44
                                    text: "Save"
                                    buttonColor: Components.ThemeManager.accent
                                    fontSize: 12

                                    onClicked: {
                                        if (backend) {
                                            backend.setTablePassword(tablePasswordField.text)
                                            tablePasswordField.text = ""
                                        }
                                    }
                                }
                            }
                        }
                    }

                    // Tables found on the network (mDNS)
                    SettingsCard {
                        Layout.rightMargin: Components.ThemeManager.spaceSm
                        Layout.bottomMargin: Components.ThemeManager.spaceLg
                        Layout.preferredHeight: networkColumn.implicitHeight + 2 * Components.ThemeManager.spaceLg

                        ColumnLayout {
                            id: networkColumn
                            anchors.fill: parent
                            anchors.margins: Components.ThemeManager.spaceLg
                            spacing: Components.ThemeManager.spaceMd

                            RowLayout {
                                Layout.fillWidth: true
                                spacing: Components.ThemeManager.spaceSm

                                SectionLabel {
                                    text: "Tables on your network"
                                    Layout.fillWidth: true
                                }

                                ModernControlButton {
                                    Layout.preferredWidth: 116
                                    Layout.preferredHeight: 44
                                    text: "Refresh"
                                    icon: "refresh"
                                    outlined: true
                                    buttonColor: Components.ThemeManager.textSecondary
                                    fontSize: 12

                                    onClicked: refreshSerialPorts()
                                }
                            }

                            // The connected table already sits in the status
                            // card above, so it is filtered from this list.
                            Repeater {
                                model: backend ? backend.discoveredTables : []

                                delegate: RowLayout {
                                    required property var modelData
                                    readonly property bool isCurrent: isSerialConnected && modelData.url === selectedPort

                                    visible: !isCurrent
                                    Layout.fillWidth: true
                                    spacing: Components.ThemeManager.spaceSm

                                    Rectangle {
                                        Layout.fillWidth: true
                                        Layout.preferredHeight: 60
                                        radius: Components.ThemeManager.radiusSm
                                        color: Components.ThemeManager.cardColor
                                        border.color: Components.ThemeManager.borderColor
                                        border.width: 1

                                        Column {
                                            anchors.verticalCenter: parent.verticalCenter
                                            anchors.left: parent.left
                                            anchors.right: parent.right
                                            anchors.leftMargin: Components.ThemeManager.spaceLg
                                            anchors.rightMargin: Components.ThemeManager.spaceMd
                                            spacing: 2

                                            Label {
                                                text: modelData.name || modelData.url
                                                color: Components.ThemeManager.textPrimary
                                                font.family: Components.ThemeManager.fontDisplay
                                                font.pixelSize: Components.ThemeManager.fontSizeBody
                                                elide: Text.ElideRight
                                                width: parent.width
                                            }

                                            Label {
                                                text: modelData.url
                                                color: Components.ThemeManager.textSecondary
                                                font.family: Components.ThemeManager.fontBody
                                                font.pixelSize: Components.ThemeManager.fontSizeCaption
                                                elide: Text.ElideRight
                                                width: parent.width
                                            }
                                        }
                                    }

                                    ModernControlButton {
                                        Layout.preferredWidth: 116
                                        Layout.preferredHeight: 44
                                        text: "Connect"
                                        buttonColor: Components.ThemeManager.accent
                                        fontSize: 12

                                        onClicked: {
                                            if (backend) backend.connectSerial(modelData.url)
                                        }
                                    }
                                }
                            }

                            Label {
                                visible: !backend || backend.discoveredTables.length === 0
                                text: "No tables found. Tap Refresh, or enter the address below."
                                font.family: Components.ThemeManager.fontBody
                                font.pixelSize: Components.ThemeManager.fontSizeCaption
                                color: Components.ThemeManager.textTertiary
                                Layout.fillWidth: true
                                wrapMode: Text.WordWrap
                            }

                            // Manual address entry
                            RowLayout {
                                Layout.fillWidth: true
                                spacing: Components.ThemeManager.spaceSm

                                TextField {
                                    id: manualAddress
                                    Layout.fillWidth: true
                                    Layout.preferredHeight: 44
                                    placeholderText: "IP or host address"
                                    placeholderTextColor: Components.ThemeManager.textTertiary
                                    font.family: Components.ThemeManager.fontBody
                                    font.pixelSize: Components.ThemeManager.fontSizeBody
                                    color: Components.ThemeManager.textPrimary
                                    verticalAlignment: TextInput.AlignVCenter
                                    leftPadding: Components.ThemeManager.spaceLg
                                    rightPadding: Components.ThemeManager.spaceLg
                                    inputMethodHints: Qt.ImhNoAutoUppercase | Qt.ImhPreferLowercase

                                    background: Rectangle {
                                        color: Components.ThemeManager.backgroundColor
                                        radius: 22
                                        border.color: manualAddress.activeFocus ? Components.ThemeManager.accent
                                                                                : Components.ThemeManager.borderColor
                                        border.width: 1
                                    }
                                }

                                ModernControlButton {
                                    Layout.preferredWidth: 116
                                    Layout.preferredHeight: 44
                                    text: "Connect"
                                    buttonColor: Components.ThemeManager.accent
                                    fontSize: 12
                                    enabled: manualAddress.text.trim() !== ""

                                    onClicked: {
                                        if (backend) {
                                            backend.connectSerial(manualAddress.text.trim())
                                            manualAddress.text = ""
                                        }
                                    }
                                }
                            }
                        }
                    }
                }

                // ---- Right column: movement + device settings ----
                ColumnLayout {
                    Layout.fillWidth: true
                    Layout.alignment: Qt.AlignTop
                    spacing: 0

                    // The table itself: movement + auto play
                    SettingsCard {
                        Layout.leftMargin: Components.ThemeManager.spaceSm
                        Layout.preferredHeight: movementColumn.implicitHeight + 2 * Components.ThemeManager.spaceLg

                        ColumnLayout {
                            id: movementColumn
                            anchors.fill: parent
                            anchors.margins: Components.ThemeManager.spaceLg
                            spacing: Components.ThemeManager.spaceMd

                            SectionLabel {
                                text: "Table"
                            }

                            RowLayout {
                                Layout.fillWidth: true
                                spacing: Components.ThemeManager.spaceSm

                                ModernControlButton {
                                    Layout.fillWidth: true
                                    Layout.preferredHeight: Components.ThemeManager.touchTarget
                                    text: "Home"
                                    icon: "home"
                                    outlined: true
                                    buttonColor: Components.ThemeManager.accent
                                    fontSize: 13
                                    enabled: isSerialConnected

                                    onClicked: {
                                        if (backend) backend.sendHome()
                                    }
                                }

                                ModernControlButton {
                                    Layout.fillWidth: true
                                    Layout.preferredHeight: Components.ThemeManager.touchTarget
                                    text: "Center"
                                    icon: "adjust"
                                    outlined: true
                                    buttonColor: Components.ThemeManager.accent
                                    fontSize: 13
                                    enabled: isSerialConnected

                                    onClicked: {
                                        if (backend) backend.moveToCenter()
                                    }
                                }

                                ModernControlButton {
                                    Layout.fillWidth: true
                                    Layout.preferredHeight: Components.ThemeManager.touchTarget
                                    text: "Edge"
                                    icon: "radio_unchecked"
                                    outlined: true
                                    buttonColor: Components.ThemeManager.accent
                                    fontSize: 13
                                    enabled: isSerialConnected

                                    onClicked: {
                                        if (backend) backend.moveToPerimeter()
                                    }
                                }
                            }

                            Rectangle {
                                Layout.fillWidth: true
                                Layout.preferredHeight: 1
                                color: Components.ThemeManager.borderLight
                            }

                            RowLayout {
                                Layout.fillWidth: true
                                spacing: Components.ThemeManager.spaceSm

                                ColumnLayout {
                                    Layout.fillWidth: true
                                    spacing: 2

                                    Label {
                                        text: "Auto play"
                                        font.family: Components.ThemeManager.fontMedium
                                        font.pixelSize: Components.ThemeManager.fontSizeBody
                                        color: Components.ThemeManager.textPrimary
                                    }

                                    Label {
                                        text: "Start playing when the table powers on"
                                        font.family: Components.ThemeManager.fontBody
                                        font.pixelSize: Components.ThemeManager.fontSizeCaption
                                        color: Components.ThemeManager.textSecondary
                                        wrapMode: Text.WordWrap
                                        Layout.fillWidth: true
                                    }
                                }

                                DwSwitch {
                                    id: autoPlaySwitch
                                    checked: autoPlayOnBoot

                                    onToggled: {
                                        autoPlayOnBoot = checked
                                        if (backend) {
                                            backend.setAutoPlayOnBoot(checked)
                                        }
                                    }

                                    // A user toggle breaks the declarative binding;
                                    // this keeps the switch following loaded settings.
                                    Binding {
                                        target: autoPlaySwitch
                                        property: "checked"
                                        value: autoPlayOnBoot
                                    }
                                }
                            }

                            Rectangle {
                                Layout.fillWidth: true
                                Layout.preferredHeight: 1
                                color: Components.ThemeManager.borderLight
                            }

                            // Reboots the FluidNC controller ($Bye soft-reset);
                            // the board re-homes on the way back up.
                            ModernControlButton {
                                Layout.fillWidth: true
                                Layout.preferredHeight: Components.ThemeManager.touchTarget
                                text: "Restart table"
                                icon: "restart"
                                outlined: true
                                buttonColor: Components.ThemeManager.textSecondary
                                fontSize: 13
                                enabled: isSerialConnected

                                onClicked: {
                                    if (backend) backend.restartBackend()
                                }
                            }
                        }
                    }

                    // This screen: sleep, theme, power
                    SettingsCard {
                        Layout.leftMargin: Components.ThemeManager.spaceSm
                        Layout.bottomMargin: Components.ThemeManager.spaceLg
                        Layout.preferredHeight: screenColumn.implicitHeight + 2 * Components.ThemeManager.spaceLg

                        ColumnLayout {
                            id: screenColumn
                            anchors.fill: parent
                            anchors.margins: Components.ThemeManager.spaceLg
                            spacing: Components.ThemeManager.spaceMd

                            SectionLabel {
                                text: "This screen"
                            }

                            Label {
                                text: "Sleeps after"
                                font.family: Components.ThemeManager.fontMedium
                                font.pixelSize: Components.ThemeManager.fontSizeCaption
                                color: Components.ThemeManager.textSecondary
                            }

                            RowLayout {
                                id: timeoutGrid
                                Layout.fillWidth: true
                                spacing: Components.ThemeManager.spaceSm

                                property string currentSelection: backend ? backend.getCurrentScreenTimeoutOption() : "5 minutes"

                                Connections {
                                    target: backend
                                    function onScreenTimeoutChanged() {
                                        if (backend) {
                                            timeoutGrid.currentSelection = backend.getCurrentScreenTimeoutOption()
                                        }
                                    }
                                }

                                Repeater {
                                    model: [
                                        { label: "30 s", value: "30 seconds" },
                                        { label: "1 m", value: "1 minute" },
                                        { label: "5 m", value: "5 minutes" },
                                        { label: "10 m", value: "10 minutes" },
                                        { label: "Never", value: "Never" }
                                    ]

                                    ChoiceChip {
                                        required property var modelData

                                        Layout.fillWidth: true
                                        Layout.preferredHeight: Components.ThemeManager.touchTarget
                                        label: modelData.label
                                        selected: timeoutGrid.currentSelection === modelData.value

                                        onClicked: {
                                            if (backend) {
                                                backend.setScreenTimeoutByOption(modelData.value)
                                                timeoutGrid.currentSelection = modelData.value
                                            }
                                        }
                                    }
                                }
                            }

                            Rectangle {
                                Layout.fillWidth: true
                                Layout.preferredHeight: 1
                                color: Components.ThemeManager.borderLight
                            }

                            RowLayout {
                                Layout.fillWidth: true
                                spacing: Components.ThemeManager.spaceSm

                                Label {
                                    text: "Night mode"
                                    font.family: Components.ThemeManager.fontMedium
                                    font.pixelSize: Components.ThemeManager.fontSizeBody
                                    color: Components.ThemeManager.textPrimary
                                    Layout.fillWidth: true
                                }

                                DwSwitch {
                                    id: darkModeSwitch
                                    checked: Components.ThemeManager.darkMode

                                    onToggled: {
                                        Components.ThemeManager.darkMode = checked
                                    }
                                }
                            }

                            Rectangle {
                                Layout.fillWidth: true
                                Layout.preferredHeight: 1
                                color: Components.ThemeManager.borderLight
                            }

                            ModernControlButton {
                                Layout.fillWidth: true
                                Layout.preferredHeight: Components.ThemeManager.touchTarget
                                text: "Shut down Pi"
                                icon: "power"
                                outlined: true
                                buttonColor: Components.ThemeManager.danger
                                fontSize: 13

                                onClicked: {
                                    if (backend) backend.shutdownPi()
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}
