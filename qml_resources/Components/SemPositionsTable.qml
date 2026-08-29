import QtQuick
import QtQuick.Controls
import "../Config"

// SEM Positions Table
//
// Read-only table of calculated SEM positions with the same pinned-header
// scroll architecture as PositionResultsTable (see that file for the full
// rationale): the outer horizontal Flickable moves the header and rows
// together, the internal ListView scrolls vertically under the pinned
// header, the vertical bar is re-parented to the root so it stays at the
// visible right edge, and gutters keep the last column and last row clear
// of the overlay bars.
//
// The original look is preserved: the # column anchors left and a flexible
// filler pushes the R/T columns toward the right edge whenever the
// component is wider than its fixed columns. When it is narrower, the
// filler collapses to zero and horizontal scrolling engages.
//
// Optional Source column (showSource, default false) between # and the
// filler — the SEM Angle Calc page turns it on to label candidate rows;
// Position Alignment leaves it off. Its model roles may be absent there,
// so the delegate reads them through the model object rather than named
// required properties (which would abort delegate creation when a role
// is missing).
//
// Model role contract (SI units — the delegate converts for display), a
// subset of the PositionResultsTable contract:
//   stageR (rad), stageT (rad)
//   source, sourceDetail (strings) — only read when showSource is true

Item {

    id: root

    // Rows model; null/empty shows the empty-state label.
    property var model: null

    // Show the Source column (candidate provenance) before the filler.
    property bool showSource: false

    // Source column width; pages with short provenance details (the
    // alignment page's "Position 2") narrow it so the R/T columns stay
    // on-screen inside a 400 px card without horizontal scroll.
    property int sourceColumnWidth: AppConfig.tableSourceColumnWidth

    // Empty-state label; pages override it with context-specific
    // guidance (e.g. the Position Alignment page's minimum-rows hint).
    property string emptyText: "No calculated positions."

    // Per-category explanation texts for the Source tooltips, keyed by
    // the source value (e.g. "Calculated (primary)"). A row's tooltip
    // combines its category text with the row's sourceDetail (e.g. the
    // measured candidate's image file name); empty entries contribute
    // nothing.
    property var sourceToolTips: ({})

    // Fixed row width: index (+ optional source) + two angle columns + the
    // spacing gaps that remain once the filler joins the row. Whatever
    // width the component grants beyond this is absorbed by the filler.
    readonly property int fixedRowWidth:
        AppConfig.tableIndexColumnWidth
        + (showSource ? sourceColumnWidth
                        + AppConfig.tableColumnSpacing : 0)
        + 2 * AppConfig.tableAngleColumnWidth
        + 3 * AppConfig.tableColumnSpacing

    // Filler between the left columns and R/T. Zero once the fixed columns
    // plus the scrollbar gutter no longer fit — horizontal scroll takes
    // over from there. (Tracks root.width, not the content column, which
    // would loop.)
    readonly property int fillerWidth:
        Math.max(0, width - vScrollBar.width - fixedRowWidth)

    // Full unclipped row width (never narrower than the fixed columns).
    readonly property int rowContentWidth: fixedRowWidth + fillerWidth

    // --- Display conversion (SI -> display units) ---
    // Display-only rounding: the model keeps full-precision SI values.
    function stageDegText(rad) { return (rad * 180 / Math.PI).toFixed(1) }

    // Fixed row capacity: when set (> 0), implicitHeight is exactly this
    // many rows regardless of the model, so the host card never resizes as
    // data loads — extra rows scroll. When 0 (default), the table hugs its
    // loaded rows instead (the Position Alignment page's behavior).
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

    implicitWidth: fixedRowWidth
    // preferredRows if declared; otherwise hug the loaded rows, but at
    // least one row's worth so the empty-state label has space.
    implicitHeight: heightForRows(
        preferredRows > 0 ? preferredRows : Math.max(1, rowsView.count))

    // Right-aligned angle cell; bold header variant below.
    component ValueCell: Label {

        width: AppConfig.tableAngleColumnWidth
        height: AppConfig.tableRowHeight
        font.pixelSize: AppConfig.tableCellFontSize
        color: AppConfig.universalForeground
        rightPadding: AppConfig.tableCellRightPadding
        horizontalAlignment: Text.AlignRight
        verticalAlignment: Text.AlignVCenter

    }

    component HeaderCell: ValueCell { }

    component IndexCell: Label {

        width: AppConfig.tableIndexColumnWidth
        height: AppConfig.tableRowHeight
        font.pixelSize: AppConfig.tableCellFontSize
        color: AppConfig.universalForeground
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter

    }

    // Left-aligned provenance cell; elides with a full-text tooltip (a
    // source may be a long image file name). Invisible unless showSource —
    // Row positioners skip invisible items and their spacing, so the
    // alignment page's geometry is unchanged.
    component SourceCell: ToolTippedLabel {

        width: root.sourceColumnWidth
        height: AppConfig.tableRowHeight
        font.pixelSize: AppConfig.tableCellFontSize
        color: AppConfig.universalForeground
        rightPadding: AppConfig.tableCellRightPadding
        verticalAlignment: Text.AlignVCenter
        visible: root.showSource

    }

    component RowFiller: Item {

        width: root.fillerWidth
        height: 1

    }

    Flickable {

        id: hFlick

        anchors.fill: parent
        // Gutter: reserve the vertical scrollbar's width past the last
        // column (always — a conditional gutter would make the content
        // width jump while scrolling).
        contentWidth: root.rowContentWidth + vScrollBar.width
        contentHeight: height
        flickableDirection: Flickable.HorizontalFlick
        boundsBehavior: Flickable.StopAtBounds
        clip: true

        ScrollBar.horizontal: ScrollBar {

            id: hScrollBar
            policy: ScrollBar.AsNeeded

        }

        Column {

            width: root.rowContentWidth
            height: hFlick.height

            Row {

                id: headerRow
                spacing: AppConfig.tableColumnSpacing

                IndexCell { text: "#" }

                SourceCell { text: "Source" }

                RowFiller { }

                HeaderCell { text: "R (deg)" }

                HeaderCell { text: "T (deg)" }

            }

            Rectangle {

                id: headerSeparator
                width: root.rowContentWidth
                height: AppConfig.tableHeaderSeparatorWidth
                color: AppConfig.containerBorderColor

            }

            ListView {

                id: rowsView

                width: root.rowContentWidth
                // Bottom gutter: last row clears the horizontal overlay bar
                // (the vertical analog of the vScrollBar gutter above).
                height: hFlick.height - headerRow.height - headerSeparator.height
                        - hScrollBar.height
                clip: true
                model: root.model
                boundsBehavior: Flickable.StopAtBounds

                // Re-parented to root: pinned to the visible right edge,
                // below the header, above the horizontal bar's lane.
                ScrollBar.vertical: ScrollBar {

                    id: vScrollBar
                    parent: root
                    policy: ScrollBar.AsNeeded
                    anchors.top: parent.top
                    anchors.topMargin: AppConfig.tableRowHeight
                                       + AppConfig.tableHeaderSeparatorWidth
                    anchors.right: parent.right
                    anchors.bottom: parent.bottom
                    anchors.bottomMargin: hScrollBar.height

                }

                delegate: Item {

                    id: rowDelegate

                    // Named, prefixed roles — no collisions with Item's own
                    // x/y/rotation properties. `source`/`sourceDetail` are
                    // optional (absent from the alignment page's model), so
                    // they are read via the model object: a named required
                    // property would abort delegate creation when the role
                    // is missing.
                    required property int index
                    required property real stageR
                    required property real stageT
                    required property var model

                    width: root.rowContentWidth
                    height: AppConfig.tableRowHeight

                    Row {

                        spacing: AppConfig.tableColumnSpacing

                        IndexCell { text: rowDelegate.index + 1 }

                        SourceCell {

                            // "Category" or "Category: detail" (a measured
                            // row reads "Measured: <image file name>", so a
                            // glance ties it to its position).
                            text: {
                                if (!root.showSource
                                        || rowDelegate.model.source === undefined)
                                    return ""
                                var detail = rowDelegate.model.sourceDetail
                                return detail
                                       ? rowDelegate.model.source + ": " + detail
                                       : rowDelegate.model.source
                            }
                            // Category explanation (from sourceToolTips,
                            // keyed by category) + the full provenance
                            // detail, one per line.
                            toolTipText: {
                                var parts = []
                                var explain = root.sourceToolTips[
                                    rowDelegate.model.source]
                                if (explain)
                                    parts.push(explain)
                                var detail = rowDelegate.model.sourceDetail
                                if (detail)
                                    parts.push(detail)
                                return parts.join("\n")
                            }

                        }

                        RowFiller { }

                        ValueCell { text: root.stageDegText(rowDelegate.stageR) }

                        ValueCell { text: root.stageDegText(rowDelegate.stageT) }

                    }

                    // Row separator — same treatment as PositionResultsTable.
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
        text: root.emptyText
        // The empty text can be a full calculator status sentence (the
        // alignment page binds the SEM verdict here) — wrap inside the
        // component instead of overflowing the card.
        width: Math.min(implicitWidth,
                        root.width - 2 * AppConfig.tableColumnSpacing)
        wrapMode: Text.WordWrap
        horizontalAlignment: Text.AlignHCenter
        font.pixelSize: AppConfig.tableCellFontSize
        color: AppConfig.universalForeground

    }

}
