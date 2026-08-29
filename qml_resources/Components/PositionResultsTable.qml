import QtQuick
import QtQuick.Controls
import "../Config"

// Position Results Table
//
// Header-pinned table of per-position microscope readouts, with a
// per-row action menu in the leading column.
// Vertical scroll: internal ListView (the header sits above it, so it
// stays pinned). Horizontal scroll: outer Flickable moves the header and
// rows together, so columns can never drift out from under their headers.
//
// Model role contract (SI units — the delegate converts for display):
//   filled (bool) — whether the slot holds a recorded position; pending
//   rows serve null for the eight SI roles and render dashes.
//   stageR (rad), stageT (rad), stageX (m), stageY (m), beamX (m),
//   beamY (m), scanR (rad), wd (m)
// Plus one optional role, read through `model.<role>` rather than as a
// named required property so a model without it still renders:
//   millingAngleDeg (real or null; null renders "NA")
//
// There is deliberately no position-number role: a position's number is
// exactly its 1-based row index, so the delegate reads `index + 1`. The
// rows are fixed slots mirroring ASV's Define Spin Mill Position
// activity, so that number is a stable slot identity — slots never
// shift, and no renumbering exists anymore.
//
// Dumb component: it reaches into no controller. Row actions are emitted
// as signals carrying the position number, and the page wires them.

