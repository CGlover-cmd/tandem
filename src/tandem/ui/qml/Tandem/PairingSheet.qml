import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import Tandem

// PIN pairing, shown over the window. The TV shows a PIN; the user types it here.
Item {
    id: root
    required property QtObject pairing
    property bool demoMode: false

    readonly property string pairingState: pairing.state
    readonly property bool shown: pairingState !== "closed"
    readonly property bool askingForPin: pairingState === "enterPin" || pairingState === "checking"

    visible: opacity > 0
    opacity: shown ? 1 : 0
    Behavior on opacity { NumberAnimation { duration: Theme.durationNormal; easing.type: Easing.OutCubic } }

    onShownChanged: {
        if (shown) {
            pin.clear()
            panel.forceActiveFocus()
        }
    }

    Connections {
        target: root.pairing
        function onStateChanged() {
            if (root.pairingState === "enterPin") {
                if (root.pairing.error !== "")
                    pin.clear()
                pin.forceActiveFocus()
            } else if (root.pairingState === "done" || root.pairingState === "failed") {
                panel.forceActiveFocus()
            }
        }
    }

    // Scrim: dims the window and takes clicks, so the sheet must be answered or cancelled.
    Rectangle {
        anchors.fill: parent
        color: Theme.scrim
        MouseArea {
            anchors.fill: parent
            enabled: root.shown
            acceptedButtons: Qt.AllButtons
        }
    }

    Rectangle {
        id: panel
        anchors.centerIn: parent
        width: Math.min(420, root.width - 2 * Theme.space5)
        height: column.implicitHeight + 2 * Theme.space6
        radius: Theme.radiusSheet
        color: Theme.sheet
        border.color: Theme.hairline
        border.width: 1
        scale: root.shown ? 1 : 0.92
        Behavior on scale {
            enabled: !Theme.reduceMotion
            SpringAnimation { spring: Theme.springStiffness - 0.5; damping: Theme.springDamping; epsilon: 0.001 }
        }

        Accessible.role: Accessible.Dialog
        Accessible.name: title.text

        Keys.onEscapePressed: root.pairing.cancel()
        Keys.onReturnPressed: {
            if (root.pairingState === "done" || root.pairingState === "failed")
                root.pairing.close()
        }

        ColumnLayout {
            id: column
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.margins: Theme.space6
            spacing: Theme.space3

            Rectangle {
                Layout.alignment: Qt.AlignHCenter
                implicitWidth: 56
                implicitHeight: 56
                radius: 28
                color: root.pairingState === "failed" ? Qt.rgba(Theme.danger.r, Theme.danger.g, Theme.danger.b, 0.14)
                                                      : Theme.accentTint
                Text {
                    anchors.centerIn: parent
                    font.family: Theme.iconFamily
                    font.pixelSize: 24
                    color: root.pairingState === "failed" ? Theme.danger : Theme.accent
                    text: root.pairingState === "done" ? Theme.glyphCheck
                          : root.pairingState === "failed" ? Theme.glyphWarning : Theme.glyphTv
                    Accessible.ignored: true
                }
            }

            Label {
                id: title
                Layout.fillWidth: true
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.Wrap
                color: Theme.label
                font.family: Theme.displayFamily
                font.pixelSize: Theme.title
                font.weight: Font.DemiBold
                Accessible.role: Accessible.Heading
                text: root.pairingState === "done" ? qsTr("Paired")
                      : root.pairingState === "failed" ? qsTr("Couldn't pair")
                      : qsTr("Pair with %1").arg(root.pairing.deviceName)
            }

            Label {
                Layout.fillWidth: true
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.Wrap
                color: Theme.secondaryLabel
                text: {
                    switch (root.pairingState) {
                    case "starting": return qsTr("Asking the TV for a PIN…")
                    case "enterPin": return qsTr("Enter the 4-digit PIN shown on your TV.")
                    case "checking": return qsTr("Checking the PIN…")
                    case "done": return qsTr("%1 is ready to use. Tandem will remember it.").arg(root.pairing.deviceName)
                    case "failed": return root.pairing.error
                    default: return ""
                    }
                }
            }

            Spinner {
                Layout.alignment: Qt.AlignHCenter
                Layout.topMargin: Theme.space2
                visible: root.pairingState === "starting"
            }

            // Four digit boxes over an invisible text field, which keeps typing, pasting and
            // screen-reader support.
            Item {
                Layout.alignment: Qt.AlignHCenter
                Layout.topMargin: Theme.space2
                implicitWidth: boxes.implicitWidth
                implicitHeight: boxes.implicitHeight
                visible: root.askingForPin

                TextField {
                    id: pin
                    anchors.fill: parent
                    opacity: 0
                    enabled: root.pairingState === "enterPin"
                    maximumLength: 4
                    inputMethodHints: Qt.ImhDigitsOnly
                    validator: RegularExpressionValidator { regularExpression: /[0-9]{0,4}/ }
                    cursorVisible: false
                    selectByMouse: false
                    background: null
                    Accessible.name: qsTr("PIN")
                    Accessible.description: qsTr("The 4-digit PIN shown on your TV")
                    onTextEdited: {
                        if (text.length === 4)
                            root.pairing.submitPin(text)
                    }
                    onAccepted: root.pairing.submitPin(text)
                }

                Row {
                    id: boxes
                    spacing: Theme.space2 + 2

                    Repeater {
                        model: 4
                        Rectangle {
                            required property int index
                            readonly property bool next: pin.activeFocus && index === Math.min(pin.text.length, 3)
                            width: 52
                            height: 62
                            radius: Theme.radiusMedium
                            color: Theme.fieldFill
                            border.width: next ? 2 : 1
                            border.color: next ? Theme.focusRing : Theme.hairline
                            opacity: pin.enabled ? 1 : 0.6

                            Label {
                                anchors.centerIn: parent
                                text: pin.text.charAt(parent.index)
                                color: Theme.label
                                font.family: Theme.displayFamily
                                font.pixelSize: 28
                                font.weight: Font.DemiBold
                            }
                        }
                    }
                }

                TapHandler { onTapped: pin.forceActiveFocus() }
            }

            Label {
                Layout.fillWidth: true
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.Wrap
                visible: root.askingForPin && root.pairing.error !== ""
                text: root.pairing.error
                color: Theme.danger
                font.pixelSize: Theme.footnote
                Accessible.role: Accessible.AlertMessage
            }

            Label {
                Layout.fillWidth: true
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.Wrap
                visible: root.demoMode && root.askingForPin
                text: qsTr("Demo: any 4 digits work, except 0000.")
                color: Theme.secondaryLabel
                font.pixelSize: Theme.caption
            }

            RowLayout {
                Layout.fillWidth: true
                Layout.topMargin: Theme.space3
                spacing: Theme.space2

                Item { Layout.fillWidth: true }

                PillButton {
                    visible: root.pairingState === "starting" || root.askingForPin
                    text: qsTr("Cancel")
                    onClicked: root.pairing.cancel()
                }
                PillButton {
                    visible: root.askingForPin
                    enabled: root.pairingState === "enterPin" && pin.text.length === 4
                    prominent: true
                    text: qsTr("Continue")
                    onClicked: root.pairing.submitPin(pin.text)
                }
                PillButton {
                    visible: root.pairingState === "done" || root.pairingState === "failed"
                    prominent: root.pairingState === "done"
                    text: root.pairingState === "done" ? qsTr("Done") : qsTr("Close")
                    onClicked: root.pairing.close()
                }

                Item { Layout.fillWidth: true }
            }
        }
    }
}
