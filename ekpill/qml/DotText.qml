import QtQuick

// Numerals drawn as dots — the Nothing figure style.
//
// The NothingOS face (NDot) is not installed and is not in any repository, and
// asking someone to drop a foreign font on their machine for one look is a bad
// price. The digits are laid out on a 5x7 grid and rendered as circles instead:
// exact at any size, tinted like any other item, and independent of what fonts
// the machine happens to have.
//
// Circles rather than squares, because round dots are what NOS uses; square ones
// read as an eighties pixel font.
Item {
    id: dt

    property string value: ""

    // Height of a digit in pixels — the same thing plain text is measured by.
    property real size: 14
    // Space between dots as a fraction of their diameter; it doubles as weight.
    // There are no strokes here, only dots, so "bolder" means "denser".
    property real gapRatio: 0.22
    property color color: "#ffffff"

    // Back out the diameter from the height: seven rows plus six gaps.
    readonly property real dotSize: size / (7 + 6 * gapRatio)
    readonly property real gap: dotSize * gapRatio
    readonly property real pitch: dotSize + gap
    // Space between glyphs; one empty grid column by default.
    property real charGap: dotSize + gap

    // Seven rows tall. Widths differ: a colon in five columns would look like a
    // hole between the digits.
    readonly property var glyphs: ({
        // A zero with no diagonal: Nothing draws a smooth oval, and the slash
        // is a terminal-font habit, not this look.
        "0": ["01110", "10001", "10001", "10001", "10001", "10001", "01110"],
        "1": ["00100", "01100", "00100", "00100", "00100", "00100", "01110"],
        "2": ["01110", "10001", "00001", "00010", "00100", "01000", "11111"],
        "3": ["11111", "00010", "00100", "00010", "00001", "10001", "01110"],
        "4": ["00010", "00110", "01010", "10010", "11111", "00010", "00010"],
        "5": ["11111", "10000", "11110", "00001", "00001", "10001", "01110"],
        "6": ["00110", "01000", "10000", "11110", "10001", "10001", "01110"],
        "7": ["11111", "00001", "00010", "00100", "01000", "01000", "01000"],
        "8": ["01110", "10001", "10001", "01110", "10001", "10001", "01110"],
        "9": ["01110", "10001", "10001", "01111", "00001", "00010", "01100"],
        ":": ["0", "0", "1", "0", "0", "1", "0"],
        ".": ["0", "0", "0", "0", "0", "0", "1"],
        "-": ["000", "000", "000", "111", "000", "000", "000"],
        "%": ["11001", "11010", "00100", "00100", "00100", "01011", "10011"],
        "°": ["111", "101", "111", "000", "000", "000", "000"],
        " ": ["00", "00", "00", "00", "00", "00", "00"],
        "A": ["01110", "10001", "10001", "11111", "10001", "10001", "10001"],
        "P": ["11110", "10001", "10001", "11110", "10000", "10000", "10000"],
        "M": ["10001", "11011", "10101", "10001", "10001", "10001", "10001"]
    })

    // Lit dots as {x, y} in pixels, recomputed only when the string changes
    // rather than keeping a Repeater over all 35 cells of every glyph.
    readonly property var cells: {
        var out = [];
        var s = String(dt.value);
        var cx = 0;
        for (var i = 0; i < s.length; i++) {
            var g = dt.glyphs[s[i]];
            // An unknown glyph is not drawn but still takes space, so the line
            // does not jump around on a surprise character.
            var w = g ? g[0].length : 3;
            if (g) {
                for (var r = 0; r < g.length; r++)
                    for (var c = 0; c < w; c++)
                        if (g[r][c] === "1")
                            out.push({ x: cx + c * dt.pitch, y: r * dt.pitch });
            }
            cx += w * dt.pitch;
            if (i < s.length - 1) cx += dt.charGap;
        }
        return out;
    }

    // Width from the same formula, not from the last lit dot: a glyph with an
    // empty final column ("1", "7") would otherwise measure a column short and
    // its neighbours would shuffle.
    implicitWidth: {
        var s = String(dt.value);
        if (!s.length) return 0;
        var w = 0;
        for (var i = 0; i < s.length; i++) {
            var g = dt.glyphs[s[i]];
            w += (g ? g[0].length : 3) * dt.pitch;
        }
        return w + (s.length - 1) * dt.charGap - dt.gap;
    }
    implicitHeight: 7 * dt.pitch - dt.gap

    Repeater {
        model: dt.cells

        Rectangle {
            required property var modelData
            x: modelData.x
            y: modelData.y
            width: dt.dotSize
            height: dt.dotSize
            radius: dt.dotSize / 2
            color: dt.color
        }
    }
}
