import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import DuneWeaver 1.0
import "../components"
import "../components" as Components

Page {
    id: page

    property var backend: null
    property var stackView: null
    property var mainWindow: null

    // State management for navigation
    property bool showingPlaylistDetail: false
    property string selectedPlaylist: ""
    property var selectedPlaylistData: null
    property var currentPlaylistPatterns: []
    property var currentPlaylistRawPatterns: []  // Raw patterns with full paths for API calls

    // Playlist execution settings (loaded from backend/persisted settings)
    property real pauseTime: backend ? backend.pauseBetweenPatterns : 10800
    property string clearPattern: backend ? backend.playlistClearPattern : "adaptive"
    property string runMode: backend ? backend.playlistRunMode : "loop"
    property bool shuffle: backend ? backend.playlistShuffle : true

    PlaylistModel {
        id: playlistModel
    }

    // Update patterns when playlist selection changes
    onSelectedPlaylistChanged: {
        if (selectedPlaylist) {
            currentPlaylistPatterns = playlistModel.getPatternsForPlaylist(selectedPlaylist)
            currentPlaylistRawPatterns = playlistModel.getRawPatternsForPlaylist(selectedPlaylist)
        } else {
            currentPlaylistPatterns = []
            currentPlaylistRawPatterns = []
        }
    }

    // Function to remove a pattern from the current playlist
    function removePatternAtIndex(index) {
        if (index >= 0 && index < currentPlaylistRawPatterns.length && backend) {
            var updatedPatterns = currentPlaylistRawPatterns.slice()  // Create a copy
            updatedPatterns.splice(index, 1)  // Remove the pattern at index
            backend.updatePlaylistPatterns(selectedPlaylist, updatedPatterns)
        }
    }

    // Function to navigate to playlist detail
    function showPlaylistDetail(playlistName, playlistData) {
        selectedPlaylist = playlistName
        selectedPlaylistData = playlistData
        showingPlaylistDetail = true
    }

    // Function to go back to playlist list
    function showPlaylistList() {
        showingPlaylistDetail = false
        selectedPlaylist = ""
        selectedPlaylistData = null
    }

    Rectangle {
        anchors.fill: parent
        color: Components.ThemeManager.backgroundColor
    }

    // Playlist List View (shown by default)
    Item {
        id: playlistListView
        anchors.fill: parent
        visible: !showingPlaylistDetail

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
                    anchors.rightMargin: Components.ThemeManager.spaceMd
                    spacing: Components.ThemeManager.spaceSm

                    ConnectionStatus {
                        backend: page.backend
                    }

                    Label {
                        text: "Playlists"
                        font.family: Components.ThemeManager.fontDisplay
                        font.pixelSize: Components.ThemeManager.fontSizeTitle
                        color: Components.ThemeManager.textPrimary
                    }

                    Label {
                        // ListView.count is reactive; rowCount() is a plain
                        // function call and would only evaluate once.
                        text: playlistsList.count + " playlists"
                        font.family: Components.ThemeManager.fontBody
                        font.pixelSize: Components.ThemeManager.fontSizeCaption
                        color: Components.ThemeManager.textTertiary
                    }

                    Item {
                        Layout.fillWidth: true
                    }

                    // Create new playlist
                    Rectangle {
                        Layout.preferredWidth: 44
                        Layout.preferredHeight: 44
                        radius: 22
                        color: createPlaylistMouseArea.pressed ? Components.ThemeManager.accentPressed
                                                               : Components.ThemeManager.accent

                        Components.Icon {
                            anchors.centerIn: parent
                            name: "add"
                            size: 22
                            color: Components.ThemeManager.onAccent
                        }

                        MouseArea {
                            id: createPlaylistMouseArea
                            anchors.fill: parent
                            onClicked: createPlaylistDialog.open()
                        }
                    }
                }
            }

            // Playlist List
            ListView {
                id: playlistsList
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.margins: Components.ThemeManager.spaceLg
                model: playlistModel
                spacing: Components.ThemeManager.spaceMd
                clip: true

                ScrollBar.vertical: ScrollBar {
                    active: true
                    policy: ScrollBar.AsNeeded
                }

                delegate: Rectangle {
                    width: ListView.view.width
                    height: 76
                    color: mouseArea.pressed ? Components.ThemeManager.pressedColor
                                             : Components.ThemeManager.surfaceColor
                    radius: Components.ThemeManager.radiusMd
                    border.color: Components.ThemeManager.borderColor
                    border.width: 1

                    scale: mouseArea.pressed ? 0.98 : 1.0
                    Behavior on scale {
                        NumberAnimation { duration: 100; easing.type: Easing.OutQuad }
                    }

                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: Components.ThemeManager.spaceLg
                        anchors.rightMargin: Components.ThemeManager.spaceLg
                        spacing: Components.ThemeManager.spaceLg

                        Rectangle {
                            Layout.preferredWidth: 44
                            Layout.preferredHeight: 44
                            radius: 22
                            color: Components.ThemeManager.accentSoft

                            Components.Icon {
                                anchors.centerIn: parent
                                name: "queue_music"
                                size: 20
                                color: Components.ThemeManager.accent
                            }
                        }

                        Column {
                            Layout.fillWidth: true
                            spacing: 2

                            Label {
                                text: model.name
                                font.family: Components.ThemeManager.fontDisplay
                                font.pixelSize: 16
                                color: Components.ThemeManager.textPrimary
                                elide: Text.ElideRight
                                width: parent.width
                            }

                            Label {
                                text: model.itemCount + " patterns"
                                color: Components.ThemeManager.textSecondary
                                font.family: Components.ThemeManager.fontBody
                                font.pixelSize: Components.ThemeManager.fontSizeCaption
                            }
                        }
                    }

                    MouseArea {
                        id: mouseArea
                        anchors.fill: parent
                        onClicked: {
                            showPlaylistDetail(model.name, model)
                        }
                    }
                }

                // Empty state
                Item {
                    anchors.fill: parent
                    visible: playlistsList.count === 0

                    Column {
                        anchors.centerIn: parent
                        spacing: Components.ThemeManager.spaceLg

                        Components.Icon {
                            name: "queue_music"
                            size: 44
                            color: Components.ThemeManager.textTertiary
                            anchors.horizontalCenter: parent.horizontalCenter
                        }

                        Label {
                            text: "No playlists yet"
                            anchors.horizontalCenter: parent.horizontalCenter
                            color: Components.ThemeManager.textSecondary
                            font.family: Components.ThemeManager.fontDisplay
                            font.pixelSize: Components.ThemeManager.fontSizeTitle
                        }

                        Label {
                            text: "Tap + to gather patterns into a set\nthe table can weave through"
                            anchors.horizontalCenter: parent.horizontalCenter
                            color: Components.ThemeManager.textTertiary
                            font.family: Components.ThemeManager.fontBody
                            font.pixelSize: Components.ThemeManager.fontSizeBody
                            horizontalAlignment: Text.AlignHCenter
                        }
                    }
                }
            }
        }
    }

    // Playlist Detail View (shown when a playlist is selected)
    Item {
        id: playlistDetailView
        anchors.fill: parent
        visible: showingPlaylistDetail

        ColumnLayout {
            anchors.fill: parent
            spacing: 0

            // Header with back button
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
                    anchors.leftMargin: Components.ThemeManager.spaceSm
                    anchors.rightMargin: Components.ThemeManager.spaceMd
                    spacing: Components.ThemeManager.spaceSm

                    Rectangle {
                        Layout.preferredWidth: 44
                        Layout.preferredHeight: 44
                        radius: 22
                        color: backArea.pressed ? Components.ThemeManager.pressedColor : "transparent"

                        Components.Icon {
                            anchors.centerIn: parent
                            name: "arrow_back"
                            size: 20
                            color: Components.ThemeManager.textPrimary
                        }

                        MouseArea {
                            id: backArea
                            anchors.fill: parent
                            onClicked: showPlaylistList()
                        }
                    }

                    Label {
                        text: selectedPlaylist
                        font.family: Components.ThemeManager.fontDisplay
                        font.pixelSize: Components.ThemeManager.fontSizeTitle
                        color: Components.ThemeManager.textPrimary
                        Layout.fillWidth: true
                        elide: Text.ElideRight
                    }

                    Label {
                        text: currentPlaylistPatterns.length + " patterns"
                        font.family: Components.ThemeManager.fontBody
                        font.pixelSize: Components.ThemeManager.fontSizeCaption
                        color: Components.ThemeManager.textTertiary
                    }

                    // Delete playlist
                    Rectangle {
                        Layout.preferredWidth: 44
                        Layout.preferredHeight: 44
                        radius: 22
                        color: deletePlaylistMouseArea.pressed ? Components.ThemeManager.pressedColor : "transparent"

                        Components.Icon {
                            anchors.centerIn: parent
                            name: "delete"
                            size: 20
                            color: Components.ThemeManager.danger
                        }

                        MouseArea {
                            id: deletePlaylistMouseArea
                            anchors.fill: parent
                            onClicked: deletePlaylistDialog.open()
                        }
                    }
                }
            }

            // Content - Pattern list on left, controls on right
            RowLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                spacing: 0

                // Left side - Pattern List
                Rectangle {
                    Layout.fillHeight: true
                    Layout.preferredWidth: page.width * 0.4
                    color: Components.ThemeManager.surfaceColor

                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: Components.ThemeManager.spaceLg
                        spacing: Components.ThemeManager.spaceMd

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: Components.ThemeManager.spaceSm

                            SectionLabel {
                                text: "Patterns"
                                Layout.fillWidth: true
                            }

                            // Add pattern button
                            Rectangle {
                                Layout.preferredWidth: 40
                                Layout.preferredHeight: 40
                                radius: 20
                                color: addPatternMouseArea.pressed ? Components.ThemeManager.pressedColor : "transparent"
                                border.width: 1
                                border.color: Components.ThemeManager.accent

                                Components.Icon {
                                    anchors.centerIn: parent
                                    name: "add"
                                    size: 20
                                    color: Components.ThemeManager.accent
                                }

                                MouseArea {
                                    id: addPatternMouseArea
                                    anchors.fill: parent
                                    onClicked: {
                                        // Navigate to full-page pattern selector
                                        stackView.push("PatternSelectorPage.qml", {
                                            backend: backend,
                                            stackView: stackView,
                                            playlistName: selectedPlaylist,
                                            existingPatterns: currentPlaylistRawPatterns
                                        })
                                    }
                                }
                            }
                        }

                        ListView {
                            id: patternListView
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            clip: true
                            model: currentPlaylistPatterns
                            spacing: Components.ThemeManager.spaceSm

                            ScrollBar.vertical: ScrollBar {
                                active: true
                                policy: ScrollBar.AsNeeded
                            }

                            delegate: Rectangle {
                                width: ListView.view.width
                                height: 48
                                color: Components.ThemeManager.cardColor
                                radius: Components.ThemeManager.radiusSm
                                border.color: Components.ThemeManager.borderLight
                                border.width: 1

                                RowLayout {
                                    anchors.fill: parent
                                    anchors.leftMargin: Components.ThemeManager.spaceMd
                                    anchors.rightMargin: Components.ThemeManager.spaceXs
                                    spacing: Components.ThemeManager.spaceSm

                                    Label {
                                        text: index + 1
                                        font.family: Components.ThemeManager.fontMedium
                                        font.pixelSize: Components.ThemeManager.fontSizeCaption
                                        color: Components.ThemeManager.textTertiary
                                        Layout.preferredWidth: 20
                                        horizontalAlignment: Text.AlignRight
                                    }

                                    Label {
                                        text: modelData
                                        font.family: Components.ThemeManager.fontBody
                                        font.pixelSize: 13
                                        color: Components.ThemeManager.textPrimary
                                        Layout.fillWidth: true
                                        elide: Text.ElideRight
                                    }

                                    // Remove pattern
                                    Rectangle {
                                        Layout.preferredWidth: 40
                                        Layout.preferredHeight: 40
                                        radius: 20
                                        color: removePatternArea.pressed ? Components.ThemeManager.pressedColor : "transparent"

                                        Components.Icon {
                                            anchors.centerIn: parent
                                            name: "close"
                                            size: 16
                                            color: Components.ThemeManager.textTertiary
                                        }

                                        MouseArea {
                                            id: removePatternArea
                                            anchors.fill: parent
                                            onClicked: {
                                                removePatternAtIndex(index)
                                            }
                                        }
                                    }
                                }
                            }
                        }

                        // Empty playlist message
                        Item {
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            visible: currentPlaylistPatterns.length === 0

                            Column {
                                anchors.centerIn: parent
                                spacing: Components.ThemeManager.spaceSm

                                Components.Icon {
                                    name: "queue_music"
                                    size: 30
                                    color: Components.ThemeManager.textTertiary
                                    anchors.horizontalCenter: parent.horizontalCenter
                                }

                                Label {
                                    text: "No patterns yet — tap +"
                                    anchors.horizontalCenter: parent.horizontalCenter
                                    color: Components.ThemeManager.textSecondary
                                    font.family: Components.ThemeManager.fontBody
                                    font.pixelSize: Components.ThemeManager.fontSizeBody
                                }
                            }
                        }
                    }
                }

                Rectangle {
                    Layout.fillHeight: true
                    Layout.preferredWidth: 1
                    color: Components.ThemeManager.borderColor
                }

                // Right side - controls
                Rectangle {
                    Layout.fillHeight: true
                    Layout.fillWidth: true
                    color: Components.ThemeManager.backgroundColor

                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: Components.ThemeManager.spaceLg
                        spacing: Components.ThemeManager.spaceMd

                        // Play + shuffle
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: Components.ThemeManager.spaceSm

                            ModernControlButton {
                                Layout.fillWidth: true
                                Layout.preferredHeight: Components.ThemeManager.controlHeight
                                icon: "play_arrow"
                                text: "Weave this playlist"
                                buttonColor: Components.ThemeManager.accent
                                onClicked: {
                                    if (backend) {
                                        backend.executePlaylist(selectedPlaylist, pauseTime, clearPattern, runMode, shuffle)

                                        // Navigate to execution page
                                        if (mainWindow) {
                                            mainWindow.shouldNavigateToExecution = true
                                        }
                                    }
                                }
                            }

                            ChoiceChip {
                                Layout.preferredWidth: 110
                                Layout.preferredHeight: Components.ThemeManager.controlHeight
                                label: "Shuffle"
                                selected: shuffle
                                onClicked: {
                                    // Don't assign directly to shuffle - that breaks the binding.
                                    // Update the backend and let the binding propagate the change.
                                    if (backend) backend.setPlaylistShuffle(!backend.playlistShuffle)
                                }
                            }
                        }

                        // Settings
                        ScrollView {
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            contentWidth: availableWidth
                            clip: true

                            ScrollBar.vertical.policy: ScrollBar.AsNeeded

                            ColumnLayout {
                                width: parent.width
                                spacing: Components.ThemeManager.spaceMd

                                SectionLabel {
                                    text: "Play order"
                                }

                                RowLayout {
                                    Layout.fillWidth: true
                                    spacing: Components.ThemeManager.spaceSm

                                    ChoiceChip {
                                        Layout.fillWidth: true
                                        label: "Loop forever"
                                        selected: runMode === "loop"
                                        onClicked: {
                                            runMode = "loop"
                                            if (backend) backend.setPlaylistRunMode("loop")
                                        }
                                    }

                                    ChoiceChip {
                                        Layout.fillWidth: true
                                        label: "Play once"
                                        selected: runMode === "single"
                                        onClicked: {
                                            runMode = "single"
                                            if (backend) backend.setPlaylistRunMode("single")
                                        }
                                    }
                                }

                                SectionLabel {
                                    Layout.topMargin: Components.ThemeManager.spaceSm
                                    text: "Rest between patterns"
                                }

                                GridLayout {
                                    id: pauseGrid
                                    Layout.fillWidth: true
                                    columns: 6
                                    rowSpacing: Components.ThemeManager.spaceSm
                                    columnSpacing: Components.ThemeManager.spaceSm

                                    property string currentSelection: backend ? backend.getCurrentPauseOption() : "0s"

                                    Connections {
                                        target: backend
                                        function onPauseBetweenPatternsChanged(pause) {
                                            if (backend) {
                                                pauseGrid.currentSelection = backend.getCurrentPauseOption()
                                                pauseTime = backend.pauseBetweenPatterns
                                            }
                                        }
                                    }

                                    Repeater {
                                        model: [
                                            { label: "0 s", option: "0s", seconds: 0 },
                                            { label: "1 m", option: "1 min", seconds: 60 },
                                            { label: "5 m", option: "5 min", seconds: 300 },
                                            { label: "15 m", option: "15 min", seconds: 900 },
                                            { label: "30 m", option: "30 min", seconds: 1800 },
                                            { label: "1 h", option: "1 hour", seconds: 3600 },
                                            { label: "2 h", option: "2 hour", seconds: 7200 },
                                            { label: "3 h", option: "3 hour", seconds: 10800 },
                                            { label: "4 h", option: "4 hour", seconds: 14400 },
                                            { label: "5 h", option: "5 hour", seconds: 18000 },
                                            { label: "6 h", option: "6 hour", seconds: 21600 },
                                            { label: "12 h", option: "12 hour", seconds: 43200 }
                                        ]

                                        ChoiceChip {
                                            required property var modelData

                                            Layout.fillWidth: true
                                            label: modelData.label
                                            selected: pauseGrid.currentSelection === modelData.option

                                            onClicked: {
                                                if (backend) {
                                                    backend.setPauseByOption(modelData.option)
                                                    pauseGrid.currentSelection = modelData.option
                                                    pauseTime = modelData.seconds
                                                }
                                            }
                                        }
                                    }
                                }

                                SectionLabel {
                                    Layout.topMargin: Components.ThemeManager.spaceSm
                                    text: "Clear before each pattern"
                                }

                                GridLayout {
                                    Layout.fillWidth: true
                                    columns: 2
                                    rowSpacing: Components.ThemeManager.spaceSm
                                    columnSpacing: Components.ThemeManager.spaceSm

                                    Repeater {
                                        model: [
                                            { label: "Adaptive clear", value: "adaptive" },
                                            { label: "Clear from center", value: "clear_center" },
                                            { label: "Clear from edge", value: "clear_perimeter" },
                                            { label: "Keep the sand", value: "none" }
                                        ]

                                        ChoiceChip {
                                            required property var modelData

                                            Layout.fillWidth: true
                                            label: modelData.label
                                            selected: clearPattern === modelData.value

                                            onClicked: {
                                                clearPattern = modelData.value
                                                if (backend) backend.setPlaylistClearPattern(modelData.value)
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

    // ==================== Dialogs ====================

    // Create Playlist Dialog
    Popup {
        id: createPlaylistDialog
        modal: true
        x: (parent.width - width) / 2
        y: (parent.height - height) / 2
        width: 340
        height: 210
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside

        background: Rectangle {
            color: Components.ThemeManager.surfaceColor
            radius: Components.ThemeManager.radiusMd
            border.color: Components.ThemeManager.borderColor
            border.width: 1
        }

        contentItem: ColumnLayout {
            anchors.fill: parent
            anchors.margins: Components.ThemeManager.spaceLg
            spacing: Components.ThemeManager.spaceMd

            Label {
                text: "New playlist"
                font.family: Components.ThemeManager.fontDisplay
                font.pixelSize: Components.ThemeManager.fontSizeTitle
                color: Components.ThemeManager.textPrimary
                Layout.alignment: Qt.AlignHCenter
            }

            TextField {
                id: newPlaylistNameField
                Layout.fillWidth: true
                Layout.preferredHeight: 48
                placeholderText: "Playlist name"
                placeholderTextColor: Components.ThemeManager.textTertiary
                font.family: Components.ThemeManager.fontBody
                font.pixelSize: Components.ThemeManager.fontSizeBody
                color: Components.ThemeManager.textPrimary
                verticalAlignment: TextInput.AlignVCenter
                leftPadding: Components.ThemeManager.spaceLg
                rightPadding: Components.ThemeManager.spaceLg

                background: Rectangle {
                    color: Components.ThemeManager.backgroundColor
                    radius: 24
                    border.color: newPlaylistNameField.activeFocus ? Components.ThemeManager.accent
                                                                   : Components.ThemeManager.borderColor
                    border.width: 1
                }

                onAccepted: {
                    if (text.trim().length > 0 && backend) {
                        backend.createPlaylist(text.trim())
                    }
                }
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: Components.ThemeManager.spaceSm

                ModernControlButton {
                    Layout.fillWidth: true
                    Layout.preferredHeight: Components.ThemeManager.touchTarget
                    text: "Cancel"
                    outlined: true
                    buttonColor: Components.ThemeManager.textSecondary
                    onClicked: {
                        newPlaylistNameField.text = ""
                        createPlaylistDialog.close()
                    }
                }

                ModernControlButton {
                    Layout.fillWidth: true
                    Layout.preferredHeight: Components.ThemeManager.touchTarget
                    text: "Create"
                    buttonColor: Components.ThemeManager.accent
                    enabled: newPlaylistNameField.text.trim().length > 0
                    onClicked: {
                        if (backend) {
                            backend.createPlaylist(newPlaylistNameField.text.trim())
                        }
                    }
                }
            }
        }

        onOpened: {
            newPlaylistNameField.text = ""
            newPlaylistNameField.forceActiveFocus()
        }
    }

    // Delete Playlist Confirmation Dialog
    Popup {
        id: deletePlaylistDialog
        modal: true
        x: (parent.width - width) / 2
        y: (parent.height - height) / 2
        width: 340
        height: 200
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside

        background: Rectangle {
            color: Components.ThemeManager.surfaceColor
            radius: Components.ThemeManager.radiusMd
            border.color: Components.ThemeManager.borderColor
            border.width: 1
        }

        contentItem: ColumnLayout {
            anchors.fill: parent
            anchors.margins: Components.ThemeManager.spaceLg
            spacing: Components.ThemeManager.spaceMd

            Label {
                text: "Delete playlist?"
                font.family: Components.ThemeManager.fontDisplay
                font.pixelSize: Components.ThemeManager.fontSizeTitle
                color: Components.ThemeManager.textPrimary
                Layout.alignment: Qt.AlignHCenter
            }

            Label {
                text: "\"" + selectedPlaylist + "\" will be removed from the table. Its patterns stay in your library."
                font.family: Components.ThemeManager.fontBody
                font.pixelSize: Components.ThemeManager.fontSizeBody
                color: Components.ThemeManager.textSecondary
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: Components.ThemeManager.spaceSm

                ModernControlButton {
                    Layout.fillWidth: true
                    Layout.preferredHeight: Components.ThemeManager.touchTarget
                    text: "Cancel"
                    outlined: true
                    buttonColor: Components.ThemeManager.textSecondary
                    onClicked: deletePlaylistDialog.close()
                }

                ModernControlButton {
                    Layout.fillWidth: true
                    Layout.preferredHeight: Components.ThemeManager.touchTarget
                    text: "Delete"
                    buttonColor: Components.ThemeManager.danger
                    onClicked: {
                        if (backend && selectedPlaylist) {
                            backend.deletePlaylist(selectedPlaylist)
                        }
                        deletePlaylistDialog.close()
                    }
                }
            }
        }
    }

    // ==================== Backend Signal Handlers ====================

    Connections {
        target: backend

        function onPlaylistCreated(success, message) {
            if (success) {
                playlistModel.refresh()
            }
            newPlaylistNameField.text = ""
            createPlaylistDialog.close()
        }

        function onPlaylistDeleted(success, message) {
            if (success) {
                playlistModel.refresh()
                showPlaylistList()  // Navigate back to list
            }
        }

        function onPatternAddedToPlaylist(success, message) {
            if (success) {
                playlistModel.refresh()
                // Refresh current playlist patterns if we're viewing one
                if (selectedPlaylist) {
                    currentPlaylistPatterns = playlistModel.getPatternsForPlaylist(selectedPlaylist)
                    currentPlaylistRawPatterns = playlistModel.getRawPatternsForPlaylist(selectedPlaylist)
                }
            }
        }

        function onPlaylistModified(success, message) {
            if (success) {
                playlistModel.refresh()
                // Refresh current playlist patterns
                if (selectedPlaylist) {
                    currentPlaylistPatterns = playlistModel.getPatternsForPlaylist(selectedPlaylist)
                    currentPlaylistRawPatterns = playlistModel.getRawPatternsForPlaylist(selectedPlaylist)
                }
            }
        }
    }
}
