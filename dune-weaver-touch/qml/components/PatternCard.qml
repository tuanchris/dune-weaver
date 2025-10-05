import QtQuick 2.15
import QtQuick.Controls 2.15

Rectangle {
    property alias name: nameLabel.text
    property string preview: "" // Disabled property alias to prevent WebP loading
    
    signal clicked()
    
    color: mouseArea.pressed ? "#e0e0e0" : "#f5f5f5"
    radius: 8
    border.color: "#d0d0d0"
    
    Column {
        anchors.fill: parent
        anchors.margins: 10
        spacing: 10
        
        Image {
            id: previewImage
            width: parent.width
            height: parent.height - nameLabel.height - 10
            fillMode: Image.PreserveAspectFit
            source: "" // Disabled to prevent WebP decoding errors on touch display
            
            Rectangle {
                anchors.fill: parent
                color: "#f0f0f0"
                visible: previewImage.status === Image.Error || previewImage.source == ""
                
                Text {
                    anchors.centerIn: parent
                    text: "No Preview"
                    color: "#999"
                }
            }
        }
        
        Label {
            id: nameLabel
            width: parent.width
            elide: Label.ElideRight
            horizontalAlignment: Label.AlignHCenter
            font.pixelSize: 12
        }
    }
    
    MouseArea {
        id: mouseArea
        anchors.fill: parent
        onClicked: parent.clicked()
    }
}