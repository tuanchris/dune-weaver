import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import DuneWeaver 1.0

Page {
    header: ToolBar {
        RowLayout {
            anchors.fill: parent
            anchors.margins: 10
            
            Button {
                text: "← Back"
                font.pixelSize: 14
                flat: true
                onClicked: stackView.pop()
            }
            
            Label {
                text: "Playlists"
                Layout.fillWidth: true
                font.pixelSize: 20
                font.bold: true
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
            color: mouseArea.pressed ? "#e0e0e0" : "#f5f5f5"
            radius: 8
            border.color: "#d0d0d0"
            
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
                    }
                    
                    Label {
                        text: model.itemCount + " patterns"
                        color: "#666"
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
        color: "#999"
        font.pixelSize: 18
    }
}