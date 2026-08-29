import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../Config"
import "../Components"

// FIB Angle Calculator page.

Item {

    id: root

    // Minimum useful height — the content-area Flickable in main.qml holds
    // the page at this when the window is shorter, and scrolls.
    implicitHeight: pageColumn.implicitHeight + 2 * AppConfig.pageMargin

    ColumnLayout {

        id: pageColumn
        anchors.fill: parent
        anchors.margins: AppConfig.pageMargin
        spacing: AppConfig.pageSectionSpacing

        Label {

            text: "FIB Angle Calculator"
            font.pixelSize: AppConfig.pageHeadingFontSize
            font.bold: true

        }

        Label {

            text: "Calculate the milling angle from the measured AOI ellipse."
            font.pixelSize: AppConfig.pageBodyFontSize
            Layout.fillWidth: true
            wrapMode: Label.WordWrap

        }

        Item { Layout.preferredHeight: AppConfig.pageHeadingSpacerHeight }

        // Row 1 — the FIB calc card, centered on the page.
        Card {

            id: fibMillingAngleCalcCard
            Layout.alignment: Qt.AlignHCenter
            Layout.fillWidth: true
            Layout.maximumWidth: AppConfig.positionAlignmentControlsColumnMaxWidth

            // Uniform spin box column: every box in this card takes the
            // widest box's derived width (each still self-measures from
            // its own range via CustomSpinBox's TextMetrics sizing, so a
            // range change re-derives all three).
            readonly property real spinBoxColumnWidth: Math.max(
                targetMillingAngleSB.implicitWidth,
                aoiDiameterSB.implicitWidth,
                measuredEllipseHeightSB.implicitWidth)

            ColumnLayout {

                spacing: AppConfig.containerSpacing

                RowLayout {

                    Layout.fillWidth: true

                    ToolTippedLabel {

                        id: targetMillingAngleLabel
                        Layout.fillWidth: true
                        text: "Target Milling Angle (deg)"
                        toolTipText: Strings.targetMillingAngleLabelTooltip

                    }

                    CustomSpinBox {

                        id: targetMillingAngleSB
                        Layout.preferredWidth: fibMillingAngleCalcCard.spinBoxColumnWidth
                        decimals: 1
                        floatFrom: 0.0
                        floatTo: 90.0
                        floatValue: 4.0
                        floatStep: 0.1
                        showArrows: true

                    }

                }

                RowLayout {

                    Layout.fillWidth: true

                    ToolTippedLabel {

                        id: aoiDiameterLabel
                        Layout.fillWidth: true
                        text: "AOI Diameter (µm)"
                        toolTipText: Strings.aoiDiameterLabelTooltip

                    }

                    CustomSpinBox {

                        id: aoiDiameterSB
                        Layout.preferredWidth: fibMillingAngleCalcCard.spinBoxColumnWidth
                        decimals: 0
                        from: 100
                        to: 3000
                        value: 800
                        stepSize: 10
                        showArrows: true

                    }

                }

                RowLayout {

                    Layout.fillWidth: true

                    ToolTippedLabel {

                        id: measuredEllipseHeightLabel
                        Layout.fillWidth: true
                        text: "Measured Ellipse Height (µm)"
                        toolTipText: Strings.measuredEllipseHeightLabelTooltip

                    }

                    CustomSpinBox {

                        id: measuredEllipseHeightSB
                        Layout.preferredWidth: fibMillingAngleCalcCard.spinBoxColumnWidth
                        decimals: 1
                        floatFrom: 0.1
                        // Dynamic clamp: keep the measured height below the
                        // diameter so the asin ratio stays < 1. Shrinking
                        // the diameter re-clamps this box.
                        floatTo: Math.max(measuredEllipseHeightSB.floatFrom, aoiDiameterSB.value - 0.1)
                        floatStep: 0.1
                        floatValue: 55.8

                    }

                }

                Item { Layout.preferredHeight: 6 }

                RowLayout {

                    Layout.fillWidth: true

                    ToolTippedLabel {

                        id: calculatedMillingAngleLabel
                        Layout.fillWidth: true
                        text: "Calculated Milling Angle (deg)"

                    }

                    Label {

                        id: calculatedMillingAngleResultLabel
                        text: appController.fib.calculatedMillingAngle.toFixed(2)

                    }

                }

                RowLayout {

                    Layout.fillWidth: true

                    ToolTippedLabel {

                        id: tiltByAngleLabel
                        Layout.fillWidth: true
                        text: "Tilt By Angle (deg)"
                        toolTipText: Strings.tiltByAngleLabelTooltip

                    }

                    Label {

                        id: tiltByAngleResultLabel
                        text: appController.fib.tiltStageBy.toFixed(1)

                    }

                }

            }

        }

        // Row 2 — both view figures side by side, so the beam geometry and
        // the FIB's-eye ellipse are visible simultaneously. Equal halves:
        // the unit preferred width makes the layout ignore the cards'
        // content-driven implicit widths when splitting the row.
        RowLayout {

            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.preferredHeight: AppConfig.imageViewerMinimumHeight
            spacing: AppConfig.pageSectionSpacing

            Card {

                id: fib2DViewCard
                title: "2D View"
                titleBold: false
                backgroundColor: AppConfig.universalBackground
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.preferredWidth: 1

                Fib2DView {

                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    millingAngleDeg: appController.fib.calculatedMillingAngle

                }

            }

            Card {

                id: fibFIBViewCard
                title: "FIB View"
                titleBold: false
                backgroundColor: AppConfig.universalBackground
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.preferredWidth: 1

                FibFIBView {

                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    aoiDiameterUm: appController.fib.aoiDiameter
                    ellipseHeightUm: appController.fib.measuredEllipseHeight

                }

            }

        }

    }

    // Push the FIB page's live spin-box values into the controller (one-way
    // QML -> Python). Binding elements fire on any change, including the
    // height box's programmatic clamp when the diameter shrinks. Outputs flow
    // the other way (labels bind to appController.fib.*), so there is no loop.
    Binding {
        target: appController.fib
        property: "targetMillingAngle"
        value: targetMillingAngleSB.realValue
    }
    Binding {
        target: appController.fib
        property: "aoiDiameter"
        value: aoiDiameterSB.value
    }
    Binding {
        target: appController.fib
        property: "measuredEllipseHeight"
        value: measuredEllipseHeightSB.realValue
    }

    // Broadcast this card's uniform spin-box width (the widest of its three
    // boxes) so the SEM Angle Calc and Position Alignment pages can match their
    // target-milling-angle box to it. One-way publish; the subscribers floor it
    // with their own implicitWidth, so there is no cross-page layout loop.
    Binding {
        target: AppConfig
        property: "calcSpinBoxWidth"
        value: fibMillingAngleCalcCard.spinBoxColumnWidth
    }

}
