import QtQuick
import QtQuick.Layouts
import ".."

// Wallpaper — the art the app ships, plus whatever the user put in
// Pictures\Wallpapers, and the one click that makes it the desktop.
//
// Windows owns the desktop, so this is not a compositor carousel: it is a
// picker that hands SystemParametersInfoW a path and the fill mode a user
// expects from the Settings app. The chosen image is read back from Windows,
// not remembered here, so the highlight tells the truth.
Item {
    id: page
    property var ekpill

    readonly property int pad: 18
    readonly property int cols: 3
    implicitWidth: 520
    implicitHeight: 430

    property string flash: ""
    Timer {
        id: flashTimer
        interval: 1600
        onTriggered: page.flash = ""
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: page.pad
        spacing: 10

        // ------------------------------------------------------------- header
        RowLayout {
            Layout.fillWidth: true
            spacing: 10

            Text {
                text: "Wallpaper"
                color: page.ekpill.colFg
                font { family: page.ekpill.fontFam; pixelSize: 15; bold: true }
            }

            Text {
                Layout.fillWidth: true
                text: page.flash !== "" ? page.flash
                    : backend.wallpaperImages.length
                      + (backend.wallpaperImages.length === 1 ? " image" : " images")
                color: page.flash !== "" ? page.ekpill.colFg : page.ekpill.colMuted
                elide: Text.ElideRight
                font { family: page.ekpill.fontFam; pixelSize: 10 }
            }

            Text {
                text: "Refresh"
                color: page.ekpill.colMuted
                font { family: page.ekpill.fontFam; pixelSize: 10 }
                MouseArea {
                    anchors.fill: parent
                    anchors.margins: -6
                    cursorShape: Qt.PointingHandCursor
                    onClicked: backend.refreshWallpapers()
                }
            }
        }

        // ----------------------------------------------------------- the mode
        RowLayout {
            Layout.fillWidth: true
            spacing: 6

            Repeater {
                model: ["fill", "fit", "center", "span"]

                Rectangle {
                    required property string modelData
                    width: modeLabel.implicitWidth + 20
                    height: 22
                    radius: 11
                    color: backend.wallpaperMode === modelData
                           ? page.ekpill.colFg : page.ekpill.colTile

                    Text {
                        id: modeLabel
                        anchors.centerIn: parent
                        text: modelData === "fill" ? "Fill"
                            : modelData === "fit" ? "Fit"
                            : modelData === "center" ? "Centre" : "Span"
                        color: backend.wallpaperMode === modelData
                               ? page.ekpill.colBg : page.ekpill.colFg
                        font { family: page.ekpill.fontFam; pixelSize: 9; bold: true }
                    }

                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        onClicked: backend.setWallpaperMode(modelData)
                    }
                }
            }

            Item { Layout.fillWidth: true }
        }

        // -------------------------------------------------------------- grid
        Item {
            Layout.fillWidth: true
            Layout.fillHeight: true

            Text {
                anchors.centerIn: parent
                width: parent.width - 30
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.WordWrap
                visible: backend.wallpaperImages.length === 0
                text: "No wallpapers found.\nDrop images into " + backend.wallpaperFolder
                color: page.ekpill.colMuted
                font { family: page.ekpill.fontFam; pixelSize: 11 }
            }

            GridView {
                anchors.fill: parent
                visible: backend.wallpaperImages.length > 0
                clip: true
                cellWidth: Math.floor(page.width / page.cols)
                cellHeight: 104
                model: backend.wallpaperImages
                boundsBehavior: Flickable.StopAtBounds

                delegate: Item {
                    required property var modelData
                    width: GridView.view.cellWidth
                    height: GridView.view.cellHeight

                    readonly property bool active:
                        backend.wallpaperCurrent.toLowerCase()
                        === modelData.path.toLowerCase()

                    Rectangle {
                        anchors.fill: parent
                        anchors.margins: 4
                        radius: 9
                        color: "#0b0b0b"
                        border.width: active ? 1 : 0
                        border.color: page.ekpill.colFg
                        clip: true

                        Image {
                            anchors.fill: parent
                            anchors.margins: active ? 1 : 0
                            source: modelData.url
                            sourceSize.width: 360          // thumbnails, not 4K decodes
                            sourceSize.height: 220
                            fillMode: Image.PreserveAspectCrop
                            asynchronous: true
                            cache: false
                        }

                        // The name sits on the image; bundled art says so.
                        Rectangle {
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.bottom: parent.bottom
                            height: 26
                            color: Qt.rgba(0, 0, 0, 0.62)

                            Text {
                                anchors.left: parent.left
                                anchors.leftMargin: 8
                                anchors.right: badge.left
                                anchors.verticalCenter: parent.verticalCenter
                                text: modelData.name
                                color: page.ekpill.colFg
                                elide: Text.ElideMiddle
                                font { family: page.ekpill.fontFam; pixelSize: 9; bold: active }
                            }

                            Text {
                                id: badge
                                anchors.right: parent.right
                                anchors.rightMargin: 8
                                anchors.verticalCenter: parent.verticalCenter
                                visible: modelData.bundled
                                text: "Bundled"
                                color: page.ekpill.colMuted
                                font { family: page.ekpill.fontFam; pixelSize: 8 }
                            }
                        }
                    }

                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        onClicked: {
                            backend.setWallpaper(modelData.path);
                            page.flash = modelData.name + " set";
                            flashTimer.restart();
                        }
                    }
                }
            }
        }

        // ------------------------------------------------------------- footer
        Text {
            Layout.fillWidth: true
            text: "Folder: " + backend.wallpaperFolder
                  + " · click an image to set it, " + backend.wallpaperMode
            color: Qt.rgba(1, 1, 1, 0.28)
            elide: Text.ElideMiddle
            font { family: page.ekpill.fontFam; pixelSize: 9 }
        }
    }
}
