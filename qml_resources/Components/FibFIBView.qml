import QtQuick
import QtQuick.Controls
import "../Config"
import "../Js"

// FIB View — the AOI circle as seen from the FIB column.
//
// The milled AOI is a true circle on the sample surface; viewed along the
// FIB axis it foreshortens into an ellipse whose height/width ratio is
// exactly h/D = sin(milling angle), so the figure sweeps from a flat line
// at 0° to a full circle at 90°. White double-headed dimension arrows call
// out the two measured quantities: width (AOI diameter) below the ellipse,
// height (measured ellipse height) through the center — mirroring how the
// user measures them on the FIB image.
//
// The figure is fluid — all geometry derives from the item's current size.

Item {

    id: root

    // The measured inputs (µm) this figure displays. The page binds these
    // to appController.fib.aoiDiameter / .measuredEllipseHeight. Defaults
    // mirror the controller's so a standalone instance draws sensibly.
    property real aoiDiameterUm: 800.0
    property real ellipseHeightUm: 55.8

    // Animated copies: the Behaviors sweep the shape and the chip readouts
    // smoothly whenever the bound inputs change. A diameter shrink that
    // trips the page's height clamp animates both concurrently.
    property real displayedDiameterUm: aoiDiameterUm
    property real displayedEllipseHeightUm: ellipseHeightUm

    Behavior on displayedDiameterUm {
        NumberAnimation {
            duration: AppConfig.fibFIBViewAnimationMs
            easing.type: Easing.InOutQuad
        }
    }

    Behavior on displayedEllipseHeightUm {
        NumberAnimation {
            duration: AppConfig.fibFIBViewAnimationMs
            easing.type: Easing.InOutQuad
        }
    }

    // On-screen aspect as currently drawn. Clamped because the two
    // animations run independently: mid-sweep the ratio can transiently
    // exceed 1 (height clamp chasing a shrinking diameter) — the figure
    // saturates at a circle instead of inverting.
    readonly property real displayedRatio:
        Math.max(0.0, Math.min(1.0,
            displayedEllipseHeightUm / Math.max(displayedDiameterUm, 0.001)))

    // --- Fluid geometry ---
    // The center sits above the vertical midpoint: the width arrow, its
    // chip, and the legend all hang below the ellipse, so the below-center
    // budget is larger. The major axis is width-limited while the ellipse
    // is flat and cedes width as the aspect grows — dividing the vertical
    // budget by the ratio keeps the minor axis inside it at every aspect,
    // so a circle at 90° exactly fills the height fraction. The epsilon
    // guards the division; below it the width term is the binding one.
    readonly property real centerX: width / 2
    readonly property real centerY: AppConfig.fibFIBViewCenterYFraction * height
    readonly property real majorRadius: 0.5 * Math.min(
        AppConfig.fibFIBViewWidthFraction * width,
        AppConfig.fibFIBViewHeightFraction * height
            / Math.max(displayedRatio, 0.01))
    readonly property real minorRadius: majorRadius * displayedRatio
    readonly property real widthArrowY:
        centerY + minorRadius + AppConfig.fibFIBViewDimensionGap

    // Deliberately no implicit size: the figure fills whatever the view
    // card gives it, and the page's scroll floor stays governed by
    // AppConfig.imageViewerMinimumHeight.

    // Single canvas: unlike Fib2DView there is no static layer — the
    // ellipse and both dimension arrows all move with the animated ratio.
    Canvas {

        id: figureCanvas
        anchors.fill: parent
        onWidthChanged: requestPaint()
        onHeightChanged: requestPaint()

        // Born hidden (non-current StackLayout tab): repaint on reveal so
        // the first look at the tab is never a stale/blank texture.
        onVisibleChanged: if (visible) requestPaint()

        // Watch both radii: in the height-limited regime the minor axis
        // is constant (the ratio cancels out of budget/ratio * ratio)
        // while the major axis animates, so minorRadius alone misses
        // repaints and the figure renders stale.
        readonly property real currentMinor: root.minorRadius
        onCurrentMinorChanged: requestPaint()
        readonly property real currentMajor: root.majorRadius
        onCurrentMajorChanged: requestPaint()

        onPaint: {
            var ctx = getContext("2d")
            ctx.clearRect(0, 0, width, height)

            // Blue AOI ellipse: aspect = h/D exactly (circle at 90°).
            DiagramFunctions.drawEllipse(
                ctx, root.centerX, root.centerY,
                root.majorRadius, root.minorRadius,
                AppConfig.universalAccent,
                AppConfig.fibFIBViewEllipseLineWidth)

            // Height dimension: through the center, spanning the minor
            // axis. Vanishes gracefully at edge-on aspect.
            DiagramFunctions.drawDimensionArrow(
                ctx, root.centerX, root.centerY - root.minorRadius,
                root.centerX, root.centerY + root.minorRadius,
                AppConfig.fibFIBViewArrowHeadLength,
                AppConfig.universalForeground,
                AppConfig.fibFIBViewDimensionLineWidth)

            // Width dimension: below the ellipse, spanning the major axis.
            DiagramFunctions.drawDimensionArrow(
                ctx, root.centerX - root.majorRadius, root.widthArrowY,
                root.centerX + root.majorRadius, root.widthArrowY,
                AppConfig.fibFIBViewArrowHeadLength,
                AppConfig.universalForeground,
                AppConfig.fibFIBViewDimensionLineWidth)
        }

    }

    // Height readout chip, centered just above the ellipse top — outside
    // the figure, riding the minor axis as it sweeps (the mirror of the
    // width chip below).
    Rectangle {

        id: heightReadoutChip
        x: root.centerX - width / 2
        y: root.centerY - root.minorRadius - AppConfig.fibFIBViewLabelOffset - height
        width: heightReadout.implicitWidth + 12
        height: heightReadout.implicitHeight + 4
        radius: AppConfig.buttonRadius
        color: AppConfig.universalBackground
        // border.color: AppConfig.universalForeground
        // border.width: 1

        Label {

            id: heightReadout
            anchors.centerIn: parent
            text: root.displayedEllipseHeightUm.toFixed(1) + " µm"
            font.pixelSize: AppConfig.pageBodyFontSize
            color: AppConfig.universalForeground

        }

    }

    // Width readout chip, centered below the width arrow.
    Rectangle {

        id: widthReadoutChip
        x: root.centerX - width / 2
        y: root.widthArrowY + AppConfig.fibFIBViewLabelOffset
        width: widthReadout.implicitWidth + 12
        height: widthReadout.implicitHeight + 4
        radius: AppConfig.buttonRadius
        color: AppConfig.universalBackground
        // border.color: AppConfig.universalForeground
        // border.width: 1

        Label {

            id: widthReadout
            anchors.centerIn: parent
            text: root.displayedDiameterUm.toFixed(0) + " µm"
            font.pixelSize: AppConfig.pageBodyFontSize
            color: AppConfig.universalForeground

        }

    }

    // Legend, bottom-center — single entry; the center-Y fraction reserves
    // this band so the ellipse and dimension chain never reach it.
    Row {

        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottom: parent.bottom
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

}
