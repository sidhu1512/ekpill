import QtQuick
import QtQuick.Layouts
import ".."

// Clipboard history — what you copied, newest first, kept by the EkPill
// because Windows hands the Win+V history to nobody.
//
// Tap a row to reuse it (it goes back on the clipboard and rises to the top);
// the ✕ drops one entry. Recording is off until switched on in Settings, so
// this list starts empty and nothing has touched disk before the user asked.
Item {
    id: page
    property var ekpill

    readonly property int pad: 18
    implicitWidth: 380
    implicitHeight: 420

    // A tap is a copy: say so, briefly, where the eye already is.
    property string flash: ""
    Timer {
        id: flashTimer
        interval: 1400
        onTriggered: page.flash = ""
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: page.pad
        spacing: 12

        // ------------------------------------------------------------ header
        RowLayout {
            Layout.fillWidth: true
            Layout.rightMargin: (page.ekpill && page.ekpill.pinned) ? 32 : 0
            spacing: 10

            Text {
                Layout.fillWidth: true
                text: "Clipboard"
                color: page.ekpill.colFg
                font { family: page.ekpill.fontFam; pixelSize: 15; bold: true }
            }

            Text {
                visible: backend.clipEnabled && backend.clipCount > 0
                text: backend.clipCount + (backend.clipCount === 1 ? " entry" : " entries")
                color: page.ekpill.colMuted
                font { family: page.ekpill.fontFam; pixelSize: 11 }
            }

            Text {
                visible: backend.clipEnabled && backend.clipCount > 0
                text: "Clear"
                color: page.ekpill.colMuted
                font { family: page.ekpill.fontFam; pixelSize: 11 }
                MouseArea {
                    anchors.fill: parent
                    anchors.margins: -6
                    cursorShape: Qt.PointingHandCursor
                    onClicked: backend.clearClips()
                }
            }

            Text {
                visible: !backend.clipEnabled
                text: "Off"
                color: page.ekpill.colMuted
                font { family: page.ekpill.fontFam; pixelSize: 11 }
                MouseArea {
                    anchors.fill: parent
                    anchors.margins: -6
                    cursorShape: Qt.PointingHandCursor
                    onClicked: backend.setClipEnabled(true)
                }
            }
        }

        Text {
            Layout.fillWidth: true
            text: page.flash !== "" ? page.flash
                : backend.clipEnabled
                  ? "Text only · " + backend.clipCount + " of 50 kept · in clipboard.json"
                  : "Nothing is recorded or written until this is switched on."
            color: Qt.rgba(1, 1, 1, 0.28)
            elide: Text.ElideRight
            font { family: page.ekpill.fontFam; pixelSize: 10 }
        }

        Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: page.ekpill.colLine }

        // -------------------------------------------------------- empty state
        Item {
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: backend.clipItems.length === 0

            Text {
                anchors.centerIn: parent
                width: parent.width - 8
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.WordWrap
                text: backend.clipEnabled ? "Nothing copied yet."
                                          : "Clipboard history is off."
                color: page.ekpill.colMuted
                font { family: page.ekpill.fontFam; pixelSize: 12 }
            }
        }

        // ------------------------------------------------------------- list
        ListView {
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: backend.clipItems.length > 0
            clip: true
            spacing: 6
            model: backend.clipItems

            delegate: Rectangle {
                required property int index
                required property var modelData

                width: ListView.view.width
                height: 34
                radius: 8
                color: Qt.rgba(1, 1, 1, 0.07)

                Text {
                    id: rowText
                    anchors.left: parent.left
                    anchors.right: rowTime.left
                    anchors.verticalCenter: parent.verticalCenter
                    anchors.leftMargin: 10
                    anchors.rightMargin: 8
                    color: page.ekpill.colFg
                    elide: Text.ElideMiddle
                    maximumLineCount: 1
                    text: modelData.text.replace("\n", " ⏎ ")
                    font { family: page.ekpill.fontFam; pixelSize: 11 }
                }

                Text {
                    id: rowTime
                    anchors.right: rowDrop.left
                    anchors.verticalCenter: parent.verticalCenter
                    anchors.rightMargin: 4
                    text: Qt.formatTime(new Date(modelData.time * 1000), "hh:mm")
                    color: page.ekpill.colMuted
                    font { family: page.ekpill.fontFam; pixelSize: 9 }
                }

                Rectangle {
                    anchors.right: parent.right
                    anchors.rightMargin: 8
                    anchors.verticalCenter: parent.verticalCenter
                    width: 18
                    height: 18
                    radius: 9
                    color: rowDrop.containsMouse ? Qt.rgba(1, 1, 1, 0.15) : "transparent"

                    Glyph {
                        anchors.centerIn: parent
                        glyph: "\uE711"
                        size: 8
                        fontFam: page.ekpill ? page.ekpill.iconFam : "Segoe Fluent Icons"
                        color: rowDrop.containsMouse ? page.ekpill.colFg : page.ekpill.colMuted
                    }

                    MouseArea {
                        id: rowDrop
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: backend.removeClip(index)
                    }
                }

                // The whole row is the reuse gesture; the ✕ above wins on top.
                MouseArea {
                    anchors.fill: parent
                    z: -1
                    cursorShape: Qt.PointingHandCursor
                    onClicked: {
                        backend.copyClip(index);
                        page.flash = "Copied back to the clipboard";
                        flashTimer.restart();
                    }
                }
            }
        }
    }
}