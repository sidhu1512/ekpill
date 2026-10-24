import QtQuick
import QtQuick.Layouts
import ".."   // Glyph lives in the parent directory

// Power menu — sleep, lock, log out, restart, shut down, in the same capsule.
Item {
    id: page
    property var ekpill
    property string pendingAction: ""

    Timer {
        id: resetTimer
        interval: 3500
        onTriggered: page.pendingAction = ""
    }

    readonly property int pad: 14
    implicitWidth: 340
    implicitHeight: 120

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: page.pad
        spacing: 6

        // Dedicated header row so close button never collides with power tiles
        RowLayout {
            Layout.fillWidth: true
            Layout.rightMargin: (page.ekpill && page.ekpill.pinned) ? 36 : 0

            Text {
                text: "Power"
                color: page.ekpill ? page.ekpill.colFg : "#ffffff"
                font { family: page.ekpill ? page.ekpill.fontFam : "Segoe UI"; pixelSize: 12; bold: true }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 8

            Repeater {
                model: [
                    { glyph: "\uE72E", label: "Lock",     action: "lock" },     // lock
                    { glyph: "\uE708", label: "Sleep",    action: "sleep" },    // quiet hours
                    { glyph: "\uE77B", label: "Sign out", action: "signout" },  // contact
                    { glyph: "\uE72C", label: "Restart",  action: "restart" },  // refresh
                    { glyph: "\uE7E8", label: "Shut",     action: "shutdown" }  // power
                ]

                delegate: Item {
                    required property var modelData
                    readonly property bool isPending: page.pendingAction === modelData.action
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    scale: powerMa.pressed ? 0.94 : 1.0
                    Behavior on scale { NumberAnimation { duration: 90; easing.type: Easing.OutQuad } }

                    Rectangle {
                        anchors.fill: parent
                        radius: 12
                        color: isPending ? Qt.rgba(1, 0.2, 0.2, 0.22)
                                         : (hover.hovered ? (page.ekpill ? page.ekpill.colTile : Qt.rgba(1, 1, 1, 0.08)) : Qt.rgba(1, 1, 1, 0.04))
                        border.width: isPending ? 1 : 0
                        border.color: page.ekpill ? page.ekpill.colCrit : "#ef4444"
                        Behavior on color { ColorAnimation { duration: 140 } }
                    }

                    ColumnLayout {
                        anchors.centerIn: parent
                        spacing: 4

                        Glyph {
                            Layout.alignment: Qt.AlignHCenter
                            glyph: modelData.glyph
                            size: 18
                            fontFam: page.ekpill ? page.ekpill.iconFam : "Segoe Fluent Icons"
                            color: isPending ? (page.ekpill ? page.ekpill.colCrit : "#ef4444")
                                             : (modelData.action === "shutdown" ? (page.ekpill ? page.ekpill.colCrit : "#ef4444") : (page.ekpill ? page.ekpill.colFg : "#ffffff"))
                        }

                        Text {
                            Layout.alignment: Qt.AlignHCenter
                            text: isPending ? "Confirm?" : modelData.label
                            color: isPending ? (page.ekpill ? page.ekpill.colCrit : "#ef4444") : (page.ekpill ? page.ekpill.colMuted : "#8e8e93")
                            font { family: page.ekpill ? page.ekpill.fontFam : "Segoe UI"; pixelSize: 10; bold: isPending }
                        }
                    }

                    HoverHandler { id: hover }

                    MouseArea {
                        id: powerMa
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        onClicked: {
                            if (modelData.action === "lock" || modelData.action === "sleep") {
                                page.ekpill.closeAll();
                                backend.powerAction(modelData.action);
                                return;
                            }
                            if (page.pendingAction === modelData.action) {
                                page.pendingAction = "";
                                page.ekpill.closeAll();
                                backend.powerAction(modelData.action);
                            } else {
                                page.pendingAction = modelData.action;
                                resetTimer.restart();
                            }
                        }
                    }
                }
            }
        }
    }
}
