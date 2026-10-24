import QtQuick
import QtQuick.Layouts
import ".."

// Settings — Apple-inspired compact switchboard.
// Inset grouped cards, refined micro-interactions, sleek segmented dock edge,
// and zero clutter.
Item {
    id: page
    property var ekpill

    // While capturing, the next chord becomes the binding: the window has to
    // accept keyboard input, which is exactly what backend.setFocusHeld arms.
    property string capturing: ""
    property string captureNote: ""

    // Escape cancels a capture before it takes the EkPill down.
    property double captureUsedAt: 0

    function escapeHandler() {
        if (page.captureUsedAt > 0 && Date.now() - page.captureUsedAt < 500) {
            page.captureUsedAt = 0;
            return true;
        }
        if (page.capturing === "") return false;
        page.capturing = "";
        page.captureNote = "capture cancelled";
        backend.setFocusHeld(false);
        return true;
    }

    function startCapture(which) {
        page.capturing = which;
        page.captureNote = which === "close"
                           ? "press keys, or Delete to unbind" : "";
        backend.setFocusHeld(true);
        page.forceActiveFocus();
    }

    function hotkeySpec(which) {
        return which === "launcher" ? backend.hotkeyLauncher : backend.hotkeyClose;
    }

    function hotkeyLabel(which) {
        var spec = page.hotkeySpec(which);
        return spec === "" ? "none" : spec;
    }

    // Qt key event -> the same "Ctrl+Alt+L" shape the backend parses.
    function comboFromEvent(e) {
        var mods = [];
        if (e.modifiers & Qt.ControlModifier) mods.push("Ctrl");
        if (e.modifiers & Qt.AltModifier) mods.push("Alt");
        if (e.modifiers & Qt.ShiftModifier) mods.push("Shift");
        if (e.modifiers & Qt.MetaModifier) mods.push("Win");
        var k = e.key, name = "";
        if (k >= Qt.Key_A && k <= Qt.Key_Z) name = String.fromCharCode(k);
        else if (k >= Qt.Key_0 && k <= Qt.Key_9) name = String.fromCharCode(k);
        else if (k >= Qt.Key_F1 && k <= Qt.Key_F12) name = "F" + (k - Qt.Key_F1 + 1);
        else if (k === Qt.Key_Space) name = "Space";
        else if (k === Qt.Key_Tab) name = "Tab";
        else if (k === Qt.Key_Return || k === Qt.Key_Enter) name = "Enter";
        else if (k === Qt.Key_Up) name = "Up";
        else if (k === Qt.Key_Down) name = "Down";
        else if (k === Qt.Key_Left) name = "Left";
        else if (k === Qt.Key_Right) name = "Right";
        else if (k === Qt.Key_Home) name = "Home";
        else if (k === Qt.Key_End) name = "End";
        else if (k === Qt.Key_PageUp) name = "Pgup";
        else if (k === Qt.Key_PageDown) name = "Pgdn";
        if (name === "") return "";
        if (mods.length === 0) {
            page.captureNote = "needs Ctrl, Alt, Shift or Win";
            return "";
        }
        return mods.join("+") + "+" + name;
    }

    // Escape cancels; anything else tries the bind and reports the outcome.
    Keys.onPressed: (event) => {
        if (page.capturing === "")
            return;
        event.accepted = true;
        if (event.key === Qt.Key_Escape) {
            page.captureUsedAt = Date.now();
            page.capturing = "";
            page.captureNote = "capture cancelled";
            backend.setFocusHeld(false);
            return;
        }
        if (page.capturing === "close" && event.modifiers === Qt.NoModifier
                && (event.key === Qt.Key_Delete || event.key === Qt.Key_Backspace)) {
            backend.setHotkey("close", "");
            page.capturing = "";
            backend.setFocusHeld(false);
            page.captureNote = "close key unbound";
            return;
        }
        var spec = page.comboFromEvent(event);
        if (spec === "")
            return;
        var which = page.capturing;
        var ok = backend.setHotkey(which, spec);
        var live = page.hotkeyLabel(which);
        page.capturing = "";
        backend.setFocusHeld(false);
        page.captureNote = ok ? (page.hotkeySpec(which) === ""
                                 ? "close key unbound"
                                 : which + " bound to " + spec)
                              : (spec + " is unavailable — kept " + live);
    }

    readonly property int pad: 12
    implicitWidth: 250
    implicitHeight: col.implicitHeight + pad * 2

    // --- Apple Inset Grouped UI Components ---

    component SwitchControl: Rectangle {
        id: swCtrl
        property bool checked: false
        property bool activeEnabled: true

        width: 30
        height: 16
        radius: 8
        color: checked ? Qt.rgba(1, 1, 1, 0.90) : Qt.rgba(1, 1, 1, 0.16)
        opacity: activeEnabled ? 1 : 0.4
        Behavior on color { ColorAnimation { duration: 150 } }

        Rectangle {
            width: 12
            height: 12
            radius: 6
            color: swCtrl.checked ? "#101012" : Qt.rgba(1, 1, 1, 0.82)
            anchors.verticalCenter: parent.verticalCenter
            x: swCtrl.checked ? parent.width - width - 2 : 2
            Behavior on x { NumberAnimation { duration: 150; easing.type: Easing.OutQuad } }
        }
    }

    component SettingRow: Rectangle {
        id: rowComp
        property string icon: ""
        property string label: ""
        property bool showSeparator: false
        default property alias content: rowContent.children

        Layout.fillWidth: true
        Layout.preferredHeight: 32
        color: "transparent"

        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: 10
            anchors.rightMargin: 10
            spacing: 8

            Glyph {
                Layout.alignment: Qt.AlignVCenter
                glyph: rowComp.icon
                size: 13
                fontFam: page.ekpill ? page.ekpill.iconFam : "Segoe Fluent Icons"
                color: page.ekpill ? page.ekpill.colFg : "#ffffff"
                opacity: 0.85
            }

            Text {
                Layout.fillWidth: true
                text: rowComp.label
                color: page.ekpill ? page.ekpill.colFg : "#ffffff"
                font { family: page.ekpill ? page.ekpill.fontFam : "Segoe UI"; pixelSize: 11 }
                elide: Text.ElideRight
            }

            Item {
                id: rowContent
                Layout.alignment: Qt.AlignVCenter
                implicitWidth: childrenRect.width
                implicitHeight: childrenRect.height
            }
        }

        Rectangle {
            visible: rowComp.showSeparator
            anchors.left: parent.left
            anchors.leftMargin: 31
            anchors.right: parent.right
            anchors.rightMargin: 10
            anchors.bottom: parent.bottom
            height: 1
            color: Qt.rgba(1, 1, 1, 0.05)
        }
    }

    component SettingGroup: Rectangle {
        default property alias rows: groupCol.children
        Layout.fillWidth: true
        Layout.preferredHeight: groupCol.implicitHeight
        radius: 10
        color: Qt.rgba(1, 1, 1, 0.04)
        border.color: Qt.rgba(1, 1, 1, 0.06)
        border.width: 1

        ColumnLayout {
            id: groupCol
            anchors.left: parent.left
            anchors.right: parent.right
            spacing: 0
        }
    }

    ColumnLayout {
        id: col
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.margins: page.pad
        spacing: 8

        // ------------------------------------------------------------ header
        RowLayout {
            Layout.fillWidth: true
            Layout.rightMargin: (page.ekpill && page.ekpill.pinned) ? 32 : 0
            spacing: 8

            Rectangle {
                Layout.preferredWidth: 22
                Layout.preferredHeight: 22
                radius: 11
                color: backArea.containsMouse ? Qt.rgba(1, 1, 1, 0.12) : Qt.rgba(1, 1, 1, 0.05)
                scale: backArea.pressed ? 0.94 : 1.0
                Behavior on scale { NumberAnimation { duration: 90 } }

                Glyph {
                    anchors.centerIn: parent
                    glyph: "\uE72B"
                    size: 11
                    fontFam: page.ekpill ? page.ekpill.iconFam : "Segoe Fluent Icons"
                    color: page.ekpill ? page.ekpill.colFg : "#ffffff"
                }

                MouseArea {
                    id: backArea
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: if (page.ekpill) page.ekpill.backToQuick()
                }
            }

            Text {
                text: "Settings"
                color: page.ekpill ? page.ekpill.colFg : "#ffffff"
                font { family: page.ekpill ? page.ekpill.fontFam : "Segoe UI"; pixelSize: 13; bold: true }
            }
        }

        // -------------------------------------------------- general card
        SettingGroup {
            // Do not disturb
            SettingRow {
                icon: "\uE7ED"
                label: "Focus"
                showSeparator: true

                SwitchControl {
                    checked: backend.notifDnd
                    activeEnabled: true
                }

                MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    onClicked: backend.openDndSettings()
                }
            }

            // Auto-hide
            SettingRow {
                icon: "\uE8F4"
                label: "Auto-hide"
                showSeparator: true

                SwitchControl {
                    checked: page.ekpill ? page.ekpill.autoHide : false
                    activeEnabled: true
                }

                MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    onClicked: if (page.ekpill) page.ekpill.autoHide = !page.ekpill.autoHide
                }
            }

            // Start with Windows
            SettingRow {
                icon: "\uE7E8"
                label: "Start with Windows"
                showSeparator: false

                SwitchControl {
                    checked: backend.autostart
                    activeEnabled: backend.autostartAvailable
                }

                MouseArea {
                    anchors.fill: parent
                    enabled: backend.autostartAvailable
                    cursorShape: Qt.PointingHandCursor
                    onClicked: backend.setAutostart(!backend.autostart)
                }
            }
        }

        // ------------------------------------------------------ dock edge
        SettingGroup {
            SettingRow {
                icon: "\uE7C4"
                label: "Position"
                showSeparator: false

                Rectangle {
                    width: 96
                    height: 22
                    radius: 6
                    color: Qt.rgba(1, 1, 1, 0.08)

                    Row {
                        anchors.fill: parent
                        spacing: 0

                        Repeater {
                            model: [
                                { "pos": "top", "label": "Top", "glyph": "\uE74A" },
                                { "pos": "right", "label": "Side", "glyph": "\uE76C" }
                            ]

                            Rectangle {
                                required property var modelData
                                width: 48
                                height: 22
                                radius: 5
                                color: page.ekpill && page.ekpill.pillPos === modelData.pos
                                       ? Qt.rgba(1, 1, 1, 0.88)
                                       : "transparent"
                                Behavior on color { ColorAnimation { duration: 120 } }

                                Row {
                                    anchors.centerIn: parent
                                    spacing: 4

                                    Glyph {
                                        anchors.verticalCenter: parent.verticalCenter
                                        glyph: modelData.glyph
                                        size: 10
                                        fontFam: page.ekpill ? page.ekpill.iconFam : "Segoe Fluent Icons"
                                        color: page.ekpill && page.ekpill.pillPos === modelData.pos
                                               ? "#101012"
                                               : Qt.rgba(1, 1, 1, 0.6)
                                    }

                                    Text {
                                        anchors.verticalCenter: parent.verticalCenter
                                        text: modelData.label
                                        color: page.ekpill && page.ekpill.pillPos === modelData.pos
                                               ? "#101012"
                                               : Qt.rgba(1, 1, 1, 0.6)
                                        font { family: page.ekpill ? page.ekpill.fontFam : "Segoe UI"; pixelSize: 9; bold: true }
                                    }
                                }

                                MouseArea {
                                    anchors.fill: parent
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: if (page.ekpill) page.ekpill.pillPos = modelData.pos
                                }
                            }
                        }
                    }
                }
            }
        }

        // -------------------------------------------------------- hotkeys
        SettingGroup {
            Repeater {
                model: [
                    { "which": "launcher", "label": "Launcher", "glyph": "\uE721" },
                    { "which": "close", "label": "Close", "glyph": "\uE711" }
                ]

                delegate: SettingRow {
                    required property var modelData
                    required property int index
                    icon: modelData.glyph
                    label: modelData.label
                    showSeparator: index === 0

                    Rectangle {
                        width: Math.max(68, chipText.implicitWidth + 14)
                        height: 20
                        radius: 5
                        color: page.capturing === modelData.which
                               ? Qt.rgba(1, 1, 1, 0.88)
                                : (chipArea.containsMouse ? Qt.rgba(1, 1, 1, 0.12) : Qt.rgba(1, 1, 1, 0.08))
                        border.color: Qt.rgba(1, 1, 1, 0.08)
                        border.width: 1

                        Text {
                            id: chipText
                            anchors.centerIn: parent
                            text: page.capturing === modelData.which ? "press keys…"
                                 : page.hotkeyLabel(modelData.which)
                            color: page.capturing === modelData.which ? "#101012"
                                                                      : page.ekpill ? page.ekpill.colFg : "#ffffff"
                            font { family: page.ekpill ? page.ekpill.fontFam : "Segoe UI"; pixelSize: 9; bold: true }
                        }

                        MouseArea {
                            id: chipArea
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: page.startCapture(modelData.which)
                        }
                    }
                }
            }
        }

        // ------------------------------------------------ status note
        Text {
            Layout.fillWidth: true
            visible: page.captureNote !== ""
            text: page.captureNote
            color: page.ekpill ? page.ekpill.colMuted : Qt.rgba(1, 1, 1, 0.5)
            font { family: page.ekpill ? page.ekpill.fontFam : "Segoe UI"; pixelSize: 9 }
            horizontalAlignment: Text.AlignHCenter
        }
    }
}
