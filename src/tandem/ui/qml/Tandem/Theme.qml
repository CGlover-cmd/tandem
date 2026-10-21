pragma Singleton
import QtQuick

// Design tokens. Every colour, size and timing in the UI comes from here.
// Text colours meet WCAG AA (4.5:1) on the surfaces they sit on; tests/ui checks this.
QtObject {
    // Follows Windows. Writable so an appearance setting (and tests) can override it.
    property bool dark: Qt.styleHints.colorScheme === Qt.ColorScheme.Dark
    // Set from Windows' "Animation effects" setting at startup.
    property bool reduceMotion: false

    // Type: Segoe UI Variable on Windows 11, Segoe UI on Windows 10.
    readonly property var _families: Qt.fontFamilies()
    readonly property string textFamily: _families.indexOf("Segoe UI Variable Text") >= 0
                                         ? "Segoe UI Variable Text" : "Segoe UI"
    readonly property string displayFamily: _families.indexOf("Segoe UI Variable Display") >= 0
                                            ? "Segoe UI Variable Display" : "Segoe UI"
    readonly property string iconFamily: _families.indexOf("Segoe Fluent Icons") >= 0
                                         ? "Segoe Fluent Icons" : "Segoe MDL2 Assets"
    readonly property int largeTitle: 28
    readonly property int title: 22
    readonly property int headline: 15
    readonly property int body: 14
    readonly property int footnote: 13
    readonly property int caption: 12

    // Icon glyphs (Segoe Fluent Icons / MDL2 Assets code points).
    readonly property string glyphTv: ""
    readonly property string glyphSpeaker: ""
    readonly property string glyphMusic: ""
    readonly property string glyphDevice: ""
    readonly property string glyphCheck: ""
    readonly property string glyphWarning: ""

    // Shape and spacing.
    readonly property int radiusSmall: 8
    readonly property int radiusMedium: 12
    readonly property int radiusLarge: 20
    readonly property int radiusSheet: 28
    readonly property int space1: 4
    readonly property int space2: 8
    readonly property int space3: 12
    readonly property int space4: 16
    readonly property int space5: 24
    readonly property int space6: 32

    // Motion. Springs are used for things the user touches; easing for things that appear.
    readonly property int durationFast: reduceMotion ? 0 : 140
    readonly property int durationNormal: reduceMotion ? 0 : 240
    readonly property real springStiffness: 4.0
    readonly property real springDamping: 0.32

    // Colour.
    readonly property color windowTop: dark ? "#1C1C1E" : "#F5F5F7"
    readonly property color windowBottom: dark ? "#111114" : "#E9ECF2"
    readonly property color blobA: dark ? Qt.rgba(0.04, 0.52, 1.0, 0.16) : Qt.rgba(0.0, 0.48, 1.0, 0.16)
    readonly property color blobB: dark ? Qt.rgba(0.75, 0.35, 0.95, 0.16) : Qt.rgba(0.69, 0.32, 0.87, 0.10)
    readonly property color surface: dark ? Qt.rgba(0.17, 0.17, 0.18, 0.72) : Qt.rgba(1, 1, 1, 0.72)
    readonly property color surfaceHover: dark ? Qt.rgba(0.20, 0.20, 0.21, 0.78) : Qt.rgba(1, 1, 1, 0.90)
    readonly property color sheet: dark ? Qt.rgba(0.16, 0.16, 0.17, 0.94) : Qt.rgba(1, 1, 1, 0.94)
    readonly property color scrim: dark ? Qt.rgba(0, 0, 0, 0.45) : Qt.rgba(0, 0, 0, 0.18)
    readonly property color hairline: dark ? Qt.rgba(1, 1, 1, 0.10) : Qt.rgba(0, 0, 0, 0.08)
    readonly property color shadow: dark ? Qt.rgba(0, 0, 0, 0.45) : Qt.rgba(0.1, 0.12, 0.2, 0.14)
    readonly property color fieldFill: dark ? Qt.rgba(1, 1, 1, 0.08) : Qt.rgba(0, 0, 0, 0.05)

    readonly property color label: dark ? "#F5F5F7" : "#1D1D1F"
    readonly property color secondaryLabel: dark ? "#A1A1A6" : "#5E5E63"
    readonly property color accent: dark ? "#6CB6FF" : "#005EBD"
    readonly property color accentFill: dark ? "#0071E3" : "#0066CC"
    readonly property color accentTint: dark ? Qt.rgba(0.30, 0.64, 1.0, 0.13) : Qt.rgba(0.0, 0.40, 0.80, 0.10)
    readonly property color accentTintPressed: dark ? Qt.rgba(0.30, 0.64, 1.0, 0.26) : Qt.rgba(0.0, 0.40, 0.80, 0.18)
    readonly property color textOnAccent: "#FFFFFF"
    readonly property color success: dark ? "#30D158" : "#1E7A34"
    readonly property color warning: dark ? "#FF9F0A" : "#B25000"
    readonly property color danger: dark ? "#FF7B73" : "#D70015"
    readonly property color focusRing: accent
}
