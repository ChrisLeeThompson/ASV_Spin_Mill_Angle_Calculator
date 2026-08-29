pragma Singleton
import QtQuick
import QtQuick.Controls.Universal

QtObject {

    // Theme colors
    readonly property int universalTheme: Universal.Dark
    readonly property color universalAccent: "#2ea2ec"
    readonly property color universalForeground: "#ffffff"
    readonly property color universalBackground: "#1e2c36"
    readonly property color textDisabledColor: "#8498a4"
    readonly property color placeholderTextColor: "#9CBBD2"
    readonly property color catbugMittenColor: "#eb70a9"

    // Main window
    readonly property int mainWindowWidth: 1200
    readonly property int mainWindowHeight: 1028
    readonly property int mainWindowMinimumWidth: 750
    readonly property int mainWindowMinimumHeight: 550

    // Asset paths
    // Square-padded so rotating the wrapping Item about its center is
    // stable (rotated 90 deg for a down chevron). Its path fill is
    // already #ffffff = universalForeground, so no color overlay is
    // needed here.
    readonly property url iconChevronRight: "../assets/chevron-right-square.svg"

    // Tooltip durations
    readonly property int toolTipDelayMs: 1500
    readonly property int toolTipTimeoutMs: 10000

    // Buttons
    readonly property int buttonRadius: 4
    readonly property int buttonPadding: 10
    readonly property int buttonLeftRightPadding: 16
    readonly property int buttonMargins: 6

    // Dialogs
    readonly property int dialogDefaultWidth: 360
    readonly property int dialogWideWidth: 460
    readonly property int dialogPadding: 16

    // Side Bar
    readonly property color sideBarBackground: "#263640"
    readonly property int navItemFontSize: 18
    readonly property int sideBarWidth: 200
    readonly property int sideBarMargins: 8
    readonly property int sideBarColumnSpacing: 4

    // Status Bar
    readonly property int statusBarLabelFontSize: 16
    readonly property int statusBarHorizontalMargin: 12
    readonly property int statusBarProgressWidth: 300
    readonly property int statusBarIndicatorLabelWidth: 200
    // How long controller status messages stay up before the bar clears.
    readonly property int statusBarMessageDurationMs: 10000

    // Activity colors
    readonly property color activityCompleteColor: "#33ff33"
    readonly property color activityRunningColor: "#2ea2ec"
    readonly property color activityExceptionColor: "#ffc633"
    // Position Alignment "updated" state: the review capture was re-taken
    // by hand (Update button) — accent blue, deliberately not the green
    // reserved for a routine-verified alignment.
    readonly property color activityUpdatedColor: universalAccent

    // Container colors
    readonly property color containerBackground: "#263640"
    readonly property color containerBorderColor: "#2e3e49"

    // Container — layout
    readonly property int containerRadius: 6
    readonly property int containerBorderWidth: 2
    readonly property int containerPadding: 12
    readonly property int containerSideMargin: 12
    readonly property int containerSpacing: 16

    // Container — title
    readonly property int containerTitleFontSize: 16

    // Pages
    readonly property int pageMargin: 20
    readonly property int pageHeadingFontSize: 20
    readonly property int pageBodyFontSize: 16
    readonly property int pageHeadingSpacerHeight: 16
    readonly property int pageSectionSpacing: 10 // Used for column layouts, for example
    readonly property int buttonRowSpacing: 10 // Used for the bottom button row layout
    readonly property int settingsFormRowSpacing: 12
    readonly property int settingsFormColumnSpacing: 30
    readonly property int settingsPageMaxWidth: 400

    // Position alignment page
    readonly property int positionAlignmentControlsColumnMaxWidth: 400
    // The image viewer's floor: with the content-area scroll, this is what
    // the viewer shrinks to before the page stops compressing and scrolls.
    readonly property int imageViewerMinimumHeight: 300

    // FIB image viewer (Position Alignment live view + ellipse overlay).
    // The overlay color follows the run state: universalAccent while running,
    // activityCompleteColor on success (same colors the card border uses).
    readonly property real fibViewerEllipseLineWidth: 2.0
    readonly property int fibViewerCenterMarkerSize: 12   // "+" half-length
    readonly property real fibViewerCenterMarkerLineWidth: 1.5
    // Frame-center reference cross (the centering target): full-opacity
    // accent so both legs read over the FIB image's bright horizontal
    // banding (the old 40%-alpha gray horizontal leg vanished into it).
    readonly property color fibViewerCrosshairColor: universalAccent
    readonly property real fibViewerCrosshairLineWidth: 1.0
    readonly property int fibViewerFooterFontSize: 14

    // Position results table
    readonly property int tableCellFontSize: 14
    readonly property int tableRowHeight: 28
    // Per-column widths, sized to the wider of the header text and the
    // widest expected value at tableCellFontSize (units live in the headers,
    // so long headers like "Scan R (deg)" are usually the binding constraint).
    readonly property int tableIndexColumnWidth: 28    // "12" centered
    readonly property int tableAngleColumnWidth: 64    // "R (deg)"
    readonly property int tableStageColumnWidth: 96    // "Stage X (mm)" / "-149.9850"
    readonly property int tableBeamColumnWidth: 92     // "Beam X (µm)"
    readonly property int tableScanRColumnWidth: 96    // "Scan R (deg)"
    readonly property int tableWdColumnWidth: 72       // "WD (mm)" / "10.254"
    readonly property int tableMillingAngleColumnWidth: 140  // "Milling Angle (deg)"
    // Row-action chevron column, ahead of the index column. Sized to the
    // chevron glyph plus its hit area — deliberately narrow so it costs
    // the already-scrolling Position Alignment table as little as possible.
    readonly property int tableActionColumnWidth: 24
    readonly property int tableActionIconSize: 12
    readonly property int tableColumnSpacing: 12
    readonly property int tableCellRightPadding: 12
    readonly property int tableHeaderSeparatorWidth: 2
    readonly property int tableRowSeparatorWidth: 1
    // Pending and deactivated slot rows in the Position Alignment table.
    readonly property real tableInactiveRowOpacity: 0.45
    readonly property int tableHeight: 180

    // SEM angle calc page — table extensions
    // File Name column: capture names run ~60 chars, so they elide (the
    // cell's tooltip carries the full name); 200 keeps R/T on-screen at
    // the default window width before horizontal scroll engages.
    readonly property int tableFileNameColumnWidth: 200
    // Source column: "Calculated (primary)" / "Calculated (alternate)"
    // / "Measured: <file name>".
    // Wide enough that a measured row's timestamp prefix (the part that
    // distinguishes the capture) survives the elide; tooltip has the rest.
    readonly property int tableSourceColumnWidth: 260
    // Narrow variant for the Position Alignment page's 400 px card, whose
    // provenance details are short ("Position 2") — keeps the R/T columns
    // on-screen without horizontal scroll.
    readonly property int tableSourceColumnWidthNarrow: 150
    // (Table heights are declared at the call sites, in rows — see
    // preferredRows on the SEM page's two tables.)
    // Results card floor. StatusLogView has no natural height (implicit 0 by
    // design, so text length cannot leak into the page's implicitHeight), so
    // this is what keeps the card from collapsing once the page scrolls;
    // Layout.fillHeight grows it on taller windows and the block scrolls.
    // ~8 audit lines — small enough that the full card stack fits the
    // default window without a scrollbar.
    readonly property int semResultsMinimumHeight: 160
    // Max width for the SEM page's stacked tables, sized to fully show the
    // Spin Mill Positions table's 10 columns without horizontal scroll:
    // 1008 content (900 summed column widths + 9 * 12 spacing) + the always-
    // reserved vertical-scrollbar gutter + 2 * containerPadding (the Card's
    // padding). Wider windows center the tables instead of over-stretching.
    readonly property int semTablesMaxWidth: 1060

    // Shared width for the calc pages' target-milling-angle spin box. Published
    // at runtime by the FIB Angle Calculator page (the widest of its three input
    // boxes) and read by the SEM Angle Calc and Position Alignment pages so that
    // box is the same width on all three. Writable (not readonly): it is a
    // broadcast measurement, 0 until the FIB page publishes — each subscriber
    // binds Math.max(own implicitWidth, this) so it never collapses.
    property real calcSpinBoxWidth: 0

    // FIB angle calculator page
    readonly property int fibAngleCalcControlsMaxWidth: 420
    readonly property int fibViewStackMaxWidth: 700

    // FIB 2D view figure. The figure is fluid: beam length derives from the
    // item's size via the radius fraction; the milling-angle arc radius is a
    // fraction of the beam length. The pivot sits below the item's vertical
    // midpoint (center-Y fraction) because the beams only extend upward —
    // this fills the frame instead of leaving an empty bottom half.
    readonly property real fib2DViewLineWidth: 1.0
    readonly property real fib2DViewIndicatorWidth: 3.0
    readonly property real fib2DViewArcWidth: 2.0
    readonly property real fib2DViewRadiusFraction: 0.55
    readonly property real fib2DViewArcRadiusFraction: 0.55
    // Half-length of the ellipse (AOI) line as a fraction of the beam length.
    readonly property real fib2DViewEllipseLineFraction: 0.83
    readonly property real fib2DViewCenterYFraction: 0.55
    readonly property int fib2DViewLabelOffset: 6
    readonly property int fib2DViewLegendFontSize: 14
    readonly property int fib2DViewLegendSwatchWidth: 24
    readonly property int fib2DViewLegendSwatchHeight: 3
    readonly property int fib2DViewAnimationMs: 300

    // FIB "FIB View" figure — the AOI circle as seen from the FIB column.
    // Fluid: while the ellipse is flat its major axis takes the full width
    // fraction; as the aspect grows toward a circle the height fraction
    // (the minor axis' vertical budget) takes over and the figure cedes
    // width, so the 90°-milling case (a full circle) always fits. The
    // center sits above the vertical midpoint because the dimension chain
    // (width arrow, value chip) and the legend hang below.
    readonly property real fibFIBViewEllipseLineWidth: 3.0
    readonly property real fibFIBViewDimensionLineWidth: 1.0
    readonly property real fibFIBViewWidthFraction: 0.9
    readonly property real fibFIBViewHeightFraction: 0.62
    readonly property real fibFIBViewCenterYFraction: 0.42
    readonly property int fibFIBViewArrowHeadLength: 10
    readonly property int fibFIBViewDimensionGap: 10
    readonly property int fibFIBViewLabelOffset: 6
    readonly property int fibFIBViewAnimationMs: 300

}
