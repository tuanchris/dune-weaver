import QtQuick 2.15
import QtQuick.VirtualKeyboard 2.15
import QtQuick.VirtualKeyboard.Settings 2.15

Item {
    id: keyboardLoader
    
    // Configure keyboard settings
    Component.onCompleted: {
        // Set keyboard style (can be "default", "retro", etc.)
        VirtualKeyboardSettings.styleName = "default"
        
        // Set available locales (languages)
        VirtualKeyboardSettings.activeLocales = ["en_US"]
        
        // Enable word candidate list
        VirtualKeyboardSettings.wordCandidateList.enabled = true
        
        // Set keyboard height (as percentage of screen)
        VirtualKeyboardSettings.fullScreenMode = false
    }
    
    InputPanel {
        id: inputPanel
        z: 99999
        y: window.height
        anchors.left: parent.left
        anchors.right: parent.right
        
        states: State {
            name: "visible"
            when: inputPanel.active
            PropertyChanges {
                target: inputPanel
                y: window.height - inputPanel.height
            }
        }
        
        transitions: Transition {
            from: ""
            to: "visible"
            reversible: true
            ParallelAnimation {
                NumberAnimation {
                    target: inputPanel
                    property: "y"
                    duration: 250
                    easing.type: Easing.InOutQuad
                }
            }
        }
    }
}