import QtQuick
import QtQuick.Controls
import "../Config"

// Spin Mill Positions Table
//
// Read-only, header-pinned table of positions parsed from spin mill
// position images. Same scroll architecture as PositionResultsTable (see
// that file for the full rationale): the outer horizontal Flickable moves
// the header and rows together, the internal ListView scrolls vertically
// under the pinned header, the vertical bar is re-parented to the root so
// it stays at the visible right edge, and gutters keep the last column and
// last row clear of the overlay bars.
//
// Differs from PositionResultsTable by the leading File Name column
// (left-aligned, elides with a hover tooltip carrying the full capture
// name) and the fileName model role. Kept as a sibling component so the
// Position Alignment page's table — whose model will never carry
// fileName — stays untouched.
//
// Model role contract (SI units — the delegate converts for display):
//   fileName (string), stageR (rad), stageT (rad), stageX (m), stageY (m),
//   beamX (m), beamY (m), scanR (rad), wd (m)

Item {

    id: root

    // Rows model; null/empty shows the empty-state label.
    property var model: null

    // Column definitions — the header row renders from this list, and the
    // row delegates reference the same AppConfig width constants, so headers
    // and cells stay aligned by construction. Units live in the headers;
    // cells are bare numbers. Alignment lives in the spec because the File
    // Name column breaks PositionResultsTable's index-0-only centering rule.
    readonly property var columns: [
        { title: "#",            width: AppConfig.tableIndexColumnWidth,    align: Text.AlignHCenter },
        { title: "File Name",    width: AppConfig.tableFileNameColumnWidth, align: Text.AlignLeft },
        { title: "R (deg)",      width: AppConfig.tableAngleColumnWidth,    align: Text.AlignRight },
        { title: "T (deg)",      width: AppConfig.tableAngleColumnWidth,    align: Text.AlignRight },
        { title: "Stage X (mm)", width: AppConfig.tableStageColumnWidth,    align: Text.AlignRight },
        { title: "Stage Y (mm)", width: AppConfig.tableStageColumnWidth,    align: Text.AlignRight },
        { title: "Beam X (µm)",  width: AppConfig.tableBeamColumnWidth,     align: Text.AlignRight },
        { title: "Beam Y (µm)",  width: AppConfig.tableBeamColumnWidth,     align: Text.AlignRight },
        { title: "Scan R (deg)", width: AppConfig.tableScanRColumnWidth,    align: Text.AlignRight },
        { title: "WD (mm)",      width: AppConfig.tableWdColumnWidth,       align: Text.AlignRight }
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

    // Fixed row capacity: when set (> 0), implicitHeight is exactly this
    // many rows regardless of the model, so the host card never resizes as
    // data loads — extra rows scroll. When 0 (default), the table hugs its
    // loaded rows instead.
    property int preferredRows: 0

    // Height of exactly n data rows: header + separator + n rows + the
    // horizontal bar's lane. The one place this table's vertical metric
    // lives — hosts size the table in rows (preferredRows) rather than in
    // hand-tuned pixels, so a row-height or font change cannot silently
    // invalidate them.
    function heightForRows(n) {
        return AppConfig.tableRowHeight
               + AppConfig.tableHeaderSeparatorWidth
               + n * AppConfig.tableRowHeight
               + hScrollBar.height
    }

    // preferredRows if declared; otherwise hug the loaded rows, but at
    // least one row's worth so the empty-state label has space.
    implicitHeight: heightForRows(
        preferredRows > 0 ? preferredRows : Math.max(1, rowsView.count))

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

    Flickable {

        id: hFlick

        anchors.fill: parent
        // Gutter: reserve the vertical scrollbar's width past the last
        // column so a full right scroll leaves the WD values clear of the
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
                    required property string fileName
                    required property real stageR
                    required property real stageT
                    required property real stageX
                    required property real stageY
                    required property real beamX
                    required property real beamY
                    required property real scanR
                    required property real wd

                    width: root.tableContentWidth
                    height: AppConfig.tableRowHeight

                    Row {

                        spacing: AppConfig.tableColumnSpacing

                        Label {

                            width: AppConfig.tableIndexColumnWidth
                            height: AppConfig.tableRowHeight
                            text: rowDelegate.index + 1
                            font.pixelSize: AppConfig.tableCellFontSize
                            color: AppConfig.universalForeground
                            horizontalAlignment: Text.AlignHCenter
                            verticalAlignment: Text.AlignVCenter

                        }

                        // Capture names run ~60 chars — elide, with the full
                        // name reachable on hover (ToolTippedLabel shows its
                        // tooltip whenever truncated).
                        ToolTippedLabel {

                            width: AppConfig.tableFileNameColumnWidth
                            height: AppConfig.tableRowHeight
                            font.pixelSize: AppConfig.tableCellFontSize
                            color: AppConfig.universalForeground
                            rightPadding: AppConfig.tableCellRightPadding
                            verticalAlignment: Text.AlignVCenter
                            text: rowDelegate.fileName

                        }

                        ValueCell { width: AppConfig.tableAngleColumnWidth; text: root.stageDegText(rowDelegate.stageR) }
                        ValueCell { width: AppConfig.tableAngleColumnWidth; text: root.stageDegText(rowDelegate.stageT) }
                        ValueCell { width: AppConfig.tableStageColumnWidth; text: root.stageMmText(rowDelegate.stageX) }
                        ValueCell { width: AppConfig.tableStageColumnWidth; text: root.stageMmText(rowDelegate.stageY) }
                        ValueCell { width: AppConfig.tableBeamColumnWidth; text: root.beamUmText(rowDelegate.beamX) }
                        ValueCell { width: AppConfig.tableBeamColumnWidth; text: root.beamUmText(rowDelegate.beamY) }
                        ValueCell { width: AppConfig.tableScanRColumnWidth; text: root.scanDegText(rowDelegate.scanR) }
                        ValueCell { width: AppConfig.tableWdColumnWidth; text: root.wdMmText(rowDelegate.wd) }

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

    Label {

        anchors.centerIn: parent
        visible: rowsView.count === 0
        text: "No images loaded."
        font.pixelSize: AppConfig.tableCellFontSize
        color: AppConfig.universalForeground

    }

}
