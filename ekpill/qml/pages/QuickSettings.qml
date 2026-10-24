import QtQuick
import QtQuick.Layouts
// Shared components live one level up; a QML file only auto-resolves types in
// its own directory, so the parent has to be imported explicitly.
import ".."

// Quick settings — the page the EkPill opens into when nothing is playing.
// Apple iOS / Dynamic EkPill aesthetic:
// - Ultra-compact, icon-driven minimalism ("Icons are enough, we don't need names")
// - Pure obsidian black background with frosted monochrome glass surfaces
// - Masterpiece buttery smoothness, zero clutter, zero circus colors
// - Authentic Apple battery indicator with dynamic fill & charging bolt
// - Inline Wi-Fi and Bluetooth drill-down sheets
Item {
    id: page
    property var ekpill

    readonly property int pad: 12
    property string subView: "main"   // "main" | "wifi" | "bt"

    property string wifiPasswordSsid: ""
    property string wifiPasswordText: ""

    onWifiPasswordSsidChanged: {
        var open = (wifiPasswordSsid !== "");
        backend.setFocusHeld(open);
        if (open) wifiPwBox.forceActiveFocus();
    }
    Component.onDestruction: {
        if (wifiPasswordSsid !== "") backend.setFocusHeld(false);
    }

    function escapeHandler() {
        if (subView !== "main") {
            subView = "main";
            wifiPasswordSsid = "";
            wifiPasswordText = "";
            return true;
        }
        return false;
    }

    implicitWidth: 340
    implicitHeight: subView === "main" ? (col.implicitHeight + pad * 2)
                  : subView === "wifi" ? Math.min(460, wifiCol.implicitHeight + pad * 2)
                  : Math.min(460, btCol.implicitHeight + pad * 2)

    // =========================================================================
    // 1. MAIN QUICK SETTINGS VIEW (Apple Dynamic EkPill / Control Center Grade)
    // =========================================================================
    ColumnLayout {
        id: col
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.margins: page.pad
        spacing: 8
        visible: page.subView === "main"

        // ---------------------------------------------------------- 1. Now Playing Mini Player
        RowLayout {
            Layout.fillWidth: true
            Layout.preferredHeight: 34
            Layout.rightMargin: (page.ekpill && page.ekpill.pinned) ? 36 : 0
            spacing: 10

            // Squircle album artwork / music icon
            Rectangle {
                Layout.preferredWidth: 34
                Layout.preferredHeight: 34
                radius: 9
                color: Qt.rgba(1, 1, 1, 0.07)
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
                    visible: backend.mediaArt === "" && backend.mediaActive
                    active: backend.mediaPlaying
                    barColor: page.ekpill ? page.ekpill.colFg : "#ffffff"
                    barCount: 4
                    maxHeight: 18
                }

                Glyph {
                    anchors.centerIn: parent
                    visible: backend.mediaArt === "" && !backend.mediaActive
                    glyph: "\uE8D6"   // music note
                    size: 15
                    fontFam: page.ekpill ? page.ekpill.iconFam : "Segoe Fluent Icons"
                    color: Qt.rgba(1, 1, 1, 0.40)
                }

                MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    onClicked: if (page.ekpill) page.ekpill.openPage("media")
                }
            }

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 1

                Text {
                    Layout.fillWidth: true
                    text: backend.mediaActive ? (backend.mediaTitle !== "" ? backend.mediaTitle : "Media Playing") : "Now Playing"
                    color: backend.mediaActive ? (page.ekpill ? page.ekpill.colFg : "#ffffff") : Qt.rgba(1, 1, 1, 0.70)
                    elide: Text.ElideRight
                    font { family: page.ekpill ? page.ekpill.fontFam : "Segoe UI"; pixelSize: 12; bold: true }
                }

                Text {
                    Layout.fillWidth: true
                    text: backend.mediaActive
                          ? (backend.mediaArtist !== "" ? backend.mediaArtist
                             + (backend.mediaDurationText !== "0:00"
                                ? " · " + backend.mediaPositionText + " / " + backend.mediaDurationText : "")
                             : (backend.mediaDurationText !== "0:00"
                                ? backend.mediaPositionText + " / " + backend.mediaDurationText : "Playing"))
                          : "No active audio"
                    color: page.ekpill ? page.ekpill.colMuted : "#8e8e93"
                    elide: Text.ElideRight
                    font { family: page.ekpill ? page.ekpill.fontFam : "Segoe UI"; pixelSize: 10 }
                }
            }

            // Transport controls
            RowLayout {
                Layout.alignment: Qt.AlignVCenter
                spacing: 5
                opacity: backend.mediaActive ? 1.0 : 0.40

                // Previous
                Rectangle {
                    width: 26; height: 26; radius: 13
                    color: prevMa.pressed ? Qt.rgba(1, 1, 1, 0.16) : (prevMa.containsMouse ? Qt.rgba(1, 1, 1, 0.09) : "transparent")
                    scale: prevMa.pressed ? 0.92 : 1.0
                    Behavior on scale { NumberAnimation { duration: 90 } }

                    Glyph {
                        anchors.centerIn: parent
                        glyph: "\uE892"
                        size: 11
                        fontFam: page.ekpill ? page.ekpill.iconFam : "Segoe Fluent Icons"
                        color: backend.mediaActive ? (page.ekpill ? page.ekpill.colFg : "#ffffff") : Qt.rgba(1, 1, 1, 0.50)
                    }

                    MouseArea {
                        id: prevMa
                        anchors.fill: parent
                        enabled: backend.mediaActive
                        hoverEnabled: true
                        cursorShape: backend.mediaActive ? Qt.PointingHandCursor : Qt.ArrowCursor
                        onClicked: backend.mediaCommand("prev")
                    }
                }

                // Play / Pause (Apple circular tactile button)
                Rectangle {
                    width: 30; height: 30; radius: 15
                    color: playMa.pressed ? Qt.rgba(1, 1, 1, 0.22) : (playMa.containsMouse ? Qt.rgba(1, 1, 1, 0.14) : Qt.rgba(1, 1, 1, 0.08))
                    border.width: 1
                    border.color: Qt.rgba(1, 1, 1, 0.12)
                    scale: playMa.pressed ? 0.92 : 1.0
                    Behavior on scale { NumberAnimation { duration: 90 } }

                    Glyph {
                        anchors.centerIn: parent
                        glyph: backend.mediaPlaying ? "\uE769" : "\uE768"
                        size: 12
                        fontFam: page.ekpill ? page.ekpill.iconFam : "Segoe Fluent Icons"
                        color: page.ekpill ? page.ekpill.colFg : "#ffffff"
                    }

                    MouseArea {
                        id: playMa
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: backend.mediaCommand("toggle")
                    }
                }

                // Next
                Rectangle {
                    width: 26; height: 26; radius: 13
                    color: nextMa.pressed ? Qt.rgba(1, 1, 1, 0.16) : (nextMa.containsMouse ? Qt.rgba(1, 1, 1, 0.09) : "transparent")
                    scale: nextMa.pressed ? 0.92 : 1.0
                    Behavior on scale { NumberAnimation { duration: 90 } }

                    Glyph {
                        anchors.centerIn: parent
                        glyph: "\uE893"
                        size: 11
                        fontFam: page.ekpill ? page.ekpill.iconFam : "Segoe Fluent Icons"
                        color: backend.mediaActive ? (page.ekpill ? page.ekpill.colFg : "#ffffff") : Qt.rgba(1, 1, 1, 0.50)
                    }

                    MouseArea {
                        id: nextMa
                        anchors.fill: parent
                        enabled: backend.mediaActive
                        hoverEnabled: true
                        cursorShape: backend.mediaActive ? Qt.PointingHandCursor : Qt.ArrowCursor
                        onClicked: backend.mediaCommand("next")
                    }
                }
            }
        }

        // ---------------------------------------------------------- 2. Volume Capsule
        RowLayout {
            Layout.fillWidth: true
            spacing: 8

            // Tactile Mute Toggle Button
            Rectangle {
                width: 24; height: 24; radius: 12
                color: muteMa.pressed ? Qt.rgba(1, 1, 1, 0.20) : (muteMa.containsMouse ? Qt.rgba(1, 1, 1, 0.12) : Qt.rgba(1, 1, 1, 0.06))
                border.width: 1
                border.color: Qt.rgba(1, 1, 1, 0.09)
                scale: muteMa.pressed ? 0.94 : 1.0
                Behavior on scale { NumberAnimation { duration: 90 } }

                Glyph {
                    anchors.centerIn: parent
                    glyph: backend.muted ? "\uE74F" : (backend.volume > 0.6 ? "\uE767" : (backend.volume > 0 ? "\uE994" : "\uE74F"))
                    size: 12
                    fontFam: page.ekpill ? page.ekpill.iconFam : "Segoe Fluent Icons"
                    color: backend.muted ? (page.ekpill ? page.ekpill.colMuted : "#8e8e93") : (page.ekpill ? page.ekpill.colFg : "#ffffff")
                }

                MouseArea {
                    id: muteMa
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: backend.toggleMute()
                }
            }

            // Apple Capsule Slider Track (pure white fill on obsidian frosted track)
            SliderBar {
                id: volSlider
                Layout.fillWidth: true
                Layout.preferredHeight: 22
                trackHeight: 22
                trackColor: Qt.rgba(1, 1, 1, 0.08)
                fillColor: Qt.rgba(1, 1, 1, 0.92)
                value: backend.muted ? 0 : backend.volume
                onMoved: function (v) {
                    if (backend.muted && v > 0) backend.toggleMute();
                    backend.setVolume(v);
                }
            }

            // Volume percentage label
            Text {
                Layout.preferredWidth: 30
                horizontalAlignment: Text.AlignRight
                text: backend.muted ? "—" : Math.round(backend.volume * 100) + "%"
                color: page.ekpill ? page.ekpill.colMuted : "#8e8e93"
                font { family: page.ekpill ? page.ekpill.fontFam : "Segoe UI"; pixelSize: 11; bold: true }
            }
        }

        // ---------------------------------------------------------- 3. Quick Action Icon Pods
        // Frosted monochrome glass styling (obsidian glass, crisp white iconography)
        RowLayout {
            Layout.fillWidth: true
            spacing: 7

            // 1. Wi-Fi Icon Button
            Rectangle {
                id: wifiTile
                Layout.fillWidth: true
                Layout.preferredHeight: 38
                radius: 12
                color: wifiMa.pressed ? Qt.rgba(1, 1, 1, 0.20)
                     : (wifiMa.containsMouse ? Qt.rgba(1, 1, 1, 0.14)
                        : (backend.wifiConnected ? Qt.rgba(1, 1, 1, 0.11) : Qt.rgba(1, 1, 1, 0.06)))
                border.width: 1
                border.color: backend.wifiConnected
                              ? Qt.rgba(1, 1, 1, 0.18)
                              : (wifiMa.containsMouse ? Qt.rgba(1, 1, 1, 0.14) : Qt.rgba(1, 1, 1, 0.08))
                scale: wifiMa.pressed ? 0.94 : 1.0
                Behavior on scale { NumberAnimation { duration: 90; easing.type: Easing.OutQuad } }

                Glyph {
                    anchors.centerIn: parent
                    glyph: "\uE701"
                    size: 16
                    fontFam: page.ekpill ? page.ekpill.iconFam : "Segoe Fluent Icons"
                    color: backend.wifiConnected ? "#ffffff" : (wifiMa.containsMouse ? "#ffffff" : Qt.rgba(1, 1, 1, 0.50))
                }

                MouseArea {
                    id: wifiMa
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: {
                        page.subView = "wifi";
                        backend.scanWifi();
                    }
                }
            }

            // 2. Bluetooth Icon Button
            Rectangle {
                id: btTile
                Layout.fillWidth: true
                Layout.preferredHeight: 38
                radius: 12
                color: btMa.pressed ? Qt.rgba(1, 1, 1, 0.20)
                     : (btMa.containsMouse ? Qt.rgba(1, 1, 1, 0.14)
                        : (backend.bluetoothOn ? Qt.rgba(1, 1, 1, 0.11) : Qt.rgba(1, 1, 1, 0.06)))
                border.width: 1
                border.color: backend.bluetoothOn
                              ? Qt.rgba(1, 1, 1, 0.18)
                              : (btMa.containsMouse ? Qt.rgba(1, 1, 1, 0.14) : Qt.rgba(1, 1, 1, 0.08))
                scale: btMa.pressed ? 0.94 : 1.0
                Behavior on scale { NumberAnimation { duration: 90; easing.type: Easing.OutQuad } }

                Glyph {
                    anchors.centerIn: parent
                    glyph: "\uE702"
                    size: 16
                    fontFam: page.ekpill ? page.ekpill.iconFam : "Segoe Fluent Icons"
                    color: backend.bluetoothOn ? "#ffffff" : (btMa.containsMouse ? "#ffffff" : Qt.rgba(1, 1, 1, 0.50))
                }

                MouseArea {
                    id: btMa
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: {
                        page.subView = "bt";
                        backend.scanBluetooth();
                    }
                }
            }

            // 3. Focus (DND) Icon Button
            Rectangle {
                id: dndTile
                Layout.fillWidth: true
                Layout.preferredHeight: 38
                radius: 12
                color: dndMa.pressed ? Qt.rgba(1, 1, 1, 0.20)
                     : (dndMa.containsMouse ? Qt.rgba(1, 1, 1, 0.14)
                        : (backend.notifDnd ? Qt.rgba(1, 1, 1, 0.11) : Qt.rgba(1, 1, 1, 0.06)))
                border.width: 1
                border.color: backend.notifDnd
                              ? Qt.rgba(1, 1, 1, 0.18)
                              : (dndMa.containsMouse ? Qt.rgba(1, 1, 1, 0.14) : Qt.rgba(1, 1, 1, 0.08))
                scale: dndMa.pressed ? 0.94 : 1.0
                Behavior on scale { NumberAnimation { duration: 90; easing.type: Easing.OutQuad } }

                Glyph {
                    anchors.centerIn: parent
                    glyph: backend.notifDnd ? "\uE708" : "\uEA8F"
                    size: 16
                    fontFam: page.ekpill ? page.ekpill.iconFam : "Segoe Fluent Icons"
                    color: backend.notifDnd ? "#ffffff" : (dndMa.containsMouse ? "#ffffff" : Qt.rgba(1, 1, 1, 0.50))
                }

                MouseArea {
                    id: dndMa
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: backend.openDndSettings()
                }
            }

            // 4. Files Icon Button
            Rectangle {
                id: filesTile
                Layout.fillWidth: true
                Layout.preferredHeight: 38
                radius: 12
                color: filesMa.pressed ? Qt.rgba(1, 1, 1, 0.20)
                     : (filesMa.containsMouse ? Qt.rgba(1, 1, 1, 0.14) : Qt.rgba(1, 1, 1, 0.06))
                border.width: 1
                border.color: filesMa.containsMouse ? Qt.rgba(1, 1, 1, 0.14) : Qt.rgba(1, 1, 1, 0.08)
                scale: filesMa.pressed ? 0.94 : 1.0
                Behavior on scale { NumberAnimation { duration: 90; easing.type: Easing.OutQuad } }

                Glyph {
                    anchors.centerIn: parent
                    glyph: "\uE8B7"
                    size: 16
                    fontFam: page.ekpill ? page.ekpill.iconFam : "Segoe Fluent Icons"
                    color: filesMa.containsMouse ? "#ffffff" : Qt.rgba(1, 1, 1, 0.65)
                }

                MouseArea {
                    id: filesMa
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: page.ekpill.openPage("files")
                }
            }

            // 5. Idle Record Button (visible only when idle)
            Rectangle {
                id: idleRecBtn
                visible: !backend.recActive
                Layout.fillWidth: true
                Layout.preferredHeight: 38
                radius: 12
                color: idleRecMa.pressed ? Qt.rgba(1, 1, 1, 0.20)
                     : (idleRecMa.containsMouse ? Qt.rgba(1, 1, 1, 0.14) : Qt.rgba(1, 1, 1, 0.06))
                border.width: 1
                border.color: idleRecMa.containsMouse ? Qt.rgba(1, 0.27, 0.23, 0.40) : Qt.rgba(1, 1, 1, 0.08)
                scale: idleRecMa.pressed ? 0.94 : 1.0
                Behavior on scale { NumberAnimation { duration: 90; easing.type: Easing.OutQuad } }

                Glyph {
                    anchors.centerIn: parent
                    glyph: "\uE714"   // video camera
                    size: 16
                    fontFam: page.ekpill ? page.ekpill.iconFam : "Segoe Fluent Icons"
                    color: idleRecMa.containsMouse ? "#ff453a" : Qt.rgba(1, 1, 1, 0.70)
                }

                MouseArea {
                    id: idleRecMa
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: {
                        backend.setRecFps(60);
                        backend.setRecMic(true);
                        backend.startRecord();
                        if (page.ekpill) page.ekpill.closeAll();
                    }
                }
            }
        }

        // ---------------------------------- Extended Apple Dynamic EkPill Screen Recording Bar (Active State)
        Rectangle {
            id: activeRecBar
            visible: backend.recActive
            Layout.fillWidth: true
            Layout.preferredHeight: 40
            radius: 12
            color: backend.recPaused ? Qt.rgba(1, 0.72, 0.1, 0.10) : Qt.rgba(1, 1, 1, 0.06)
            border.width: 1
            border.color: backend.recPaused ? Qt.rgba(1, 0.72, 0.1, 0.35) : Qt.rgba(1, 0.27, 0.23, 0.30)

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 12
                anchors.rightMargin: 10
                spacing: 8

                // Breathing red dot
                Rectangle {
                    width: 7; height: 7; radius: 3.5
                    color: backend.recPaused ? "#fbbf24" : "#ff453a"
                    SequentialAnimation on opacity {
                        running: backend.recActive && !backend.recPaused
                        loops: Animation.Infinite
                        NumberAnimation { to: 0.35; duration: 900; easing.type: Easing.InOutSine }
                        NumberAnimation { to: 1.0; duration: 900; easing.type: Easing.InOutSine }
                    }
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 0

                    Text {
                        text: backend.recTimeText
                        color: page.ekpill ? page.ekpill.colFg : "#ffffff"
                        font { family: page.ekpill ? page.ekpill.fontFam : "Segoe UI"; pixelSize: 12; bold: true }
                    }

                    Text {
                        text: backend.recPaused ? "Paused" : "Screen Recording · 60 FPS"
                        color: backend.recPaused ? "#fbbf24" : Qt.rgba(1, 1, 1, 0.55)
                        font { family: page.ekpill ? page.ekpill.fontFam : "Segoe UI"; pixelSize: 9 }
                    }
                }

                // Pause Button
                Rectangle {
                    width: 24; height: 24; radius: 12
                    color: pauseMa.pressed ? Qt.rgba(1, 1, 1, 0.22) : (pauseMa.containsMouse ? Qt.rgba(1, 1, 1, 0.14) : Qt.rgba(1, 1, 1, 0.08))
                    border.width: 1
                    border.color: Qt.rgba(1, 1, 1, 0.12)
                    scale: pauseMa.pressed ? 0.90 : (pauseMa.containsMouse ? 1.04 : 1.0)
                    Behavior on scale { NumberAnimation { duration: 90; easing.type: Easing.OutQuad } }

                    Glyph {
                        anchors.centerIn: parent
                        glyph: backend.recPaused ? "\uE768" : "\uE769"
                        size: 10
                        fontFam: page.ekpill ? page.ekpill.iconFam : "Segoe Fluent Icons"
                        color: backend.recPaused ? "#fbbf24" : (page.ekpill ? page.ekpill.colFg : "#ffffff")
                    }

                    MouseArea {
                        id: pauseMa
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: backend.pauseRecord()
                    }
                }

                // Stop Button (Apple signature circular ring with red rounded square inside)
                Rectangle {
                    width: 24; height: 24; radius: 12
                    color: stopMa.pressed ? Qt.rgba(1, 0.27, 0.23, 0.35) : (stopMa.containsMouse ? Qt.rgba(1, 0.27, 0.23, 0.20) : Qt.rgba(1, 1, 1, 0.08))
                    border.width: 1.5
                    border.color: stopMa.containsMouse ? "#ffffff" : Qt.rgba(1, 1, 1, 0.60)
                    scale: stopMa.pressed ? 0.90 : (stopMa.containsMouse ? 1.04 : 1.0)
                    Behavior on scale { NumberAnimation { duration: 90; easing.type: Easing.OutQuad } }

                    Rectangle {
                        anchors.centerIn: parent
                        width: 8; height: 8; radius: 2
                        color: "#ff453a"
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
        }

        // ---------------------------------------------------------- 4. Bottom Utility Bar
        RowLayout {
            Layout.fillWidth: true
            Layout.topMargin: 2
            spacing: 8

            // Apple Battery Pill Badge
            Rectangle {
                Layout.preferredHeight: 24
                Layout.preferredWidth: battWidget.implicitWidth + 12
                radius: 12
                color: Qt.rgba(1, 1, 1, 0.05)
                border.width: 1
                border.color: Qt.rgba(1, 1, 1, 0.08)

                AppleBattery {
                    id: battWidget
                    anchors.centerIn: parent
                    fontFam: page.ekpill ? page.ekpill.fontFam : "Segoe UI"
                    batteryWidth: 18
                    batteryHeight: 9
                }
            }

            Item { Layout.fillWidth: true }

            // Audio Mixer
            Rectangle {
                Layout.preferredWidth: 24
                Layout.preferredHeight: 24
                radius: 12
                color: mixerMa.pressed ? Qt.rgba(1, 1, 1, 0.18) : (mixerMa.containsMouse ? Qt.rgba(1, 1, 1, 0.12) : Qt.rgba(1, 1, 1, 0.05))
                border.width: 1
                border.color: Qt.rgba(1, 1, 1, 0.07)
                scale: mixerMa.pressed ? 0.92 : 1.0
                Behavior on scale { NumberAnimation { duration: 90 } }

                Glyph {
                    anchors.centerIn: parent
                    glyph: "\uE995"
                    size: 11
                    fontFam: page.ekpill ? page.ekpill.iconFam : "Segoe Fluent Icons"
                    color: page.ekpill ? page.ekpill.colFg : "#ffffff"
                }

                MouseArea {
                    id: mixerMa
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: page.ekpill.openPage("audio")
                }
            }

            // Launcher / Search
            Rectangle {
                Layout.preferredWidth: 24
                Layout.preferredHeight: 24
                radius: 12
                color: searchMa.pressed ? Qt.rgba(1, 1, 1, 0.18) : (searchMa.containsMouse ? Qt.rgba(1, 1, 1, 0.12) : Qt.rgba(1, 1, 1, 0.05))
                border.width: 1
                border.color: Qt.rgba(1, 1, 1, 0.07)
                scale: searchMa.pressed ? 0.92 : 1.0
                Behavior on scale { NumberAnimation { duration: 90 } }

                Glyph {
                    anchors.centerIn: parent
                    glyph: "\uE721"
                    size: 11
                    fontFam: page.ekpill ? page.ekpill.iconFam : "Segoe Fluent Icons"
                    color: page.ekpill ? page.ekpill.colFg : "#ffffff"
                }

                MouseArea {
                    id: searchMa
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: page.ekpill.openPage("launcher")
                }
            }

            // Settings
            Rectangle {
                Layout.preferredWidth: 24
                Layout.preferredHeight: 24
                radius: 12
                color: settingsMa.pressed ? Qt.rgba(1, 1, 1, 0.18) : (settingsMa.containsMouse ? Qt.rgba(1, 1, 1, 0.12) : Qt.rgba(1, 1, 1, 0.05))
                border.width: 1
                border.color: Qt.rgba(1, 1, 1, 0.07)
                scale: settingsMa.pressed ? 0.92 : 1.0
                Behavior on scale { NumberAnimation { duration: 90 } }

                Glyph {
                    anchors.centerIn: parent
                    glyph: "\uE713"
                    size: 11
                    fontFam: page.ekpill ? page.ekpill.iconFam : "Segoe Fluent Icons"
                    color: page.ekpill ? page.ekpill.colFg : "#ffffff"
                }

                MouseArea {
                    id: settingsMa
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: page.ekpill.openPage("settings")
                }
            }

            // Power Menu
            Rectangle {
                Layout.preferredWidth: 24
                Layout.preferredHeight: 24
                radius: 12
                color: powerMa.pressed ? Qt.rgba(1, 1, 1, 0.18) : (powerMa.containsMouse ? Qt.rgba(1, 1, 1, 0.12) : Qt.rgba(1, 1, 1, 0.05))
                border.width: 1
                border.color: Qt.rgba(1, 1, 1, 0.07)
                scale: powerMa.pressed ? 0.92 : 1.0
                Behavior on scale { NumberAnimation { duration: 90 } }

                Glyph {
                    anchors.centerIn: parent
                    glyph: "\uE7E8"
                    size: 11
                    fontFam: page.ekpill ? page.ekpill.iconFam : "Segoe Fluent Icons"
                    color: page.ekpill ? page.ekpill.colFg : "#ffffff"
                }

                MouseArea {
                    id: powerMa
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: page.ekpill.openPage("power")
                }
            }
        }
    }

    // =========================================================================
    // 2. INLINE WI-FI SCAN & CONNECT VIEW (Apple Inset Card Aesthetic)
    // =========================================================================
    ColumnLayout {
        id: wifiCol
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.margins: page.pad
        spacing: 10
        visible: page.subView === "wifi"

        // Header with Back button, Title, Status, and Refresh
        RowLayout {
            Layout.fillWidth: true
            Layout.rightMargin: (page.ekpill && page.ekpill.pinned) ? 36 : 0
            spacing: 10

            Rectangle {
                Layout.preferredWidth: 26
                Layout.preferredHeight: 26
                radius: 13
                color: backWifiMa.containsMouse ? Qt.rgba(1, 1, 1, 0.14) : Qt.rgba(1, 1, 1, 0.06)
                scale: backWifiMa.pressed ? 0.92 : 1.0
                Behavior on scale { NumberAnimation { duration: 90 } }

                Glyph {
                    anchors.centerIn: parent
                    glyph: "\uE72B"   // back arrow
                    size: 11
                    fontFam: page.ekpill ? page.ekpill.iconFam : "Segoe Fluent Icons"
                    color: page.ekpill ? page.ekpill.colFg : "#ffffff"
                }

                MouseArea {
                    id: backWifiMa
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: {
                        page.subView = "main";
                        page.wifiPasswordSsid = "";
                    }
                }
            }

            Text {
                Layout.fillWidth: true
                text: "Wi-Fi Networks"
                color: page.ekpill ? page.ekpill.colFg : "#ffffff"
                font { family: page.ekpill ? page.ekpill.fontFam : "Segoe UI"; pixelSize: 13; bold: true }
            }

            Text {
                visible: backend.wifiBusy
                text: "Scanning..."
                color: page.ekpill ? page.ekpill.colMuted : "#8e8e93"
                font { family: page.ekpill ? page.ekpill.fontFam : "Segoe UI"; pixelSize: 10 }
            }

            Rectangle {
                Layout.preferredWidth: 26
                Layout.preferredHeight: 26
                radius: 13
                color: refreshWifiMa.containsMouse ? Qt.rgba(1, 1, 1, 0.14) : Qt.rgba(1, 1, 1, 0.06)
                scale: refreshWifiMa.pressed ? 0.92 : 1.0
                Behavior on scale { NumberAnimation { duration: 90 } }

                Glyph {
                    anchors.centerIn: parent
                    glyph: "\uE72C"   // refresh
                    size: 11
                    fontFam: page.ekpill ? page.ekpill.iconFam : "Segoe Fluent Icons"
                    color: page.ekpill ? page.ekpill.colFg : "#ffffff"
                }

                MouseArea {
                    id: refreshWifiMa
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: backend.scanWifi()
                }
            }
        }

        // Active Connection Card
        Rectangle {
            visible: backend.wifiConnected
            Layout.fillWidth: true
            Layout.preferredHeight: 48
            radius: 12
            color: Qt.rgba(1, 1, 1, 0.08)
            border.width: 1
            border.color: Qt.rgba(1, 1, 1, 0.14)

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 12
                anchors.rightMargin: 12
                spacing: 10

                Glyph {
                    glyph: "\uE701"
                    size: 16
                    fontFam: page.ekpill ? page.ekpill.iconFam : "Segoe Fluent Icons"
                    color: "#ffffff"
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 1

                    Text {
                        Layout.fillWidth: true
                        text: backend.wifiSsid
                        color: page.ekpill ? page.ekpill.colFg : "#ffffff"
                        elide: Text.ElideRight
                        font { family: page.ekpill ? page.ekpill.fontFam : "Segoe UI"; pixelSize: 12; bold: true }
                    }

                    Text {
                        Layout.fillWidth: true
                        text: "Connected · Signal " + backend.wifiSignal + "%"
                        color: page.ekpill ? page.ekpill.colMuted : "#8e8e93"
                        font { family: page.ekpill ? page.ekpill.fontFam : "Segoe UI"; pixelSize: 10 }
                    }
                }

                Rectangle {
                    Layout.preferredWidth: 68
                    Layout.preferredHeight: 24
                    radius: 12
                    color: disconnMa.containsMouse ? Qt.rgba(1, 1, 1, 0.18) : Qt.rgba(1, 1, 1, 0.08)
                    border.width: 1
                    border.color: Qt.rgba(1, 1, 1, 0.12)

                    Text {
                        anchors.centerIn: parent
                        text: "Disconnect"
                        color: page.ekpill ? page.ekpill.colFg : "#ffffff"
                        font { family: page.ekpill ? page.ekpill.fontFam : "Segoe UI"; pixelSize: 9; bold: true }
                    }

                    MouseArea {
                        id: disconnMa
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: backend.disconnectWifi()
                    }
                }
            }
        }

        // Password prompt card
        Rectangle {
            visible: page.wifiPasswordSsid !== ""
            Layout.fillWidth: true
            Layout.preferredHeight: 70
            radius: 12
            color: Qt.rgba(1, 1, 1, 0.07)
            border.width: 1
            border.color: Qt.rgba(1, 1, 1, 0.20)

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 8
                spacing: 5

                Text {
                    text: "Password for " + page.wifiPasswordSsid
                    color: page.ekpill ? page.ekpill.colFg : "#ffffff"
                    font { family: page.ekpill ? page.ekpill.fontFam : "Segoe UI"; pixelSize: 11; bold: true }
                }

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 6

                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 26
                        radius: 8
                        color: Qt.rgba(1, 1, 1, 0.05)
                        border.width: 1
                        border.color: Qt.rgba(1, 1, 1, 0.15)

                        TextInput {
                            id: wifiPwBox
                            anchors.fill: parent
                            anchors.leftMargin: 8
                            anchors.rightMargin: 8
                            anchors.verticalCenter: parent.verticalCenter
                            echoMode: TextInput.Password
                            selectByMouse: true
                            color: page.ekpill ? page.ekpill.colFg : "#ffffff"
                            font { family: page.ekpill ? page.ekpill.fontFam : "Segoe UI"; pixelSize: 11 }
                            onTextChanged: page.wifiPasswordText = text
                            onAccepted: {
                                if (page.wifiPasswordSsid !== "") {
                                    backend.connectWifi(page.wifiPasswordSsid, text);
                                    page.wifiPasswordSsid = "";
                                    text = "";
                                }
                            }
                        }
                    }

                    Rectangle {
                        Layout.preferredWidth: 56
                        Layout.preferredHeight: 26
                        radius: 8
                        color: page.ekpill ? page.ekpill.colFg : "#ffffff"

                        Text {
                            anchors.centerIn: parent
                            text: "Connect"
                            color: page.ekpill ? page.ekpill.colBg : "#000000"
                            font { family: page.ekpill ? page.ekpill.fontFam : "Segoe UI"; pixelSize: 9; bold: true }
                        }

                        MouseArea {
                            anchors.fill: parent
                            cursorShape: Qt.PointingHandCursor
                            onClicked: {
                                if (page.wifiPasswordSsid !== "") {
                                    backend.connectWifi(page.wifiPasswordSsid, wifiPwBox.text);
                                    page.wifiPasswordSsid = "";
                                    wifiPwBox.text = "";
                                }
                            }
                        }
                    }

                    Rectangle {
                        Layout.preferredWidth: 46
                        Layout.preferredHeight: 26
                        radius: 8
                        color: Qt.rgba(1, 1, 1, 0.08)

                        Text {
                            anchors.centerIn: parent
                            text: "Cancel"
                            color: page.ekpill ? page.ekpill.colMuted : "#8e8e93"
                            font { family: page.ekpill ? page.ekpill.fontFam : "Segoe UI"; pixelSize: 9 }
                        }

                        MouseArea {
                            anchors.fill: parent
                            cursorShape: Qt.PointingHandCursor
                            onClicked: {
                                page.wifiPasswordSsid = "";
                                wifiPwBox.text = "";
                            }
                        }
                    }
                }
            }
        }

        // Error message if any
        Text {
            visible: backend.wifiError !== ""
            Layout.fillWidth: true
            text: backend.wifiError
            color: page.ekpill ? page.ekpill.colCrit : "#ff453a"
            wrapMode: Text.Wrap
            font { family: page.ekpill ? page.ekpill.fontFam : "Segoe UI"; pixelSize: 10 }
        }

        // Scanned Networks List
        Flickable {
            Layout.fillWidth: true
            Layout.preferredHeight: 220
            contentHeight: netListCol.implicitHeight
            clip: true

            ColumnLayout {
                id: netListCol
                width: parent.width
                spacing: 5

                Repeater {
                    model: backend.wifiNetworks

                    Rectangle {
                        id: netItem
                        required property var modelData
                        Layout.fillWidth: true
                        Layout.preferredHeight: 40
                        radius: 10
                        color: netItemMa.containsMouse ? Qt.rgba(1, 1, 1, 0.08) : Qt.rgba(1, 1, 1, 0.035)
                        border.width: 1
                        border.color: netItem.modelData.connected ? Qt.rgba(1, 1, 1, 0.20) : Qt.rgba(1, 1, 1, 0.06)

                        RowLayout {
                            anchors.fill: parent
                            anchors.leftMargin: 10
                            anchors.rightMargin: 10
                            spacing: 8

                            Glyph {
                                glyph: "\uE701"
                                size: 13
                                fontFam: page.ekpill ? page.ekpill.iconFam : "Segoe Fluent Icons"
                                color: netItem.modelData.connected ? "#ffffff" : (page.ekpill ? page.ekpill.colMuted : "#8e8e93")
                            }

                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 1

                                Text {
                                    Layout.fillWidth: true
                                    text: netItem.modelData.ssid
                                    color: page.ekpill ? page.ekpill.colFg : "#ffffff"
                                    elide: Text.ElideRight
                                    font { family: page.ekpill ? page.ekpill.fontFam : "Segoe UI"; pixelSize: 11; bold: netItem.modelData.connected }
                                }

                                Text {
                                    Layout.fillWidth: true
                                    text: "Signal " + (netItem.modelData.signal || 0) + "% · " + (netItem.modelData.security || "Secured")
                                    color: page.ekpill ? page.ekpill.colMuted : "#8e8e93"
                                    font { family: page.ekpill ? page.ekpill.fontFam : "Segoe UI"; pixelSize: 9 }
                                }
                            }

                            // If connected, show Forget button
                            Rectangle {
                                visible: netItem.modelData.connected
                                Layout.preferredWidth: 46
                                Layout.preferredHeight: 20
                                radius: 10
                                color: Qt.rgba(1, 1, 1, 0.08)

                                Text {
                                    anchors.centerIn: parent
                                    text: "Forget"
                                    color: page.ekpill ? page.ekpill.colMuted : "#8e8e93"
                                    font { family: page.ekpill ? page.ekpill.fontFam : "Segoe UI"; pixelSize: 9 }
                                }

                                MouseArea {
                                    anchors.fill: parent
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: backend.forgetWifi(netItem.modelData.ssid)
                                }
                            }

                            // Lock glyph if secured
                            Glyph {
                                visible: netItem.modelData.security !== "Open" && !netItem.modelData.connected
                                glyph: "\uE72E"
                                size: 10
                                fontFam: page.ekpill ? page.ekpill.iconFam : "Segoe Fluent Icons"
                                color: page.ekpill ? page.ekpill.colMuted : "#8e8e93"
                            }
                        }

                        MouseArea {
                            id: netItemMa
                            anchors.fill: parent
                            z: -1
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: {
                                if (netItem.modelData.connected) return;
                                if (netItem.modelData.security === "Open") {
                                    backend.connectWifi(netItem.modelData.ssid, "");
                                } else {
                                    page.wifiPasswordSsid = netItem.modelData.ssid;
                                }
                            }
                        }
                    }
                }

                Text {
                    visible: !backend.wifiBusy && backend.wifiNetworks.length === 0
                    Layout.fillWidth: true
                    Layout.topMargin: 16
                    horizontalAlignment: Text.AlignHCenter
                    text: "No Wi-Fi networks found"
                    color: page.ekpill ? page.ekpill.colMuted : "#8e8e93"
                    font { family: page.ekpill ? page.ekpill.fontFam : "Segoe UI"; pixelSize: 11 }
                }
            }
        }
    }

    // =========================================================================
    // 3. INLINE BLUETOOTH DEVICES VIEW (Apple Inset Card Aesthetic)
    // =========================================================================
    ColumnLayout {
        id: btCol
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.margins: page.pad
        spacing: 10
        visible: page.subView === "bt"

        // Header with Back button and Refresh
        RowLayout {
            Layout.fillWidth: true
            Layout.rightMargin: (page.ekpill && page.ekpill.pinned) ? 36 : 0
            spacing: 10

            Rectangle {
                Layout.preferredWidth: 26
                Layout.preferredHeight: 26
                radius: 13
                color: backBtMa.containsMouse ? Qt.rgba(1, 1, 1, 0.14) : Qt.rgba(1, 1, 1, 0.06)
                scale: backBtMa.pressed ? 0.92 : 1.0
                Behavior on scale { NumberAnimation { duration: 90 } }

                Glyph {
                    anchors.centerIn: parent
                    glyph: "\uE72B"   // back arrow
                    size: 11
                    fontFam: page.ekpill ? page.ekpill.iconFam : "Segoe Fluent Icons"
                    color: page.ekpill ? page.ekpill.colFg : "#ffffff"
                }

                MouseArea {
                    id: backBtMa
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: page.subView = "main"
                }
            }

            Text {
                Layout.fillWidth: true
                text: "Bluetooth Devices"
                color: page.ekpill ? page.ekpill.colFg : "#ffffff"
                font { family: page.ekpill ? page.ekpill.fontFam : "Segoe UI"; pixelSize: 13; bold: true }
            }

            Text {
                visible: backend.bluetoothBusy
                text: "Scanning..."
                color: page.ekpill ? page.ekpill.colMuted : "#8e8e93"
                font { family: page.ekpill ? page.ekpill.fontFam : "Segoe UI"; pixelSize: 10 }
            }

            Rectangle {
                Layout.preferredWidth: 26
                Layout.preferredHeight: 26
                radius: 13
                color: refreshBtMa.containsMouse ? Qt.rgba(1, 1, 1, 0.14) : Qt.rgba(1, 1, 1, 0.06)
                scale: refreshBtMa.pressed ? 0.92 : 1.0
                Behavior on scale { NumberAnimation { duration: 90 } }

                Glyph {
                    anchors.centerIn: parent
                    glyph: "\uE72C"   // refresh
                    size: 11
                    fontFam: page.ekpill ? page.ekpill.iconFam : "Segoe Fluent Icons"
                    color: page.ekpill ? page.ekpill.colFg : "#ffffff"
                }

                MouseArea {
                    id: refreshBtMa
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: backend.scanBluetooth()
                }
            }
        }

        // Bluetooth Radio Toggle Card
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 44
            radius: 12
            color: Qt.rgba(1, 1, 1, 0.06)
            border.width: 1
            border.color: Qt.rgba(1, 1, 1, 0.10)

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 12
                anchors.rightMargin: 12
                spacing: 10

                Glyph {
                    glyph: "\uE702"
                    size: 15
                    fontFam: page.ekpill ? page.ekpill.iconFam : "Segoe Fluent Icons"
                    color: backend.bluetoothOn ? "#ffffff" : (page.ekpill ? page.ekpill.colMuted : "#8e8e93")
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 1

                    Text {
                        text: "Bluetooth Radio"
                        color: page.ekpill ? page.ekpill.colFg : "#ffffff"
                        font { family: page.ekpill ? page.ekpill.fontFam : "Segoe UI"; pixelSize: 11; bold: true }
                    }

                    Text {
                        text: backend.bluetoothOn ? "Radio enabled" : "Radio turned off"
                        color: page.ekpill ? page.ekpill.colMuted : "#8e8e93"
                        font { family: page.ekpill ? page.ekpill.fontFam : "Segoe UI"; pixelSize: 9 }
                    }
                }

                Rectangle {
                    Layout.preferredWidth: 58
                    Layout.preferredHeight: 24
                    radius: 12
                    color: backend.bluetoothOn ? (page.ekpill ? page.ekpill.colFg : "#ffffff") : Qt.rgba(1, 1, 1, 0.10)

                    Text {
                        anchors.centerIn: parent
                        text: backend.bluetoothOn ? "Turn off" : "Turn on"
                        color: backend.bluetoothOn ? (page.ekpill ? page.ekpill.colBg : "#000000") : (page.ekpill ? page.ekpill.colFg : "#ffffff")
                        font { family: page.ekpill ? page.ekpill.fontFam : "Segoe UI"; pixelSize: 9; bold: true }
                    }

                    MouseArea {
                        id: toggleBtMa
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        onClicked: backend.toggleBluetooth()
                    }
                }
            }
        }

        // Bluetooth Devices List
        Flickable {
            Layout.fillWidth: true
            Layout.preferredHeight: 220
            contentHeight: btListCol.implicitHeight
            clip: true

            ColumnLayout {
                id: btListCol
                width: parent.width
                spacing: 5

                Repeater {
                    model: backend.bluetoothDevices

                    Rectangle {
                        id: btItem
                        required property var modelData
                        Layout.fillWidth: true
                        Layout.preferredHeight: 40
                        radius: 10
                        color: btItemMa.containsMouse ? Qt.rgba(1, 1, 1, 0.08) : Qt.rgba(1, 1, 1, 0.035)
                        border.width: 1
                        border.color: btItem.modelData.connected ? Qt.rgba(1, 1, 1, 0.20) : Qt.rgba(1, 1, 1, 0.06)

                        RowLayout {
                            anchors.fill: parent
                            anchors.leftMargin: 10
                            anchors.rightMargin: 10
                            spacing: 8

                            Glyph {
                                glyph: "\uE702"
                                size: 13
                                fontFam: page.ekpill ? page.ekpill.iconFam : "Segoe Fluent Icons"
                                color: btItem.modelData.connected ? "#ffffff" : (page.ekpill ? page.ekpill.colMuted : "#8e8e93")
                            }

                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 1

                                Text {
                                    Layout.fillWidth: true
                                    text: btItem.modelData.name || btItem.modelData.id || "Bluetooth Device"
                                    color: page.ekpill ? page.ekpill.colFg : "#ffffff"
                                    elide: Text.ElideRight
                                    font { family: page.ekpill ? page.ekpill.fontFam : "Segoe UI"; pixelSize: 11; bold: btItem.modelData.connected }
                                }

                                Text {
                                    Layout.fillWidth: true
                                    text: btItem.modelData.connected
                                          ? "Connected"
                                          : (btItem.modelData.paired ? "Paired · not connected" : "Not paired")
                                    color: btItem.modelData.connected ? "#ffffff" : (page.ekpill ? page.ekpill.colMuted : "#8e8e93")
                                    font { family: page.ekpill ? page.ekpill.fontFam : "Segoe UI"; pixelSize: 9 }
                                }
                            }

                            Rectangle {
                                Layout.preferredWidth: 54
                                Layout.preferredHeight: 20
                                radius: 10
                                color: removeBtMa.containsMouse ? Qt.rgba(1, 1, 1, 0.14) : Qt.rgba(1, 1, 1, 0.06)
                                border.width: 1
                                border.color: Qt.rgba(1, 1, 1, 0.10)

                                Text {
                                    anchors.centerIn: parent
                                    text: "Remove"
                                    color: page.ekpill ? page.ekpill.colFg : "#ffffff"
                                    font { family: page.ekpill ? page.ekpill.fontFam : "Segoe UI"; pixelSize: 9; bold: true }
                                }

                                MouseArea {
                                    id: removeBtMa
                                    anchors.fill: parent
                                    hoverEnabled: true
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: backend.removeBluetooth(btItem.modelData.mac || btItem.modelData.id)
                                }
                            }
                        }

                        MouseArea {
                            id: btItemMa
                            anchors.fill: parent
                            z: -1
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: backend.openBluetoothSettings()
                        }
                    }
                }

                Text {
                    visible: backend.bluetoothError !== ""
                    Layout.fillWidth: true
                    Layout.topMargin: 4
                    text: backend.bluetoothError
                    wrapMode: Text.Wrap
                    color: page.ekpill ? page.ekpill.colCrit : "#ff453a"
                    font { family: page.ekpill ? page.ekpill.fontFam : "Segoe UI"; pixelSize: 9 }
                }

                Text {
                    visible: !backend.bluetoothBusy && backend.bluetoothDevices.length === 0
                    Layout.fillWidth: true
                    Layout.topMargin: 16
                    horizontalAlignment: Text.AlignHCenter
                    text: "Nothing is paired in Windows"
                    color: page.ekpill ? page.ekpill.colMuted : "#8e8e93"
                    font { family: page.ekpill ? page.ekpill.fontFam : "Segoe UI"; pixelSize: 11 }
                }
            }
        }
    }
}
