import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import DuneWeaver 1.0
import "../components" as Components

Page {
    background: Rectangle {
        color: Components.ThemeManager.backgroundColor
    }

    header: ToolBar {
        background: Rectangle {
            color: Components.ThemeManager.surfaceColor
            border.color: Components.ThemeManager.borderColor
            border.width: 1
        }

        RowLayout {
            anchors.fill: parent
            anchors.margins: 10

            Button {
                text: "← Back"
                font.pixelSize: 14
                flat: true
                onClicked: stackView.pop()
                contentItem: Text {
                    text: parent.text
                    font: parent.font
                    color: Components.ThemeManager.textPrimary
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                }
            }

            Label {
                text: "Playlists"
                Layout.fillWidth: true
                font.pixelSize: 20
                font.bold: true
                color: Components.ThemeManager.textPrimary
            }
        }
    }

    PlaylistModel {
        id: playlistModel
    }

    ListView {
        anchors.fill: parent
        anchors.margins: 20
        model: playlistModel
        spacing: 10

        delegate: Rectangle {
            width: parent.width
            height: 80
            color: mouseArea.pressed ? Components.ThemeManager.buttonBackgroundHover : Components.ThemeManager.cardColor
            radius: 8
            border.color: Components.ThemeManager.borderColor

            RowLayout {
                anchors.fill: parent
                anchors.margins: 15
                spacing: 15

                Column {
                    Layout.fillWidth: true
                    spacing: 5

                    Label {
                        text: model.name
                        font.pixelSize: 16
                        font.bold: true
                        color: Components.ThemeManager.textPrimary
                    }

                    Label {
                        text: model.itemCount + " patterns"
                        color: Components.ThemeManager.textSecondary
                        font.pixelSize: 14
                    }
                }

                Button {
                    text: "Play"
                    Layout.preferredWidth: 80
                    Layout.preferredHeight: 40
                    font.pixelSize: 14
                    enabled: false // TODO: Implement playlist execution
                }
            }

            MouseArea {
                id: mouseArea
                anchors.fill: parent
                onClicked: {
                    // TODO: Navigate to playlist detail page
                }
            }
        }
    }

    Label {
        anchors.centerIn: parent
        text: "No playlists found"
        visible: playlistModel.rowCount() === 0
        color: Components.ThemeManager.textTertiary
        font.pixelSize: 18
    }
}