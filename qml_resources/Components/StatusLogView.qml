import QtQuick
import QtQuick.Controls
import "../Config"

// Scrollable plain-text log.
//
// Dumb, property-driven: the caller binds `text`; the view renders it
// without wrapping, scrolls on both axes with reserved scrollbar gutters
// (the tables' idiom), and keeps the end of the text in view — the newest
// or final lines carry the important part. The Flickable's implicit size
// stays 0 so text length never leaks into the page grid's sizing — the
// host card dictates the size.

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
