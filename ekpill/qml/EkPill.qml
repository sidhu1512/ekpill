import QtQuick
import QtQuick.Layouts
import "pages"
import "Theme.js" as Theme

// One pill for everything.
//
// Collapsed it shows the weekday, a dot-matrix clock and the battery. The
// pointer arriving opens quick settings; it flows back when the pointer
// leaves. Two dock edges: the top edge is horizontal, the right edge is a
// slim upright strip that opens into the same upright panel — nothing is
// rotated, so every label is read normally.
Item {
    id: root
    // The view resizes this root to the window (SizeRootObjectToView), so no
    // anchors here — the host owns the geometry.

    // ---------------------------------------------------------- preferences
    // Where the EkPill lives: top | right.
    property string pillPos: "top"
    property int pillH: 40
    property int cornerR: 13
    readonly property int animMs: 340
    readonly property int animFast: 170

    // -------------------------------------------------------------- palette
    readonly property color colBg: Theme.bg
    readonly property color colFg: Theme.fg
    readonly property color colCrit: Theme.crit
    readonly property color colMuted: Qt.rgba(1, 1, 1, Theme.mutedAlpha)
    readonly property color colLine: Qt.rgba(1, 1, 1, Theme.lineAlpha)
    readonly property color colTile: Qt.rgba(1, 1, 1, Theme.tileAlpha)

    readonly property string fontFam: "Segoe UI"
    readonly property string iconFam: backend.iconFont

    // ------------------------------------------------------------- geometry
    readonly property bool atTop: pillPos === "top"
    readonly property bool atRight: pillPos === "right"
    readonly property bool vertical: atRight
    readonly property int pillThickness: atTop ? pillH : 54

    // Old settings may still say left/bottom; fold them into the two edges
    // this build actually has instead of rendering off-screen.
    Component.onCompleted: {
        if (pillPos !== "top" && pillPos !== "right")
            pillPos = "top";
    }

    // ---------------------------------------------------------- interaction
    property bool pinned: false
    property string page: ""            // explicit page set by a click
    property bool hovered: backend.hovered
    // Escape (or the close button) puts the EkPill away. The pointer may
    // still be resting on the capsule, and a hover-opened EkPill would
    // spring straight back up, so a dismissal is its own state: it lasts
    // until the pointer leaves and comes back.
    property bool dismissed: false
    property bool expanded: (pinned || hovered) && !dismissed
    // Hover always lands on quick settings. A playing track used to hijack
    // the hover and leave the rest of the EkPill unreachable; the player is
    // now one tap away from the card at the top of quick settings.
    readonly property string activePage:
        !expanded ? ""
                  : (page !== "" ? page : "quick")

    onExpandedChanged: {
        if (!expanded) {
            page = "";
            backend.setFocusHeld(false);
        } else {
            autoHidden = false;
        }
        root.updateHotRegion();
    }

    // A dismissal ends when the pointer leaves: the EkPill can be summoned
    // again the next time it comes back.
    onHoveredChanged: if (!hovered) dismissed = false

    // ------------------------------------------------------------ auto-hide
    // With nothing pinned and the pointer away, the capsule retires after a
    // quiet spell and returns the moment the pointer finds its (invisible) hot
    // region, a hotkey, or a click. The hot region follows the capsule's
    // geometry rather than its opacity, so "hidden" still catches the pointer.
    property bool autoHide: true
    property int autoHideMs: 8000
    property bool autoHidden: false

    onAutoHideChanged: {
        // One handler per signal in QML, so the persist write lives here too.
        backend.saveWindowState(pillPos, pinned, page, backend.notifDnd, autoHide);
        if (!autoHide)
            autoHidden = false;
    }

    // Bound rather than restarted by hand: an EkPill that *starts* collapsed
    // has had no transition to arm a timer on, so the idle spell has to come
    // from the state itself. Anything that expands or hides stops it.
    Timer {
        id: quietTimer
        interval: root.autoHideMs
        // A dismissed EkPill stays visible: it is waiting for the pointer to
        // leave, and fading out under the pointer would leave nothing there
        // to come back to.
        running: root.autoHide && !root.expanded && !root.autoHidden && !root.dismissed
        onTriggered: if (root.autoHide && !root.expanded) root.autoHidden = true
    }

    // Placement survives a restart: these values are the whole persisted
    // surface, so the writes live here, next to the state itself.
    onPinnedChanged: backend.saveWindowState(pillPos, pinned, page, backend.notifDnd, autoHide)
    onPillPosChanged: backend.saveWindowState(pillPos, pinned, page, backend.notifDnd, autoHide)
    onPageChanged: {
        // Opening a page is an explicit request, so it ends a dismissal.
        if (page !== "") dismissed = false;
        root.updateHotRegion();
        backend.saveWindowState(pillPos, pinned, page, backend.notifDnd, autoHide);
    }

    // A global hotkey pressed while another app has focus arrives from the
    // native RegisterHotKey filter (backend.hotkey).
    Connections {
        target: backend
        function onHotkey(name) {
            if (name === "launcher") root.openPage("launcher");
            else if (name === "record") root.openPage("record");
            else if (name === "close") root.closeAll();
        }
    }

    // Escape closes whatever is open. The backend only reports the key when
    // the pointer is on the EkPill, so the key still belongs to the app the
    // user is typing in everywhere else. A page that is using the keyboard
    // gets first refusal — a rename in progress is cancelled, and only the
    // next Escape takes the EkPill down.
    Connections {
        target: backend
        function onEscapePressed() {
            var item = inlinePanel.item;
            if (item && item.escapeHandler) {
                if (item.escapeHandler()) return;
            }
            root.closeAll();
        }
    }

    // Light Dismiss: clicking anywhere outside the open EkPill collapses it
    Connections {
        target: backend
        function onOutsideClicked() {
            if (root.expanded || root.page !== "") {
                root.closeAll();
            }
        }
    }

    // Return to quick settings when media session ends while unpinned
    Connections {
        target: backend
        function onMediaChanged() {
            if (!backend.mediaActive && root.page === "media" && !root.pinned) {
                root.backToQuick();
            }
        }
    }

    // -------------------------------------------------------------- the clock
    property date now: new Date()
    readonly property string timeText: Qt.formatTime(now, "hh:mm")
    readonly property string dayText: Qt.formatDateTime(now, "ddd").toUpperCase()

    Timer {
        interval: 1000
        running: true
        repeat: true
        triggeredOnStart: true
        onTriggered: root.now = new Date()
    }

    // ---------------------------------------------------------------- capsule
    readonly property real armWidth:
        Math.max(nLeft.implicitWidth, nRight.implicitWidth)
    readonly property real collapsedLen:
        atTop ? Math.max(clock.implicitWidth + 2 * (armWidth + 24) + 40, 150)
              : Math.max(rimColumn.implicitHeight + 24, 132)

    // There is exactly one Loader, and it lives inside the capsule. A second
    // "measuring" loader at root would render a duplicate of the page at the
    // window origin; instead the page reports its own implicit size, which does
    // not depend on the capsule's size, so the capsule can follow it.
    readonly property real wantLen:
        (expanded && inlinePanel.item) ? inlinePanel.item.implicitWidth : collapsedLen
    readonly property real wantThick:
        (expanded && inlinePanel.item) ? inlinePanel.item.implicitHeight : pillThickness

    Item {
        id: capsule

        width: expanded ? wantLen : (vertical ? pillThickness : collapsedLen)
        height: expanded ? wantThick : (vertical ? collapsedLen : pillThickness)

        onXChanged: root.updateHotRegion()
        onYChanged: root.updateHotRegion()
        onWidthChanged: root.updateHotRegion()
        onHeightChanged: root.updateHotRegion()

        // Auto-hidden: still laid out (the hot region needs the geometry),
        // just invisible.
        opacity: root.autoHidden ? 0 : 1
        Behavior on opacity { NumberAnimation { duration: root.animFast } }

        x: vertical ? root.width - width
                    : (root.width > 0 ? Math.round((root.width - width) / 2) : 0)
        y: vertical ? (root.height > 0 ? Math.round((root.height - height) / 2) : 0)
                    : 0

        Behavior on width { SpringAnimation { spring: 3.8; damping: 0.32; epsilon: 0.25 } }
        Behavior on height { SpringAnimation { spring: 3.8; damping: 0.32; epsilon: 0.25 } }
        Behavior on x { enabled: root.width > 0; SpringAnimation { spring: 3.8; damping: 0.32; epsilon: 0.25 } }
        Behavior on y { enabled: root.height > 0; SpringAnimation { spring: 3.8; damping: 0.32; epsilon: 0.25 } }

        // Everything stays upright: the right edge uses a tall panel, not a
        // rotated copy of the top one.
        Item {
            id: inner
            anchors.fill: parent

            // Lowest layer: when collapsed, a click anywhere on the bare capsule pins
            // it open. When a page is open, clicks on padding/background are safely
            // absorbed so controls and panels remain open without accidental unpinning.
            MouseArea {
                anchors.fill: parent
                z: 0
                hoverEnabled: true
                // A dismissal is meant to last until the pointer leaves. If
                // the backend misses that leave (both can happen inside one
                // 40 ms poll), the latch stayed set and the next hover did
                // nothing. A real enter is proof the pointer came back, so it
                // clears the latch here as well.
                onEntered: {
                    if (!root.pinned) root.dismissed = false;
                    root.autoHidden = false;
                }
                acceptedButtons: Qt.LeftButton | Qt.RightButton
                onClicked: (mouse) => {
                    if (!root.pinned && mouse.button === Qt.LeftButton) {
                        root.dismissed = false;
                        root.pinned = true;
                    }
                    mouse.accepted = true;
                }
            }

            Rectangle {
                id: surface
                anchors.fill: parent
                z: 1
                color: root.colBg
                border.width: 1
                border.color: Qt.rgba(1, 1, 1, 0.12)
                radius: root.expanded
                        ? Math.min(24, Math.min(width, height) / 2)
                        : (root.vertical ? width / 2 : height / 2)
                Behavior on radius {
                    SpringAnimation { spring: 3.8; damping: 0.32; epsilon: 0.25 }
                }
            }

            // ------------------------------------------------ collapsed content
            Item {
                id: collapsedContent
                anchors.fill: parent
                z: 2
                opacity: root.expanded ? 0 : 1
                visible: opacity > 0.01
                Behavior on opacity { NumberAnimation { duration: root.animFast } }

                // Top edge: one horizontal row.
                RowLayout {
                    anchors.fill: parent
                    visible: !root.vertical
                    spacing: 0

                    RowLayout {
                        id: nLeft
                        anchors.left: parent.left
                        anchors.leftMargin: 20
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: 8

                        // Active screen recording pill indicator
                        RowLayout {
                            Layout.alignment: Qt.AlignVCenter
                            visible: backend.recActive
                            spacing: 5

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

                            Text {
                                text: backend.recTimeText
                                color: backend.recPaused ? "#fbbf24" : "#ff453a"
                                font { family: root.fontFam; pixelSize: 11; bold: true }
                            }

                            MouseArea {
                                anchors.fill: parent
                                anchors.margins: -4
                                cursorShape: Qt.PointingHandCursor
                                onClicked: root.openPage("quick")
                            }
                        }

                        Glyph {
                            Layout.alignment: Qt.AlignVCenter
                            glyph: "\uE701"   // Wi-Fi
                            size: 14
                            fontFam: root.iconFam
                            color: backend.wifiConnected ? root.colFg : root.colMuted
                        }

                        Text {
                            Layout.alignment: Qt.AlignVCenter
                            text: root.dayText
                            color: root.colMuted
                            font { family: root.fontFam; pixelSize: 11; letterSpacing: 0.6 }
                        }
                    }

                    DotText {
                        id: clock
                        anchors.centerIn: parent
                        value: root.timeText
                        size: 17
                        color: root.colFg
                    }

                    RowLayout {
                        id: nRight
                        anchors.right: parent.right
                        anchors.rightMargin: 18
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: 6

                        AppleBattery {
                            fontFam: root.fontFam
                            batteryWidth: 20
                            batteryHeight: 10
                        }
                    }
                }

                // Right edge: a narrow upright strip. Clock, day, battery and
                // Wi-Fi stacked, every glyph upright.
                ColumnLayout {
                    id: rimColumn
                    anchors.centerIn: parent
                    visible: root.vertical
                    spacing: 7

                    Item {
                        Layout.alignment: Qt.AlignHCenter
                        Layout.preferredWidth: 8
                        Layout.preferredHeight: backend.recActive ? 8 : 0
                        visible: backend.recActive

                        Rectangle {
                            anchors.fill: parent
                            radius: 4
                            color: backend.recPaused ? "#fbbf24" : "#ff453a"
                            SequentialAnimation on opacity {
                                running: backend.recActive && !backend.recPaused
                                loops: Animation.Infinite
                                NumberAnimation { to: 0.35; duration: 900; easing.type: Easing.InOutSine }
                                NumberAnimation { to: 1.0; duration: 900; easing.type: Easing.InOutSine }
                            }
                        }
                    }

                    DotText {
                        Layout.alignment: Qt.AlignHCenter
                        value: root.timeText
                        size: 12
                        color: root.colFg
                    }

                    Text {
                        Layout.alignment: Qt.AlignHCenter
                        text: root.dayText
                        color: root.colMuted
                        font { family: root.fontFam; pixelSize: 9; letterSpacing: 0.5 }
                    }

                    AppleBattery {
                        Layout.alignment: Qt.AlignHCenter
                        fontFam: root.fontFam
                        batteryWidth: 16
                        batteryHeight: 8
                        showPercent: false
                    }

                    Glyph {
                        Layout.alignment: Qt.AlignHCenter
                        glyph: "\uE701"
                        size: 11
                        fontFam: root.iconFam
                        color: backend.wifiConnected ? root.colFg : root.colMuted
                    }
                }
            }

            // --------------------------------------------------- opened content
            Item {
                id: openContent
                anchors.fill: parent
                z: 3
                opacity: root.expanded ? 1 : 0
                visible: opacity > 0.01
                Behavior on opacity { NumberAnimation { duration: root.animFast } }

                Loader {
                    id: inlinePanel
                    anchors.fill: parent
                    source: root.activePage === "" ? ""
                          : root.activePage === "media" ? "pages/MediaPage.qml"
                          : root.activePage === "audio" ? "pages/AudioView.qml"
                          : root.activePage === "quick" ? "pages/QuickSettings.qml"
                          : root.activePage === "launcher" ? "pages/LauncherPage.qml"
                          : root.activePage === "power" ? "pages/PowerPage.qml"
                          : root.activePage === "settings" ? "pages/SettingsPage.qml"
                          : root.activePage === "files" ? "pages/FilesPage.qml"
                          : root.activePage === "record" ? "pages/RecordView.qml"
                          : ""
                    asynchronous: false
                    onLoaded: item.ekpill = root
                }
            }

            // ---------------------------------------------------- the way out
            // One close control for the whole shell. A page opened by a click
            // *pins* the EkPill, and the only release was a click on the bare
            // capsule underneath the page — which a grid or a list covers, so
            // from inside most pages there was no way to collapse at all. It
            // shows only while pinned: a hover-opened EkPill still flows back
            // on its own.
            // Apple Frosted Glass Close Control - perfectly inset & aligned
            Rectangle {
                id: closeBtn
                z: 10
                width: 24
                height: 24
                radius: 12
                anchors.top: parent.top
                anchors.right: parent.right
                anchors.topMargin: 16
                anchors.rightMargin: 16
                color: closeArea.pressed ? Qt.rgba(1, 1, 1, 0.24) : (closeArea.containsMouse ? Qt.rgba(1, 1, 1, 0.15) : Qt.rgba(1, 1, 1, 0.08))
                border.width: 1
                border.color: Qt.rgba(1, 1, 1, 0.12)
                scale: closeArea.pressed ? 0.90 : 1.0
                Behavior on scale { NumberAnimation { duration: 90 } }
                visible: opacity > 0.01
                opacity: root.pinned ? 1 : 0
                Behavior on opacity { NumberAnimation { duration: root.animFast } }

                Text {
                    anchors.centerIn: parent
                    text: "\ue711"              // close
                    color: closeArea.containsMouse ? root.colFg : Qt.rgba(1, 1, 1, 0.70)
                    font { family: root.iconFam; pixelSize: 9 }
                }

                MouseArea {
                    id: closeArea
                    objectName: "closeButton"   // --test-close drives this control
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: root.closeAll()
                }
            }
        }

    }

    // ------------------------------------------ concave notch corners
    // These sit at root level, in absolute screen coordinates. As children of
    // the capsule they would inherit its own offset a second time and land off
    // to the side of the screen. Two of them flank the EkPill wherever it docks.
    NotchCorner {
        id: notchBefore
        // Above a right-docked pill the square is filled at its top-right
        // (screen edge + capsule top); a top-docked pill fills top-left.
        side: root.vertical ? "right" : "left"
        flipY: false
        fill: root.colBg
        r: root.cornerR
        x: root.atRight ? root.width - width : Math.round(capsule.x) - width
        y: root.vertical ? capsule.y - height : 0
        opacity: (root.expanded || root.autoHidden) ? 0 : 1
        Behavior on opacity { NumberAnimation { duration: root.animFast } }
    }

    NotchCorner {
        id: notchAfter
        // Below a right-docked pill the square is filled at its bottom-right;
        // the top-docked one fills top-right.
        side: "right"
        flipY: root.vertical
        fill: root.colBg
        r: root.cornerR
        x: root.atRight ? root.width - width : Math.round(capsule.x + capsule.width)
        y: root.vertical ? capsule.y + capsule.height : 0
        opacity: (root.expanded || root.autoHidden) ? 0 : 1
        Behavior on opacity { NumberAnimation { duration: root.animFast } }
    }

    // ------------------------------------------------------------- navigation
    function openPage(p) {
        root.dismissed = false;
        root.page = p;
        root.pinned = true;
        backend.setFocusHeld(p === "launcher");
        root.updateHotRegion();
    }
    function closeAll() {
        // Only latch the dismissal while the pointer is actually resting on
        // the ekpill. Closing by clicking elsewhere used to leave `dismissed`
        // set with no hover change to clear it, so the next hover did nothing
        // and only the second one opened the ekpill.
        root.dismissed = root.hovered;
        root.pinned = false;
        root.page = "";
        backend.setFocusHeld(false);
        root.updateHotRegion();
    }
    function backToQuick() { root.page = ""; root.pinned = false; }

    // Diagnostics for the headless selftest, readable as plain properties.
    readonly property int loaderStatus: inlinePanel.status
    readonly property string loaderError:
        inlinePanel.status === 3 ? "page failed to load" : ""
    readonly property bool loaderHasItem: inlinePanel.item !== null
    readonly property var panelItem: inlinePanel.item
    readonly property real panelImplicitWidth:
        inlinePanel.item ? inlinePanel.item.implicitWidth : -1
    readonly property real panelImplicitHeight:
        inlinePanel.item ? inlinePanel.item.implicitHeight : -1
    readonly property real capsuleOpacity: capsule.opacity

    function getExpectedPageSize(p) {
        if (p === "files") return Qt.size(520, 486);
        if (p === "launcher") return Qt.size(470, 420);
        if (p === "settings") return Qt.size(250, 265);
        if (p === "record") return Qt.size(380, 420);
        if (p === "audio") return Qt.size(380, 260);
        if (p === "media") return Qt.size(372, 182);
        if (p === "power") return Qt.size(340, 120);
        if (p === "quick") return Qt.size(340, 170);
        return Qt.size(340, 170);
    }

    function updateHotRegion() {
        var cx0 = Math.round(capsule.x), cy0 = Math.round(capsule.y);
        var cx1 = cx0 + Math.round(capsule.width), cy1 = cy0 + Math.round(capsule.height);
        var x0 = cx0, y0 = cy0, x1 = cx1, y1 = cy1;

        if (root.expanded || root.page !== "") {
            var active = root.activePage !== "" ? root.activePage : (root.page !== "" ? root.page : "quick");
            var expSize = getExpectedPageSize(active);
            var tw = Math.round(inlinePanel.item ? Math.max(inlinePanel.item.implicitWidth, expSize.width) : expSize.width);
            var th = Math.round(inlinePanel.item ? Math.max(inlinePanel.item.implicitHeight, expSize.height) : expSize.height);
            var targetX = root.atRight ? root.width - tw
                                       : Math.round((root.width - tw) / 2);
            var targetY = root.atTop ? 0 : Math.round((root.height - th) / 2);
            x0 = Math.min(x0, targetX);
            y0 = Math.min(y0, targetY);
            x1 = Math.max(x1, targetX + tw);
            y1 = Math.max(y1, targetY + th);
        }

        backend.setHotRegion(x0, y0, Math.max(1, x1 - x0), Math.max(1, y1 - y0));
    }

    // Keep the host's idea of the interactive area in step with the animation.
    Timer {
        interval: 50
        running: true
        repeat: true
        onTriggered: root.updateHotRegion()
    }

    // ------------------------------------------- capture geometry (selftest)
    // The capsule body is black on a transparent window, so a grab of the
    // overlay is black-on-black: there is no pixel that reveals where the pill
    // ends. The capture asks instead of guessing, so the preview can crop to
    // the real silhouette rather than to the text inside it.
    readonly property rect capRect: Qt.rect(capsule.x, capsule.y,
                                            capsule.width, capsule.height)
}
