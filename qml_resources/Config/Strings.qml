pragma Singleton
import QtQuick
import "."

QtObject {

    // Main window
    readonly property string mainWindowTitle: "ASV Spin Mill Angle Calculator 3.0.0"

    // Generic confirm-dialog button defaults (overridable per instance)
    readonly property string dialogDefaultAcceptText: "Ok"
    readonly property string dialogDefaultRejectText: "Cancel"

    // Tooltips
    readonly property string targetMillingAngleLabelTooltip: "The milling angle set in Auto Slice And View (ASV)."

        // Position alignment page
    readonly property string useBeamShiftLabelTooltip: "Beam shift will be utilized to center the area of interest (AOI) ellipse, in addition to stage x and stage y moves."
    readonly property string startAlignmentDialogMessage: "The alignment routine is about to control the microscope." +
                                                          " Ensure ASV has moved the stage to a spin mill position before proceeding."
    readonly property string startAlignmentDialogTitle: "Start Position Alignment"
    readonly property string tiltLimitDialogTitle: "Stage Tilt Limit"
    // Pinned at the top of the Status Log card's scrollback. The log view
    // does not word-wrap (it scrolls horizontally), so line breaks are
    // authored here with \n.
    readonly property string positionAlignmentInstructionsText: "With the stage at a spin mill position, press Start to begin an alignment routine.\n" +
                                                                "The routine finds the AOI ellipse, tilts to the target milling angle, centers the ellipse\n" +
                                                                "in the FIB view, and levels it with FIB scan rotation, then pauses for " +
                                                                "review.\n\nPress Confirm to record the position, Start to re-run, or Stop\n" +
                                                                "to cancel. Repeat for each spin mill position."

        // FIB angle calc page
    readonly property string aoiDiameterLabelTooltip: "The diameter of the area of interest (AOI) circle set in Auto Slice And View (ASV)."
    readonly property string measuredEllipseHeightLabelTooltip: "The height of the AOI ellipse measured from the perspective of the FIB (FIB view)."
    readonly property string tiltByAngleLabelTooltip: "The degrees to tilt the stage by to reach the calculated target milling angle."

        // SEM angle calc page
    readonly property string loadSpinMillPositionImagesButtonTooltip: "Load logged spin mill position images from: ''<Project Directory>\\ImageLogs\\<site_name>\\Sample Preparation\\Define Spin Mill Position''\\" +
                                                                      "AutoSliceAndView.Services.Services.Positioning.SpinMillPositioningService''.\nTo enable spin mill position image logging, go to the Logging page in ASV Settings and" +
                                                                      " check ''Log Spin Mill Position Images''."

        // Empty state for the Results card, shown until a load populates it
        // (and again after Clear Positions).
    readonly property string semResultsPlaceholderText: "Load spin mill position images to view results."

        // Source-column tooltips for the Calculated SEM Positions table.
    readonly property string semSourceCalculatedTooltip: "The primary calculated position: the stage rotation and tilt to position the sample surface" +
                                                              " perpendicular to the SEM (using the target milling angle as reference). Position is calculated from finding the rotation where the AOI ellipse " +
                                                         "is horizontal to the FIB view x-axis with zero scan rotation."
    readonly property string semSourceAlternateTooltip: "The second (alternate) valid solution, ~180° away in stage rotation; requires a larger stage tilt."
    readonly property string semSourceMeasuredTooltip: "Image was captured with FIB scan rotation ~0°; its stage rotation is used directly," +
                                                            " with the tilt correction applied."

}
