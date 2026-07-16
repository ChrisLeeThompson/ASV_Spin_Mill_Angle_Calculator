import QtQuick
import QtQuick.Controls
import QtQuick.Controls.Universal
import QtQuick.Layouts
import QtQuick.Window
import "./Components"
import "./Config"
import "./Pages"

// Application root window.

ApplicationWindow {

    id: app_window
    title: Strings.mainWindowTitle
    width: AppConfig.mainWindowWidth
    height: AppConfig.mainWindowHeight
    minimumWidth: AppConfig.mainWindowMinimumWidth
    minimumHeight: AppConfig.mainWindowMinimumHeight
    Universal.theme: AppConfig.universalTheme
    Universal.accent: AppConfig.universalAccent
    Universal.foreground: AppConfig.universalForeground
    Universal.background: AppConfig.universalBackground
    visible: true

    ColumnLayout {

        anchors.fill: parent
        spacing: 0

        RowLayout {

            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 0

            SideBar {

                id: mainSideBar
                Layout.preferredWidth: AppConfig.sideBarWidth
                Layout.fillHeight: true

                primaryModel: ListModel {
                    ListElement { name: "Position Alignment" }
                    ListElement { name: "FIB Angle Calc" }
                    ListElement { name: "SEM Angle Calc" }
                }

                // No secondary (e.g. Settings) pages yet. To add one later:
                //   1. give the SideBar a secondaryModel, e.g.
                //        secondaryModel: ListModel { ListElement { name: "Settings" } }
                //   2. add a matching page as the next child of the StackLayout
                //      below (child order must mirror the models).
                // The SideBar already offsets secondary indices past the
                // primary ones, so the StackLayout indices line up.

            }

            // Content-area scroll: when the window is too short for the
            // current page, the page is held at its minimum useful height
            // (its implicitHeight — each page exposes one) and scrolls
            // vertically. When the window is tall enough, the page gets the
            // full viewport and its fill layouts stretch as usual, so no
            // scrollbar appears. The SideBar and StatusBar stay fixed.
            Flickable {

                id: contentScroll
                Layout.fillWidth: true
                Layout.fillHeight: true
                contentWidth: width
                contentHeight: Math.max(height, _currentPageImplicitHeight)
                flickableDirection: Flickable.VerticalFlick
                boundsBehavior: Flickable.StopAtBounds
                clip: true

                // Track the current page only — sizing to the tallest of all
                // pages would add blank scroll range on the shorter ones.
                readonly property real _currentPageImplicitHeight:
                    mainStackLayout.children[mainStackLayout.currentIndex]
                        ? mainStackLayout.children[mainStackLayout.currentIndex].implicitHeight
                        : 0

                ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

                StackLayout {

                    id: mainStackLayout
                    width: contentScroll.width
                    height: contentScroll.contentHeight
                    currentIndex: mainSideBar.currentPageIndex

                    PositionAlignmentPage { id: positionAlignmentPage }

                    FIBAngleCalcPage { id: fibAngleCalcPage }

                    SEMAngleCalcPage { id: semAngleCalcPage }

                }

            }

        }

        StatusBar {

            id: mainStatusBar
            Layout.fillWidth: true
            // Persistent right-corner indicator: microscope connection state.
            statusIndicator: appController.microscope.connectionStatus

            // Message slot driven by controller statusUpdated signals via
            // the Connections blocks below (Hydra pattern).
            // Center progress: an indeterminate pulse while the Position
            // Alignment automation runs (a convergence loop has no
            // meaningful fraction).
            busy: appController.positionAlignment.isRunning
            indeterminate: appController.positionAlignment.isRunning
        }

    }

    // Route controller status to the StatusBar. One Connections block per
    // sub-controller that emits statusUpdated; ignoreUnknownSignals keeps
    // this safe for controllers that gain the signal later.
    Connections {

        target: appController.sem
        ignoreUnknownSignals: true

        function onStatusUpdated(text) {
            mainStatusBar.showMessage(text, AppConfig.statusBarMessageDurationMs)
        }

    }

    Connections {

        target: appController.positionAlignment
        ignoreUnknownSignals: true

        function onStatusUpdated(text) {
            mainStatusBar.showMessage(text, AppConfig.statusBarMessageDurationMs)
        }

    }

}
