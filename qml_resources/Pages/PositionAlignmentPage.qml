import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../Config"
import "../Components"

// Position Alignment page.

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

            text: "Automated Spin Mill Position Alignment"
            font.pixelSize: AppConfig.pageHeadingFontSize
            font.bold: true

        }

        Label {

            text: "Center the AOI in the FIB view, at the target milling angle, for each position defined during the ASV Define Spin Mill Position activity."
            font.pixelSize: AppConfig.pageBodyFontSize
            Layout.fillWidth: true
            wrapMode: Label.WordWrap

        }

        Item { Layout.preferredHeight: AppConfig.pageHeadingSpacerHeight }

        // Two-column body. Explicit Layout.row/column on every child —
        // auto-flow would misplace items after the image viewer's rowSpan.
        // The grid takes the window's surplus height, and row 3 is the
        // ONLY row that can grow (both its cards fillHeight; rows 0-2 are
        // capped by the fixed-height column-0 cards, so the image viewer
        // stays flush with the Spin Mill Positions card; do not add
        // Layout.verticalStretchFactor to the viewer — it would mark
        // rows 0-2 stretchy and spread the left cards apart). The
        // Calculated SEM Positions and Status Log cards therefore
        // stretch together, keeping their bottom edges aligned at any
        // window height. Column 0 is pinned at exactly
        // positionAlignmentControlsColumnMaxWidth by each card's minimum/
        // preferred/maximumWidth trio — any one alone lets the grid's width
        // distribution move the column. Any future column-0 child must carry
        // the same trio, and column-1 content must not demand implicit
        // width or height (StatusLogView keeps its implicit size 0 for
        // exactly this reason).
        GridLayout {

            columns: 2
            rowSpacing: AppConfig.pageSectionSpacing
            columnSpacing: AppConfig.pageSectionSpacing
            Layout.fillWidth: true
            Layout.fillHeight: true

            Card {

                id: connectToMicroscopeCard
                Layout.row: 0
                Layout.column: 0
                Layout.fillWidth: true
                Layout.minimumWidth: AppConfig.positionAlignmentControlsColumnMaxWidth
                Layout.preferredWidth: AppConfig.positionAlignmentControlsColumnMaxWidth
                Layout.maximumWidth: AppConfig.positionAlignmentControlsColumnMaxWidth
                Layout.alignment: Qt.AlignTop

                ColumnLayout {

                    spacing: AppConfig.containerSpacing

                    RowLayout {

                        Layout.fillWidth: true

                        ToolTippedLabel {

                            id: connectToMicroscopeLabel
                            Layout.fillWidth: true
                            text: "Connect To Microscope"

                        }

                        Switch {

                            id: connectToMicroscopeSwitch
                            Layout.alignment: Qt.AlignVCenter
                            // Locked during the (up to ~30 s) threaded
                            // connect attempt — it can't be cancelled —
                            // and during an alignment run (a mid-run
                            // disconnect would strand the stage).
                            enabled: !appController.microscope.isConnecting
                                     && !appController.positionAlignment.isRunning
                            // onToggled fires on user interaction only —
                            // never on the snap-back Binding's programmatic
                            // writes, so there is no echo loop.
                            onToggled: checked
                                       ? appController.microscope.connectMicroscope()
                                       : appController.microscope.disconnectMicroscope()

                        }

                    }

                    RowLayout {

                        Layout.fillWidth: true

                        Label {

                            id: connectToMicroscopeStatusLabel
                            Layout.fillWidth: true
                            elide: Text.ElideRight
                            text: appController.microscope.statusText

                        }

                    }

                }


            }

            Card {

                id: positionAlignmentParametersCard
                Layout.row: 1
                Layout.column: 0
                Layout.fillWidth: true
                Layout.minimumWidth: AppConfig.positionAlignmentControlsColumnMaxWidth
                Layout.preferredWidth: AppConfig.positionAlignmentControlsColumnMaxWidth
                Layout.maximumWidth: AppConfig.positionAlignmentControlsColumnMaxWidth
                Layout.alignment: Qt.AlignTop

                ColumnLayout {

                    spacing: AppConfig.containerSpacing

                    RowLayout {

                        Layout.fillWidth: true

                        ToolTippedLabel {

                            id: positionAlignmentTargetMillingAngleLabel
                            Layout.fillWidth: true
                            Layout.alignment: Qt.AlignLeft
                            text: "Target Milling Angle"
                            toolTipText: Strings.targetMillingAngleLabelTooltip

                        }

                        CustomSpinBox {

                            id: positionAlignmentTargetMillingAngleSB
                            // Match the FIB page's spin-box width (broadcast
                            // via AppConfig); floored by our own content so
                            // it never collapses before the FIB publishes.
                            Layout.preferredWidth: Math.max(
                                                       implicitWidth, AppConfig.calcSpinBoxWidth)
                            // Inputs are snapshotted at Start; locked
                            // mid-run so the UI can't imply otherwise.
                            enabled: !appController.positionAlignment.isRunning
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
                            Layout.preferredWidth: AppConfig.calcSpinBoxWidth
                            enabled: !appController.positionAlignment.isRunning
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

                            id: useBeamShiftLabel
                            Layout.fillWidth: true
                            Layout.alignment: Qt.AlignLeft
                            text: "Use Beam Shift"
                            toolTipText: Strings.useBeamShiftLabelTooltip

                        }

                        CheckBox {

                            id: useBeamShiftCheckBox
                            Layout.alignment: Qt.AlignVCenter
                            enabled: !appController.positionAlignment.isRunning

                        }

                    }

                }



            }

            Card {

                id: positionAlignmentPositionResultsCard
                Layout.row: 2
                Layout.column: 0
                Layout.fillWidth: true
                Layout.minimumWidth: AppConfig.positionAlignmentControlsColumnMaxWidth
                Layout.preferredWidth: AppConfig.positionAlignmentControlsColumnMaxWidth
                Layout.maximumWidth: AppConfig.positionAlignmentControlsColumnMaxWidth
                Layout.alignment: Qt.AlignTop
                backgroundColor: AppConfig.universalBackground
                title: "Spin Mill Positions"
                titleBold: false

                // Per-position readouts pulled from the microscope via
                // AutoScript when the user clicks Confirm (see the column
                // contract in PositionResultsTable.qml).
                PositionResultsTable {

                    id: positionResultsTable
                    Layout.fillWidth: true
                    Layout.preferredHeight: AppConfig.tableHeight
                    model: appController.positionAlignment.positionsModel

                }

            }

            Card {

                id: calculatedSemPositionsCard
                Layout.row: 3
                Layout.column: 0
                Layout.fillWidth: true
                Layout.minimumWidth: AppConfig.positionAlignmentControlsColumnMaxWidth
                Layout.preferredWidth: AppConfig.positionAlignmentControlsColumnMaxWidth
                Layout.maximumWidth: AppConfig.positionAlignmentControlsColumnMaxWidth
                // Row 3 is the grid's stretch row: this card grows with
                // the window alongside the Status Log card, keeping the
                // two bottom edges aligned.
                Layout.fillHeight: true
                Layout.alignment: Qt.AlignTop
                backgroundColor: AppConfig.universalBackground
                title: "Calculated SEM Positions"
                titleBold: false

                // SEM positions derived from the confirmed spin mill
                // positions (the SEM page's sinusoid calculation) — at
                // most two, once three or more positions are recorded.
                SemPositionsTable {

                    id: semPositionsTable
                    emptyText: "3 or more positions required."
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    model: appController.positionAlignment.semPositionsModel

                }

            }

            Card {

                id: imageViewerContainer
                Layout.row: 0
                Layout.column: 1
                // Spans the three rows above the Calculated SEM Positions
                // row, so the viewer's bottom edge stays flush with the
                // Spin Mill Positions card at any window size.
                Layout.rowSpan: 3
                Layout.fillWidth: true
                Layout.fillHeight: true
                // Preferred = floor: feeds the page's implicitHeight so the
                // viewer never collapses in scroll mode; inert while the
                // spanned left-card rows sum taller than this.
                Layout.preferredHeight: AppConfig.imageViewerMinimumHeight
                backgroundColor: AppConfig.universalBackground
                title: "FIB View"
                titleBold: false
                // Border signals the run state: blue accent while the
                // routine runs, green on a successful match, amber on an
                // exception, default otherwise.
                borderColor: {
                    var state = appController.positionAlignment.viewerState
                    if (state === "running")
                        return AppConfig.universalAccent
                    if (state === "success")
                        return AppConfig.activityCompleteColor
                    if (state === "exception")
                        return AppConfig.activityExceptionColor
                    return AppConfig.containerBorderColor
                }

                FibImageViewer {

                    id: fibImageViewer
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    frameSeq: appController.positionAlignment.frameSeq
                    ellipseFit: appController.positionAlignment.ellipseFit
                    viewerState: appController.positionAlignment.viewerState

                }

            }

            // Status Log: opens with the instructions, then accumulates
            // the routine's per-step status, results, and errors (the
            // controller's session scrollback, auto-followed at the
            // bottom). To remove: delete this whole block and change the
            // image viewer's Layout.rowSpan from 3 to 4 — the viewer then
            // expands down flush with the Calculated SEM Positions card
            // bottom instead.
            Card {

                id: statusLogCard
                Layout.row: 3
                Layout.column: 1
                Layout.fillWidth: true
                // fillHeight in the shared row: matches the Calculated SEM
                // Positions card height.
                Layout.fillHeight: true
                backgroundColor: AppConfig.universalBackground
                title: "Status Log"
                titleBold: false

                StatusLogView {

                    id: statusLogView
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    text: Strings.positionAlignmentInstructionsText
                          + "\n\n"
                          + appController.positionAlignment.statusLog

                }

            }

            RowLayout {

                Layout.row: 4
                Layout.column: 1
                Layout.fillWidth: true
                spacing: AppConfig.buttonRowSpacing

                RoundButton {

                    id: clearPositionsButton
                    Layout.alignment: Qt.AlignLeft
                    radius: AppConfig.buttonRadius
                    padding: AppConfig.buttonPadding
                    leftPadding: AppConfig.buttonLeftRightPadding
                    rightPadding: AppConfig.buttonLeftRightPadding
                    text: "Clear Positions"
                    // Clears both the spin mill and SEM positions tables.
                    enabled: appController.positionAlignment.positionsModel.count > 0
                             && !appController.positionAlignment.isRunning
                    onClicked: appController.positionAlignment.clearPositions()

                }

                Item { Layout.fillWidth: true }

                RoundButton {

                    id: startButton
                    radius: AppConfig.buttonRadius
                    padding: AppConfig.buttonPadding
                    leftPadding: AppConfig.buttonLeftRightPadding
                    rightPadding: AppConfig.buttonLeftRightPadding
                    text: "Start"
                    enabled: appController.microscope.isConnected
                             && !appController.positionAlignment.isRunning
                    // First Start per session confirms taking control of
                    // the stage; the dialog's checkbox suppresses it for
                    // the rest of the session.
                    onClicked: {
                        if (appController.positionAlignment.suppressStartDialog)
                            appController.positionAlignment.startAlignment()
                        else
                            startConfirmDialog.open()
                    }

                }

                RoundButton {

                    id: stopButton
                    radius: AppConfig.buttonRadius
                    padding: AppConfig.buttonPadding
                    leftPadding: AppConfig.buttonLeftRightPadding
                    rightPadding: AppConfig.buttonLeftRightPadding
                    text: "Stop"
                    // canStop (not isRunning): already-stopping runs
                    // can't be stopped harder.
                    enabled: appController.positionAlignment.canStop
                    onClicked: appController.positionAlignment.stopAlignment()

                }

                RoundButton {

                    id: confirmButton
                    Layout.alignment: Qt.AlignRight
                    radius: AppConfig.buttonRadius
                    padding: AppConfig.buttonPadding
                    leftPadding: AppConfig.buttonLeftRightPadding
                    rightPadding: AppConfig.buttonLeftRightPadding
                    text: "Confirm"
                    // Records the reviewed position into the Spin Mill
                    // Positions table (SEM candidates recalculate once
                    // three or more rows exist).
                    enabled: appController.positionAlignment.canConfirm
                             && appController.microscope.isConnected
                    onClicked: appController.positionAlignment.confirmPosition()

                }

            }

        }

    }

    // Reflect the controller's connection state onto the switch (one-way
    // Python -> QML, the SEM page's Binding idiom in the other direction).
    // A Binding element survives the user's direct writes to `checked` (a
    // plain `checked:` binding would be destroyed by the first click) and
    // re-asserts whenever its value CHANGES. `isConnecting` is OR-ed in so
    // the value transitions true -> false when a connect attempt fails —
    // with plain `isConnected` it would go false -> false and never
    // re-assert, leaving the switch stuck on after an error.
    Binding {
        target: connectToMicroscopeSwitch
        property: "checked"
        value: appController.microscope.isConnected
               || appController.microscope.isConnecting
    }

    // Push the alignment inputs into the controller (one-way QML ->
    // Python, the SEM page's Binding idiom); the controller snapshots
    // them into immutable params at Start.
    Binding {
        target: appController.positionAlignment
        property: "targetMillingAngle"
        value: positionAlignmentTargetMillingAngleSB.realValue
    }
    Binding {
        target: appController.positionAlignment
        property: "aoiDiameter"
        value: aoiDiameterSB.value
    }
    Binding {
        target: appController.positionAlignment
        property: "useBeamShift"
        value: useBeamShiftCheckBox.checked
    }

    // First-Start confirmation: the routine takes control of the stage.
    ConfirmDialog {
        id: startConfirmDialog
        title: Strings.startAlignmentDialogTitle
        message: Strings.startAlignmentDialogMessage
        showSuppressCheckBox: true
        onAccepted: {
            if (suppressChecked)
                appController.positionAlignment.suppressStartDialog = true
            appController.positionAlignment.startAlignment()
        }
    }

    // Modal notice when the routine would need a stage tilt at or past
    // the -37.9° limit (message composed by the backend).
    ConfirmDialog {
        id: tiltLimitDialog
        title: Strings.tiltLimitDialogTitle
        showRejectButton: false
    }

    Connections {
        target: appController.positionAlignment
        function onTiltLimitExceeded(message) {
            tiltLimitDialog.message = message
            tiltLimitDialog.open()
        }
    }

}