Item {

    id: root

    // Rows model — one row per fixed slot.
    property var model: null

    // Row-action gating, bound by the page.
    //   actionsEnabled — whether any row action may touch the microscope
    //                    right now.
    //   canReconfirm   — a reviewed capture is armed and may overwrite
    //                    a row (see PositionAlignmentController).
    property bool actionsEnabled: true
    property bool canReconfirm: false

    // Slots 1..activeCount are active; rows past the count dim and their
    // actions deactivate. The page binds the Number of Spin Mill
    // Positions here.
    property int activeCount: 0

    // Row actions, carrying the row's 1-based position number — exactly
    // the row's index + 1; the controller resolves it back to a slot at
    // the moment it acts. reconfirmRequested serves both menu faces:
    // "Re-confirm" on a filled slot and "Confirm here" on a pending one.
    signal goToRequested(int positionNumber)
    signal reconfirmRequested(int positionNumber)

    // Column definitions — the header row renders from this list, and the
    // row delegates reference the same AppConfig width constants, so headers
    // and cells stay aligned by construction. Units live in the headers;
    // cells are bare numbers.
    //
    // `align` is per column rather than derived from the index: with a
    // non-numeric leading column an "index 0 is the centered one" rule
    // no longer holds (the SpinMillPositionsTable idiom).
    readonly property var columns: [
        { title: "",             width: AppConfig.tableActionColumnWidth,      align: Text.AlignHCenter },
        { title: "#",            width: AppConfig.tableIndexColumnWidth,       align: Text.AlignHCenter },
        { title: "R (deg)",      width: AppConfig.tableAngleColumnWidth,       align: Text.AlignRight },
        { title: "T (deg)",      width: AppConfig.tableAngleColumnWidth,       align: Text.AlignRight },
        { title: "Stage X (mm)", width: AppConfig.tableStageColumnWidth,       align: Text.AlignRight },
        { title: "Stage Y (mm)", width: AppConfig.tableStageColumnWidth,       align: Text.AlignRight },
        { title: "Beam X (µm)",  width: AppConfig.tableBeamColumnWidth,        align: Text.AlignRight },
        { title: "Beam Y (µm)",  width: AppConfig.tableBeamColumnWidth,        align: Text.AlignRight },
        { title: "Scan R (deg)", width: AppConfig.tableScanRColumnWidth,       align: Text.AlignRight },
        { title: "WD (mm)",      width: AppConfig.tableWdColumnWidth,          align: Text.AlignRight },
        { title: "Milling Angle (deg)", width: AppConfig.tableMillingAngleColumnWidth, align: Text.AlignRight }
    ]

    // Full unclipped table width: all column widths plus the spacing gaps
    // between them.
    readonly property int tableContentWidth: {
        var w = 0
        for (var i = 0; i < columns.length; ++i) {
            w += columns[i].width
        }
        return w + (columns.length - 1) * AppConfig.tableColumnSpacing
    }

    // --- Display conversions (SI -> display units) ---
    // Display-only rounding: the model keeps full-precision SI values.
    function stageDegText(rad) { return (rad * 180 / Math.PI).toFixed(1) }  // R, T
    function scanDegText(rad) { return (rad * 180 / Math.PI).toFixed(2) }   // Scan R
    function stageMmText(m) { return (m * 1e3).toFixed(4) }
    function beamUmText(m) { return (m * 1e6).toFixed(2) }
    function wdMmText(m) { return (m * 1e3).toFixed(4) }
    // Two decimals even though the stage only commands 0.1 steps: the
    // measurement is finer than the actuation, and the second digit is
    // what shows a site sitting consistently high or low. Unmeasured
    // rows read "NA" — never the tilt-derived model angle, which is not
    // a measurement.
    function millingAngleText(deg) {
        return (deg === undefined || deg === null) ? "NA" : deg.toFixed(2)
    }

    implicitHeight: AppConfig.tableHeight

    // Right-aligned numeric cell shared by the row delegates. Width is set
    // per instance from the same AppConfig constant as the matching header
    // column (see the `columns` list above).
    component ValueCell: Label {

        height: AppConfig.tableRowHeight
        font.pixelSize: AppConfig.tableCellFontSize
        color: AppConfig.universalForeground
        rightPadding: AppConfig.tableCellRightPadding
        horizontalAlignment: Text.AlignRight
        verticalAlignment: Text.AlignVCenter

    }

    // A single menu shared by the whole table, not one per delegate: a
    // menu owned by a delegate dies with it when the row scrolls out of
    // the pool.
    // `menuPosition` carries which row opened it, and `menuRowFilled` /
    // `menuRowActive` snapshot that row's state at popup time. All three
    // are only meaningful while the menu is open — they are reset on
    // close so stale values can never describe a row the menu is no
    // longer over.
    property int menuPosition: -1
    property bool menuRowFilled: false
    property bool menuRowActive: false

    Menu {

        id: rowActionMenu

        // Deferred rather than assigned directly: choosing a MenuItem both
        // fires its onTriggered and closes the menu, and the order of
        // those two is not ours to rely on. Qt.callLater puts the reset
        // after the current event, so it can never blank the number out
        // from under the handler that is using it.
        onClosed: Qt.callLater(function () {
            root.menuPosition = -1
            root.menuRowFilled = false
            root.menuRowActive = false
        })

        MenuItem {

            text: "Go To"
            // Only a recorded, active slot has somewhere to go to.
            enabled: root.actionsEnabled && root.menuRowFilled
                     && root.menuRowActive
            onTriggered: root.goToRequested(root.menuPosition)
            ToolTip.text: !root.menuRowActive
                          ? Strings.rowInactiveTooltip
                          : (root.menuRowFilled
                             ? Strings.rowGoToTooltip
                             : Strings.rowGoToPendingTooltip)
            ToolTip.delay: AppConfig.toolTipDelayMs
            ToolTip.timeout: AppConfig.toolTipTimeoutMs
            ToolTip.visible: hovered

        }

        MenuItem {

            // "Re-confirm" replaces a filled slot's values; "Confirm
            // here" records into a pending slot instead of the lowest
            // pending one. Both are the same signal — the controller
            // writes the armed capture into the named slot either way.
            text: root.menuRowFilled ? "Re-confirm" : "Confirm here"
            // Gated on the armed review, which is what keeps a slot from
            // being written by a capture nobody has looked at.
            enabled: root.actionsEnabled && root.canReconfirm
                     && root.menuRowActive
            onTriggered: root.reconfirmRequested(root.menuPosition)
            ToolTip.text: !root.menuRowActive
                          ? Strings.rowInactiveTooltip
                          : (root.canReconfirm
                             ? (root.menuRowFilled
                                ? Strings.rowReconfirmTooltip
                                : Strings.rowConfirmHereTooltip)
                             : Strings.rowReconfirmDisabledTooltip)
            ToolTip.delay: AppConfig.toolTipDelayMs
            ToolTip.timeout: AppConfig.toolTipTimeoutMs
            ToolTip.visible: hovered

        }

    }

    Flickable {

        id: hFlick

        anchors.fill: parent
        // Gutter: reserve the vertical scrollbar's width past the last
        // column so a full right scroll leaves the last values clear of the
        // overlay bar. Always reserved — transient bars appear/disappear
        // while scrolling, and a conditional gutter would make the content
        // width jump.
        contentWidth: root.tableContentWidth + vScrollBar.width
        contentHeight: height
        flickableDirection: Flickable.HorizontalFlick
        boundsBehavior: Flickable.StopAtBounds
        clip: true

        ScrollBar.horizontal: ScrollBar {

            id: hScrollBar
            policy: ScrollBar.AsNeeded

        }

        Column {

            width: root.tableContentWidth
            height: hFlick.height

            Row {

                id: headerRow
                spacing: AppConfig.tableColumnSpacing

                Repeater {

                    model: root.columns

                    delegate: Label {

                        required property var modelData

                        width: modelData.width
                        height: AppConfig.tableRowHeight
                        text: modelData.title
                        font.pixelSize: AppConfig.tableCellFontSize
                        color: AppConfig.universalForeground
                        rightPadding: modelData.align === Text.AlignRight
                                      ? AppConfig.tableCellRightPadding : 0
                        horizontalAlignment: modelData.align
                        verticalAlignment: Text.AlignVCenter

                    }

                }

            }

            Rectangle {

                id: headerSeparator
                width: root.tableContentWidth
                height: AppConfig.tableHeaderSeparatorWidth
                color: AppConfig.containerBorderColor

            }

            ListView {

                id: rowsView

                width: root.tableContentWidth
                // Bottom gutter: also subtract the horizontal scrollbar's
                // height so a scroll to the bottom of the list leaves the
                // last row clear of the overlay bar (the vertical analog of
                // the vScrollBar gutter in hFlick.contentWidth).
                height: hFlick.height - headerRow.height - headerSeparator.height
                        - hScrollBar.height
                clip: true
                model: root.model
                boundsBehavior: Flickable.StopAtBounds

                // An attached bar would sit at the ListView's right edge —
                // inside the horizontally-scrolled content, off-screen until
                // the user scrolls right. Parent it to root so it stays
                // pinned to the visible right edge, below the header.
                ScrollBar.vertical: ScrollBar {

                    id: vScrollBar
                    parent: root
                    policy: ScrollBar.AsNeeded
                    anchors.top: parent.top
                    anchors.topMargin: AppConfig.tableRowHeight
                                       + AppConfig.tableHeaderSeparatorWidth
                    anchors.right: parent.right
                    anchors.bottom: parent.bottom
                    // Stop above the horizontal bar's lane so the two
                    // overlay bars don't cross in the corner.
                    anchors.bottomMargin: hScrollBar.height

                }

                delegate: Item {

                    id: rowDelegate

                    // Named, prefixed roles — no collisions with Item's own
                    // x/y/rotation properties.
                    required property int index
                    required property bool filled
                    // `var`, not `real`: pending rows serve null for the
                    // SI roles, and a `real` property would warn "Unable
                    // to assign [undefined] to double" on every one.
                    required property var stageR
                    required property var stageT
                    required property var stageX
                    required property var stageY
                    required property var beamX
                    required property var beamY
                    required property var scanR
                    required property var wd
                    // The optional role goes through `model` rather than a
                    // named required property: a named one aborts delegate
                    // creation when the role is absent, and millingAngleDeg
                    // is legitimately null on an unmeasured row.
                    required property var model

                    // The position number is the row's ordinal, full stop —
                    // never a model role. Slots are fixed and never shift,
                    // so `index + 1` is a stable slot identity mirroring
                    // ASV's own numbering — not a renumbering scheme.
                    readonly property int positionNumber: index + 1

                    // Active slots are the first activeCount rows; a row
                    // past the count dims and its actions deactivate.
                    readonly property bool active: index < root.activeCount

                    width: root.tableContentWidth
                    height: AppConfig.tableRowHeight

                    Row {

                        spacing: AppConfig.tableColumnSpacing
                        // Pending and deactivated slots read as dimmed:
                        // their values are placeholders, or excluded from
                        // the SEM calculation.
                        opacity: rowDelegate.filled && rowDelegate.active
                                 ? 1.0 : AppConfig.tableInactiveRowOpacity

                        // Row-action chevron. A button plus a Menu, not a
                        // ComboBox: Go To / Re-confirm are one-shot
                        // actions, and a ComboBox would imply one of them is
                        // the row's current "value".
                        Item {

                            width: AppConfig.tableActionColumnWidth
                            height: AppConfig.tableRowHeight

                            Image {

                                id: chevron
                                anchors.centerIn: parent
                                width: AppConfig.tableActionIconSize
                                height: AppConfig.tableActionIconSize
                                // Square-padded asset rotated to point down;
                                // its fill is already universalForeground, so
                                // no recolor pass is needed.
                                rotation: 90
                                source: AppConfig.iconChevronRight
                                sourceSize.width: width * 2
                                sourceSize.height: height * 2
                                fillMode: Image.PreserveAspectFit
                                opacity: chevronHover.containsMouse ? 1.0 : 0.7

                            }

                            MouseArea {

                                id: chevronHover
                                anchors.fill: parent
                                hoverEnabled: true
                                onClicked: {
                                    root.menuPosition = rowDelegate.positionNumber
                                    root.menuRowFilled = rowDelegate.filled
                                    root.menuRowActive = rowDelegate.active
                                    rowActionMenu.popup(
                                        parent, 0, parent.height)
                                }

                            }

                        }

                        Label {

                            width: AppConfig.tableIndexColumnWidth
                            height: AppConfig.tableRowHeight
                            // Fixed slots 1..N, lined up with ASV's own
                            // spin mill position numbering — a slot keeps
                            // its number for good.
                            text: rowDelegate.positionNumber
                            font.pixelSize: AppConfig.tableCellFontSize
                            color: AppConfig.universalForeground
                            horizontalAlignment: Text.AlignHCenter
                            verticalAlignment: Text.AlignVCenter

                        }

                        // Pending slots render an em dash in every cell —
                        // the conversion helpers never receive null, and
                        // "NA" stays reserved for filled-but-unmeasured.
                        ValueCell { width: AppConfig.tableAngleColumnWidth; text: rowDelegate.filled ? root.stageDegText(rowDelegate.stageR) : "—" }
                        ValueCell { width: AppConfig.tableAngleColumnWidth; text: rowDelegate.filled ? root.stageDegText(rowDelegate.stageT) : "—" }
                        ValueCell { width: AppConfig.tableStageColumnWidth; text: rowDelegate.filled ? root.stageMmText(rowDelegate.stageX) : "—" }
                        ValueCell { width: AppConfig.tableStageColumnWidth; text: rowDelegate.filled ? root.stageMmText(rowDelegate.stageY) : "—" }
                        ValueCell { width: AppConfig.tableBeamColumnWidth; text: rowDelegate.filled ? root.beamUmText(rowDelegate.beamX) : "—" }
                        ValueCell { width: AppConfig.tableBeamColumnWidth; text: rowDelegate.filled ? root.beamUmText(rowDelegate.beamY) : "—" }
                        ValueCell { width: AppConfig.tableScanRColumnWidth; text: rowDelegate.filled ? root.scanDegText(rowDelegate.scanR) : "—" }
                        ValueCell { width: AppConfig.tableWdColumnWidth; text: rowDelegate.filled ? root.wdMmText(rowDelegate.wd) : "—" }
                        ValueCell {
                            width: AppConfig.tableMillingAngleColumnWidth
                            text: rowDelegate.filled
                                  ? root.millingAngleText(
                                        rowDelegate.model.millingAngleDeg)
                                  : "—"
                        }

                    }

                    // Row separator — continuous across the column gaps,
                    // matching the reference table.
                    Rectangle {

                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.bottom: parent.bottom
                        height: AppConfig.tableRowSeparatorWidth
                        color: AppConfig.containerBorderColor

                    }

                }

            }

        }

    }

}
