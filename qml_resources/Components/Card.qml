import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../Config"

// Lightweight reusable container

Pane {

    id: root

    // Children declared inside a Card land in this content column.
    default property alias content: contentColumn.data

    // Per-instance overrides.
    property color backgroundColor: AppConfig.containerBackground
    property alias contentSpacing: contentColumn.spacing

    // Suppresses the border for cards used as invisible containers
    // (pair with backgroundColor: "transparent"); padding still applies,
    // so content insets match bordered neighbors.
    property bool borderless: false

    // Border color override for state-signalling cards (e.g. the image
    // viewer's idle/running/success/exception colors).
    property color borderColor: AppConfig.containerBorderColor

    // Optional title above the content (bold by default); hidden when empty.
    property string title: ""
    property bool titleBold: true

    // Optional trailing slot on the title line, right-justified (a
    // summary readout, a small action). Items declared here sit in line
    // with the title rather than below it, which the default `content`
    // alias cannot express. The title elides to yield space, so a long
    // title never pushes the slot off the card.
    property alias headerExtra: headerExtraArea.data

    focusPolicy: Qt.StrongFocus
    padding: AppConfig.containerPadding

    background: Rectangle {

        color: root.backgroundColor
        radius: AppConfig.containerRadius
        border.color: root.borderColor
        border.width: root.borderless ? 0 : AppConfig.containerBorderWidth

    }

    contentItem: ColumnLayout {

        id: contentColumn
        spacing: AppConfig.containerSpacing

        // Declared first so call-site children (appended via the default
        // alias) land below it. ColumnLayout skips it when invisible, so
        // titleless cards are unaffected — the header is invisible only
        // when there is neither a title nor a trailing item.
        RowLayout {

            id: headerRow
            visible: root.title !== ""
                     || headerExtraArea.children.length > 0
            Layout.fillWidth: true
            spacing: AppConfig.containerSpacing

            Label {

                visible: root.title !== ""
                text: root.title
                font.pixelSize: AppConfig.containerTitleFontSize
                font.bold: root.titleBold
                // Takes the slack so the trailing slot is pushed right,
                // and elides rather than squeezing it.
                Layout.fillWidth: true
                elide: Text.ElideRight

            }

            RowLayout {

                id: headerExtraArea
                Layout.alignment: Qt.AlignRight | Qt.AlignVCenter
                spacing: AppConfig.containerSpacing
                visible: children.length > 0

            }

        }

    }

}
