import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../Config"

Label {

    id: root

    property string toolTipText: ""

    font.pixelSize: AppConfig.pageBodyFontSize
    Layout.alignment: Qt.AlignLeft | Qt.AlignVCenter

    // Truncate with "…" when the layout squeezes the label below its
    // implicit width — without this, the painted text spills out of the
    // label's bounds and under neighboring controls (QML text does not
    // clip to its item by default).
    elide: Text.ElideRight

    HoverHandler { id: labelHover }

    // Falls back to the full label text when elided and no explicit
    // tooltip is set, so the complete string stays reachable on hover.
    ToolTip.text: root.toolTipText !== "" ? root.toolTipText : root.text
    ToolTip.visible: (root.toolTipText !== "" || root.truncated)
                     && labelHover.hovered
    ToolTip.delay: AppConfig.toolTipDelayMs
    ToolTip.timeout: AppConfig.toolTipTimeoutMs

}
