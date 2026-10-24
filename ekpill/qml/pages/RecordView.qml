import QtQuick
import QtQuick.Layouts
import ".."

// Screen Recorder (FPS: 30/60, destination directory, mic toggle).
Item {
    id: page
    property var ekpill

    readonly property int pad: 18
    implicitWidth: 380
    implicitHeight: col.implicitHeight + pad * 2

    readonly property var fpsOptions: [30, 60]
    readonly property var dirOptions: ["Videos", "Pictures", "Desktop"]

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

            Rectangle {
                Layout.preferredWidth: 10
                Layout.preferredHeight: 10
                radius: 5
                color: !backend.recActive ? (page.ekpill ? page.ekpill.colMuted : "#888888")
                     : backend.recPaused ? "#fbbf24" : "#ef4444"

                SequentialAnimation on opacity {
                    running: backend.recActive && !backend.recPaused
                    loops: Animation.Infinite
                    NumberAnimation { to: 0.3; duration: 600; easing.type: Easing.InOutSine }
                    NumberAnimation { to: 1.0; duration: 600; easing.type: Easing.InOutSine }
                }
            }

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 1

                Text {
                    text: !backend.recActive ? "Screen Recorder"
                        : backend.recPaused ? "Recording Paused"
                                            : "Recording in Progress"
                    color: page.ekpill ? page.ekpill.colFg : "#ffffff"
                    font { family: page.ekpill ? page.ekpill.fontFam : "Segoe UI"; pixelSize: 14; bold: true }
                }

                Text {
                    Layout.fillWidth: true
                    text: backend.recActive
                          ? (backend.recFile.split(/[\\/]/).pop() || "Capturing...")
                          : "Ready to capture"
                    color: page.ekpill ? page.ekpill.colMuted : "#888888"
                    elide: Text.ElideMiddle
                    font { family: page.ekpill ? page.ekpill.fontFam : "Segoe UI"; pixelSize: 10 }
                }
            }

            Text {
                visible: backend.recActive
                text: backend.recTimeText
                color: backend.recPaused ? "#fbbf24" : "#ef4444"
                font { family: page.ekpill ? page.ekpill.fontFam : "Segoe UI"; pixelSize: 15; bold: true }
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 1
            color: page.ekpill ? page.ekpill.colLine : Qt.rgba(1, 1, 1, 0.12)
        }

        // ---------------------------------------------------------------- FPS
        RowLayout {
            Layout.fillWidth: true
            spacing: 8

            Text {
                Layout.preferredWidth: 70
                text: "FPS"
                color: page.ekpill ? page.ekpill.colMuted : "#888888"
                font { family: page.ekpill ? page.ekpill.fontFam : "Segoe UI"; pixelSize: 10; bold: true; letterSpacing: 1 }
            }

            Repeater {
                model: page.fpsOptions

                Rectangle {
                    required property var modelData
                    Layout.preferredWidth: 46
                    Layout.preferredHeight: 26
                    radius: 8
                    color: backend.recFps === modelData
                           ? Qt.rgba(1, 1, 1, 0.22)
                           : (fpsMa.containsMouse ? Qt.rgba(1, 1, 1, 0.12) : Qt.rgba(1, 1, 1, 0.05))
                    border.width: 1
                    border.color: backend.recFps === modelData ? (page.ekpill ? page.ekpill.colFg : "#ffffff") : Qt.rgba(1, 1, 1, 0.12)

                    Text {
                        anchors.centerIn: parent
                        text: String(modelData)
                        color: page.ekpill ? page.ekpill.colFg : "#ffffff"
                        font { family: page.ekpill ? page.ekpill.fontFam : "Segoe UI"; pixelSize: 10; bold: backend.recFps === modelData }
                    }

                    MouseArea {
                        id: fpsMa
                        anchors.fill: parent
                        hoverEnabled: true
                        enabled: !backend.recActive
                        cursorShape: Qt.PointingHandCursor
                        onClicked: backend.setRecFps(modelData)
                    }
                }
            }

            Item { Layout.fillWidth: true }
        }

        // ----------------------------------------------------------- Directory
        RowLayout {
            Layout.fillWidth: true
            spacing: 8

            Text {
                Layout.preferredWidth: 70
                text: "FOLDER"
                color: page.ekpill ? page.ekpill.colMuted : "#888888"
                font { family: page.ekpill ? page.ekpill.fontFam : "Segoe UI"; pixelSize: 10; bold: true; letterSpacing: 1 }
            }

            Repeater {
                model: page.dirOptions

                Rectangle {
                    required property var modelData
                    readonly property bool isSelected: backend.recDir.toLowerCase().indexOf(modelData.toLowerCase()) >= 0
                    Layout.preferredWidth: dirText.implicitWidth + 18
                    Layout.preferredHeight: 26
                    radius: 8
                    color: isSelected
                           ? Qt.rgba(1, 1, 1, 0.22)
                           : (dirMa.containsMouse ? Qt.rgba(1, 1, 1, 0.12) : Qt.rgba(1, 1, 1, 0.05))
                    border.width: 1
                    border.color: isSelected
                                  ? (page.ekpill ? page.ekpill.colFg : "#ffffff")
                                  : Qt.rgba(1, 1, 1, 0.12)

                    Text {
                        id: dirText
                        anchors.centerIn: parent
                        text: String(modelData)
                        color: page.ekpill ? page.ekpill.colFg : "#ffffff"
                        font { family: page.ekpill ? page.ekpill.fontFam : "Segoe UI"; pixelSize: 10 }
                    }

                    MouseArea {
                        id: dirMa
                        anchors.fill: parent
                        hoverEnabled: true
                        enabled: !backend.recActive
                        cursorShape: Qt.PointingHandCursor
                        onClicked: backend.setRecPresetDir(modelData)
                    }
                }
            }

            Item { Layout.fillWidth: true }
        }

        // ------------------------------------------------------ Audio Toggles
        // No system-audio toggle: the bundled ffmpeg has no WASAPI loopback
        // input, so a switch here would promise something it cannot record.
        // Microphone audio capture toggle
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 38
            radius: 11
            color: micMa.containsMouse ? Qt.rgba(1, 1, 1, 0.09) : Qt.rgba(1, 1, 1, 0.04)

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 12
                anchors.rightMargin: 12
                spacing: 10

                Glyph {
                    glyph: backend.recMic ? "\uE720" : "\uF781"   // mic or mic off
                    size: 15
                    fontFam: page.ekpill ? page.ekpill.iconFam : "Segoe Fluent Icons"
                    color: backend.recMic ? (page.ekpill ? page.ekpill.colFg : "#ffffff")
                                          : (page.ekpill ? page.ekpill.colMuted : "#888888")
                }

                Text {
                    Layout.fillWidth: true
                    text: "Microphone Audio"
                    color: page.ekpill ? page.ekpill.colFg : "#ffffff"
                    font { family: page.ekpill ? page.ekpill.fontFam : "Segoe UI"; pixelSize: 11 }
                }

                Rectangle {
                    Layout.preferredWidth: 36
                    Layout.preferredHeight: 18
                    radius: 9
                    color: backend.recMic ? (page.ekpill ? page.ekpill.colFg : "#ffffff") : Qt.rgba(1, 1, 1, 0.16)

                    Rectangle {
                        width: 14; height: 14; radius: 7
                        y: 2
                        x: backend.recMic ? parent.width - width - 2 : 2
                        color: backend.recMic ? "#000000" : "#ffffff"
                        Behavior on x { NumberAnimation { duration: 150; easing.type: Easing.OutCubic } }
                    }
                }
            }

            MouseArea {
                id: micMa
                anchors.fill: parent
                hoverEnabled: true
                enabled: !backend.recActive
                cursorShape: Qt.PointingHandCursor
                onClicked: backend.setRecMic(!backend.recMic)
            }
        }

        // ---------------------------------------------------- Action Buttons
        RowLayout {
            Layout.fillWidth: true
            spacing: 10

            // Start button
            Rectangle {
                visible: !backend.recActive
                Layout.fillWidth: true
                Layout.preferredHeight: 42
                radius: 12
                color: startMa.containsMouse ? "#dc2626" : "#ef4444"
                scale: startMa.pressed ? 0.96 : 1.0
                Behavior on scale { NumberAnimation { duration: 90; easing.type: Easing.OutQuad } }

                RowLayout {
                    anchors.centerIn: parent
                    spacing: 8

                    Rectangle {
                        width: 8; height: 8; radius: 4
                        color: "#ffffff"
                    }

                    Text {
                        text: "Start Recording"
                        color: "#ffffff"
                        font { family: page.ekpill ? page.ekpill.fontFam : "Segoe UI"; pixelSize: 12; bold: true }
                    }
                }

                MouseArea {
                    id: startMa
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: backend.startRecord()
                }
            }

            // Pause / Resume button
            Rectangle {
                visible: backend.recActive
                Layout.fillWidth: true
                Layout.preferredHeight: 42
                radius: 12
                color: pauseMa.containsMouse ? Qt.rgba(1, 1, 1, 0.18) : Qt.rgba(1, 1, 1, 0.10)
                border.width: 1
                border.color: Qt.rgba(1, 1, 1, 0.2)
                scale: pauseMa.pressed ? 0.96 : 1.0
                Behavior on scale { NumberAnimation { duration: 90; easing.type: Easing.OutQuad } }

                Text {
                    anchors.centerIn: parent
                    text: backend.recPaused ? "Resume" : "Pause"
                    color: page.ekpill ? page.ekpill.colFg : "#ffffff"
                    font { family: page.ekpill ? page.ekpill.fontFam : "Segoe UI"; pixelSize: 12; bold: true }
                }

                MouseArea {
                    id: pauseMa
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: backend.pauseRecord()
                }
            }

            // Stop button
            Rectangle {
                visible: backend.recActive
                Layout.fillWidth: true
                Layout.preferredHeight: 42
                radius: 12
                color: stopMa.containsMouse ? "#dc2626" : "#ef4444"
                scale: stopMa.pressed ? 0.96 : 1.0
                Behavior on scale { NumberAnimation { duration: 90; easing.type: Easing.OutQuad } }

                Text {
                    anchors.centerIn: parent
                    text: "Stop & Save"
                    color: "#ffffff"
                    font { family: page.ekpill ? page.ekpill.fontFam : "Segoe UI"; pixelSize: 12; bold: true }
                }

                MouseArea {
                    id: stopMa
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: backend.stopRecord()
                }
            }
        }

        // Open recordings folder
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 34
            radius: 10
            color: folderMa.containsMouse ? Qt.rgba(1, 1, 1, 0.12) : Qt.rgba(1, 1, 1, 0.05)
            scale: folderMa.pressed ? 0.97 : 1.0
            Behavior on scale { NumberAnimation { duration: 90; easing.type: Easing.OutQuad } }

            RowLayout {
                anchors.centerIn: parent
                spacing: 8

                Glyph {
                    glyph: "\uE838"   // folder
                    size: 14
                    fontFam: page.ekpill ? page.ekpill.iconFam : "Segoe Fluent Icons"
                    color: page.ekpill ? page.ekpill.colFg : "#ffffff"
                }

                Text {
                    text: "Open Recordings Folder"
                    color: page.ekpill ? page.ekpill.colFg : "#ffffff"
                    font { family: page.ekpill ? page.ekpill.fontFam : "Segoe UI"; pixelSize: 11 }
                }
            }

            MouseArea {
                id: folderMa
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: backend.openRecordDir()
            }
        }
    }
}
