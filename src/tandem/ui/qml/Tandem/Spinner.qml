import QtQuick
import Tandem

// Activity arc. With reduced motion it stays still; the text beside it says what's happening.
Item {
    id: root
    property bool running: true
    property color color: Theme.accent
    implicitWidth: 18
    implicitHeight: 18
    Accessible.ignored: true

    Canvas {
        id: canvas
        anchors.fill: parent
        onPaint: {
            const ctx = getContext("2d")
            ctx.reset()
            ctx.lineWidth = 2
            ctx.lineCap = "round"
            ctx.strokeStyle = root.color
            ctx.beginPath()
            ctx.arc(width / 2, height / 2, width / 2 - 2, 0, Math.PI * 1.5)
            ctx.stroke()
        }

        RotationAnimator on rotation {
            from: 0
            to: 360
            duration: 900
            loops: Animation.Infinite
            running: root.running && root.visible && !Theme.reduceMotion
        }
    }

    onColorChanged: canvas.requestPaint()
}
