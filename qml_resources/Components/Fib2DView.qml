import QtQuick
import QtQuick.Controls
import "../Config"
import "../Js"

// FIB 2D view — simplified beam-geometry figure for the FIB Angle Calculator.
//
// White SEM and FIB beam lines converge at the figure center (FIB on the
// right of the SEM). A blue diameter line represents the sample surface /
// AOI ellipse seen edge-on: its tilt from horizontal is the stage tilt
// (milling angle − 38°), so at milling angle 0 it lies parallel to the FIB
// beam. A pink arc pivoted at the center spans from the FIB line to the
// blue line's right arm — its sweep IS the milling angle — with a degree
// readout at the arc's midpoint.
//
// Screen-angle convention (matches Js/diagramFunctions.js): 0° = horizontal
// right, positive = counter-clockwise. The figure is fluid — all geometry
// derives from the item's current size.

Item {

    id: root

    // The milling angle (deg) this figure displays. The page binds this to
    // appController.fib.calculatedMillingAngle.
    property real millingAngleDeg: 0.0

    // --- Instrument geometry (display-only mirror; the shared source of
    // truth is asv_spin_mill_angle_calc/spin_mill_geometry.py) ---
    // FIB sits 52° from the SEM column, i.e. 38° above horizontal, on the
    // right side of the SEM.
    readonly property real semScreenAngleDeg: 90.0
    readonly property real fibScreenAngleDeg: 90.0 - 52.0

    // --- Tilt mapping ---
    // Surface tilt from horizontal = milling angle − 38 (β = tilt + 38),
    // clamped to the stage's physical range. The blue line's right-arm
    // screen angle is −tilt: positive tilt dips the right arm below the
    // FIB line, opening the milling-angle arc between them.
    readonly property real clampedTiltDeg:
        Math.max(-38.0, Math.min(60.0, millingAngleDeg - 38.0))

    // Animated copy of the tilt: the Behavior sweeps the figure smoothly
    // whenever the bound milling angle changes (Hydra-style).
    property real displayedTiltDeg: clampedTiltDeg

    Behavior on displayedTiltDeg {
        NumberAnimation {
            duration: AppConfig.fib2DViewAnimationMs
            easing.type: Easing.InOutQuad
        }
    }

    // Milling angle as currently drawn (tracks the animation).
    readonly property real displayedMillingAngleDeg: displayedTiltDeg + 38.0

    // --- Fluid geometry ---
    // The pivot sits below the vertical midpoint: the beams only extend
    // upward, so a lowered center fills the frame instead of leaving an
    // empty bottom half.
    readonly property real centerX: width / 2
    readonly property real centerY: AppConfig.fib2DViewCenterYFraction * height
    readonly property real beamLength:
        AppConfig.fib2DViewRadiusFraction * Math.min(width, height)
    readonly property real arcRadius:
        AppConfig.fib2DViewArcRadiusFraction * beamLength
    readonly property real ellipseHalfLength:
        AppConfig.fib2DViewEllipseLineFraction * beamLength

    // Deliberately no implicit size: the figure fills whatever the view
    // card gives it, and the page's scroll floor stays governed by
    // AppConfig.imageViewerMinimumHeight.

    // Static layer: the white SEM and FIB beam lines. Radius 0 → the lines
    // run to the exact convergence point (no hub gap).
    Canvas {

        id: staticCanvas
        anchors.fill: parent
        onWidthChanged: requestPaint()
        onHeightChanged: requestPaint()

        onPaint: {
            var ctx = getContext("2d")
            ctx.clearRect(0, 0, width, height)
            DiagramFunctions.drawRadialLine(
                ctx, root.centerX, root.centerY, 0, root.beamLength,
                root.semScreenAngleDeg,
                AppConfig.universalForeground, AppConfig.fib2DViewLineWidth)
            DiagramFunctions.drawRadialLine(
                ctx, root.centerX, root.centerY, 0, root.beamLength,
                root.fibScreenAngleDeg,
                AppConfig.universalForeground, AppConfig.fib2DViewLineWidth)
        }

    }

    // Dynamic layer: the blue ellipse line and the pink milling-angle arc.
    // Split from the static layer so the beams don't repaint every frame
    // while the tilt animates.
    Canvas {

        id: dynamicCanvas
        anchors.fill: parent
        onWidthChanged: requestPaint()
        onHeightChanged: requestPaint()

        readonly property real currentTilt: root.displayedTiltDeg
        onCurrentTiltChanged: requestPaint()

        onPaint: {
            var ctx = getContext("2d")
            ctx.clearRect(0, 0, width, height)

            // Blue ellipse line: full diameter through the center, right
            // arm at screen angle −tilt.
            DiagramFunctions.drawDiameterLine(
                ctx, root.centerX, root.centerY, root.ellipseHalfLength,
                -currentTilt,
                AppConfig.universalAccent, AppConfig.fib2DViewIndicatorWidth)

            // Pink milling-angle arc: from the blue line's right arm CCW up
            // to the FIB line. Collapses to nothing at milling angle 0
            // (line parallel to the beam).
            var beta = root.displayedMillingAngleDeg
            if (beta < 0.05)
                return
            DiagramFunctions.drawArc(
                ctx, root.centerX, root.centerY, root.arcRadius,
                root.fibScreenAngleDeg - beta, root.fibScreenAngleDeg,
                AppConfig.catbugMittenColor, AppConfig.fib2DViewArcWidth)
        }

    }

    // White beam labels at the outer ends of the SEM and FIB lines,
    // nudged outward by half the label size along the beam direction.
    Repeater {

        model: [
            { name: "SEM", angle: root.semScreenAngleDeg },
            { name: "FIB", angle: root.fibScreenAngleDeg }
        ]

        delegate: Label {

            required property var modelData

            readonly property var _pos: DiagramFunctions.getRadialLabelPosition(
                root.centerX, root.centerY, root.beamLength, 0,
                modelData.angle, AppConfig.fib2DViewLabelOffset)

            x: _pos.x - width / 2
               + (width / 2 + 6) * Math.cos(modelData.angle * Math.PI / 180)
            y: _pos.y - height / 2
               - (height / 2 + 2) * Math.sin(modelData.angle * Math.PI / 180)
            text: modelData.name
            font.pixelSize: AppConfig.pageBodyFontSize
            color: AppConfig.universalForeground

        }

    }

    // Milling-angle readout in a chip on the arc's bisector, just outside
    // the arc. The opaque background keeps the value legible when the beam
    // and ellipse lines pass beneath it at small angles; the clearance term
    // pushes the chip's inner edge (not its center) past the arc radius.
    Rectangle {

        id: millingAngleReadoutChip

        readonly property real _midAngleDeg:
            root.fibScreenAngleDeg - root.displayedMillingAngleDeg / 2
        readonly property real _midAngleRad: _midAngleDeg * Math.PI / 180
        readonly property real _clearance:
            (width / 2) * Math.abs(Math.cos(_midAngleRad))
            + (height / 2) * Math.abs(Math.sin(_midAngleRad))
        readonly property var _pos: DiagramFunctions.getRadialLabelPosition(
            root.centerX, root.centerY, root.arcRadius, 0,
            _midAngleDeg, AppConfig.fib2DViewLabelOffset + _clearance)

        x: _pos.x - width / 2
        y: _pos.y - height / 2
        width: millingAngleReadout.implicitWidth + 12
        height: millingAngleReadout.implicitHeight + 4
        radius: AppConfig.buttonRadius
        color: AppConfig.universalBackground
        border.color: AppConfig.catbugMittenColor
        border.width: 1

        Label {

            id: millingAngleReadout
            anchors.centerIn: parent
            text: root.displayedMillingAngleDeg.toFixed(1) + "°"
            font.pixelSize: AppConfig.pageBodyFontSize
            color: AppConfig.catbugMittenColor

        }

    }

    // Legend, bottom-center: directly below the pivot is the one spot the
    // ellipse line can never sweep through (it would need a ±90° tilt).
    Row {

        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottom: parent.bottom
        spacing: 20

        Row {

            spacing: 8

            Rectangle {

                anchors.verticalCenter: parent.verticalCenter
                width: AppConfig.fib2DViewLegendSwatchWidth
                height: AppConfig.fib2DViewLegendSwatchHeight
                radius: height / 2
                color: AppConfig.universalAccent

            }

            Label {

                text: "AOI Circle"
                font.pixelSize: AppConfig.fib2DViewLegendFontSize
                color: AppConfig.universalForeground

            }

        }

        Row {

            spacing: 8

            Rectangle {

                anchors.verticalCenter: parent.verticalCenter
                width: AppConfig.fib2DViewLegendSwatchWidth
                height: AppConfig.fib2DViewLegendSwatchHeight
                radius: height / 2
                color: AppConfig.catbugMittenColor

            }

            Label {

                text: "Milling Angle"
                font.pixelSize: AppConfig.fib2DViewLegendFontSize
                color: AppConfig.universalForeground

            }

        }

    }

}
