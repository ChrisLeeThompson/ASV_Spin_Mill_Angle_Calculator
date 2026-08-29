import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import QtQuick.Layouts
import "../Config"
import "../Components"

// SEM Angle Calculator page.

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

            text: "SEM Angle Calculator"
            font.pixelSize: AppConfig.pageHeadingFontSize
            font.bold: true

        }

        Label {

            text: "Calculate SEM stage positions from saved spin mill position images."
            font.pixelSize: AppConfig.pageBodyFontSize
            Layout.fillWidth: true
            wrapMode: Label.WordWrap

        }

        Item { Layout.preferredHeight: AppConfig.pageHeadingSpacerHeight }

        // Controls card — centered at the top (mirrors the FIB calc page:
        // fillWidth + maximumWidth + AlignHCenter caps then centers the card).
        Card {

            id: semAngleCalcCard
            Layout.alignment: Qt.AlignHCenter
            Layout.fillWidth: true
            Layout.maximumWidth: AppConfig.positionAlignmentControlsColumnMaxWidth

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
                        // Match the FIB page's spin-box width (broadcast via
                        // AppConfig); floored by our own content so it never
                        // collapses before the FIB page publishes.
                        Layout.preferredWidth: Math.max(
                            implicitWidth, AppConfig.calcSpinBoxWidth)
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
                    spacing: AppConfig.buttonRowSpacing

                    RoundButton {

                        id: loadSpinMillPositionImagesButton
                        Layout.fillWidth: true
                        radius: AppConfig.buttonRadius
                        padding: AppConfig.buttonPadding
                        leftPadding: AppConfig.buttonLeftRightPadding
                        rightPadding: AppConfig.buttonLeftRightPadding
                        text: "Load Spin Mill Position Images"
                        onClicked: loadImagesDialog.open()

                        ToolTip.text: Strings.loadSpinMillPositionImagesButtonTooltip
                        ToolTip.delay: AppConfig.toolTipDelayMs
                        ToolTip.timeout: AppConfig.toolTipTimeoutMs
                        ToolTip.visible: hovered


                    }

                    RoundButton {

                        id: clearSpinMillPositionsButton
                        radius: AppConfig.buttonRadius
                        padding: AppConfig.buttonPadding
                        leftPadding: AppConfig.buttonLeftRightPadding
                        rightPadding: AppConfig.buttonLeftRightPadding
                        text: "Clear Positions"
                        onClicked: appController.sem.clearPositions()

                    }

                }

            }

        }

        // Tables — stacked below the controls card, centered and widened.
        // semTablesMaxWidth caps them wide enough to fully show the Spin Mill
        // table's columns; AlignHCenter centers them once the window exceeds
        // that cap.
        //
        // Heights are fixed capacities, declared in rows (preferredRows —
        // each table converts to pixels itself): the cards are the same size
        // empty and loaded, so loading images never reflows the stack, and
        // rows past the capacity scroll. Deliberately not fillHeight: the
        // Results card below is the only item that fills, so every spare
        // pixel on a tall window goes to the one view that can actually use
        // it — the audit block.
        Card {

            id: spinMillPositionsCard
            title: "Spin Mill Positions"
            titleBold: false
            backgroundColor: AppConfig.universalBackground
            Layout.alignment: Qt.AlignHCenter
            Layout.fillWidth: true
            Layout.maximumWidth: AppConfig.semTablesMaxWidth

            SpinMillPositionsTable {

                id: spinMillPositionsTable
                Layout.fillWidth: true
                // One full image batch visible without scrolling.
                preferredRows: 5
                model: appController.sem.positionsModel

            }

        }

        Card {

            id: calculatedSemPositionsCard
            title: "Calculated SEM Positions"
            titleBold: false
            backgroundColor: AppConfig.universalBackground
            Layout.alignment: Qt.AlignHCenter
            Layout.fillWidth: true
            Layout.maximumWidth: AppConfig.semTablesMaxWidth

            SemPositionsTable {

                id: calculatedSemPositionsTable
                showSource: true
                // Same wording as the Position Alignment page's table.
                // This card has two row sources, and only the Calculated
                // rows need three positions — a measured
                // (already-perpendicular) position is emitted from a
                // single one, so the empty text must describe both.
                emptyText: "3 or more positions required to calculate. "
                           + "A position already perpendicular in rotation "
                           + "is listed as Measured."
                // Per-category explanations for the Source tooltips.
                // Keys must match the SOURCE_* constants in
                // sem_geometry_calculator.py.
                sourceToolTips: ({
                    "Calculated (primary)": Strings.semSourceCalculatedTooltip,
                    "Calculated (alternate)": Strings.semSourceAlternateTooltip,
                    "Measured": Strings.semSourceMeasuredTooltip
                })
                Layout.fillWidth: true
                // Holds three positions (slightly shorter than the spin mill
                // card above); a fourth row scrolls.
                preferredRows: 3
                model: appController.sem.semPositionsModel

            }

        }

        // Results — the per-load audit that also goes to the console log:
        // the load summary, any per-file parse failures, and the full
        // calculation block (fits, candidates, warnings). Replaced on every
        // load, so it always describes the positions in the tables above.
        //
        // The only fillHeight item on the page: the tables above are fixed
        // capacities, so all remaining height lands here — the one view
        // whose content is unbounded and always benefits from more of it.
        Card {

            id: resultsCard
            title: "Results"
            titleBold: false
            backgroundColor: AppConfig.universalBackground
            Layout.alignment: Qt.AlignHCenter
            Layout.fillWidth: true
            Layout.maximumWidth: AppConfig.semTablesMaxWidth
            Layout.fillHeight: true

            StatusLogView {

                id: resultsLogView
                Layout.fillWidth: true
                Layout.fillHeight: true
                // Opens at the block's tail (StatusLogView follows the end
                // of its text): the calculation warnings close the audit
                // block, so they are in view the moment data is calculated.
                // Preferred = floor. Unlike the tables, this view has no
                // natural height (implicit 0 by design), so without it the
                // card collapses to its title once the page scrolls.
                Layout.preferredHeight: AppConfig.semResultsMinimumHeight
                text: appController.sem.resultsText.length > 0
                      ? appController.sem.resultsText
                      : Strings.semResultsPlaceholderText

            }

        }

    }

    FileDialog {

        id: loadImagesDialog
        title: "Select Spin Mill Position Images"
        fileMode: FileDialog.OpenFiles
        nameFilters: ["PNG images (*.png *.PNG)"]
        currentFolder: appController.sem.lastDirectoryUrl
        onAccepted: appController.sem.loadImages(selectedFiles)

    }

    // Push the live spin-box value into the controller (one-way QML ->
    // Python, same idiom as FIBAngleCalcPage). Outputs flow the other way
    // (statusText / the two models), so there is no loop.
    Binding {
        target: appController.sem
        property: "targetMillingAngle"
        value: targetMillingAngleSB.realValue
    }

}
