import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import "../components"
import "../components" as Components

// Now Playing — the signature screen. Progress is not a percent bar: it is
// an ember arc traced around the live pattern disc, with the ball as the
// moving endpoint — the interface shows progress the way the machine makes
// it. Plain Canvas drawing only (no effects layers; linuxfb-safe).
Page {
    id: page
    property var backend: null
    property var stackView: null
    property string patternName: ""
    property string patternPreview: ""  // Backend provides this via executionStarted signal

    readonly property bool hasPattern: (backend && backend.currentFile !== "") || patternName !== ""
    readonly property real progressRatio: backend ? backend.progress / 100 : 0
    readonly property bool inPause: backend && backend.pauseRemaining >= 0

    property string displayName: {
        var name = ""
        if (backend && backend.currentFile) name = backend.currentFile
        else if (patternName) name = patternName
        if (!name) return ""
        var parts = name.split('/')
        return parts[parts.length - 1].replace('.thr', '')
    }

    function formatDuration(s) {
        if (s < 0) return ""
        var h = Math.floor(s / 3600)
        var m = Math.floor((s % 3600) / 60)
        var sec = s % 60
        function pad(n) { return (n < 10 ? "0" : "") + n }
        return h > 0 ? h + ":" + pad(m) + ":" + pad(sec) : m + ":" + pad(sec)
    }

    // Direct connection to backend signals
    Connections {
        target: backend

        function onExecutionStarted(fileName, preview) {
            patternName = fileName
            patternPreview = preview
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
                    text: "Now Playing"
                    font.family: Components.ThemeManager.fontDisplay
                    font.pixelSize: Components.ThemeManager.fontSizeTitle
                    color: Components.ThemeManager.textPrimary
                }

                Item {
                    Layout.fillWidth: true
                }
            }
        }

        // Content
        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 0

            // ---- Left: the disc and its progress ring ----
            Item {
                id: stage
                Layout.fillHeight: true
                Layout.preferredWidth: page.width * 0.55

                Item {
                    id: ringWrap
                    anchors.centerIn: parent
                    width: Math.min(stage.width, stage.height) - 2 * Components.ThemeManager.spaceXl
                    height: width

                    // Track + progress arc, redrawn only when progress moves
                    Canvas {
                        id: arcCanvas
                        anchors.fill: parent

                        // While weaving: fraction of the pattern drawn.
                        // Between patterns: the countdown to the next one.
                        property real ratio: {
                            if (inPause)
                                return backend && backend.pauseTotal > 0
                                       ? 1 - backend.pauseRemaining / backend.pauseTotal : 0
                            return hasPattern ? progressRatio : 0
                        }
                        onRatioChanged: requestPaint()
                        Connections {
                            target: Components.ThemeManager
                            function onDarkModeChanged() { arcCanvas.requestPaint() }
                        }

                        onPaint: {
                            var ctx = getContext("2d")
                            var w = width, h = height
                            ctx.clearRect(0, 0, w, h)
                            var cx = w / 2, cy = h / 2
                            var lineW = 5
                            var r = Math.min(w, h) / 2 - lineW / 2
                            if (r <= 0)
                                return  // layout not settled yet

                            ctx.lineWidth = lineW
                            ctx.lineCap = "round"

                            // Track
                            ctx.beginPath()
                            ctx.strokeStyle = String(Components.ThemeManager.cardColor)
                            ctx.arc(cx, cy, r, 0, 2 * Math.PI)
                            ctx.stroke()

                            // Progress, from 12 o'clock
                            if (ratio > 0) {
                                ctx.beginPath()
                                ctx.strokeStyle = String(Components.ThemeManager.accent)
                                ctx.arc(cx, cy, r, -Math.PI / 2,
                                        -Math.PI / 2 + ratio * 2 * Math.PI)
                                ctx.stroke()
                            }
                        }
                    }

                    // The ball: endpoint of the arc (two stacked dots stand in
                    // for a glow — no shadow effects on linuxfb)
                    Item {
                        anchors.fill: parent
                        rotation: arcCanvas.ratio * 360
                        visible: (hasPattern || inPause) && arcCanvas.ratio > 0

                        Rectangle {
                            anchors.horizontalCenter: parent.horizontalCenter
                            y: -7
                            width: 19
                            height: 19
                            radius: 9.5
                            color: Components.ThemeManager.accent
                            opacity: 0.3
                        }
                        Rectangle {
                            anchors.horizontalCenter: parent.horizontalCenter
                            y: -3
                            width: 11
                            height: 11
                            radius: 5.5
                            color: Components.ThemeManager.accent
                        }
                    }

                    // Live pattern disc (the preview PNG is itself a round dish)
                    Image {
                        anchors.fill: parent
                        anchors.margins: 14
                        source: patternPreview ? "file://" + patternPreview : ""
                        fillMode: Image.PreserveAspectFit
                        asynchronous: true
                        visible: hasPattern && status === Image.Ready
                    }

                    // Resting dish when idle (or while the preview renders)
                    Rectangle {
                        anchors.fill: parent
                        anchors.margins: 14
                        radius: width / 2
                        color: Components.ThemeManager.surfaceColor
                        border.width: 1
                        border.color: Components.ThemeManager.borderColor
                        visible: !hasPattern || patternPreview === ""

                        Column {
                            anchors.centerIn: parent
                            spacing: Components.ThemeManager.spaceSm

                            Components.Icon {
                                name: "radio_unchecked"
                                size: 34
                                color: Components.ThemeManager.textTertiary
                                anchors.horizontalCenter: parent.horizontalCenter
                            }

                            Label {
                                text: {
                                    if (inPause) return "Resting between patterns"
                                    return hasPattern ? "Rendering preview" : "The table is resting"
                                }
                                font.family: Components.ThemeManager.fontMedium
                                font.pixelSize: Components.ThemeManager.fontSizeBody
                                color: Components.ThemeManager.textSecondary
                                anchors.horizontalCenter: parent.horizontalCenter
                            }
                        }
                    }
                }
            }

            // ---- Right: name, state, transport, speed ----
            Rectangle {
                Layout.fillHeight: true
                Layout.fillWidth: true
                color: Components.ThemeManager.surfaceColor

                Rectangle {
                    anchors.left: parent.left
                    width: 1
                    height: parent.height
                    color: Components.ThemeManager.borderColor
                }

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: Components.ThemeManager.spaceXl
                    spacing: 0

                    Label {
                        text: inPause ? "Up next" : "Now weaving"
                        font.family: Components.ThemeManager.fontDisplay
                        font.pixelSize: 11
                        font.letterSpacing: 1.6
                        font.capitalization: Font.AllUppercase
                        color: Components.ThemeManager.accent
                    }

                    Label {
                        Layout.fillWidth: true
                        Layout.topMargin: Components.ThemeManager.spaceSm
                        text: {
                            if (inPause && backend && backend.nextPattern)
                                return backend.nextPattern
                            return displayName || "Nothing playing"
                        }
                        font.family: Components.ThemeManager.fontDisplay
                        font.pixelSize: Components.ThemeManager.fontSizeDisplay
                        color: hasPattern || inPause ? Components.ThemeManager.textPrimary
                                                     : Components.ThemeManager.textTertiary
                        elide: Text.ElideRight
                        maximumLineCount: 2
                        wrapMode: Text.Wrap
                    }

                    // Playlist position
                    Label {
                        Layout.fillWidth: true
                        Layout.topMargin: Components.ThemeManager.spaceXs
                        visible: backend && backend.playlistActive && backend.playlistTotal > 0
                        text: {
                            if (!backend) return ""
                            var s = (backend.playlistName ? backend.playlistName + " · " : "")
                                    + (backend.playlistIndex + 1) + " of " + backend.playlistTotal
                            if (backend.playlistClearing) s += " · clearing"
                            return s
                        }
                        font.family: Components.ThemeManager.fontBody
                        font.pixelSize: Components.ThemeManager.fontSizeCaption
                        color: Components.ThemeManager.textSecondary
                        elide: Text.ElideMiddle
                    }

                    // Progress / pause countdown line
                    Label {
                        Layout.fillWidth: true
                        Layout.topMargin: Components.ThemeManager.spaceLg
                        visible: hasPattern || inPause
                        textFormat: Text.StyledText
                        text: {
                            if (!backend) return ""
                            if (inPause)
                                return "<b>" + formatDuration(backend.pauseRemaining)
                                       + "</b> until the next pattern"
                            var pct = Math.round(backend.progress)
                            var s = "<b>" + pct + "%</b> woven"
                            if (backend.isPaused) s += " · paused"
                            return s
                        }
                        font.family: Components.ThemeManager.fontBody
                        font.pixelSize: Components.ThemeManager.fontSizeBody
                        color: Components.ThemeManager.textSecondary
                    }

                    Item { Layout.fillHeight: true }

                    // Transport
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: Components.ThemeManager.spaceSm

                        ModernControlButton {
                            Layout.fillWidth: true
                            Layout.preferredWidth: 3
                            Layout.preferredHeight: Components.ThemeManager.controlHeight
                            icon: (backend && backend.isRunning && !backend.isPaused) ? "pause" : "play_arrow"
                            text: (backend && backend.isRunning && !backend.isPaused) ? "Pause" : "Resume"
                            buttonColor: Components.ThemeManager.accent
                            enabled: backend && backend.currentFile !== ""
                            onClicked: {
                                if (!backend) return
                                if (backend.isPaused) backend.resumeExecution()
                                else backend.pauseExecution()
                            }
                        }

                        ModernControlButton {
                            Layout.fillWidth: true
                            Layout.preferredWidth: 2
                            Layout.preferredHeight: Components.ThemeManager.controlHeight
                            icon: "stop"
                            text: "Stop"
                            outlined: true
                            buttonColor: Components.ThemeManager.danger
                            enabled: backend !== null
                            onClicked: if (backend) backend.stopExecution()
                        }

                        ModernControlButton {
                            Layout.fillWidth: true
                            Layout.preferredWidth: 2
                            Layout.preferredHeight: Components.ThemeManager.controlHeight
                            icon: "skip_next"
                            text: "Skip"
                            buttonColor: Components.ThemeManager.cardColor
                            enabled: backend !== null
                            onClicked: if (backend) backend.skipPattern()
                        }
                    }

                    // Speed
                    Label {
                        Layout.topMargin: Components.ThemeManager.spaceLg
                        text: "Speed · mm/s"
                        font.family: Components.ThemeManager.fontDisplay
                        font.pixelSize: 11
                        font.letterSpacing: 1.4
                        font.capitalization: Font.AllUppercase
                        color: Components.ThemeManager.textTertiary
                    }

                    // Segmented control
                    Rectangle {
                        id: speedSeg
                        Layout.fillWidth: true
                        Layout.topMargin: Components.ThemeManager.spaceSm
                        Layout.preferredHeight: 48
                        radius: height / 2
                        color: Components.ThemeManager.cardColor

                        property string currentSelection: backend ? backend.getCurrentSpeedOption() : "200"

                        Connections {
                            target: backend
                            function onSpeedChanged(speed) {
                                if (backend)
                                    speedSeg.currentSelection = backend.getCurrentSpeedOption()
                            }
                        }

                        Row {
                            anchors.fill: parent
                            anchors.margins: 4
                            spacing: 2

                            Repeater {
                                model: ["50", "100", "150", "200", "300", "500"]

                                Rectangle {
                                    property bool selected: speedSeg.currentSelection === modelData

                                    width: (parent.width - 10) / 6
                                    height: parent.height
                                    radius: height / 2
                                    color: selected ? Components.ThemeManager.backgroundColor : "transparent"
                                    border.width: selected ? 1 : 0
                                    border.color: Components.ThemeManager.borderColor

                                    Label {
                                        anchors.centerIn: parent
                                        text: modelData
                                        font.family: Components.ThemeManager.fontMedium
                                        font.pixelSize: 13
                                        color: parent.selected ? Components.ThemeManager.accent
                                                               : Components.ThemeManager.textSecondary
                                    }

                                    MouseArea {
                                        anchors.fill: parent
                                        onClicked: {
                                            if (backend) {
                                                backend.setSpeedByOption(modelData)
                                                speedSeg.currentSelection = modelData
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
