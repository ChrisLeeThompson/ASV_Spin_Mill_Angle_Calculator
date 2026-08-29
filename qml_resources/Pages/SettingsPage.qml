import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../Config"
import "../Components"

// Settings page.
//
// Controls bind to appController.settings.* (the PySide SettingsController).
// Two-way binding is achieved by:
//   1. Reading the property as the initial value (.checked).
//   2. Writing back on the user-interaction signal (onToggled).
// The SettingsController's setters are no-ops when the incoming value
// matches the stored value, so there is no feedback loop when a control
// echoes a value back to its source.
//
// Persistence is handled inside SettingsController — every successful set
// writes to QSettings immediately, no explicit save action required.

Item {

    id: root

    // Minimum useful height — the content-area Flickable in main.qml holds
    // the page at this when the window is shorter, and scrolls.
    implicitHeight: pageColumn.implicitHeight + 2 * AppConfig.pageMargin

    // Tap on empty page space drops focus from any control (matters
    // once text fields exist).
    TapHandler {
        onTapped: root.forceActiveFocus()
    }

    ColumnLayout {

        id: pageColumn
        anchors.fill: parent
        anchors.margins: AppConfig.pageMargin
        spacing: AppConfig.pageSectionSpacing

        Label {

            text: "Settings"
            font.pixelSize: AppConfig.pageHeadingFontSize
            font.bold: true

        }

        Label {

            text: "Settings are saved automatically and persist between sessions."
            font.pixelSize: AppConfig.pageBodyFontSize
            Layout.fillWidth: true
            wrapMode: Label.WordWrap

        }

        Item { Layout.preferredHeight: AppConfig.pageHeadingSpacerHeight }

        // Settings form — a bare two-column grid, left-justified at the
        // page margin (no card, no border).
        // Rows are ToolTippedLabel + control pairs addressed by explicit
        // Layout.row/column, so appending a setting is one label and one
        // control. Checkbox rows have fixed heights, so the grid never
        // resizes on data (stable-card-sizing rule).
        GridLayout {

            id: settingsGrid
            Layout.fillWidth: true
            Layout.maximumWidth: AppConfig.settingsPageMaxWidth
            Layout.alignment: Qt.AlignLeft | Qt.AlignTop
            columns: 2
            rowSpacing: AppConfig.settingsFormRowSpacing
            columnSpacing: AppConfig.settingsFormColumnSpacing

            // ---- Row 0: Save Debug Images ----
            //
            // Deliberately not disabled while a run is active: the
            // alignment snapshots the setting at Start, so a mid-run
            // toggle is harmless — it applies to the next run (the
            // tooltip says so).

            ToolTippedLabel {

                id: saveDebugImagesLabel
                Layout.row: 0
                Layout.column: 0
                text: "Save Debug Images"
                toolTipText: Strings.saveDebugImagesLabelTooltip

            }

            CheckBox {

                id: saveDebugImagesCheckBox
                Layout.row: 0
                Layout.column: 1
                Layout.alignment: Qt.AlignRight
                checked: appController.settings.saveDebugImages
                onToggled: appController.settings.saveDebugImages = checked

            }

            // ---- Rows 1-4: alignment tuning ----
            //
            // Each maps onto one AlignmentConfig field, read once at each
            // Start (AppController's tuning_provider), so these are not
            // disabled mid-run for the same reason the checkbox is not —
            // an edit applies to the next run.
            //
            // The ranges below are the dataclass's own invariants, which
            // __post_init__ re-checks: the spin box is the first guard,
            // SettingsController clamps as the second, and a combination
            // that still fails validation makes the run fall back to
            // defaults rather than refusing to start.

            ToolTippedLabel {

                id: tiltToleranceLabel
                Layout.row: 1
                Layout.column: 0
                text: "Milling Angle Tolerance (deg)"
                toolTipText: Strings.tiltToleranceLabelTooltip

            }

            CustomSpinBox {

                id: tiltToleranceSB
                Layout.row: 1
                Layout.column: 1
                Layout.alignment: Qt.AlignRight
                Layout.preferredWidth: AppConfig.calcSpinBoxWidth
                decimals: 2
                // Floored at the config's tilt_tolerance_floor_deg: a
                // tolerance under the measurement noise oscillates
                // forever, so this can only be raised from its default.
                floatFrom: 0.10
                floatTo: 0.50
                floatStep: 0.05
                floatValue: appController.settings.tiltToleranceDeg
                showArrows: true
                onValueModified:
                    appController.settings.tiltToleranceDeg = realValue

            }

            ToolTippedLabel {

                id: levelToleranceLabel
                Layout.row: 2
                Layout.column: 0
                text: "Leveling Tolerance (deg)"
                toolTipText: Strings.levelToleranceLabelTooltip

            }

            CustomSpinBox {

                id: levelToleranceSB
                Layout.row: 2
                Layout.column: 1
                Layout.alignment: Qt.AlignRight
                Layout.preferredWidth: AppConfig.calcSpinBoxWidth
                decimals: 2
                // At or above level_noise_floor_deg, the depth at which
                // leveling latches for the rest of the run.
                floatFrom: 0.20
                floatTo: 1.00
                floatStep: 0.05
                floatValue: appController.settings.levelToleranceDeg
                showArrows: true
                onValueModified:
                    appController.settings.levelToleranceDeg = realValue

            }

            ToolTippedLabel {

                id: verifyFramesLabel
                Layout.row: 3
                Layout.column: 0
                text: "Verification Frames"
                toolTipText: Strings.verifyFramesLabelTooltip

            }

            CustomSpinBox {

                id: verifyFramesSB
                Layout.row: 3
                Layout.column: 1
                Layout.alignment: Qt.AlignRight
                Layout.preferredWidth: AppConfig.calcSpinBoxWidth
                decimals: 0
                from: 1
                to: 7
                // Step 2 from an odd start keeps every reachable value
                // odd: with an even count the "median" frame is the
                // upper-middle one, so a single noisy fit decides the
                // verdict, and the config rejects it outright.
                stepSize: 2
                value: appController.settings.verifyFrames
                showArrows: true
                onValueModified:
                    appController.settings.verifyFrames = value

            }

            ToolTippedLabel {

                id: sweepCountLabel
                Layout.row: 4
                Layout.column: 0
                text: "Search Sweeps"
                toolTipText: Strings.sweepCountLabelTooltip

            }

            CustomSpinBox {

                id: sweepCountSB
                Layout.row: 4
                Layout.column: 1
                Layout.alignment: Qt.AlignRight
                Layout.preferredWidth: AppConfig.calcSpinBoxWidth
                decimals: 0
                from: 1
                to: 4
                stepSize: 1
                value: appController.settings.sweepCount
                showArrows: true
                onValueModified:
                    appController.settings.sweepCount = value

            }

        }

        // The page's one fill item: pins the card to the top on tall
        // windows instead of stretching it (page scroll contract).
        Item { Layout.fillHeight: true }

    }

}
