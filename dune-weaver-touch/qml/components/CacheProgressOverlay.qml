import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15

// Creative cache progress overlay
Rectangle {
    id: overlay
    anchors.fill: parent
    color: "#F0F4F8"
    z: 1000
    visible: backend && backend.cacheInProgress

    property var backend

    // Animated background gradient
    Rectangle {
        anchors.fill: parent
        gradient: Gradient {
            GradientStop { position: 0.0; color: "#E0E7FF" }
            GradientStop { position: 1.0; color: "#F0F4F8" }
        }

        // Animated floating particles
        Repeater {
            model: 15
            Rectangle {
                width: Math.random() * 8 + 4
                height: width
                radius: width / 2
                color: Qt.rgba(0.3, 0.5, 0.8, 0.3)
                x: Math.random() * overlay.width
                y: Math.random() * overlay.height

                SequentialAnimation on y {
                    loops: Animation.Infinite
                    running: overlay.visible
                    NumberAnimation {
                        from: Math.random() * overlay.height
                        to: -20
                        duration: Math.random() * 10000 + 8000
                        easing.type: Easing.InOutQuad
                    }
                    NumberAnimation {
                        from: -20
                        to: overlay.height + 20
                        duration: 0
                    }
                }

                SequentialAnimation on opacity {
                    loops: Animation.Infinite
                    running: overlay.visible
                    NumberAnimation { to: 0.6; duration: Math.random() * 2000 + 1000 }
                    NumberAnimation { to: 0.1; duration: Math.random() * 2000 + 1000 }
                }
            }
        }
    }

    ColumnLayout {
        anchors.centerIn: parent
        spacing: 30
        width: Math.min(500, parent.width - 80)

        // Animated icon
        Item {
            Layout.alignment: Qt.AlignHCenter
            width: 120
            height: 120

            // Rotating circles
            Repeater {
                model: 3
                Rectangle {
                    width: 80 - (index * 20)
                    height: width
                    radius: width / 2
                    anchors.centerIn: parent
                    color: "transparent"
                    border.width: 3
                    border.color: Qt.rgba(0.3, 0.5, 0.8, 0.4 - index * 0.1)

                    RotationAnimation on rotation {
                        from: index % 2 === 0 ? 0 : 360
                        to: index % 2 === 0 ? 360 : 0
                        duration: 3000 + (index * 1000)
                        loops: Animation.Infinite
                        running: overlay.visible
                    }
                }
            }

            // Center icon
            Text {
                anchors.centerIn: parent
                text: "🎨"
                font.pixelSize: 48

                SequentialAnimation on scale {
                    loops: Animation.Infinite
                    running: overlay.visible
                    NumberAnimation { to: 1.2; duration: 1000; easing.type: Easing.InOutQuad }
                    NumberAnimation { to: 1.0; duration: 1000; easing.type: Easing.InOutQuad }
                }
            }
        }

        // Creative title with rotating messages
        Column {
            Layout.alignment: Qt.AlignHCenter
            spacing: 12

            Text {
                anchors.horizontalCenter: parent.horizontalCenter
                text: "Setting Up Pattern Previews"
                font.pixelSize: 24
                font.bold: true
                color: "#1E293B"
                horizontalAlignment: Text.AlignHCenter
            }

            Text {
                anchors.horizontalCenter: parent.horizontalCenter
                text: "Generating preview images for your patterns..."
                font.pixelSize: 16
                color: "#64748B"
                horizontalAlignment: Text.AlignHCenter
            }
        }

        // Progress bar
        Column {
            Layout.alignment: Qt.AlignHCenter
            Layout.fillWidth: true
            spacing: 8

            // Progress bar container
            Rectangle {
                width: parent.width
                height: 8
                radius: 4
                color: "#CBD5E1"

                Rectangle {
                    width: parent.width * (backend ? backend.cacheProgress.percentage / 100 : 0)
                    height: parent.height
                    radius: parent.radius
                    color: "#3B82F6"

                    Behavior on width {
                        NumberAnimation { duration: 300; easing.type: Easing.OutQuad }
                    }

                    // Shimmer effect
                    Rectangle {
                        anchors.fill: parent
                        radius: parent.radius
                        gradient: Gradient {
                            orientation: Gradient.Horizontal
                            GradientStop { position: 0.0; color: "transparent" }
                            GradientStop { position: 0.5; color: Qt.rgba(1, 1, 1, 0.3) }
                            GradientStop { position: 1.0; color: "transparent" }
                        }

                        SequentialAnimation on x {
                            loops: Animation.Infinite
                            running: overlay.visible
                            NumberAnimation {
                                from: -parent.width
                                to: parent.width
                                duration: 1500
                            }
                        }
                    }
                }
            }

            // Progress text
            Row {
                anchors.horizontalCenter: parent.horizontalCenter
                spacing: 8

                Text {
                    text: backend ? Math.round(backend.cacheProgress.percentage) + "%" : "0%"
                    font.pixelSize: 14
                    font.bold: true
                    color: "#3B82F6"
                }

                Text {
                    text: "•"
                    font.pixelSize: 14
                    color: "#94A3B8"
                }

                Text {
                    text: backend ? (backend.cacheProgress.current + " of " + backend.cacheProgress.total + " patterns") : "..."
                    font.pixelSize: 14
                    color: "#64748B"
                }
            }
        }

        // Patience message
        Rectangle {
            Layout.alignment: Qt.AlignHCenter
            Layout.preferredWidth: Math.min(400, parent.width)
            Layout.preferredHeight: 80
            color: Qt.rgba(59, 130, 246, 0.1)
            radius: 12
            border.width: 1
            border.color: Qt.rgba(59, 130, 246, 0.2)

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 16
                spacing: 8

                Row {
                    Layout.alignment: Qt.AlignHCenter
                    spacing: 8

                    Text {
                        text: "☕"
                        font.pixelSize: 20
                    }

                    Text {
                        text: "Grab a coffee while we work our magic"
                        font.pixelSize: 14
                        color: "#475569"
                    }
                }

                Text {
                    Layout.alignment: Qt.AlignHCenter
                    text: "This only happens when new patterns are discovered"
                    font.pixelSize: 12
                    color: "#94A3B8"
                    font.italic: true
                }
            }
        }

        // Subtle loading dots
        Row {
            Layout.alignment: Qt.AlignHCenter
            spacing: 8

            Repeater {
                model: 3
                Rectangle {
                    width: 8
                    height: 8
                    radius: 4
                    color: "#3B82F6"

                    SequentialAnimation on opacity {
                        loops: Animation.Infinite
                        running: overlay.visible
                        PauseAnimation { duration: index * 200 }
                        NumberAnimation { to: 0.3; duration: 600 }
                        NumberAnimation { to: 1.0; duration: 600 }
                    }
                }
            }
        }
    }

    // Fade in/out animation
    Behavior on visible {
        PropertyAnimation {
            property: "opacity"
            duration: 300
        }
    }
}
