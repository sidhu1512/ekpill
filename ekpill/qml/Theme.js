.pragma library

// The one look EkPill ships with: Nothing.
//
// There is no coloured accent on purpose. Nothing separates by brightness, not
// hue, and the only colour it keeps in reserve is red — for recording and for a
// battery that is about to die.

var bg = "#000000"
var fg = "#ffffff"
var on = "#ffffff"
var ok = "#ffffff"
var crit = "#d71921"

var mutedAlpha = 0.45
var hintAlpha = 0.30
var lineAlpha = 0.14
var tileAlpha = 0.16

function muted() { return Qt.rgba(1, 1, 1, mutedAlpha) }
function hint() { return Qt.rgba(1, 1, 1, hintAlpha) }
function line() { return Qt.rgba(1, 1, 1, lineAlpha) }
function tile() { return Qt.rgba(1, 1, 1, tileAlpha) }
