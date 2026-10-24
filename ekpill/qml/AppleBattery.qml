import QtQuick
import QtQuick.Layouts

// Authentic Apple iOS Battery Indicator.
// Features a rounded rectangle shell, attached cathode cap, dynamic fill level,
// crisp typography, and charging lightning bolt.
RowLayout {
    id: battRoot
    spacing: 5

    property int percent: backend.batteryPresent ? backend.batteryPercent : 100
    property bool charging: backend.batteryCharging
    property bool present: backend.batteryPresent
    property bool showPercent: true
    property int batteryWidth: 20
    property int batteryHeight: 10
    property string fontFam: "Segoe UI"
    property color textColor: (!present) ? Qt.rgba(1, 1, 1, 0.55)
                            : (percent <= 20 && !charging ? "#ff453a" : Qt.rgba(1, 1, 1, 0.90))

    implicitWidth: (showPercent ? (percLabel.implicitWidth + spacing) : 0) + battShape.implicitWidth
    implicitHeight: Math.max(batteryHeight, showPercent ? percLabel.implicitHeight : 0)

    // Percentage Label (Native Apple order: percentage precedes battery capsule, e.g. "85% [==|]")
    Text {
        id: percLabel
        visible: battRoot.showPercent
        Layout.alignment: Qt.AlignVCenter
        text: battRoot.present ? (battRoot.percent + "%") : "AC"
        color: battRoot.textColor
        font {
            family: battRoot.fontFam
            pixelSize: 10
            bold: true
        }
    }

    // Battery Shell and Fill
    Item {
        id: battShape
        implicitWidth: battRoot.batteryWidth + 3
        implicitHeight: battRoot.batteryHeight
        Layout.preferredWidth: implicitWidth
        Layout.preferredHeight: implicitHeight
        Layout.alignment: Qt.AlignVCenter

        // Outer rounded body
        Rectangle {
            id: battBody
            anchors.left: parent.left
            anchors.verticalCenter: parent.verticalCenter
            width: battRoot.batteryWidth
            height: battRoot.batteryHeight
            radius: 3
            color: "transparent"
            border.width: 1
            border.color: (battRoot.present && battRoot.percent <= 20 && !battRoot.charging)
                          ? Qt.rgba(1.0, 0.27, 0.23, 0.70)
                          : Qt.rgba(1, 1, 1, 0.40)

            // Dynamic Fill Bar
            Rectangle {
                id: battFill
                anchors.left: parent.left
                anchors.top: parent.top
                anchors.bottom: parent.bottom
                anchors.margins: 1.5
                radius: 1.5
                visible: battRoot.present && battRoot.percent > 0
                width: Math.max(2, Math.round((parent.width - 3) * Math.min(1.0, Math.max(0.04, battRoot.percent / 100.0))))
                color: battRoot.charging ? "#30d158"
                     : (battRoot.percent <= 20 ? "#ff453a" : "#ffffff")

                Behavior on width {
                    NumberAnimation { duration: 220; easing.type: Easing.OutQuad }
                }
            }

            // Charging lightning bolt icon (crisp vector Canvas)
            Canvas {
                id: boltCanvas
                anchors.centerIn: parent
                width: 7
                height: 9
                visible: battRoot.charging
                renderTarget: Canvas.Image

                onPaint: {
                    var ctx = getContext("2d");
                    ctx.clearRect(0, 0, width, height);
                    ctx.fillStyle = (battRoot.percent >= 55) ? "#000000" : "#ffffff";
                    ctx.beginPath();
                    // Sharp Apple lightning bolt shape
                    ctx.moveTo(4.2, 0);
                    ctx.lineTo(1.2, 4.8);
                    ctx.lineTo(3.8, 4.8);
                    ctx.lineTo(2.2, 9.0);
                    ctx.lineTo(6.5, 3.8);
                    ctx.lineTo(3.8, 3.8);
                    ctx.closePath();
                    ctx.fill();
                }

                Connections {
                    target: battRoot
                    function onPercentChanged() { boltCanvas.requestPaint(); }
                    function onChargingChanged() { boltCanvas.requestPaint(); }
                }
            }
        }

        // Terminal cathode cap (directly attached to the right edge of battBody)
        Rectangle {
            anchors.left: battBody.right
            anchors.leftMargin: 1
            anchors.verticalCenter: battBody.verticalCenter
            width: 1.5
            height: Math.max(3, Math.round(battRoot.batteryHeight * 0.42))
            radius: 0.75
            color: (battRoot.present && battRoot.percent <= 20 && !battRoot.charging)
                   ? Qt.rgba(1.0, 0.27, 0.23, 0.70)
                   : Qt.rgba(1, 1, 1, 0.40)
        }
    }
}
