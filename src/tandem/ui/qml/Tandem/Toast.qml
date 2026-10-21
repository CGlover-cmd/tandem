import QtQuick
import QtQuick.Controls.Basic
import Tandem

// A short message at the bottom of the window, e.g. when connecting fails.
Rectangle {
    id: root
    property string text: ""
    signal dismissed()

    readonly property bool shown: text !== ""
    width: Math.min(label.implicitWidth + 2 * Theme.space5, parent ? parent.width - 2 * Theme.space6 : 400)
    height: label.implicitHeight + 2 * Theme.space3
    radius: height / 2
    color: Theme.dark ? "#3A3A3C" : "#1D1D1F"
    opacity: shown ? 1 : 0
    visible: opacity > 0
    Behavior on opacity { NumberAnimation { duration: Theme.durationNormal; easing.type: Easing.OutCubic } }

    Accessible.role: Accessible.AlertMessage
    Accessible.name: text

    Label {
        id: label
        anchors.centerIn: parent
        width: Math.min(implicitWidth, root.width - 2 * Theme.space5)
        text: root.text
        color: "#FFFFFF"
        wrapMode: Text.Wrap
        horizontalAlignment: Text.AlignHCenter
    }

    TapHandler { onTapped: root.dismissed() }

    onTextChanged: if (shown) dismissTimer.restart()

    Timer {
        id: dismissTimer
        interval: 5000
        running: root.shown
        onTriggered: root.dismissed()
    }
}
