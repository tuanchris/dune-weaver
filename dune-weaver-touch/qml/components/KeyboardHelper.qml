import QtQuick 2.15
import QtQuick.Controls 2.15

// Helper component to ensure virtual keyboard works properly
Item {
    id: keyboardHelper
    
    // Force show keyboard for a specific TextField
    function showKeyboardFor(textField) {
        textField.forceActiveFocus()
        Qt.inputMethod.show()
    }
    
    // Hide keyboard
    function hideKeyboard() {
        Qt.inputMethod.hide()
    }
    
    // Enhanced TextField with proper keyboard support
    component EnhancedTextField: TextField {
        activeFocusOnPress: true
        selectByMouse: true
        
        // Default input hints
        inputMethodHints: Qt.ImhNone
        
        MouseArea {
            anchors.fill: parent
            onPressed: {
                parent.forceActiveFocus()
                Qt.inputMethod.show()
                mouse.accepted = false
            }
        }
        
        onActiveFocusChanged: {
            if (activeFocus) {
                Qt.inputMethod.show()
            }
        }
        
        Keys.onReturnPressed: {
            Qt.inputMethod.hide()
            focus = false
        }
        
        Keys.onEscapePressed: {
            Qt.inputMethod.hide()
            focus = false
        }
    }
    
    // Numeric-only TextField
    component NumericTextField: EnhancedTextField {
        inputMethodHints: Qt.ImhDigitsOnly | Qt.ImhNoPredictiveText
        validator: IntValidator { bottom: 0; top: 9999 }
        
        // Only allow numeric input
        onTextChanged: {
            var numeric = text.replace(/[^0-9]/g, '')
            if (text !== numeric) {
                text = numeric
            }
        }
    }
}