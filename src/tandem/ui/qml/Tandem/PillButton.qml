import QtQuick
import QtQuick.Controls.Basic
import Tandem

// Rounded button. `prominent` fills it with the accent colour for the main action.
Button {
    id: control
    property bool prominent: false

    font.family: Theme.textFamily
    font.pixelSize: Theme.footnote
    font.weight: Font.DemiBold
    leftPadding: Theme.space4
    rightPadding: Theme.space4
    topPadding: 6
    bottomPadding: 6

    contentItem: Text {
        text: control.text
        font: control.font
        color: control.prominent ? Theme.textOnAccent : Theme.accent
        opacity: control.enabled ? 1 : 0.5
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }

    background: Rectangle {
        implicitHeight: 30
        implicitWidth: 64
        radius: height / 2
        color: control.prominent
               ? (control.down ? Qt.darker(Theme.accentFill, 1.15) : Theme.accentFill)
               : (control.down ? Theme.accentTintPressed : Theme.accentTint)
        opacity: control.enabled ? 1 : 0.5
        border.width: control.visualFocus ? 2 : 0
        border.color: Theme.focusRing
    }

    scale: down ? 0.96 : 1
    Behavior on scale {
        enabled: !Theme.reduceMotion
        SpringAnimation { spring: Theme.springStiffness; damping: Theme.springDamping; epsilon: 0.001 }
    }
}
