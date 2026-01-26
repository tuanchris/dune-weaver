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
    
    // Playlist execution settings
    property real pauseTime: backend ? backend.pauseBetweenPatterns : 0
    property string clearPattern: "adaptive"
    property string runMode: "single"
    property bool shuffle: false
    
    PlaylistModel {
        id: playlistModel
    }
    
    // Update patterns when playlist selection changes
    onSelectedPlaylistChanged: {
        if (selectedPlaylist) {
            currentPlaylistPatterns = playlistModel.getPatternsForPlaylist(selectedPlaylist)
            currentPlaylistRawPatterns = playlistModel.getRawPatternsForPlaylist(selectedPlaylist)
            console.log("Loaded patterns for", selectedPlaylist + ":", currentPlaylistPatterns)
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
    
    // Debug playlist loading
    Component.onCompleted: {
        console.log("ModernPlaylistPage completed, playlist count:", playlistModel.rowCount())
        console.log("showingPlaylistDetail:", showingPlaylistDetail)
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
    Rectangle {
        id: playlistListView
        anchors.fill: parent
        color: Components.ThemeManager.backgroundColor
        visible: !showingPlaylistDetail
        
        ColumnLayout {
            anchors.fill: parent
            spacing: 0
            
            // Header
            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 50
                color: Components.ThemeManager.surfaceColor

                // Bottom border
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
                        text: "Playlists"
                        font.pixelSize: 18
                        font.bold: true
                        color: Components.ThemeManager.textPrimary
                    }

                    Label {
                        text: playlistModel.rowCount() + " playlists"
                        font.pixelSize: 12
                        color: Components.ThemeManager.textTertiary
                    }

                    Item {
                        Layout.fillWidth: true
                    }

                    // Create new playlist button
                    Text {
                        text: "+"
                        font.pixelSize: 32
                        font.bold: true
                        color: createPlaylistMouseArea.pressed ? "#1e40af" : "#2563eb"

                        MouseArea {
                            id: createPlaylistMouseArea
                            anchors.fill: parent
                            anchors.margins: -8  // Increase touch area
                            onClicked: createPlaylistDialog.open()
                        }
                    }
                }
            }
            
            // Playlist List
            ListView {
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.margins: 15
                model: playlistModel
                spacing: 12
                clip: true
                
                ScrollBar.vertical: ScrollBar {
                    active: true
                    policy: ScrollBar.AsNeeded
                }
                
                delegate: Rectangle {
                    width: ListView.view.width
                    height: 80
                    color: Components.ThemeManager.surfaceColor
                    radius: 12
                    border.color: Components.ThemeManager.borderColor
                    border.width: 1
                    
                    // Press animation
                    scale: mouseArea.pressed ? 0.98 : 1.0
                    
                    Behavior on scale {
                        NumberAnimation { duration: 100; easing.type: Easing.OutQuad }
                    }
                    
                    RowLayout {
                        anchors.fill: parent
                        anchors.margins: 20
                        spacing: 15
                        
                        // Icon
                        Rectangle {
                            Layout.preferredWidth: 40
                            Layout.preferredHeight: 40
                            radius: 20
                            color: Components.ThemeManager.darkMode ? "#1e3a5f" : "#e3f2fd"

                            Text {
                                anchors.centerIn: parent
                                text: "♪"
                                font.pixelSize: 18
                                color: "#2196F3"
                            }
                        }
                        
                        // Playlist info
                        Column {
                            Layout.fillWidth: true
                            spacing: 4
                            
                            Label {
                                text: model.name
                                font.pixelSize: 16
                                font.bold: true
                                color: Components.ThemeManager.textPrimary
                                elide: Text.ElideRight
                                width: parent.width
                            }

                            Label {
                                text: model.itemCount + " patterns"
                                color: Components.ThemeManager.textSecondary
                                font.pixelSize: 12
                            }
                        }
                        
                        // Arrow
                        Text {
                            text: "▶"
                            font.pixelSize: 16
                            color: Components.ThemeManager.textTertiary
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
                Rectangle {
                    anchors.fill: parent
                    color: "transparent"
                    visible: playlistModel.rowCount() === 0
                    
                    Column {
                        anchors.centerIn: parent
                        spacing: 15
                        
                        Text {
                            text: "♪"
                            color: Components.ThemeManager.placeholderText
                            font.pixelSize: 64
                            anchors.horizontalCenter: parent.horizontalCenter
                        }

                        Label {
                            text: "No playlists found"
                            anchors.horizontalCenter: parent.horizontalCenter
                            color: Components.ThemeManager.textSecondary
                            font.pixelSize: 18
                        }

                        Label {
                            text: "Create playlists to organize\\nyour pattern collections"
                            anchors.horizontalCenter: parent.horizontalCenter
                            color: Components.ThemeManager.textTertiary
                            font.pixelSize: 14
                            horizontalAlignment: Text.AlignHCenter
                        }
                    }
                }
            }
        }
    }
    
    // Playlist Detail View (shown when a playlist is selected)
    Rectangle {
        id: playlistDetailView
        anchors.fill: parent
        color: Components.ThemeManager.backgroundColor
        visible: showingPlaylistDetail
        
        ColumnLayout {
            anchors.fill: parent
            spacing: 0
            
            // Header with back button
            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 50
                color: Components.ThemeManager.surfaceColor

                // Bottom border
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
                    spacing: 10
                    
                    ConnectionStatus {
                        backend: page.backend
                        Layout.rightMargin: 8
                    }
                    
                    Button {
                        text: "← Back"
                        font.pixelSize: 14
                        flat: true
                        onClicked: showPlaylistList()

                        contentItem: Text {
                            text: parent.text
                            font: parent.font
                            color: Components.ThemeManager.textPrimary
                            horizontalAlignment: Text.AlignHCenter
                            verticalAlignment: Text.AlignVCenter
                        }
                    }
                    
                    Label {
                        text: selectedPlaylist
                        font.pixelSize: 18
                        font.bold: true
                        color: Components.ThemeManager.textPrimary
                        Layout.fillWidth: true
                        elide: Text.ElideRight
                    }

                    Label {
                        text: currentPlaylistPatterns.length + " patterns"
                        font.pixelSize: 12
                        color: Components.ThemeManager.textTertiary
                    }

                    // Delete playlist button
                    Text {
                        text: "✕"
                        font.pixelSize: 20
                        color: deletePlaylistMouseArea.pressed ? "#dc2626" : Components.ThemeManager.textSecondary

                        MouseArea {
                            id: deletePlaylistMouseArea
                            anchors.fill: parent
                            anchors.margins: -8
                            onClicked: deletePlaylistDialog.open()
                        }
                    }
                }
            }
            
            // Content - Pattern list on left, controls on right
            Item {
                Layout.fillWidth: true
                Layout.fillHeight: true
                
                Row {
                    anchors.fill: parent
                    spacing: 0
                    
                    // Left side - Pattern List (40% of width)
                    Rectangle {
                        width: parent.width * 0.4
                        height: parent.height
                        color: Components.ThemeManager.surfaceColor
                        
                        ColumnLayout {
                            anchors.fill: parent
                            anchors.margins: 15
                            spacing: 10

                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 10

                                Label {
                                    text: "Patterns"
                                    font.pixelSize: 14
                                    font.bold: true
                                    color: Components.ThemeManager.textPrimary
                                    Layout.fillWidth: true
                                }

                                // Add pattern button
                                Text {
                                    text: "+"
                                    font.pixelSize: 24
                                    font.bold: true
                                    color: addPatternMouseArea.pressed ? "#1e40af" : "#2563eb"

                                    MouseArea {
                                        id: addPatternMouseArea
                                        anchors.fill: parent
                                        anchors.margins: -8
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

                            ScrollView {
                                Layout.fillWidth: true
                                Layout.fillHeight: true
                                clip: true
                                
                                ListView {
                                    id: patternListView
                                    width: parent.width
                                    model: currentPlaylistPatterns
                                    spacing: 6
                                    
                                    delegate: Rectangle {
                                        width: patternListView.width
                                        height: 40
                                        color: index % 2 === 0 ? Components.ThemeManager.cardColor : Components.ThemeManager.surfaceColor
                                        radius: 6
                                        border.color: Components.ThemeManager.borderColor
                                        border.width: 1

                                        RowLayout {
                                            anchors.fill: parent
                                            anchors.leftMargin: 10
                                            anchors.rightMargin: 5
                                            anchors.topMargin: 4
                                            anchors.bottomMargin: 4
                                            spacing: 6

                                            Label {
                                                text: (index + 1) + "."
                                                font.pixelSize: 11
                                                color: Components.ThemeManager.textSecondary
                                                Layout.preferredWidth: 22
                                            }

                                            Label {
                                                text: modelData
                                                font.pixelSize: 11
                                                color: Components.ThemeManager.textPrimary
                                                Layout.fillWidth: true
                                                elide: Text.ElideRight
                                            }

                                            // Remove pattern button - aligned right
                                            Text {
                                                text: "✕"
                                                font.pixelSize: 16
                                                color: removePatternArea.pressed ? "#ef4444" : Components.ThemeManager.textTertiary
                                                Layout.alignment: Qt.AlignRight | Qt.AlignVCenter

                                                MouseArea {
                                                    id: removePatternArea
                                                    anchors.fill: parent
                                                    anchors.margins: -8  // Increase touch area
                                                    onClicked: {
                                                        removePatternAtIndex(index)
                                                    }
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                            
                            // Empty playlist message
                            Rectangle {
                                Layout.fillWidth: true
                                Layout.fillHeight: true
                                color: "transparent"
                                visible: currentPlaylistPatterns.length === 0
                                
                                Column {
                                    anchors.centerIn: parent
                                    spacing: 10
                                    
                                    Text {
                                        text: "♪"
                                        font.pixelSize: 32
                                        color: Components.ThemeManager.placeholderText
                                        anchors.horizontalCenter: parent.horizontalCenter
                                    }

                                    Label {
                                        text: "Empty playlist"
                                        anchors.horizontalCenter: parent.horizontalCenter
                                        color: Components.ThemeManager.textSecondary
                                        font.pixelSize: 14
                                    }
                                }
                            }
                        }
                    }
                    
                    // Divider
                    Rectangle {
                        width: 1
                        height: parent.height
                        color: Components.ThemeManager.borderColor
                    }

                    // Right side - Full height controls (60% of width)
                    Rectangle {
                        width: parent.width * 0.6 - 1
                        height: parent.height
                        color: Components.ThemeManager.surfaceColor
                        
                        ColumnLayout {
                            anchors.fill: parent
                            anchors.margins: 15
                            spacing: 15
                            
                            Label {
                                text: "Playlist Controls"
                                font.pixelSize: 16
                                font.bold: true
                                color: Components.ThemeManager.textPrimary
                            }
                            
                            // Main execution buttons
                            RowLayout {
                                Layout.fillWidth: true
                                spacing: 10
                                
                                // Play Playlist button
                                Rectangle {
                                    Layout.fillWidth: true
                                    Layout.preferredHeight: 45
                                    radius: 8
                                    color: playMouseArea.pressed ? "#1e40af" : "#2563eb"
                                    
                                    Text {
                                        anchors.centerIn: parent
                                        text: "Play Playlist"
                                        color: "white"
                                        font.pixelSize: 14
                                        font.bold: true
                                    }
                                    
                                    MouseArea {
                                        id: playMouseArea
                                        anchors.fill: parent
                                        onClicked: {
                                            if (backend) {
                                                console.log("Playing playlist:", selectedPlaylist, "with settings:", {
                                                    pauseTime: pauseTime,
                                                    clearPattern: clearPattern,
                                                    runMode: runMode,
                                                    shuffle: shuffle
                                                })
                                                backend.executePlaylist(selectedPlaylist, pauseTime, clearPattern, runMode, shuffle)
                                                
                                                // Navigate to execution page
                                                console.log("🎵 Navigating to execution page after playlist start")
                                                if (mainWindow) {
                                                    console.log("🎵 Setting shouldNavigateToExecution = true")
                                                    mainWindow.shouldNavigateToExecution = true
                                                } else {
                                                    console.log("🎵 ERROR: mainWindow is null, cannot navigate")
                                                }
                                            }
                                        }
                                    }
                                }
                                
                                // Shuffle toggle button
                                Rectangle {
                                    Layout.preferredWidth: 60
                                    Layout.preferredHeight: 45
                                    radius: 8
                                    color: shuffle ? "#2563eb" : "#6b7280"
                                    
                                    Text {
                                        anchors.centerIn: parent
                                        text: "⇄"
                                        color: "white"
                                        font.pixelSize: 16
                                    }
                                    
                                    MouseArea {
                                        id: shuffleMouseArea
                                        anchors.fill: parent
                                        onClicked: {
                                            shuffle = !shuffle
                                            console.log("Shuffle toggled:", shuffle)
                                        }
                                    }
                                }
                            }
                            
                            // Settings section
                            Rectangle {
                                Layout.fillWidth: true
                                Layout.fillHeight: true
                                Layout.minimumHeight: 250
                                radius: 10
                                color: Components.ThemeManager.cardColor
                                border.color: Components.ThemeManager.borderColor
                                border.width: 1

                                ColumnLayout {
                                    anchors.fill: parent
                                    anchors.margins: 15
                                    spacing: 15

                                    Label {
                                        text: "Settings"
                                        font.pixelSize: 14
                                        font.bold: true
                                        color: Components.ThemeManager.textPrimary
                                    }

                                    // Scrollable settings content
                                    ScrollView {
                                        Layout.fillWidth: true
                                        Layout.fillHeight: true
                                        clip: true

                                        ScrollBar.vertical.policy: ScrollBar.AsNeeded

                                        ColumnLayout {
                                            width: parent.width
                                            spacing: 15
                                    
                                    // Run mode
                                    Column {
                                        Layout.fillWidth: true
                                        spacing: 8
                                        
                                        Label {
                                            text: "Run Mode:"
                                            font.pixelSize: 12
                                            color: Components.ThemeManager.textSecondary
                                            font.bold: true
                                        }
                                        
                                        RowLayout {
                                            width: parent.width
                                            spacing: 15
                                            
                                            RadioButton {
                                                id: singleModeRadio
                                                text: "Single"
                                                font.pixelSize: 11
                                                checked: true  // Default
                                                onClicked: {
                                                    runMode = "single"
                                                    console.log("Run mode set to:", runMode)
                                                }

                                                contentItem: Text {
                                                    text: parent.text
                                                    font: parent.font
                                                    color: Components.ThemeManager.textPrimary
                                                    verticalAlignment: Text.AlignVCenter
                                                    leftPadding: parent.indicator.width + parent.spacing
                                                }
                                            }

                                            RadioButton {
                                                id: loopModeRadio
                                                text: "Loop"
                                                font.pixelSize: 11
                                                checked: false
                                                onClicked: {
                                                    runMode = "loop"
                                                    console.log("Run mode set to:", runMode)
                                                }

                                                contentItem: Text {
                                                    text: parent.text
                                                    font: parent.font
                                                    color: Components.ThemeManager.textPrimary
                                                    verticalAlignment: Text.AlignVCenter
                                                    leftPadding: parent.indicator.width + parent.spacing
                                                }
                                            }
                                        }
                                    }
                                    
                                    // Pause Between Patterns
                                    Column {
                                        Layout.fillWidth: true
                                        spacing: 15
                                        
                                        Label {
                                            text: "Pause between patterns:"
                                            font.pixelSize: 12
                                            color: Components.ThemeManager.textSecondary
                                            font.bold: true
                                        }
                                        
                                        // Touch-friendly button row for pause options
                                        RowLayout {
                                            id: pauseGrid
                                            Layout.fillWidth: true
                                            spacing: 8
                                            
                                            property string currentSelection: backend ? backend.getCurrentPauseOption() : "0s"
                                            
                                            // 0s button
                                            Rectangle {
                                                Layout.preferredWidth: 60
                                                Layout.preferredHeight: 40
                                                color: pauseGrid.currentSelection === "0s" ? Components.ThemeManager.selectedBackground : Components.ThemeManager.buttonBackground
                                                border.color: pauseGrid.currentSelection === "0s" ? Components.ThemeManager.selectedBorder : Components.ThemeManager.buttonBorder
                                                border.width: 2
                                                radius: 8

                                                Label {
                                                    anchors.centerIn: parent
                                                    text: "0s"
                                                    font.pixelSize: 12
                                                    font.bold: true
                                                    color: pauseGrid.currentSelection === "0s" ? "white" : Components.ThemeManager.textPrimary
                                                }
                                                
                                                MouseArea {
                                                    anchors.fill: parent
                                                    onClicked: {
                                                        if (backend) {
                                                            backend.setPauseByOption("0s")
                                                            pauseGrid.currentSelection = "0s"
                                                            pauseTime = 0
                                                        }
                                                    }
                                                }
                                            }
                                            
                                            // 1 min button
                                            Rectangle {
                                                Layout.preferredWidth: 60
                                                Layout.preferredHeight: 40
                                                color: pauseGrid.currentSelection === "1 min" ? Components.ThemeManager.selectedBackground : Components.ThemeManager.buttonBackground
                                                border.color: pauseGrid.currentSelection === "1 min" ? Components.ThemeManager.selectedBorder : Components.ThemeManager.buttonBorder
                                                border.width: 2
                                                radius: 8

                                                Label {
                                                    anchors.centerIn: parent
                                                    text: "1m"
                                                    font.pixelSize: 12
                                                    font.bold: true
                                                    color: pauseGrid.currentSelection === "1 min" ? "white" : Components.ThemeManager.textPrimary
                                                }
                                                
                                                MouseArea {
                                                    anchors.fill: parent
                                                    onClicked: {
                                                        if (backend) {
                                                            backend.setPauseByOption("1 min")
                                                            pauseGrid.currentSelection = "1 min"
                                                            pauseTime = 60
                                                        }
                                                    }
                                                }
                                            }
                                            
                                            // 5 min button
                                            Rectangle {
                                                Layout.preferredWidth: 60
                                                Layout.preferredHeight: 40
                                                color: pauseGrid.currentSelection === "5 min" ? Components.ThemeManager.selectedBackground : Components.ThemeManager.buttonBackground
                                                border.color: pauseGrid.currentSelection === "5 min" ? Components.ThemeManager.selectedBorder : Components.ThemeManager.buttonBorder
                                                border.width: 2
                                                radius: 8

                                                Label {
                                                    anchors.centerIn: parent
                                                    text: "5m"
                                                    font.pixelSize: 12
                                                    font.bold: true
                                                    color: pauseGrid.currentSelection === "5 min" ? "white" : Components.ThemeManager.textPrimary
                                                }
                                                
                                                MouseArea {
                                                    anchors.fill: parent
                                                    onClicked: {
                                                        if (backend) {
                                                            backend.setPauseByOption("5 min")
                                                            pauseGrid.currentSelection = "5 min"
                                                            pauseTime = 300
                                                        }
                                                    }
                                                }
                                            }
                                            
                                            // 15 min button
                                            Rectangle {
                                                Layout.preferredWidth: 60
                                                Layout.preferredHeight: 40
                                                color: pauseGrid.currentSelection === "15 min" ? Components.ThemeManager.selectedBackground : Components.ThemeManager.buttonBackground
                                                border.color: pauseGrid.currentSelection === "15 min" ? Components.ThemeManager.selectedBorder : Components.ThemeManager.buttonBorder
                                                border.width: 2
                                                radius: 8

                                                Label {
                                                    anchors.centerIn: parent
                                                    text: "15m"
                                                    font.pixelSize: 12
                                                    font.bold: true
                                                    color: pauseGrid.currentSelection === "15 min" ? "white" : Components.ThemeManager.textPrimary
                                                }
                                                
                                                MouseArea {
                                                    anchors.fill: parent
                                                    onClicked: {
                                                        if (backend) {
                                                            backend.setPauseByOption("15 min")
                                                            pauseGrid.currentSelection = "15 min"
                                                            pauseTime = 900
                                                        }
                                                    }
                                                }
                                            }
                                            
                                            // 30 min button
                                            Rectangle {
                                                Layout.preferredWidth: 60
                                                Layout.preferredHeight: 40
                                                color: pauseGrid.currentSelection === "30 min" ? Components.ThemeManager.selectedBackground : Components.ThemeManager.buttonBackground
                                                border.color: pauseGrid.currentSelection === "30 min" ? Components.ThemeManager.selectedBorder : Components.ThemeManager.buttonBorder
                                                border.width: 2
                                                radius: 8

                                                Label {
                                                    anchors.centerIn: parent
                                                    text: "30m"
                                                    font.pixelSize: 12
                                                    font.bold: true
                                                    color: pauseGrid.currentSelection === "30 min" ? "white" : Components.ThemeManager.textPrimary
                                                }
                                                
                                                MouseArea {
                                                    anchors.fill: parent
                                                    onClicked: {
                                                        if (backend) {
                                                            backend.setPauseByOption("30 min")
                                                            pauseGrid.currentSelection = "30 min"
                                                            pauseTime = 1800
                                                        }
                                                    }
                                                }
                                            }
                                            
                                            // 1 hour button
                                            Rectangle {
                                                Layout.preferredWidth: 60
                                                Layout.preferredHeight: 40
                                                color: pauseGrid.currentSelection === "1 hour" ? Components.ThemeManager.selectedBackground : Components.ThemeManager.buttonBackground
                                                border.color: pauseGrid.currentSelection === "1 hour" ? Components.ThemeManager.selectedBorder : Components.ThemeManager.buttonBorder
                                                border.width: 2
                                                radius: 8

                                                Label {
                                                    anchors.centerIn: parent
                                                    text: "1h"
                                                    font.pixelSize: 12
                                                    font.bold: true
                                                    color: pauseGrid.currentSelection === "1 hour" ? "white" : Components.ThemeManager.textPrimary
                                                }

                                                MouseArea {
                                                    anchors.fill: parent
                                                    onClicked: {
                                                        if (backend) {
                                                            backend.setPauseByOption("1 hour")
                                                            pauseGrid.currentSelection = "1 hour"
                                                            pauseTime = 3600
                                                        }
                                                    }
                                                }
                                            }
                                        }

                                        // Second row for longer hour options
                                        RowLayout {
                                            Layout.fillWidth: true
                                            spacing: 8

                                            // 2h button
                                            Rectangle {
                                                Layout.preferredWidth: 60
                                                Layout.preferredHeight: 40
                                                color: pauseGrid.currentSelection === "2 hour" ? Components.ThemeManager.selectedBackground : Components.ThemeManager.buttonBackground
                                                border.color: pauseGrid.currentSelection === "2 hour" ? Components.ThemeManager.selectedBorder : Components.ThemeManager.buttonBorder
                                                border.width: 2
                                                radius: 8

                                                Label {
                                                    anchors.centerIn: parent
                                                    text: "2h"
                                                    font.pixelSize: 12
                                                    font.bold: true
                                                    color: pauseGrid.currentSelection === "2 hour" ? "white" : Components.ThemeManager.textPrimary
                                                }

                                                MouseArea {
                                                    anchors.fill: parent
                                                    onClicked: {
                                                        if (backend) {
                                                            backend.setPauseByOption("2 hour")
                                                            pauseGrid.currentSelection = "2 hour"
                                                            pauseTime = 7200
                                                        }
                                                    }
                                                }
                                            }

                                            // 3h button
                                            Rectangle {
                                                Layout.preferredWidth: 60
                                                Layout.preferredHeight: 40
                                                color: pauseGrid.currentSelection === "3 hour" ? Components.ThemeManager.selectedBackground : Components.ThemeManager.buttonBackground
                                                border.color: pauseGrid.currentSelection === "3 hour" ? Components.ThemeManager.selectedBorder : Components.ThemeManager.buttonBorder
                                                border.width: 2
                                                radius: 8

                                                Label {
                                                    anchors.centerIn: parent
                                                    text: "3h"
                                                    font.pixelSize: 12
                                                    font.bold: true
                                                    color: pauseGrid.currentSelection === "3 hour" ? "white" : Components.ThemeManager.textPrimary
                                                }

                                                MouseArea {
                                                    anchors.fill: parent
                                                    onClicked: {
                                                        if (backend) {
                                                            backend.setPauseByOption("3 hour")
                                                            pauseGrid.currentSelection = "3 hour"
                                                            pauseTime = 10800
                                                        }
                                                    }
                                                }
                                            }

                                            // 4h button
                                            Rectangle {
                                                Layout.preferredWidth: 60
                                                Layout.preferredHeight: 40
                                                color: pauseGrid.currentSelection === "4 hour" ? Components.ThemeManager.selectedBackground : Components.ThemeManager.buttonBackground
                                                border.color: pauseGrid.currentSelection === "4 hour" ? Components.ThemeManager.selectedBorder : Components.ThemeManager.buttonBorder
                                                border.width: 2
                                                radius: 8

                                                Label {
                                                    anchors.centerIn: parent
                                                    text: "4h"
                                                    font.pixelSize: 12
                                                    font.bold: true
                                                    color: pauseGrid.currentSelection === "4 hour" ? "white" : Components.ThemeManager.textPrimary
                                                }

                                                MouseArea {
                                                    anchors.fill: parent
                                                    onClicked: {
                                                        if (backend) {
                                                            backend.setPauseByOption("4 hour")
                                                            pauseGrid.currentSelection = "4 hour"
                                                            pauseTime = 14400
                                                        }
                                                    }
                                                }
                                            }

                                            // 5h button
                                            Rectangle {
                                                Layout.preferredWidth: 60
                                                Layout.preferredHeight: 40
                                                color: pauseGrid.currentSelection === "5 hour" ? Components.ThemeManager.selectedBackground : Components.ThemeManager.buttonBackground
                                                border.color: pauseGrid.currentSelection === "5 hour" ? Components.ThemeManager.selectedBorder : Components.ThemeManager.buttonBorder
                                                border.width: 2
                                                radius: 8

                                                Label {
                                                    anchors.centerIn: parent
                                                    text: "5h"
                                                    font.pixelSize: 12
                                                    font.bold: true
                                                    color: pauseGrid.currentSelection === "5 hour" ? "white" : Components.ThemeManager.textPrimary
                                                }

                                                MouseArea {
                                                    anchors.fill: parent
                                                    onClicked: {
                                                        if (backend) {
                                                            backend.setPauseByOption("5 hour")
                                                            pauseGrid.currentSelection = "5 hour"
                                                            pauseTime = 18000
                                                        }
                                                    }
                                                }
                                            }

                                            // 6h button
                                            Rectangle {
                                                Layout.preferredWidth: 60
                                                Layout.preferredHeight: 40
                                                color: pauseGrid.currentSelection === "6 hour" ? Components.ThemeManager.selectedBackground : Components.ThemeManager.buttonBackground
                                                border.color: pauseGrid.currentSelection === "6 hour" ? Components.ThemeManager.selectedBorder : Components.ThemeManager.buttonBorder
                                                border.width: 2
                                                radius: 8

                                                Label {
                                                    anchors.centerIn: parent
                                                    text: "6h"
                                                    font.pixelSize: 12
                                                    font.bold: true
                                                    color: pauseGrid.currentSelection === "6 hour" ? "white" : Components.ThemeManager.textPrimary
                                                }

                                                MouseArea {
                                                    anchors.fill: parent
                                                    onClicked: {
                                                        if (backend) {
                                                            backend.setPauseByOption("6 hour")
                                                            pauseGrid.currentSelection = "6 hour"
                                                            pauseTime = 21600
                                                        }
                                                    }
                                                }
                                            }

                                            // 12h button
                                            Rectangle {
                                                Layout.preferredWidth: 60
                                                Layout.preferredHeight: 40
                                                color: pauseGrid.currentSelection === "12 hour" ? Components.ThemeManager.selectedBackground : Components.ThemeManager.buttonBackground
                                                border.color: pauseGrid.currentSelection === "12 hour" ? Components.ThemeManager.selectedBorder : Components.ThemeManager.buttonBorder
                                                border.width: 2
                                                radius: 8

                                                Label {
                                                    anchors.centerIn: parent
                                                    text: "12h"
                                                    font.pixelSize: 12
                                                    font.bold: true
                                                    color: pauseGrid.currentSelection === "12 hour" ? "white" : Components.ThemeManager.textPrimary
                                                }

                                                MouseArea {
                                                    anchors.fill: parent
                                                    onClicked: {
                                                        if (backend) {
                                                            backend.setPauseByOption("12 hour")
                                                            pauseGrid.currentSelection = "12 hour"
                                                            pauseTime = 43200
                                                        }
                                                    }
                                                }
                                            }

                                            // Update selection when backend changes
                                            Connections {
                                                target: backend
                                                function onPauseBetweenPatternsChanged(pause) {
                                                    if (backend) {
                                                        pauseGrid.currentSelection = backend.getCurrentPauseOption()
                                                        pauseTime = backend.pauseBetweenPatterns
                                                    }
                                                }
                                            }
                                        }
                                    }
                                    
                                    // Clear pattern
                                    Column {
                                        Layout.fillWidth: true
                                        spacing: 8
                                        
                                        Label {
                                            text: "Clear Pattern:"
                                            font.pixelSize: 12
                                            color: Components.ThemeManager.textSecondary
                                            font.bold: true
                                        }
                                        
                                        GridLayout {
                                            width: parent.width
                                            columns: 2
                                            columnSpacing: 10
                                            rowSpacing: 5
                                            
                                            RadioButton {
                                                id: adaptiveRadio
                                                text: "Adaptive"
                                                font.pixelSize: 11
                                                checked: true  // Default
                                                onClicked: {
                                                    clearPattern = "adaptive"
                                                    console.log("Clear pattern set to:", clearPattern)
                                                }

                                                contentItem: Text {
                                                    text: parent.text
                                                    font: parent.font
                                                    color: Components.ThemeManager.textPrimary
                                                    verticalAlignment: Text.AlignVCenter
                                                    leftPadding: parent.indicator.width + parent.spacing
                                                }
                                            }

                                            RadioButton {
                                                id: clearCenterRadio
                                                text: "Clear Center"
                                                font.pixelSize: 11
                                                checked: false
                                                onClicked: {
                                                    clearPattern = "clear_center"
                                                    console.log("Clear pattern set to:", clearPattern)
                                                }

                                                contentItem: Text {
                                                    text: parent.text
                                                    font: parent.font
                                                    color: Components.ThemeManager.textPrimary
                                                    verticalAlignment: Text.AlignVCenter
                                                    leftPadding: parent.indicator.width + parent.spacing
                                                }
                                            }

                                            RadioButton {
                                                id: clearEdgeRadio
                                                text: "Clear Edge"
                                                font.pixelSize: 11
                                                checked: false
                                                onClicked: {
                                                    clearPattern = "clear_perimeter"
                                                    console.log("Clear pattern set to:", clearPattern)
                                                }

                                                contentItem: Text {
                                                    text: parent.text
                                                    font: parent.font
                                                    color: Components.ThemeManager.textPrimary
                                                    verticalAlignment: Text.AlignVCenter
                                                    leftPadding: parent.indicator.width + parent.spacing
                                                }
                                            }

                                            RadioButton {
                                                id: noneRadio
                                                text: "None"
                                                font.pixelSize: 11
                                                checked: false
                                                onClicked: {
                                                    clearPattern = "none"
                                                    console.log("Clear pattern set to:", clearPattern)
                                                }

                                                contentItem: Text {
                                                    text: parent.text
                                                    font: parent.font
                                                    color: Components.ThemeManager.textPrimary
                                                    verticalAlignment: Text.AlignVCenter
                                                    leftPadding: parent.indicator.width + parent.spacing
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
        }
    }

    // ==================== Dialogs ====================

    // Create Playlist Dialog
    Popup {
        id: createPlaylistDialog
        modal: true
        x: (parent.width - width) / 2
        y: (parent.height - height) / 2
        width: 320
        height: 200
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside

        background: Rectangle {
            color: Components.ThemeManager.surfaceColor
            radius: 16
            border.color: Components.ThemeManager.borderColor
            border.width: 1
        }

        contentItem: ColumnLayout {
            anchors.fill: parent
            anchors.margins: 20
            spacing: 15

            Label {
                text: "Create New Playlist"
                font.pixelSize: 18
                font.bold: true
                color: Components.ThemeManager.textPrimary
                Layout.alignment: Qt.AlignHCenter
            }

            TextField {
                id: newPlaylistNameField
                Layout.fillWidth: true
                Layout.preferredHeight: 45
                placeholderText: "Enter playlist name..."
                placeholderTextColor: Components.ThemeManager.textTertiary
                font.pixelSize: 14
                color: Components.ThemeManager.textPrimary

                background: Rectangle {
                    color: Components.ThemeManager.backgroundColor
                    radius: 8
                    border.color: newPlaylistNameField.activeFocus ? "#2563eb" : Components.ThemeManager.borderColor
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
                spacing: 10

                // Cancel button
                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 45
                    radius: 8
                    color: cancelCreateArea.pressed ? Components.ThemeManager.buttonBackgroundHover : Components.ThemeManager.cardColor
                    border.color: Components.ThemeManager.borderColor
                    border.width: 1

                    Text {
                        anchors.centerIn: parent
                        text: "Cancel"
                        color: Components.ThemeManager.textPrimary
                        font.pixelSize: 14
                    }

                    MouseArea {
                        id: cancelCreateArea
                        anchors.fill: parent
                        onClicked: {
                            newPlaylistNameField.text = ""
                            createPlaylistDialog.close()
                        }
                    }
                }

                // Create button
                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 45
                    radius: 8
                    color: createArea.pressed ? "#1e40af" : "#2563eb"
                    opacity: newPlaylistNameField.text.trim().length > 0 ? 1.0 : 0.5

                    Text {
                        anchors.centerIn: parent
                        text: "Create"
                        color: "white"
                        font.pixelSize: 14
                        font.bold: true
                    }

                    MouseArea {
                        id: createArea
                        anchors.fill: parent
                        enabled: newPlaylistNameField.text.trim().length > 0
                        onClicked: {
                            if (backend) {
                                backend.createPlaylist(newPlaylistNameField.text.trim())
                            }
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
        width: 320
        height: 180
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside

        background: Rectangle {
            color: Components.ThemeManager.surfaceColor
            radius: 16
            border.color: Components.ThemeManager.borderColor
            border.width: 1
        }

        contentItem: ColumnLayout {
            anchors.fill: parent
            anchors.margins: 20
            spacing: 15

            Label {
                text: "Delete Playlist?"
                font.pixelSize: 18
                font.bold: true
                color: Components.ThemeManager.textPrimary
                Layout.alignment: Qt.AlignHCenter
            }

            Label {
                text: "Are you sure you want to delete\n\"" + selectedPlaylist + "\"?"
                font.pixelSize: 14
                color: Components.ThemeManager.textSecondary
                horizontalAlignment: Text.AlignHCenter
                Layout.alignment: Qt.AlignHCenter
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: 10

                // Cancel button
                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 45
                    radius: 8
                    color: cancelDeleteArea.pressed ? Components.ThemeManager.buttonBackgroundHover : Components.ThemeManager.cardColor
                    border.color: Components.ThemeManager.borderColor
                    border.width: 1

                    Text {
                        anchors.centerIn: parent
                        text: "Cancel"
                        color: Components.ThemeManager.textPrimary
                        font.pixelSize: 14
                    }

                    MouseArea {
                        id: cancelDeleteArea
                        anchors.fill: parent
                        onClicked: deletePlaylistDialog.close()
                    }
                }

                // Delete button
                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 45
                    radius: 8
                    color: confirmDeleteArea.pressed ? "#991b1b" : "#dc2626"

                    Text {
                        anchors.centerIn: parent
                        text: "Delete"
                        color: "white"
                        font.pixelSize: 14
                        font.bold: true
                    }

                    MouseArea {
                        id: confirmDeleteArea
                        anchors.fill: parent
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
    }

    // ==================== Backend Signal Handlers ====================

    Connections {
        target: backend

        function onPlaylistCreated(success, message) {
            console.log("📋 Playlist created:", success, message)
            if (success) {
                playlistModel.refresh()
            }
            newPlaylistNameField.text = ""
            createPlaylistDialog.close()
        }

        function onPlaylistDeleted(success, message) {
            console.log("🗑️ Playlist deleted:", success, message)
            if (success) {
                playlistModel.refresh()
                showPlaylistList()  // Navigate back to list
            }
        }

        function onPatternAddedToPlaylist(success, message) {
            console.log("➕ Pattern added to playlist:", success, message)
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
            console.log("📝 Playlist modified:", success, message)
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