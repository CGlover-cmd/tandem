import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Effects
import QtQuick.Layouts
import Tandem

ApplicationWindow {
    id: window
    required property QtObject app

    width: 980
    height: 660
    minimumWidth: 560
    minimumHeight: 440
    visible: true
    title: qsTr("Tandem")
    color: Theme.windowBottom
    font.family: Theme.textFamily
    font.pixelSize: Theme.body

    Component.onCompleted: Theme.reduceMotion = app.reduceMotion

    // Closing the window keeps Tandem in the tray when there is one.
    onClosing: (close) => {
        close.accepted = false
        if (app.canHideToTray) {
            window.hide()
            app.windowHidden()
        } else {
            app.requestQuit()
        }
    }

    readonly property int deviceCount: app.devices.count

    // Backdrop: a soft gradient with blurred colour washes, seen through translucent surfaces.
    Rectangle {
        anchors.fill: parent
        gradient: Gradient {
            GradientStop { position: 0; color: Theme.windowTop }
            GradientStop { position: 1; color: Theme.windowBottom }
        }
    }
    Canvas {
        id: washes
        anchors.fill: parent
        onPaint: {
            const ctx = getContext("2d")
            ctx.reset()
            const size = Math.max(width, height)
            function wash(x, y, r, c) {
                const g = ctx.createRadialGradient(x, y, 0, x, y, r)
                g.addColorStop(0, c)
                g.addColorStop(1, Qt.rgba(c.r, c.g, c.b, 0))
                ctx.fillStyle = g
                ctx.fillRect(0, 0, width, height)
            }
            wash(width * 0.08, height * 0.02, size * 0.62, Theme.blobA)
            wash(width * 0.96, height * 1.02, size * 0.55, Theme.blobB)
        }
        onWidthChanged: requestPaint()
        onHeightChanged: requestPaint()
        Connections {
            target: Theme
            function onDarkChanged() { washes.requestPaint() }
        }
    }

    Item {
        id: content
        anchors.fill: parent
        enabled: !sheet.shown
        layer.enabled: sheet.visible
        layer.effect: MultiEffect { blurEnabled: true; blur: 0.5; blurMax: 32 }

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: Theme.space6
            anchors.bottomMargin: 0
            spacing: Theme.space5

            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.space3

                ColumnLayout {
                    spacing: 2
                    Label {
                        text: qsTr("Devices")
                        color: Theme.label
                        font.family: Theme.displayFamily
                        font.pixelSize: Theme.largeTitle
                        font.weight: Font.Bold
                        Accessible.role: Accessible.Heading
                    }
                    RowLayout {
                        spacing: Theme.space2
                        Spinner {
                            visible: app.discovering
                            implicitWidth: 14
                            implicitHeight: 14
                        }
                        Label {
                            color: Theme.secondaryLabel
                            text: {
                                if (window.deviceCount === 0)
                                    return qsTr("Looking for devices on your network…")
                                const found = window.deviceCount === 1 ? qsTr("1 device")
                                                                       : qsTr("%1 devices").arg(window.deviceCount)
                                return app.discovering ? qsTr("%1, still looking…").arg(found) : found
                            }
                        }
                    }
                }

                Item { Layout.fillWidth: true }

                Rectangle {
                    visible: app.demoMode
                    implicitWidth: demoLabel.implicitWidth + 2 * Theme.space3
                    implicitHeight: demoLabel.implicitHeight + Theme.space2
                    radius: height / 2
                    color: Theme.accentTint
                    Label {
                        id: demoLabel
                        anchors.centerIn: parent
                        text: qsTr("Demo devices")
                        color: Theme.accent
                        font.pixelSize: Theme.caption
                        font.weight: Font.DemiBold
                    }
                }
            }

            GridView {
                id: grid
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.leftMargin: -Theme.space2
                Layout.rightMargin: -Theme.space2
                clip: true
                model: app.devices
                focus: true
                keyNavigationEnabled: true
                // Focus rings show only once the keyboard is used, as in Windows itself.
                property bool keyboardNavigation: false
                Keys.onPressed: (event) => {
                    keyboardNavigation = true
                    event.accepted = false
                }
                boundsBehavior: Flickable.StopAtBounds
                bottomMargin: Theme.space6

                readonly property int columns: Math.max(1, Math.floor(width / 232))
                cellWidth: Math.floor(width / columns)
                cellHeight: 196

                Accessible.role: Accessible.List
                Accessible.name: qsTr("Devices")

                delegate: DeviceCard {
                    width: grid.cellWidth
                    height: grid.cellHeight
                    onActivated: window.app.activate(deviceId)
                }

                Keys.onReturnPressed: if (currentItem) app.activate(currentItem.deviceId)
                Keys.onEnterPressed: if (currentItem) app.activate(currentItem.deviceId)
                Keys.onSpacePressed: if (currentItem) app.activate(currentItem.deviceId)

                add: Transition {
                    enabled: !Theme.reduceMotion
                    NumberAnimation { property: "opacity"; from: 0; to: 1; duration: Theme.durationNormal }
                    NumberAnimation { property: "scale"; from: 0.94; to: 1; duration: Theme.durationNormal; easing.type: Easing.OutBack }
                }
                displaced: Transition {
                    enabled: !Theme.reduceMotion
                    NumberAnimation { properties: "x,y"; duration: Theme.durationNormal; easing.type: Easing.OutCubic }
                }
            }
        }

        // First-run empty state.
        ColumnLayout {
            anchors.centerIn: parent
            visible: window.deviceCount === 0
            spacing: Theme.space2
            Spinner {
                Layout.alignment: Qt.AlignHCenter
                implicitWidth: 28
                implicitHeight: 28
            }
            Label {
                Layout.alignment: Qt.AlignHCenter
                text: qsTr("Looking for devices")
                color: Theme.label
                font.pixelSize: Theme.headline
                font.weight: Font.DemiBold
            }
            Label {
                Layout.alignment: Qt.AlignHCenter
                Layout.maximumWidth: 320
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.Wrap
                text: qsTr("Make sure your PC and your speakers or TV are on the same Wi-Fi network.")
                color: Theme.secondaryLabel
            }
        }
    }

    PairingSheet {
        id: sheet
        anchors.fill: parent
        pairing: window.app.pairing
        demoMode: window.app.demoMode
        onShownChanged: if (!shown) grid.forceActiveFocus()
    }

    Toast {
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottom: parent.bottom
        anchors.bottomMargin: Theme.space5
        text: window.app.message
        onDismissed: window.app.dismissMessage()
    }
}
