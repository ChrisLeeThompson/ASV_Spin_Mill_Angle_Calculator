pragma Singleton
import QtQuick
import "."

QtObject {

    // Main window
    readonly property string mainWindowTitle: "ASV Spin Mill Angle Calculator 3.2.0"

    // Generic confirm-dialog button defaults (overridable per instance)
    readonly property string dialogDefaultAcceptText: "OK"
    readonly property string dialogDefaultRejectText: "Cancel"

    // Tooltips
    readonly property string targetMillingAngleLabelTooltip: "The milling angle set in Auto Slice And View (ASV)."

    // Position alignment page
    readonly property string useBeamShiftLabelTooltip: "Beam shift is used to center the area of interest (AOI) ellipse, in addition to stage x and stage y moves."
    readonly property string numberOfPositionsLabelTooltip: "The number of spin mill positions set in ASV's Define Spin Mill Position activity." +
                                                            " Positions beyond this count are kept but excluded from the SEM calculation —" +
                                                            " raise the count to include them again."
    readonly property string startAlignmentDialogMessage: "The alignment routine is about to control the microscope." +
                                                          " Ensure ASV has moved the stage to a spin mill position before proceeding."
    readonly property string startAlignmentDialogTitle: "Start Position Alignment"
    readonly property string tiltLimitDialogTitle: "Stage Tilt Limit"
    readonly property string clearPositionsDialogTitle: "Clear Spin Mill Positions"
    readonly property string clearPositionsDialogMessage: "All recorded spin mill positions will be reset to pending and the calculated SEM" +
                                                          " positions cleared."
    readonly property string updatePositionButtonTooltip: "Grabs a FIB image and captures the current stage position, beam shift, and scan rotation." +
                                                          " Press Confirm to record the position."
    readonly property string confirmButtonTooltip: "Record the reviewed position."
    // Per-row action menu in the Spin Mill Positions table.
    readonly property string rowGoToTooltip: "Drive the stage to this position and restore the recorded beam shift and FIB scan rotation."
    readonly property string rowReconfirmTooltip: "Replace this position's stored values with the re-captured live position."
    readonly property string rowReconfirmDisabledTooltip: "Press Update first to re-capture the live position." +
                                                           " It records what you have reviewed in the FIB view into this position."
    readonly property string rowGoToPendingTooltip: "Available once this position has been recorded."
    readonly property string rowConfirmHereTooltip: "Record the reviewed capture into this pending position."
    readonly property string rowInactiveTooltip: "This position is beyond the current Number of Spin Mill Positions." +
                                                 " Raise the count to include it again."

    // Pinned at the top of the Status Log card's scrollback. The log view
    // does not word-wrap (it scrolls horizontally), so line breaks are
    // authored here with \n.
    readonly property string positionAlignmentInstructionsText: "With the stage at a spin mill position, press Start to begin an alignment routine.\n" +
                                                                "The routine finds the AOI ellipse, tilts to the target milling angle, centers the\n" +
                                                                "ellipse in the FIB view, levels it with FIB scan rotation, then pauses for review.\n\n" +
                                                                "Press Confirm to record the position, Start to re-run, or Stop to cancel.\n" +
                                                                "Press Update to re-capture the current image and stage position.\n" +
                                                                "Set Number of Spin Mill Positions to match ASV's Define Spin Mill Position activity."

    // FIB angle calc page
    readonly property string aoiDiameterLabelTooltip: "The diameter of the area of interest (AOI) circle set in Auto Slice And View (ASV)."
    readonly property string measuredEllipseHeightLabelTooltip: "The height of the AOI ellipse measured from the perspective of the FIB (FIB view)."
    readonly property string tiltByAngleLabelTooltip: "The degrees to tilt the stage by to reach the calculated target milling angle."

    // SEM angle calc page
    readonly property string loadSpinMillPositionImagesButtonTooltip: "Load logged spin mill position images from: '<Project Directory>\\ImageLogs\\<site_name>\\Sample Preparation\\Define Spin Mill Position\\" +
                                                                      "AutoSliceAndView.Services.Services.Positioning.SpinMillPositioningService\\'.\nTo enable spin mill position image logging, go to the Logging page in ASV Settings and" +
                                                                      " check 'Log Spin Mill Position Images'."

    // Empty state for the Results card, shown until a load populates it
    // (and again after Clear Positions).
    readonly property string semResultsPlaceholderText: "Load spin mill position images to view results."

    // Settings page
    readonly property string saveDebugImagesLabelTooltip: "Save each alignment frame as a PNG plus a JSON sidecar (stage state, fit, gate verdict)," +
                                                          " one subfolder per run, under the application's 'debug_frames_dir' (the ASV_DEBUG_FRAMES_DIR" +
                                                          " environment variable overrides it). Applies from the next Start."
    readonly property string tiltToleranceLabelTooltip: "How close the measured milling angle must be to the target before the tilt loop stops." +
                                                         " Tighter means more correcting iterations, so a slower run. 0.10° is the measurement" +
                                                         " noise floor and cannot be lowered." +
                                                         " Applies from the next Start."
    readonly property string levelToleranceLabelTooltip: "How level the AOI ellipse must sit in the FIB view before the scan-rotation leveling" +
                                                          " loop stops. Tighter means more leveling iterations. Applies from the next Start."
    readonly property string verifyFramesLabelTooltip: "How many frames the final angle verdict pools. The reported angle is the median frame," +
                                                        " so more frames outvote a single noisy fit at the cost of extra grabs. Applies from the next Start."
    readonly property string sweepCountLabelTooltip: "How many tilt search sweeps the routine attempts before reporting that it could not find" +
                                                      " the AOI ellipse. Applies from the next Start."

    // Source-column tooltips for the Calculated SEM Positions table.
    readonly property string semSourceCalculatedTooltip: "The calculated position: the stage rotation and tilt setting the sample surface perpendicular" +
                                                         " to the SEM (referenced to the target milling angle), found where the AOI ellipse lies" +
                                                         " horizontal in the FIB view at zero scan rotation."
    readonly property string semSourceAlternateTooltip: "The second (alternate) valid solution, ~180° away in stage rotation; requires a larger stage tilt."
    readonly property string semSourceMeasuredTooltip: "Image was captured with FIB scan rotation ~0°; its stage rotation is used directly," +
                                                            " with the tilt correction applied."

}
