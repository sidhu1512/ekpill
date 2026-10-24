import QtQuick
import QtQuick.Layouts
import ".."

// Files — the folders you actually use, the drives on this machine, and one
// list. Clicking a folder descends in place; clicking an image, video or text
// file goes to the app Windows has registered for it, like Explorer.
//
// Delete is the Recycle Bin, never `os.remove`: the ✕ on a row is undoable in
// Explorer, which is the only kind of delete a shell should offer. A right
// click (or the ⋯ button) carries the other verbs — rename, copy, cut, paste —
// and the rename happens in place, in the capsule's own header.
Item {
    id: page
    objectName: "filesPage"
    property var ekpill

    readonly property int pad: 18
    implicitWidth: 520

    // One line of feedback for the verbs: a refused name, a paste error, a
    // cut that is waiting for somewhere to go.
    property string flash: ""
    Timer {
        id: flashTimer
        interval: 2600
        onTriggered: page.flash = ""
    }

    // Rename is an inline editor, not a dialog: the capsule already owns the
    // keyboard for the launcher, and setFocusHeld is how it keeps it.
    property string renaming: ""
    property string renameText: ""

    // Escape backs out one level before the EkPill itself goes away: a
    // rename in progress is cancelled, an open row menu is closed. The
    // EkPill asks this first, because its window never holds the keyboard
    // and the page's own key handler may never run.
    //
    // The mark is a time, not a flag: if the pointer left before the EkPill
    // got round to asking, a stale flag would swallow a later, unrelated
    // Escape and the EkPill would need two presses to close.
    property double escapeUsedAt: 0

    function escapeHandler() {
        // The page's own key handler already used this Escape.
        if (page.escapeUsedAt > 0 && Date.now() - page.escapeUsedAt < 500) {
            page.escapeUsedAt = 0;
            return true;
        }
        if (page.renaming !== "") {
            page.cancelRename();
            return true;
        }
        if (page.menuOpen) {
            page.closeMenu();
            return true;
        }
        return false;
    }

    // The row menu. It holds a path, never an index: the listing can re-sort
    // between opening the menu and choosing from it.
    property bool menuOpen: false
    property var menuEntry: null
    property real menuY: 0

    Component.onDestruction: backend.setFocusHeld(false)

    // ------------------------------------------------------------- the verbs
    function openMenu(entry, y) {
        page.menuEntry = entry;
        page.menuY = y;
        page.menuOpen = true;
    }

    function closeMenu() {
        page.menuOpen = false;
        page.menuEntry = null;
    }

    function beginRename(entry) {
        page.closeMenu();
        page.flash = "";
        page.renaming = entry.path;
        page.renameText = entry.name;
        // Typing into a TextInput breaks its `text` binding, so each rename
        // seeds the field explicitly instead of trusting the first binding.
        renameInput.text = entry.name;
        backend.setFocusHeld(true);
    }

    function cancelRename() {
        page.renaming = "";
        backend.setFocusHeld(false);
    }

    function commitRename() {
        var err = backend.renamePath(page.renaming, page.renameText);
        if (err === "") {
            page.renaming = "";
            backend.setFocusHeld(false);
        } else {
            page.flash = err;
            flashTimer.restart();
        }
    }

    function makeFolder() {
        var path = backend.newFolder();
        if (path === "") {
            page.flash = "Could not create a folder";
            flashTimer.restart();
            return;
        }
        page.beginRename({ "path": path, "name": path.split("\\").pop() });
    }

    function paste() {
        var err = backend.pasteFiles();
        page.flash = err === "" ? "Pasted" : err;
        flashTimer.restart();
    }

    function runMenu(action) {
        var entry = page.menuEntry;
        page.closeMenu();
        if (!entry)
            return;
        if (action === "open") {
            backend.activatePath(entry.path);
        } else if (action === "rename") {
            page.beginRename(entry);
        } else if (action === "copy" || action === "cut") {
            backend.copyFile(entry.path, action === "cut");
            page.flash = (action === "cut" ? "Cut " : "Copied ") + entry.name
                         + " — paste it in another folder";
            flashTimer.restart();
        } else if (action === "trash") {
            if (!backend.trashFile(entry.path)) {
                page.flash = "Could not recycle it";
                flashTimer.restart();
            }
        }
    }

    function menuActions(entry) {
        return entry === null ? [] : [
            { "label": "Open", "act": "open" },
            { "label": "Rename", "act": "rename" },
            { "label": "Copy", "act": "copy" },
            { "label": "Cut", "act": "cut" },
            { "label": "Recycle", "act": "trash" }
        ];
    }

    // Diagnostics for the headless run: --page=files --menu photographs the
    // menu, so the one interactive surface that is not a page state is shown.
    property bool demoMenu: false
    onDemoMenuChanged: if (demoMenu && backend.filesItems.length > 0) page.openMenu(backend.filesItems[0], 120)

    // Bookmark and drive lists are read once: a shell page that re-enumerates
    // drives on every frame is a page that stutters for no reason.
    property var marks: []
    property var disks: []
    Component.onCompleted: {
        page.marks = backend.bookmarks();
        page.disks = backend.drives();
    }

    implicitHeight: 486

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: page.pad
        spacing: 10

        // ------------------------------------------------------------- header
        RowLayout {
            Layout.fillWidth: true
            Layout.rightMargin: (page.ekpill && page.ekpill.pinned) ? 28 : 0
            spacing: 10

            Text {
                text: "Files"
                color: page.ekpill.colFg
                font { family: page.ekpill.fontFam; pixelSize: 15; bold: true }
            }

            Text {
                Layout.fillWidth: true
                text: backend.filesShown + (backend.filesShown === 1 ? " item" : " items")
                      + (backend.filesTotal > backend.filesShown
                         ? " of " + backend.filesTotal : "")
                color: page.ekpill.colMuted
                elide: Text.ElideRight
                font { family: page.ekpill.fontFam; pixelSize: 10 }
            }

            Repeater {
                model: ["name", "date", "size"]

                Text {
                    required property string modelData
                    text: modelData === "name" ? "Name"
                        : modelData === "date" ? "Date" : "Size"
                    color: backend.filesSort === modelData ? page.ekpill.colFg
                                                           : page.ekpill.colMuted
                    font {
                        family: page.ekpill.fontFam; pixelSize: 10
                        bold: backend.filesSort === modelData
                    }
                    MouseArea {
                        anchors.fill: parent
                        anchors.margins: -5
                        cursorShape: Qt.PointingHandCursor
                        onClicked: backend.sortFiles(modelData)
                    }
                }
            }
        }

        // --------------------------------------------------------- bookmarks
        // Two scrollable rails rather than one: seven folders plus four drives
        // do not fit across 484px, and an off-screen drive is a drive the user
        // will not find. Drag either rail sideways.
        Flickable {
            Layout.fillWidth: true
            Layout.preferredHeight: 24
            contentWidth: bookChips.implicitWidth
            contentHeight: height
            clip: true
            boundsBehavior: Flickable.StopAtBounds

            Row {
                id: bookChips
                spacing: 5

                Repeater {
                    model: page.marks

                    Rectangle {
                        required property var modelData
                        width: markRow.implicitWidth + 14
                        height: 22
                        radius: 11
                        opacity: modelData.locked ? 0.38 : 1
                        color: backend.filesPath === modelData.path
                               ? page.ekpill.colFg : page.ekpill.colTile

                        Row {
                            id: markRow
                            anchors.centerIn: parent
                            spacing: 4

                            Glyph {
                                anchors.verticalCenter: parent.verticalCenter
                                glyph: modelData.glyph
                                size: 10
                                fontFam: page.ekpill.iconFam
                                color: backend.filesPath === modelData.path
                                       ? page.ekpill.colBg : page.ekpill.colMuted
                            }

                            Text {
                                anchors.verticalCenter: parent.verticalCenter
                                text: modelData.name
                                color: backend.filesPath === modelData.path
                                       ? page.ekpill.colBg : (modelData.locked ? page.ekpill.colMuted : page.ekpill.colFg)
                                font { family: page.ekpill.fontFam; pixelSize: 10 }
                            }
                        }

                        MouseArea {
                            anchors.fill: parent
                            enabled: !modelData.locked
                            cursorShape: modelData.locked ? Qt.ArrowCursor : Qt.PointingHandCursor
                            onClicked: if (!modelData.locked) backend.browse(modelData.path)
                        }
                    }
                }
            }
        }

        // ------------------------------------------------------------- disks
        Flickable {
            Layout.fillWidth: true
            Layout.preferredHeight: 24
            contentWidth: diskChips.implicitWidth
            contentHeight: height
            clip: true
            boundsBehavior: Flickable.StopAtBounds

            Row {
                id: diskChips
                spacing: 5

                Repeater {
                    model: page.disks

                    Rectangle {
                        required property var modelData
                        width: diskRow.implicitWidth + 14
                        height: 22
                        radius: 11
                        opacity: modelData.locked ? 0.38 : 1
                        color: backend.filesPath === modelData.path
                               ? page.ekpill.colFg : page.ekpill.colTile

                        Row {
                            id: diskRow
                            anchors.centerIn: parent
                            spacing: 4

                            Text {
                                text: modelData.name.replace("\\", "")
                                color: backend.filesPath === modelData.path
                                       ? page.ekpill.colBg : (modelData.locked ? page.ekpill.colMuted : page.ekpill.colFg)
                                font { family: page.ekpill.fontFam; pixelSize: 10; bold: true }
                            }

                            Text {
                                anchors.verticalCenter: parent.verticalCenter
                                text: modelData.label !== "" ? modelData.label : modelData.kind
                                color: backend.filesPath === modelData.path
                                       ? page.ekpill.colBg : page.ekpill.colMuted
                                font { family: page.ekpill.fontFam; pixelSize: 9 }
                            }
                        }

                        MouseArea {
                            anchors.fill: parent
                            enabled: !modelData.locked
                            cursorShape: modelData.locked ? Qt.ArrowCursor : Qt.PointingHandCursor
                            onClicked: if (!modelData.locked) backend.browse(modelData.path)
                        }
                    }
                }
            }
        }

        // ------------------------------------------------- breadcrumb / rename
        RowLayout {
            visible: page.renaming === ""
            Layout.fillWidth: true
            spacing: 8

            Text {
                visible: backend.filesParent !== ""
                text: "\uE72B"          // back
                color: page.ekpill.colFg
                font { family: page.ekpill.iconFam; pixelSize: 12 }
                MouseArea {
                    anchors.fill: parent
                    anchors.margins: -6
                    cursorShape: Qt.PointingHandCursor
                    onClicked: backend.browseUp()
                }
            }

            Text {
                Layout.fillWidth: true
                text: backend.filesPath
                color: page.ekpill.colMuted
                elide: Text.ElideMiddle
                font { family: page.ekpill.fontFam; pixelSize: 10 }
            }

            Text {
                visible: backend.filesParent !== ""
                text: "Open in Explorer"
                color: page.ekpill.colMuted
                font { family: page.ekpill.fontFam; pixelSize: 10 }
                MouseArea {
                    anchors.fill: parent
                    anchors.margins: -5
                    cursorShape: Qt.PointingHandCursor
                    onClicked: backend.openExternal(backend.filesPath)
                }
            }
        }

        // The editor replaces the breadcrumb while it is up, so the page keeps
        // one row for "where am I" whatever is happening.
        RowLayout {
            visible: page.renaming !== ""
            Layout.fillWidth: true
            Layout.preferredHeight: 24
            spacing: 8

            Text {
                text: "Rename"
                color: page.ekpill.colMuted
                font { family: page.ekpill.fontFam; pixelSize: 10 }
            }

            Rectangle {
                Layout.fillWidth: true
                height: 24
                radius: 6
                color: page.ekpill.colTile

                TextInput {
                    id: renameInput
                    anchors.fill: parent
                    anchors.leftMargin: 7
                    anchors.rightMargin: 7
                    verticalAlignment: TextInput.AlignVCenter
                    text: page.renameText
                    color: page.ekpill.colFg
                    selectionColor: page.ekpill.colFg
                    selectedTextColor: page.ekpill.colBg
                    font { family: page.ekpill.fontFam; pixelSize: 11 }
                    onTextChanged: page.renameText = text
                    onVisibleChanged: if (visible) { forceActiveFocus(); selectAll(); }
                    onAccepted: page.commitRename()
                    Keys.onPressed: function (event) {
                        if (event.key === Qt.Key_Escape) {
                            // Marked, so the EkPill's own Escape watcher does
                            // not close the page on top of this.
                            page.escapeUsedAt = Date.now();
                            page.cancelRename();
                            event.accepted = true;
                        }
                    }
                }
            }

            Text {
                text: "Enter / Esc"
                color: Qt.rgba(1, 1, 1, 0.28)
                font { family: page.ekpill.fontFam; pixelSize: 9 }
            }
        }

        Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: page.ekpill.colLine }

        // ------------------------------------------------------------- empty
        Item {
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: backend.filesItems.length === 0

            Text {
                anchors.centerIn: parent
                width: parent.width - 20
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.WordWrap
                text: "This folder is empty."
                color: page.ekpill.colMuted
                font { family: page.ekpill.fontFam; pixelSize: 12 }
            }
        }

        // -------------------------------------------------------------- list
        ListView {
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: backend.filesItems.length > 0
            clip: true
            spacing: 2
            model: backend.filesItems

            delegate: Rectangle {
                id: row
                required property int index
                required property var modelData

                width: ListView.view.width
                height: 30
                radius: 7
                // A folder this user cannot open is visibly inert: dimmed,
                // no hover, no pointer cursor, no menu.
                opacity: modelData.locked ? 0.42 : 1
                color: rowHover.hovered && !modelData.locked ? Qt.rgba(1, 1, 1, 0.07) : "transparent"

                HoverHandler { id: rowHover }

                Glyph {
                    id: rowIcon
                    anchors.left: parent.left
                    anchors.leftMargin: 8
                    anchors.verticalCenter: parent.verticalCenter
                    glyph: modelData.dir ? "\uE8B7"          // folder
                         : modelData.kind === "image" ? "\uEB9F"
                         : modelData.kind === "video" ? "\uE714"
                         : modelData.kind === "audio" ? "\uE8D6"
                         : modelData.kind === "text" ? "\uE8A5"
                         : "\uE7C3"                          // document
                    size: 13
                    fontFam: page.ekpill.iconFam
                    color: modelData.dir && !modelData.locked ? page.ekpill.colFg : page.ekpill.colMuted
                }

                Text {
                    anchors.left: rowIcon.right
                    anchors.leftMargin: 9
                    anchors.right: rowMeta.left
                    anchors.rightMargin: 10
                    anchors.verticalCenter: parent.verticalCenter
                    text: modelData.name
                    color: modelData.locked ? page.ekpill.colMuted : page.ekpill.colFg
                    elide: Text.ElideMiddle
                    font { family: page.ekpill.fontFam; pixelSize: 11 }
                }

                Text {
                    id: rowMeta
                    anchors.right: parent.right
                    anchors.rightMargin: 52
                    anchors.verticalCenter: parent.verticalCenter
                    text: modelData.dir ? "" : modelData.sizeText
                    color: page.ekpill.colMuted
                    horizontalAlignment: Text.AlignRight
                    font { family: page.ekpill.fontFam; pixelSize: 9 }
                }

                // More first: ⋯ opens the verbs.
                Text {
                    id: rowMenu
                    z: 2                   // above the row's open-on-click area
                    visible: !modelData.locked
                    anchors.right: parent.right
                    anchors.rightMargin: 9
                    anchors.verticalCenter: parent.verticalCenter
                    text: "\uE712"        // more
                    color: page.ekpill.colMuted
                    opacity: rowHover.hovered ? 1 : 0
                    font { family: page.ekpill.iconFam; pixelSize: 11 }

                    MouseArea {
                        anchors.fill: parent
                        anchors.margins: -6
                        enabled: rowHover.hovered
                        cursorShape: Qt.PointingHandCursor
                        onClicked: page.openMenu(modelData, row.mapToItem(page, 0, 0).y + row.height)
                    }
                }

                // Only on hover, and only ever the Recycle Bin: the label says
                // "Recycle" so nobody has to guess.
                Text {
                    id: rowTrash
                    z: 2                   // above the row's open-on-click area
                    visible: !modelData.locked
                    anchors.right: parent.right
                    anchors.rightMargin: 28
                    anchors.verticalCenter: parent.verticalCenter
                    text: "\uE74D"
                    color: page.ekpill.colMuted
                    opacity: rowHover.hovered ? 1 : 0
                    font { family: page.ekpill.iconFam; pixelSize: 11 }

                    MouseArea {
                        anchors.fill: parent
                        anchors.margins: -6
                        // The button is invisible until the row is hovered;
                        // an invisible-but-enabled target would eat clicks
                        // meant to open the file underneath it.
                        enabled: rowHover.hovered
                        cursorShape: Qt.PointingHandCursor
                        onClicked: backend.trashFile(modelData.path)
                    }
                }

                MouseArea {
                    id: rowArea
                    anchors.fill: parent
                    acceptedButtons: Qt.LeftButton | Qt.RightButton
                    enabled: !modelData.locked
                    cursorShape: modelData.locked ? Qt.ArrowCursor : Qt.PointingHandCursor
                    onClicked: function (mouse) {
                        if (modelData.locked)
                            return;
                        if (mouse.button === Qt.RightButton)
                            page.openMenu(modelData, row.mapToItem(page, 0, 0).y + row.height);
                        else
                            backend.activateFile(index);
                    }
                }
            }
        }

        // ------------------------------------------------------------- footer
        RowLayout {
            Layout.fillWidth: true
            spacing: 12

            Text {
                Layout.fillWidth: true
                text: page.flash !== "" ? page.flash
                    : backend.filesSort === "name" ? "Folders first · sorted by name"
                    : backend.filesSort === "date" ? "Folders first · newest first"
                    : "Folders first · largest first"
                color: page.flash !== "" ? page.ekpill.colFg
                                          : Qt.rgba(1, 1, 1, 0.28)
                elide: Text.ElideRight
                font { family: page.ekpill.fontFam; pixelSize: 9 }
            }

            Text {
                text: "New folder"
                color: page.ekpill.colMuted
                font { family: page.ekpill.fontFam; pixelSize: 9 }
                MouseArea {
                    anchors.fill: parent
                    anchors.margins: -5
                    cursorShape: Qt.PointingHandCursor
                    onClicked: page.makeFolder()
                }
            }

            Text {
                visible: backend.fileClipActive
                text: (backend.fileClipCut ? "Move here" : "Paste")
                color: page.ekpill.colFg
                font { family: page.ekpill.fontFam; pixelSize: 9; bold: true }
                MouseArea {
                    anchors.fill: parent
                    anchors.margins: -5
                    cursorShape: Qt.PointingHandCursor
                    onClicked: page.paste()
                }
            }
        }
    }

    // ------------------------------------------------ click-away behind menu
    MouseArea {
        z: 90
        anchors.fill: parent
        visible: page.menuOpen
        acceptedButtons: Qt.LeftButton | Qt.RightButton
        onClicked: page.closeMenu()
    }

    // ------------------------------------------------------------ row menu
    Rectangle {
        id: contextMenu
        z: 100
        visible: page.menuOpen
        width: 168
        height: menuCol.implicitHeight + 10
        x: page.width - width - 10
        y: Math.max(8, Math.min(page.menuY, page.height - height - 10))
        radius: 10
        color: "#171717"
        border.width: 1
        border.color: page.ekpill.colLine
        opacity: page.menuOpen ? 1 : 0

        Column {
            id: menuCol
            anchors.fill: parent
            anchors.margins: 5
            spacing: 1

            Text {
                width: menuCol.width
                height: 20
                text: page.menuEntry ? page.menuEntry.name : ""
                color: page.ekpill.colMuted
                elide: Text.ElideMiddle
                verticalAlignment: Text.AlignVCenter
                font { family: page.ekpill.fontFam; pixelSize: 9; bold: true }
            }

            Repeater {
                model: page.menuActions(page.menuEntry)

                Rectangle {
                    required property var modelData
                    width: menuCol.width
                    height: 26
                    radius: 6
                    color: menuHover.hovered ? Qt.rgba(1, 1, 1, 0.08) : "transparent"

                    HoverHandler { id: menuHover }

                    Text {
                        anchors.left: parent.left
                        anchors.leftMargin: 9
                        anchors.verticalCenter: parent.verticalCenter
                        text: modelData.label
                        color: page.ekpill.colFg
                        font { family: page.ekpill.fontFam; pixelSize: 10 }
                    }

                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        onClicked: page.runMenu(modelData.act)
                    }
                }
            }
        }
    }
}
