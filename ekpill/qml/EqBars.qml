import QtQuick

// A few bars that breathe while something is playing — the EkPill's "live"
// signal, in place of an album-art thumbnail.
Item {
    id: eq

    property bool active: true
    property color barColor: "#ffffff"
    property int barCount: 4
    property real barWidth: 2.5
    property real gap: 2
    property real maxHeight: 14

    implicitWidth: barCount * barWidth + (barCount - 1) * gap
    implicitHeight: maxHeight

    Row {
        anchors.verticalCenter: parent.verticalCenter
        spacing: eq.gap

        Repeater {
            model: eq.barCount

            Rectangle {
                required property int index
                width: eq.barWidth
                radius: width / 2
                color: eq.barColor
                height: eq.active
                        ? eq.maxHeight * (0.35 + 0.65 * Math.abs(Math.sin(phase + index * 0.9)))
                        : eq.barWidth
                anchors.verticalCenter: parent.verticalCenter

                // Each bar gets its own phase and speed so the group never
                // settles into a visible loop.
                readonly property real speed: 2.2 + index * 0.35
                NumberAnimation on phase {
                    running: eq.active
                    from: 0
                    to: 2 * Math.PI
                    duration: 1100 / (1 + index * 0.15)
                    loops: Animation.Infinite
                }
                property real phase: index * 0.7

                Behavior on height {
                    NumberAnimation { duration: 160; easing.type: Easing.InOutSine }
                }
            }
        }
    }
}
