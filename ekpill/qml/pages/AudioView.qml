import QtQuick
import QtQuick.Layouts
import ".."

// Per-application WASAPI Audio Mixer & Reactive Output Visualizer.
Item {
    id: page
    property var ekpill

    readonly property int pad: 18
    implicitWidth: 380
    implicitHeight: col.implicitHeight + pad * 2

    Component.onCompleted: backend.refreshAudioStreams()

    ColumnLayout {
        id: col
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.margins: page.pad
        spacing: 12

        // ------------------------------------------------------------ header
        RowLayout {
            Layout.fillWidth: true
            Layout.rightMargin: (page.ekpill && page.ekpill.pinned) ? 28 : 0
            spacing: 10

            Rectangle {
                Layout.preferredWidth: 30
                Layout.preferredHeight: 30
                radius: 10
                color: backMa.containsMouse ? Qt.rgba(1, 1, 1, 0.14) : Qt.rgba(1, 1, 1, 0.06)
                scale: backMa.pressed ? 0.94 : 1.0
                Behavior on color { ColorAnimation { duration: 150 } }
                Behavior on scale { NumberAnimation { duration: 90; easing.type: Easing.OutQuad } }

                Glyph {
                    anchors.centerIn: parent
                    glyph: "\uE72B"   // back
                    size: 14
                    fontFam: page.ekpill ? page.ekpill.iconFam : "Segoe Fluent Icons"
                    color: page.ekpill ? page.ekpill.colFg : "#ffffff"
                }

                MouseArea {
                    id: backMa
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: if (page.ekpill) page.ekpill.openPage("quick")
                }
            }

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 1

                Text {
                    text: "Audio Mixer"
                    color: page.ekpill ? page.ekpill.colFg : "#ffffff"
                    font { family: page.ekpill ? page.ekpill.fontFam : "Segoe UI"; pixelSize: 14; bold: true }
                }

                Text {
                    Layout.fillWidth: true
                    text: backend.audioDeviceName || "Default Output"
                    color: page.ekpill ? page.ekpill.colMuted : "#8e8e93"
                    elide: Text.ElideRight
                    font { family: page.ekpill ? page.ekpill.fontFam : "Segoe UI"; pixelSize: 10 }
                }
            }

            WaveBars {
                Layout.alignment: Qt.AlignVCenter
                Layout.preferredWidth: 34
                Layout.preferredHeight: 18
                barColor: page.ekpill ? page.ekpill.colFg : "#ffffff"
                active: backend.mediaPlaying || backend.audioPeak > 0.01
            }

            Rectangle {
                Layout.preferredWidth: 26
                Layout.preferredHeight: 26
                radius: 8
                color: refMa.containsMouse ? Qt.rgba(1, 1, 1, 0.14) : Qt.rgba(1, 1, 1, 0.05)
                border.width: 1
                border.color: Qt.rgba(1, 1, 1, 0.08)
                scale: refMa.pressed ? 0.92 : 1.0
                Behavior on scale { NumberAnimation { duration: 90 } }

                Glyph {
                    anchors.centerIn: parent
                    glyph: "\uE72C"   // refresh
                    size: 11
                    fontFam: page.ekpill ? page.ekpill.iconFam : "Segoe Fluent Icons"
                    color: page.ekpill ? page.ekpill.colFg : "#ffffff"
                }

                MouseArea {
                    id: refMa
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: backend.refreshAudioStreams()
                }
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 1
            color: page.ekpill ? page.ekpill.colLine : Qt.rgba(1, 1, 1, 0.12)
        }

        // ----------------------------------------------------- Master Output
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 6

            RowLayout {
                Layout.fillWidth: true
                Text {
                    text: "MASTER VOLUME"
                    color: page.ekpill ? page.ekpill.colMuted : "#8e8e93"
                    font { family: page.ekpill ? page.ekpill.fontFam : "Segoe UI"; pixelSize: 9; bold: true; letterSpacing: 1.0 }
                }
                Item { Layout.fillWidth: true }
                Text {
                    text: backend.muted ? "Muted" : Math.round(backend.volume * 100) + "%"
                    color: page.ekpill ? page.ekpill.colFg : "#ffffff"
                    font { family: page.ekpill ? page.ekpill.fontFam : "Segoe UI"; pixelSize: 11; bold: true }
                }
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: 8

                Rectangle {
                    width: 26; height: 26; radius: 8
                    color: masterMuteMa.pressed ? Qt.rgba(1, 1, 1, 0.20)
                         : (masterMuteMa.containsMouse ? Qt.rgba(1, 1, 1, 0.12) : Qt.rgba(1, 1, 1, 0.06))
                    border.width: 1
                    border.color: Qt.rgba(1, 1, 1, 0.09)

                    Glyph {
                        anchors.centerIn: parent
                        glyph: backend.muted ? "\uE74F" : (backend.volume > 0.5 ? "\uE767" : "\uE994")
                        size: 12
                        fontFam: page.ekpill ? page.ekpill.iconFam : "Segoe Fluent Icons"
                        color: backend.muted ? (page.ekpill ? page.ekpill.colMuted : "#8e8e93")
                                             : (page.ekpill ? page.ekpill.colFg : "#ffffff")
                    }

                    MouseArea {
                        id: masterMuteMa
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: backend.toggleMute()
                    }
                }

                SliderBar {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 20
                    trackHeight: 20
                    trackColor: Qt.rgba(1, 1, 1, 0.08)
                    fillColor: Qt.rgba(1, 1, 1, 0.92)
                    value: backend.muted ? 0 : backend.volume
                    onMoved: function(v) {
                        if (backend.muted && v > 0) backend.toggleMute();
                        backend.setVolume(v);
                    }
                }
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 1
            color: page.ekpill ? page.ekpill.colLine : Qt.rgba(1, 1, 1, 0.12)
        }

        // ----------------------------------------------- Application Streams
        RowLayout {
            Layout.fillWidth: true
            Text {
                text: "APP SESSIONS (" + backend.audioStreams.length + ")"
                color: page.ekpill ? page.ekpill.colMuted : "#8e8e93"
                font { family: page.ekpill ? page.ekpill.fontFam : "Segoe UI"; pixelSize: 9; bold: true; letterSpacing: 1.0 }
            }
            Item { Layout.fillWidth: true }
            Text {
                text: "WASAPI Core Audio"
                color: Qt.rgba(1, 1, 1, 0.38)
                font { family: page.ekpill ? page.ekpill.fontFam : "Segoe UI"; pixelSize: 9 }
            }
        }

        // Empty state when no active per-app streams exist
        Rectangle {
            visible: backend.audioStreams.length === 0
            Layout.fillWidth: true
            Layout.preferredHeight: 62
            radius: 12
            color: Qt.rgba(1, 1, 1, 0.04)
            border.width: 1
            border.color: Qt.rgba(1, 1, 1, 0.07)

            ColumnLayout {
                anchors.centerIn: parent
                spacing: 3

                Text {
                    Layout.alignment: Qt.AlignHCenter
                    text: "No active app audio sessions"
                    color: page.ekpill ? page.ekpill.colFg : "#ffffff"
                    font { family: page.ekpill ? page.ekpill.fontFam : "Segoe UI"; pixelSize: 11; bold: true }
                }

                Text {
                    Layout.alignment: Qt.AlignHCenter
                    text: "Start playback in any app to mix individual levels"
                    color: page.ekpill ? page.ekpill.colMuted : "#8e8e93"
                    font { family: page.ekpill ? page.ekpill.fontFam : "Segoe UI"; pixelSize: 10 }
                }
            }
        }

        // Per-application stream sliders
        ColumnLayout {
            visible: backend.audioStreams.length > 0
            Layout.fillWidth: true
            spacing: 8

            Repeater {
                model: backend.audioStreams

                Rectangle {
                    required property var modelData
                    Layout.fillWidth: true
                    Layout.preferredHeight: 54
                    radius: 11
                    color: Qt.rgba(1, 1, 1, 0.045)
                    border.width: 1
                    border.color: Qt.rgba(1, 1, 1, 0.08)

                    ColumnLayout {
                        anchors.fill: parent
                        anchors.leftMargin: 10
                        anchors.rightMargin: 10
                        anchors.topMargin: 7
                        anchors.bottomMargin: 7
                        spacing: 4

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 6

                            Glyph {
                                glyph: "\uEC4F"   // app audio glyph
                                size: 11
                                fontFam: page.ekpill ? page.ekpill.iconFam : "Segoe Fluent Icons"
                                color: modelData.muted ? (page.ekpill ? page.ekpill.colMuted : "#8e8e93")
                                                       : (page.ekpill ? page.ekpill.colFg : "#ffffff")
                            }

                            Text {
                                Layout.fillWidth: true
                                text: modelData.name || "Application"
                                color: page.ekpill ? page.ekpill.colFg : "#ffffff"
                                elide: Text.ElideRight
                                font { family: page.ekpill ? page.ekpill.fontFam : "Segoe UI"; pixelSize: 11; bold: true }
                            }

                            Text {
                                text: modelData.muted ? "Muted" : (modelData.volume_pct + "%")
                                color: modelData.muted ? "#ff453a" : (page.ekpill ? page.ekpill.colMuted : "#8e8e93")
                                font { family: page.ekpill ? page.ekpill.fontFam : "Segoe UI"; pixelSize: 10; bold: true }
                            }
                        }

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 8

                            Rectangle {
                                width: 22; height: 18; radius: 6
                                color: appMuteMa.containsMouse ? Qt.rgba(1, 1, 1, 0.14) : Qt.rgba(1, 1, 1, 0.06)

                                Glyph {
                                    anchors.centerIn: parent
                                    glyph: modelData.muted ? "\uE74F" : "\uE767"
                                    size: 10
                                    fontFam: page.ekpill ? page.ekpill.iconFam : "Segoe Fluent Icons"
                                    color: modelData.muted ? "#ff453a" : (page.ekpill ? page.ekpill.colFg : "#ffffff")
                                }

                                MouseArea {
                                    id: appMuteMa
                                    anchors.fill: parent
                                    hoverEnabled: true
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: backend.toggleAppMute(modelData.id)
                                }
                            }

                            SliderBar {
                                Layout.fillWidth: true
                                Layout.preferredHeight: 14
                                trackHeight: 14
                                trackColor: Qt.rgba(1, 1, 1, 0.08)
                                fillColor: modelData.muted ? Qt.rgba(1, 1, 1, 0.30) : Qt.rgba(1, 1, 1, 0.88)
                                value: modelData.muted ? 0 : modelData.volume
                                onMoved: function(v) {
                                    backend.setAppVolume(modelData.id, Math.round(v * 100));
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}
