import QtQuick
import QtQuick.Shapes

// The concave fillet where the EkPill meets the screen edge — the macOS-notch
// trick, rendered with GPU-accelerated vector geometry via QtQuick.Shapes.
Shape {
    id: corner

    // "left"  — the corner to the left of the capsule (notch opens left-down)
    // "right" — mirrored
    property string side: "left"
    property color fill: "#000000"
    property real r: 12
    // Flip vertically for the bottom edge and the side edges.
    property bool flipY: false

    width: r
    height: r
    clip: true
    preferredRendererType: Shape.CurveRenderer
    transform: Scale { origin.y: corner.r / 2; yScale: corner.flipY ? -1 : 1 }

    ShapePath {
        fillColor: corner.fill
        strokeWidth: 0
        strokeColor: "transparent"

        startX: corner.side === "left" ? 0 : corner.r
        startY: 0

        PathLine { x: corner.side === "left" ? corner.r : 0; y: 0 }
        PathLine { x: corner.side === "left" ? corner.r : 0; y: corner.r }
        PathArc {
            x: corner.side === "left" ? 0 : corner.r
            y: 0
            radiusX: corner.r
            radiusY: corner.r
            useLargeArc: false
            direction: corner.side === "left" ? PathArc.Counterclockwise
                                              : PathArc.Clockwise
        }
    }
}
