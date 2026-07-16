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
        // titleless cards are unaffected.
        Label {

            visible: root.title !== ""
            text: root.title
            font.pixelSize: AppConfig.containerTitleFontSize
            font.bold: root.titleBold
            Layout.fillWidth: true
            elide: Text.ElideRight

        }

    }

}
