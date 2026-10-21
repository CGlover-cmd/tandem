import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Effects
import QtQuick.Layouts
import Tandem

// One device in the grid. The whole card is a single button: its action depends on the state.
Item {
    id: root
    required property int index
    required property string deviceId
    required property string name
    required property string kind
    required property string linkState
    required property bool needsPairing
    required property real retryIn
    signal activated()

    readonly property bool busy: linkState === "connecting"
    readonly property bool hovered: hover.hovered

    readonly property string kindText: {
        switch (kind) {
        case "apple_tv": return qsTr("Apple TV")
        case "homepod": return qsTr("HomePod")
        case "receiver": return qsTr("Speaker")
        default: return qsTr("Device")
        }
    }
    readonly property string glyph: {
        switch (kind) {
        case "apple_tv": return Theme.glyphTv
        case "homepod": return Theme.glyphSpeaker
        case "receiver": return Theme.glyphMusic
        default: return Theme.glyphDevice
        }
    }
    readonly property string statusText: {
        if (needsPairing) return qsTr("Needs pairing")
        switch (linkState) {
        case "connecting": return qsTr("Connecting…")
        case "connected": return qsTr("Connected")
        case "waiting": return retryIn > 0 ? qsTr("Retrying in %1 s").arg(Math.ceil(retryIn))
                                           : qsTr("Retrying…")
        case "failed": return qsTr("Couldn't connect")
        default: return qsTr("Not connected")
        }
    }
    readonly property color statusColor: {
        if (needsPairing) return Theme.accent
        switch (linkState) {
        case "connected": return Theme.success
        case "connecting": return Theme.accent
        case "waiting": return Theme.warning
        case "failed": return Theme.danger
        default: return Theme.secondaryLabel
        }
    }
    readonly property string actionText: {
        if (needsPairing) return qsTr("Pair")
        switch (linkState) {
        case "connected": return qsTr("Disconnect")
        case "waiting": return qsTr("Cancel")
        case "failed": return qsTr("Try again")
        case "connecting": return ""
        default: return qsTr("Connect")
        }
    }

    focus: GridView.isCurrentItem
    Accessible.role: Accessible.Button
    Accessible.name: name + ", " + kindText + ", " + statusText
    Accessible.description: actionText
    Accessible.focusable: true
    Accessible.onPressAction: if (!busy) root.activated()

    RectangularShadow {
        anchors.fill: card
        radius: card.radius
        scale: card.scale
        offset.y: root.hovered ? 8 : 4
        blur: root.hovered ? 28 : 18
        spread: -6
        color: Theme.shadow
    }

    Rectangle {
        id: card
        anchors.fill: parent
        anchors.margins: Theme.space2
        radius: Theme.radiusLarge
        color: root.hovered ? Theme.surfaceHover : Theme.surface
        border.color: Theme.hairline
        border.width: 1
        scale: tap.pressed ? 0.97 : (root.hovered ? 1.015 : 1)

        Behavior on scale {
            enabled: !Theme.reduceMotion
            SpringAnimation { spring: Theme.springStiffness; damping: Theme.springDamping; epsilon: 0.001 }
        }
        Behavior on color { ColorAnimation { duration: Theme.durationFast } }

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: Theme.space4
            spacing: Theme.space1

            RowLayout {
                Layout.fillWidth: true

                Rectangle {
                    implicitWidth: 44
                    implicitHeight: 44
                    radius: 22
                    color: Theme.accentTint

                    Text {
                        anchors.centerIn: parent
                        text: root.glyph
                        font.family: Theme.iconFamily
                        font.pixelSize: 20
                        color: Theme.accent
                        Accessible.ignored: true
                    }
                }

                Item { Layout.fillWidth: true }

                Spinner {
                    visible: root.busy || root.linkState === "waiting"
                    color: root.statusColor
                }

                PillButton {
                    visible: root.actionText !== ""
                    text: root.actionText
                    prominent: root.needsPairing
                    focusPolicy: Qt.NoFocus
                    Accessible.ignored: true
                    onClicked: {
                        root.GridView.view.currentIndex = root.index
                        root.activated()
                    }
                }
            }

            Item { Layout.fillHeight: true }

            Label {
                Layout.fillWidth: true
                text: root.name
                color: Theme.label
                font.family: Theme.displayFamily
                font.pixelSize: Theme.headline
                font.weight: Font.DemiBold
                elide: Text.ElideRight
            }

            Label {
                Layout.fillWidth: true
                text: root.kindText
                color: Theme.secondaryLabel
                font.pixelSize: Theme.caption
            }

            RowLayout {
                Layout.fillWidth: true
                Layout.topMargin: Theme.space2
                spacing: 6

                Rectangle {
                    implicitWidth: 8
                    implicitHeight: 8
                    radius: 4
                    color: root.statusColor
                }

                Label {
                    Layout.fillWidth: true
                    text: root.statusText
                    color: Theme.secondaryLabel
                    font.pixelSize: Theme.footnote
                    elide: Text.ElideRight
                }
            }
        }

        // Keyboard focus ring.
        Rectangle {
            anchors.fill: parent
            anchors.margins: -3
            radius: parent.radius + 3
            color: "transparent"
            border.width: 2
            border.color: Theme.focusRing
            visible: root.activeFocus && root.GridView.view.keyboardNavigation
        }
    }

    HoverHandler {
        id: hover
        cursorShape: Qt.PointingHandCursor
    }

    TapHandler {
        id: tap
        onTapped: {
            root.GridView.view.currentIndex = root.index
            root.GridView.view.keyboardNavigation = false
            if (!root.busy)
                root.activated()
        }
    }
}
