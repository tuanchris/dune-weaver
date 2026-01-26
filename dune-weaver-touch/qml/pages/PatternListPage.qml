import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import "../components"
import "../components" as Components

Page {
    id: page
    
    header: ToolBar {
        RowLayout {
            anchors.fill: parent
            anchors.margins: 10
            
            TextField {
                id: searchField
                Layout.fillWidth: true
                placeholderText: "Search patterns..."
                placeholderTextColor: Components.ThemeManager.textTertiary
                color: Components.ThemeManager.textPrimary
                onTextChanged: patternModel.filter(text)
                font.pixelSize: 16
            }
            
            Button {
                text: "Playlists"
                Layout.preferredHeight: 50
                font.pixelSize: 16
                onClicked: stackView.push("PlaylistPage.qml")
            }
        }
    }
    
    GridView {
        id: gridView
        anchors.fill: parent
        anchors.margins: 10
        cellWidth: 200
        cellHeight: 250
        model: patternModel
        
        delegate: PatternCard {
            width: gridView.cellWidth - 10
            height: gridView.cellHeight - 10
            name: model.name
            preview: model.preview
            
            onClicked: {
                stackView.push("PatternDetailPage.qml", {
                    patternName: model.name,
                    patternPath: model.path,
                    patternPreview: model.preview
                })
            }
        }
    }
    
    BusyIndicator {
        anchors.centerIn: parent
        running: patternModel.rowCount() === 0
        visible: running
    }
    
    Label {
        anchors.centerIn: parent
        text: "No patterns found"
        visible: patternModel.rowCount() === 0 && searchField.text !== ""
        color: "#999"
        font.pixelSize: 18
    }
}