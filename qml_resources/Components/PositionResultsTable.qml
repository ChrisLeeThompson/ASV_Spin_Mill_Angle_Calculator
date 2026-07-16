import QtQuick
import QtQuick.Controls
import "../Config"

// Position Results Table
//
// Read-only, header-pinned table of per-position microscope readouts.
// Vertical scroll: internal ListView (the header sits above it, so it
// stays pinned). Horizontal scroll: outer Flickable moves the header and
// rows together, so columns can never drift out from under their headers.
//
// Model role contract (SI units — the delegate converts for display):
//   stageR (rad), stageT (rad), stageX (m), stageY (m), beamX (m),
//   beamY (m), scanR (rad), wd (m)
// Works with a QML ListModel today and a Python QAbstractListModel
// exposing the same role names later.

Item {

    id: root

    // Rows model; null/empty shows the empty-state label.
    property var model: null

    // Column definitions — the header row renders from this list, and the
    // row delegates reference the same AppConfig width constants, so headers
    // and cells stay aligned by construction. Units live in the headers;
    // cells are bare numbers.
    readonly property var columns: [
        { title: "#",            width: AppConfig.tableIndexColumnWidth },
        { title: "R (deg)",      width: AppConfig.tableAngleColumnWidth },
        { title: "T (deg)",      width: AppConfig.tableAngleColumnWidth },
        { title: "Stage X (mm)", width: AppConfig.tableStageColumnWidth },
        { title: "Stage Y (mm)", width: AppConfig.tableStageColumnWidth },
        { title: "Beam X (µm)",  width: AppConfig.tableBeamColumnWidth },
        { title: "Beam Y (µm)",  width: AppConfig.tableBeamColumnWidth },
        { title: "Scan R (deg)", width: AppConfig.tableScanRColumnWidth },
        { title: "WD (mm)",      width: AppConfig.tableWdColumnWidth }
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

                        required property int index
                        required property var modelData

                        width: modelData.width
                        height: AppConfig.tableRowHeight
                        text: modelData.title
                        font.pixelSize: AppConfig.tableCellFontSize
                        color: AppConfig.universalForeground
                        rightPadding: index === 0 ? 0 : AppConfig.tableCellRightPadding
                        horizontalAlignment: index === 0 ? Text.AlignHCenter
                                                         : Text.AlignRight
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
        text: "No confirmed positions."
        font.pixelSize: AppConfig.tableCellFontSize
        color: AppConfig.universalForeground

    }

}
