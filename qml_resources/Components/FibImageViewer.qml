import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../Config"
import "../Js/diagramFunctions.js" as DiagramFunctions

// FIB image viewer for the Position Alignment page.
//
// Dumb, property-driven component (no appController reach-ins): the page
// binds frameSeq/ellipseFit/viewerState from the controller.
// Layers: placeholder label (no frame yet) -> live Image (provider-fed,
// letterboxed with preserved aspect ratio) -> Canvas overlay (frame-center
// reference cross, detected ellipse + center marker, drawn in display
// pixels so strokes stay crisp at any window size) -> success chips
// (ellipse width/height, the FIB-page chip style). Per-step status and
// measured readouts live in the page's Status Log card, not here.
//
// The overlay maps image pixels to display pixels through the Image's
// painted geometry (paintedWidth/sourceSize), so it stays registered
// under both letterbox orientations and window resizes.

Item {

    id: root

    // --- Public API --------------------------------------------------
    // Bumped by the controller per published frame; 0 = nothing yet.
    property int frameSeq: 0
    // Fit map from the controller; {} or valid:false when no detection.
    // Keys: valid, centerXPx, centerYPx, majorRadiusPx, minorRadiusPx,
    // rotationDeg, millingAngleDeg, widthUm, heightUm, offsetXUm,
    // offsetYUm.
    property var ellipseFit: ({})
    // "idle" | "running" | "success" | "exception" — picks the overlay
    // color; the page maps the same state onto the Card border.
    property string viewerState: "idle"
    property string idleText: "No FIB image."
    // Advisories from the last finished run (width mismatch, mid-run
    // re-anchor). Shown as an amber chip on success; full texts live
    // in the Status Log card, the chip's tooltip repeats them.
    property var warnings: []

    readonly property bool hasFit: !!ellipseFit
                                   && ellipseFit.valid === true
    readonly property color overlayColor:
        viewerState === "success" ? AppConfig.activityCompleteColor
                                  : AppConfig.universalAccent

    onEllipseFitChanged: overlay.requestPaint()
    onViewerStateChanged: overlay.requestPaint()
    onFrameSeqChanged: overlay.requestPaint()

    ColumnLayout {

        anchors.fill: parent
        spacing: AppConfig.pageSectionSpacing

        Item {

            id: viewport
            Layout.fillWidth: true
            Layout.fillHeight: true

            Label {

                id: placeholderLabel
                anchors.centerIn: parent
                visible: root.frameSeq === 0
                text: root.idleText
                font.pixelSize: AppConfig.pageBodyFontSize

            }

            Image {

                id: liveFrame
                anchors.fill: parent
                visible: root.frameSeq > 0
                fillMode: Image.PreserveAspectFit
                cache: false
                smooth: true
                asynchronous: false
                // The seq query forces a re-request of the provider's
                // latest frame; the provider itself ignores the id.
                source: root.frameSeq > 0
                        ? "image://fibAlignment/frame?seq=" + root.frameSeq
                        : ""

            }

            Canvas {

                id: overlay
                anchors.fill: parent
                visible: root.frameSeq > 0
                renderTarget: Canvas.FramebufferObject

                onPaint: {
                    var ctx = getContext("2d")
                    ctx.reset()
                    var sourceW = liveFrame.sourceSize.width
                    var sourceH = liveFrame.sourceSize.height
                    var paintedW = liveFrame.paintedWidth
                    var paintedH = liveFrame.paintedHeight
                    if (root.frameSeq === 0 || sourceW <= 0
                            || sourceH <= 0 || paintedW <= 0
                            || paintedH <= 0)
                        return

                    // Image px -> display px through the painted geometry.
                    var scale = paintedW / sourceW
                    var offX = (liveFrame.width - paintedW) / 2
                    var offY = (liveFrame.height - paintedH) / 2

                    ctx.save()
                    ctx.beginPath()
                    ctx.rect(offX, offY, paintedW, paintedH)
                    ctx.clip()

                    // Frame-center reference cross (the centering
                    // target), snapped to the half-pixel grid: Canvas
                    // strokes center on the coordinate, so an integer
                    // coordinate blurs a 1 px line across two rows at
                    // half strength. floor (not round) keeps the snap a
                    // no-op when the true center is already on the
                    // half-pixel grid (odd viewport sizes).
                    var centerX = Math.floor(offX + paintedW / 2) + 0.5
                    var centerY = Math.floor(offY + paintedH / 2) + 0.5
                    DiagramFunctions.drawLine(
                        ctx, offX, centerY, offX + paintedW, centerY,
                        AppConfig.fibViewerCrosshairColor,
                        AppConfig.fibViewerCrosshairLineWidth)
                    DiagramFunctions.drawLine(
                        ctx, centerX, offY, centerX, offY + paintedH,
                        AppConfig.fibViewerCrosshairColor,
                        AppConfig.fibViewerCrosshairLineWidth)

                    if (root.hasFit) {
                        var fit = root.ellipseFit
                        var fitX = offX + fit.centerXPx * scale
                        var fitY = offY + fit.centerYPx * scale
                        DiagramFunctions.drawRotatedEllipse(
                            ctx, fitX, fitY,
                            fit.majorRadiusPx * scale,
                            fit.minorRadiusPx * scale,
                            fit.rotationDeg,
                            root.overlayColor,
                            AppConfig.fibViewerEllipseLineWidth)
                        // Detected-center "+" marker.
                        var arm = AppConfig.fibViewerCenterMarkerSize
                        DiagramFunctions.drawLine(
                            ctx, fitX - arm, fitY, fitX + arm, fitY,
                            root.overlayColor,
                            AppConfig.fibViewerCenterMarkerLineWidth)
                        DiagramFunctions.drawLine(
                            ctx, fitX, fitY - arm, fitX, fitY + arm,
                            root.overlayColor,
                            AppConfig.fibViewerCenterMarkerLineWidth)
                    }
                    ctx.restore()
                }

                onWidthChanged: requestPaint()
                onHeightChanged: requestPaint()
                onVisibleChanged: requestPaint()

                // The painted geometry settles after each source reload
                // and on resizes — repaint when it does.
                Connections {
                    target: liveFrame
                    function onPaintedWidthChanged() {
                        overlay.requestPaint()
                    }
                    function onPaintedHeightChanged() {
                        overlay.requestPaint()
                    }
                }

            }

            // Ellipse width/height chips (the FIB-page readout-chip
            // style), shown once a run ends in success.
            Row {

                visible: root.viewerState === "success" && root.hasFit
                anchors.horizontalCenter: parent.horizontalCenter
                anchors.bottom: parent.bottom
                anchors.bottomMargin: 8
                spacing: 8

                Rectangle {

                    width: widthReadout.implicitWidth + 12
                    height: widthReadout.implicitHeight + 4
                    radius: AppConfig.buttonRadius
                    color: AppConfig.universalBackground
                    border.color: AppConfig.containerBorderColor
                    border.width: 1

                    Label {

                        id: widthReadout
                        anchors.centerIn: parent
                        text: "Width " + (root.hasFit
                              ? root.ellipseFit.widthUm.toFixed(1)
                              : "0") + " µm"
                        font.pixelSize: AppConfig.fibViewerFooterFontSize

                    }

                }

                Rectangle {

                    width: heightReadout.implicitWidth + 12
                    height: heightReadout.implicitHeight + 4
                    radius: AppConfig.buttonRadius
                    color: AppConfig.universalBackground
                    border.color: AppConfig.containerBorderColor
                    border.width: 1

                    Label {

                        id: heightReadout
                        anchors.centerIn: parent
                        text: "Height " + (root.hasFit
                              ? root.ellipseFit.heightUm.toFixed(1)
                              : "0") + " µm"
                        font.pixelSize: AppConfig.fibViewerFooterFontSize

                    }

                }

                Rectangle {

                    visible: root.warnings.length > 0
                    width: advisoryReadout.implicitWidth + 12
                    height: advisoryReadout.implicitHeight + 4
                    radius: AppConfig.buttonRadius
                    color: AppConfig.universalBackground
                    border.color: AppConfig.activityExceptionColor
                    border.width: 1

                    Label {

                        id: advisoryReadout
                        anchors.centerIn: parent
                        text: "⚠ " + root.warnings.length
                              + (root.warnings.length > 1
                                 ? " advisories" : " advisory")
                        color: AppConfig.activityExceptionColor
                        font.pixelSize: AppConfig.fibViewerFooterFontSize

                    }

                    MouseArea {

                        id: advisoryHover
                        anchors.fill: parent
                        hoverEnabled: true

                    }

                    ToolTip.visible: advisoryHover.containsMouse
                    ToolTip.text: root.warnings.join("\n")

                }

            }

        }

    }

}
