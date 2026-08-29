import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../Config"

// Modal confirmation dialog.
//
// A word-wrapped message with OK/Cancel buttons (texts from the Strings
// defaults, overridable per instance), an optional "do not show this
// again" checkbox, and an informational mode (showRejectButton: false)
// for notices like the tilt-limit dialog. Centered on the window
// overlay; callers handle onAccepted / onRejected.

Dialog {

    id: root

    property alias message: messageLabel.text
    property string acceptText: Strings.dialogDefaultAcceptText
    property string rejectText: Strings.dialogDefaultRejectText
    property bool showRejectButton: true
    property alias showSuppressCheckBox: suppressCheckBox.visible
    property alias suppressChecked: suppressCheckBox.checked

    modal: true
    parent: Overlay.overlay
    anchors.centerIn: parent
    width: Math.min(440, parent ? parent.width - 2 * AppConfig.pageMargin
                                : 440)
    padding: AppConfig.containerPadding

    contentItem: ColumnLayout {

        spacing: AppConfig.containerSpacing

        Label {

            id: messageLabel
            Layout.fillWidth: true
            // Zeroed preferred width: a wrapping Label's implicitWidth
            // is its full unwrapped text width; the dialog's width must
            // win.
            Layout.preferredWidth: 0
            wrapMode: Label.WordWrap
            font.pixelSize: AppConfig.pageBodyFontSize

        }

        CheckBox {

            id: suppressCheckBox
            visible: false
            text: "Do not show this again"

        }

    }

    footer: DialogButtonBox {

        alignment: Qt.AlignRight
        background: null

        RoundButton {

            text: root.acceptText
            radius: AppConfig.buttonRadius
            padding: AppConfig.buttonPadding
            leftPadding: AppConfig.buttonLeftRightPadding
            rightPadding: AppConfig.buttonLeftRightPadding
            DialogButtonBox.buttonRole: DialogButtonBox.AcceptRole

        }

        RoundButton {

            visible: root.showRejectButton
            text: root.rejectText
            radius: AppConfig.buttonRadius
            padding: AppConfig.buttonPadding
            leftPadding: AppConfig.buttonLeftRightPadding
            rightPadding: AppConfig.buttonLeftRightPadding
            DialogButtonBox.buttonRole: DialogButtonBox.RejectRole

        }

    }

}
