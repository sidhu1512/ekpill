import QtQuick

// Dynamic reactive audio visualizer wave bars.
// Binds to backend.audioLevels (WASAPI / Core Audio) when active,
// with graceful physical spring animation and fluid decay when paused.
Item {
    id: wave

    property color barColor: "#ffffff"
    property bool  active: true
    property int   barCount: 7
    property real  gap: 2
    property real  maxHeight: height

    // Real-time levels 0..1 from backend
    property var levels: backend.audioLevels

    implicitWidth: barCount * 3 + (barCount - 1) * gap
    implicitHeight: 18

    Row {
        anchors.fill: parent
        spacing: wave.gap

        Repeater {
            model: wave.barCount

            Rectangle {
                required property int index

                width: Math.max(2, (wave.width - wave.gap * (wave.barCount - 1)) / wave.barCount)
                radius: width / 2
                color: wave.barColor
                anchors.verticalCenter: parent.verticalCenter

                // Level computation with power curve (0.6) for natural optical response
                readonly property real lvl: (wave.levels && wave.levels.length > index)
                                            ? wave.levels[index]
                                            : 0.08

                height: Math.max(2, Math.pow(Math.min(1.0, lvl), 0.6) * wave.maxHeight)
                opacity: 0.55 + 0.45 * (height / Math.max(1, wave.maxHeight))

                Behavior on height {
                    SpringAnimation { spring: 4.5; damping: 0.32; epsilon: 0.25 }
                }

                Behavior on opacity {
                    NumberAnimation { duration: 150; easing.type: Easing.OutCubic }
                }
            }
        }
    }
}
