import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// Launcher: app search, recents first.
// Everything the Start Menu exposes is searchable.
Item {
    id: page
    property var ekpill

    readonly property int pad: 16
    implicitWidth: 470
    implicitHeight: 420

    // apps() is the full Start Menu list; match() narrows it as you type.
    property var allApps: []
    property var matches: []

    Component.onCompleted: {
        allApps = backend.apps();
        refresh("");
    }

    function refresh(text) {
        var q = (text || "").toLowerCase().trim();
        var out = [];
        if (q === "") {
            out = allApps.slice(0, 60);
        } else {
            for (var i = 0; i < allApps.length && out.length < 60; i++) {
                var a = allApps[i];
                if (a.name.toLowerCase().indexOf(q) !== -1)
                    out.push(a);
            }
        }
        matches = out;
        appList.currentIndex = matches.length ? 0 : -1;
    }

    function activate(index) {
        if (matches.length === 0 || index < 0) return;
        var item = matches[index];
        if (item) backend.launch(item.path);
        page.ekpill.closeAll();
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: page.pad
        spacing: 12

        // ------------------------------------------------------------- search
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 6

            TextField {
                id: search
                Layout.fillWidth: true
                Layout.rightMargin: (page.ekpill && page.ekpill.pinned) ? 32 : 0
                focus: true
                placeholderText: "Search apps..."
                color: page.ekpill.colFg
                placeholderTextColor: page.ekpill.colMuted
                font { family: page.ekpill.fontFam; pixelSize: 15 }
                selectByMouse: true
                background: Rectangle {
                    color: page.ekpill.colTile
                    radius: 10
                }
                onTextChanged: page.refresh(text)

                Keys.onEscapePressed: page.ekpill.closeAll()
                Keys.onUpPressed: appList.decrementCurrentIndex()
                Keys.onDownPressed: appList.incrementCurrentIndex()
                Keys.onReturnPressed: page.activate(appList.currentIndex)
                Keys.onEnterPressed: page.activate(appList.currentIndex)
            }
        }

        // --------------------------------------------------------------- list
        ListView {
            id: appList
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            model: page.matches
            spacing: 2
            currentIndex: -1

            delegate: Item {
                required property var modelData
                required property int index
                width: appList.width
                height: 34

                Rectangle {
                    anchors.fill: parent
                    radius: 8
                    color: index === appList.currentIndex ? page.ekpill.colTile : "transparent"
                }

                Text {
                    anchors.left: parent.left
                    anchors.leftMargin: 10
                    anchors.verticalCenter: parent.verticalCenter
                    text: modelData.name
                    color: page.ekpill.colFg
                    font { family: page.ekpill.fontFam; pixelSize: 13 }
                }

                MouseArea {
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onEntered: appList.currentIndex = index
                    onClicked: page.activate(index)
                }
            }
        }
    }
}
