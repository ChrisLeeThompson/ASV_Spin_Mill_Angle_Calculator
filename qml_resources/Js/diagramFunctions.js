.pragma library

// =============================================================================
// DIAGRAM FUNCTIONS
//
// Generic Canvas drawing utilities for the beam-geometry figures (borrowed
// from Hydra Bio Cryo Utilities 3.0, trimmed to the primitives used here).
//
// This library contains NO instrument geometry — callers pass screen angles
// in. For example, the FIB reference line is drawn with:
//
//     DiagramFunctions.drawRadialLine(ctx, cx, cy, 0, len,
//                                     fibScreenAngleDeg, strokeStyle, width)
//
// Angle convention (screen angles):
//   0 deg = horizontal right, positive = counter-clockwise.
//   Conversion to the canvas' clockwise-positive y-down frame is handled
//   internally by each function.
// =============================================================================

// -----------------------------------------------------------------------------
// CORE DRAWING
// -----------------------------------------------------------------------------

// Generic line drawing function (used internally by other draw functions).
function drawLine(ctx, startX, startY, endX, endY, strokeStyle, lineWidth) {
    ctx.strokeStyle = strokeStyle;
    ctx.lineWidth = lineWidth;
    ctx.beginPath();
    ctx.moveTo(startX, startY);
    ctx.lineTo(endX, endY);
    ctx.stroke();
}

// -----------------------------------------------------------------------------
// RADIAL LINES - Lines at arbitrary screen angles from the figure center
// -----------------------------------------------------------------------------

// Draw a radial line starting at the reference circle edge, extending
// outward by lineLength at the given screen angle. Pass a radius of 0 to
// start the line at the exact center.
function drawRadialLine(ctx, centerX, centerY, referenceCircleRadius,
                        lineLength, angleDeg, strokeStyle, lineWidth) {
    var angleRad = angleDeg * Math.PI / 180;
    var startX = centerX + referenceCircleRadius * Math.cos(angleRad);
    var startY = centerY - referenceCircleRadius * Math.sin(angleRad);
    var endX = centerX + (referenceCircleRadius + lineLength) * Math.cos(angleRad);
    var endY = centerY - (referenceCircleRadius + lineLength) * Math.sin(angleRad);
    drawLine(ctx, startX, startY, endX, endY, strokeStyle, lineWidth);
}

// Draw a diameter line through the center at a specified screen angle.
function drawDiameterLine(ctx, centerX, centerY, referenceCircleRadius,
                          angleDeg, strokeStyle, lineWidth) {
    var angleRad = angleDeg * Math.PI / 180;
    var startX = centerX - referenceCircleRadius * Math.cos(angleRad);
    var startY = centerY + referenceCircleRadius * Math.sin(angleRad);
    var endX = centerX + referenceCircleRadius * Math.cos(angleRad);
    var endY = centerY - referenceCircleRadius * Math.sin(angleRad);
    drawLine(ctx, startX, startY, endX, endY, strokeStyle, lineWidth);
}

// -----------------------------------------------------------------------------
// ARC DRAWING
// -----------------------------------------------------------------------------

// Draw an arc between two screen angles (counter-clockwise from startAngleDeg
// to endAngleDeg when endAngleDeg > startAngleDeg).
function drawArc(ctx, centerX, centerY, radius, startAngleDeg,
                 endAngleDeg, strokeStyle, lineWidth) {
    ctx.strokeStyle = strokeStyle;
    ctx.lineWidth = lineWidth;
    // Negate angles to convert from CCW screen convention to canvas CW.
    var startAngle = -startAngleDeg * Math.PI / 180;
    var endAngle = -endAngleDeg * Math.PI / 180;
    ctx.beginPath();
    ctx.arc(centerX, centerY, radius, startAngle, endAngle, true);
    ctx.stroke();
}

// -----------------------------------------------------------------------------
// ELLIPSE DRAWING
// -----------------------------------------------------------------------------

