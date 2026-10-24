import QtQuick

// A system-font icon centred on the ink, not on the advance box.
//
// A plain Text centres on its frame, whose width is the glyph's advance. Icon
// faces put the ink off-centre inside that advance — a gear at pixelSize 16 can
// advance 9.6px while the drawing is 13px wide — so anchors.centerIn visibly
// drags the icon sideways. TextMetrics gives bounding/tightBounding rects
// relative to the baseline, so we line the ink centre up with the item centre.
Item {
    id: glyph

    property string glyph: ""
    property color color: "#ffffff"
    property string fontFam: "Segoe Fluent Icons"
    property real size: 16

    implicitWidth: size
    implicitHeight: size

    TextMetrics {
        id: tm
        font { family: glyph.fontFam; pixelSize: glyph.size }
        text: glyph.glyph
    }

    readonly property real baselineY: -tm.boundingRect.y
    readonly property real inkX: tm.tightBoundingRect.x + tm.tightBoundingRect.width / 2
    readonly property real inkY: baselineY + tm.tightBoundingRect.y
                                 + tm.tightBoundingRect.height / 2

    Text {
        text: glyph.glyph
        color: glyph.color
        font { family: glyph.fontFam; pixelSize: glyph.size }

        // Round the position: at fractional coordinates the icon smears across
        // subpixels and looks dirty.
        x: Math.round(glyph.width / 2 - glyph.inkX)
        y: Math.round(glyph.height / 2 - glyph.inkY)

        Behavior on color { ColorAnimation { duration: 160 } }
    }
}
