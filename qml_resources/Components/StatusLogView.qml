import QtQuick
import QtQuick.Controls
import "../Config"

// Scrollable plain-text log.
//
// Dumb, property-driven: the caller binds `text` and the view renders it
// without wrapping, scrolling on both axes (the tables' two-axis idiom:
// AsNeeded scrollbars with RESERVED gutters — content sizes include the
// bars' thickness so they never overlay the text, and margins keep the
// two bars out of each other's corner). The view keeps the END of the
// text in view: appended scrollback lands on the newest line, and a
// replaced block lands on its tail — where the important part is (the
// SEM Results card's warnings close the audit block).
//
// The Flickable's implicit size stays 0 (text length must not leak into
// the page grid's row/column sizing — the host card dictates the size).

Item {

    id: root

    property alias text: logLabel.text

    Flickable {

        id: logFlick
        anchors.fill: parent
        // Reserved gutters: the bars own their lanes, never the text.
        contentWidth: logLabel.implicitWidth + vScrollBar.width
        contentHeight: logLabel.implicitHeight + hScrollBar.height
        flickableDirection: Flickable.HorizontalAndVerticalFlick
        boundsBehavior: Flickable.StopAtBounds
        clip: true

        // Follow the end of the text: pin to the bottom when the content
        // outgrows the viewport, and rewind to the top when it no longer
        // fills it (a snapshot consumer clearing back to its placeholder —
        // without the clamp a stale scroll offset would leave the short
        // text out of view).
        onContentHeightChanged: contentY = Math.max(0, contentHeight - height)

        ScrollBar.horizontal: ScrollBar {

            id: hScrollBar
            policy: ScrollBar.AsNeeded

        }

        ScrollBar.vertical: ScrollBar {

            id: vScrollBar
            // Re-parented to the component root (the tables' idiom):
            // custom anchors on a bar still parented to its Flickable
            // fight the attached-property geometry management and QML
            // reports a possible anchor loop.
            parent: root
            policy: ScrollBar.AsNeeded
            anchors.top: parent.top
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            // Stop above the horizontal bar so the two never cross.
            anchors.bottomMargin: hScrollBar.height

        }

        Label {

            id: logLabel
            textFormat: Text.PlainText
            font.pixelSize: AppConfig.tableCellFontSize

        }

    }

}
