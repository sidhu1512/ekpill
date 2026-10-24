import QtQuick

// A hairline bar or capsule you can drag — the EkPill's slider shape, shared by the
// volume control and the player's seek bar.
Item {
    id: sb

    property real value: 0
    property color fillColor: "#ffffff"
    property color trackColor: Qt.rgba(1, 1, 1, 0.16)
    property real trackHeight: 5
    property bool interactive: true

    property bool dragging: false
    signal moved(real v)

    implicitHeight: Math.max(18, trackHeight)
    implicitWidth: 140

    Rectangle {
        id: track
        anchors.verticalCenter: parent.verticalCenter
        width: parent.width
        height: sb.trackHeight
        radius: height / 2
        color: sb.trackColor
        border.width: sb.trackHeight > 10 ? 1 : 0
        border.color: Qt.rgba(1, 1, 1, 0.08)
        clip: true

        Rectangle {
            id: fill
            width: parent.width * Math.max(0, Math.min(1, sb.value))
            height: parent.height
            radius: height / 2
            color: sb.fillColor
            Behavior on width {
                enabled: !sb.dragging
                NumberAnimation { duration: 100; easing.type: Easing.OutQuad }
            }
        }

        MouseArea {
            id: ma
            anchors.fill: parent
            anchors.margins: -4
            enabled: sb.interactive
            preventStealing: true
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor

            function apply(mx) {
                var local = ma.mapToItem(track, mx, 0).x;
                sb.moved(Math.max(0, Math.min(1, local / track.width)));
            }

            onPressed: function (m) { sb.dragging = true; apply(m.x); }
            onPositionChanged: function (m) { if (pressed) apply(m.x); }
            onReleased: sb.dragging = false
            onCanceled: sb.dragging = false
        }
    }
}
