import QtQuick
import QtQuick.Layouts
import ".."   // Glyph / EqBars / SliderBar live in the parent directory

// The player the EkPill becomes the moment something starts playing:
// album art on the left, what it is and where we are in the middle, transport
// and a seek bar you can drag straight on the capsule.
Item {
    id: page
    property var ekpill

    function escapeHandler() {
        if (page.ekpill) {
            page.ekpill.backToQuick();
            return true;
        }
        return false;
    }

    readonly property int pad: 14
    implicitWidth: 372
    implicitHeight: 182

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: page.pad
        spacing: 8

        // ------------------------------------------------------------- header back
        RowLayout {
            Layout.fillWidth: true
            Layout.rightMargin: (page.ekpill && page.ekpill.pinned) ? 32 : 0
            spacing: 6

            Rectangle {
                Layout.preferredWidth: 24
                Layout.preferredHeight: 24
                radius: 12
                color: backMa.pressed ? Qt.rgba(1, 1, 1, 0.16) : (backMa.containsMouse ? Qt.rgba(1, 1, 1, 0.09) : "transparent")
                scale: backMa.pressed ? 0.94 : 1.0
                Behavior on scale { NumberAnimation { duration: 90 } }

                Glyph {
                    anchors.centerIn: parent
                    glyph: "\uE72B"
                    size: 12
                    fontFam: page.ekpill ? page.ekpill.iconFam : "Segoe Fluent Icons"
                    color: page.ekpill ? page.ekpill.colFg : "#ffffff"
                }

                MouseArea {
                    id: backMa
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: if (page.ekpill) page.ekpill.backToQuick()
                }
            }

            Text {
                text: "Now Playing"
                color: page.ekpill ? page.ekpill.colMuted : "#888888"
                font { family: page.ekpill ? page.ekpill.fontFam : "Segoe UI"; pixelSize: 11; bold: true }
                MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    onClicked: if (page.ekpill) page.ekpill.backToQuick()
                }
            }

            Item { Layout.fillWidth: true }

            WaveBars {
                Layout.alignment: Qt.AlignVCenter
                Layout.preferredWidth: 28
                Layout.preferredHeight: 14
                barColor: page.ekpill ? page.ekpill.colFg : "#ffffff"
                active: backend.mediaPlaying
            }
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 16

            // ------------------------------------------------------------ artwork
            Rectangle {
                Layout.preferredWidth: 104
                Layout.preferredHeight: 104
                Layout.alignment: Qt.AlignVCenter
                radius: 16
                color: page.ekpill ? page.ekpill.colTile : Qt.rgba(1, 1, 1, 0.07)
                border.width: 1
                border.color: Qt.rgba(1, 1, 1, 0.10)
                clip: true

                Image {
                    anchors.fill: parent
                    source: backend.mediaArt
                    fillMode: Image.PreserveAspectCrop
                    visible: backend.mediaArt !== ""
                    asynchronous: true
                }

                EqBars {
                    anchors.centerIn: parent
                    visible: backend.mediaArt === ""
                    active: backend.mediaPlaying
                    barColor: page.ekpill ? page.ekpill.colFg : "#ffffff"
                    barCount: 5
                    maxHeight: 40
                }
            }

            // -------------------------------------------------------- title + seek
            ColumnLayout {
                Layout.fillWidth: true
                Layout.alignment: Qt.AlignVCenter
                spacing: 6

                Text {
                    Layout.fillWidth: true
                    text: backend.mediaTitle !== "" ? backend.mediaTitle : "Nothing playing"
                    color: page.ekpill ? page.ekpill.colFg : "#ffffff"
                    elide: Text.ElideRight
                    font { family: page.ekpill ? page.ekpill.fontFam : "Segoe UI"; pixelSize: 15; bold: true }
                }

                Text {
                    Layout.fillWidth: true
                    text: backend.mediaArtist !== "" ? backend.mediaArtist : "System Media Session"
                    color: page.ekpill ? page.ekpill.colMuted : "#8e8e93"
                    elide: Text.ElideRight
                    font { family: page.ekpill ? page.ekpill.fontFam : "Segoe UI"; pixelSize: 11 }
                }

                SliderBar {
                    Layout.fillWidth: true
                    Layout.topMargin: 2
                    value: backend.mediaProgress
                    fillColor: page.ekpill ? page.ekpill.colFg : "#ffffff"
                    onMoved: function (v) { backend.mediaSeekFraction(v); }
                }

                RowLayout {
                    Layout.fillWidth: true

                    Text {
                        text: backend.mediaPositionText
                        color: page.ekpill ? page.ekpill.colMuted : "#8e8e93"
                        font { family: page.ekpill ? page.ekpill.fontFam : "Segoe UI"; pixelSize: 10; bold: true }
                    }

                    Item { Layout.fillWidth: true }

                    Text {
                        text: backend.mediaDurationText
                        color: page.ekpill ? page.ekpill.colMuted : "#8e8e93"
                        font { family: page.ekpill ? page.ekpill.fontFam : "Segoe UI"; pixelSize: 10; bold: true }
                    }
                }

                // --------------------------------------------------------- transport
                RowLayout {
                    Layout.alignment: Qt.AlignHCenter
                    Layout.topMargin: 2
                    spacing: 26

                    Glyph {
                        Layout.alignment: Qt.AlignVCenter
                        glyph: "\uE892"    // previous
                        size: 18
                        fontFam: page.ekpill ? page.ekpill.iconFam : "Segoe Fluent Icons"
                        color: page.ekpill ? page.ekpill.colFg : "#ffffff"
                        MouseArea {
                            anchors.fill: parent
                            anchors.margins: -6
                            cursorShape: Qt.PointingHandCursor
                            onClicked: backend.mediaCommand("prev")
                        }
                    }

                    Glyph {
                        Layout.alignment: Qt.AlignVCenter
                        glyph: backend.mediaPlaying ? "\uE769" : "\uE768"
                        size: 24
                        fontFam: page.ekpill ? page.ekpill.iconFam : "Segoe Fluent Icons"
                        color: page.ekpill ? page.ekpill.colFg : "#ffffff"
                        MouseArea {
                            anchors.fill: parent
                            anchors.margins: -6
                            cursorShape: Qt.PointingHandCursor
                            onClicked: backend.mediaCommand("toggle")
                        }
                    }

                    Glyph {
                        Layout.alignment: Qt.AlignVCenter
                        glyph: "\uE893"    // next
                        size: 18
                        fontFam: page.ekpill ? page.ekpill.iconFam : "Segoe Fluent Icons"
                        color: page.ekpill ? page.ekpill.colFg : "#ffffff"
                        MouseArea {
                            anchors.fill: parent
                            anchors.margins: -6
                            cursorShape: Qt.PointingHandCursor
                            onClicked: backend.mediaCommand("next")
                        }
                    }
                }
            }
        }
    }
}