// Draw an axis-aligned ellipse outline centered at (centerX, centerY).
// Uses Qt's non-standard Context2D ellipse(x, y, w, h) — a bounding-rect
// signature that adds a closed subpath (NOT the HTML5 7-argument form).
function drawEllipse(ctx, centerX, centerY, radiusX, radiusY,
                     strokeStyle, lineWidth) {
    ctx.strokeStyle = strokeStyle;
    ctx.lineWidth = lineWidth;
    ctx.beginPath();
    ctx.ellipse(centerX - radiusX, centerY - radiusY,
                radiusX * 2, radiusY * 2);
    ctx.stroke();
}

// Draw a rotated ellipse outline. DIVERGES from this library's CCW
// screen-angle convention: rotationDeg is the major-axis angle in the
// canvas' y-down frame, positive CLOCKWISE — the cv2.fitEllipse
// convention the ellipse detector reports, passed through unchanged.
function drawRotatedEllipse(ctx, centerX, centerY, radiusX, radiusY,
                            rotationDeg, strokeStyle, lineWidth) {
    ctx.save();
    ctx.translate(centerX, centerY);
    ctx.rotate(rotationDeg * Math.PI / 180);
    drawEllipse(ctx, 0, 0, radiusX, radiusY, strokeStyle, lineWidth);
    ctx.restore();
}

// -----------------------------------------------------------------------------
// DIMENSION ARROWS
// -----------------------------------------------------------------------------

// Half-angle of the stroked V arrowheads. Fixed glyph geometry (like the
// '<->' arrow style it mimics), not a themable constant.
var _ARROW_HEAD_HALF_ANGLE_RAD = 25 * Math.PI / 180;

// Draw a double-headed dimension arrow (<->) between two raw canvas points.
// Takes screen coordinates directly (no screen-angle convention involved).
// Heads shrink continuously to a third of the span when the span is short,
// so the glyph never pops during animation; sub-pixel spans draw nothing.
function drawDimensionArrow(ctx, x1, y1, x2, y2, headLength,
                            strokeStyle, lineWidth) {
    var dx = x2 - x1;
    var dy = y2 - y1;
    var span = Math.sqrt(dx * dx + dy * dy);
    if (span < 0.5)
        return;
    var head = Math.min(headLength, span / 3);
    var angle = Math.atan2(dy, dx);
    var a1 = angle + _ARROW_HEAD_HALF_ANGLE_RAD;
    var a2 = angle - _ARROW_HEAD_HALF_ANGLE_RAD;
    ctx.strokeStyle = strokeStyle;
    ctx.lineWidth = lineWidth;
    ctx.beginPath();
    ctx.moveTo(x1, y1);
    ctx.lineTo(x2, y2);
    ctx.moveTo(x1 + head * Math.cos(a1), y1 + head * Math.sin(a1));
    ctx.lineTo(x1, y1);
    ctx.lineTo(x1 + head * Math.cos(a2), y1 + head * Math.sin(a2));
    ctx.moveTo(x2 - head * Math.cos(a1), y2 - head * Math.sin(a1));
    ctx.lineTo(x2, y2);
    ctx.lineTo(x2 - head * Math.cos(a2), y2 - head * Math.sin(a2));
    ctx.stroke();
}

// -----------------------------------------------------------------------------
// LABEL POSITIONING HELPERS
// -----------------------------------------------------------------------------

// Calculate label position at the end of a radial line, optionally offset
// further outward by labelOffset. Returns {x, y}.
function getRadialLabelPosition(centerX, centerY, referenceCircleRadius,
                                lineLength, angleDeg, labelOffset) {
    var angleRad = angleDeg * Math.PI / 180;
    var offset = labelOffset || 0;
    var distance = referenceCircleRadius + lineLength + offset;
    return {
        x: centerX + distance * Math.cos(angleRad),
        y: centerY - distance * Math.sin(angleRad)
    };
}
