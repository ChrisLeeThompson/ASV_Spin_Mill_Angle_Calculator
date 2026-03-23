"""
Module creates a class for 2D plotting.

Uses the modern ``backend_qtagg`` backend for clean PySide6
rendering.  Figure creation uses ``constrained_layout=True``
instead of ``tight_layout()`` to avoid layout thrashing and
clipping artifacts during widget resize.
"""
import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from matplotlib.patches import Arc, Ellipse as MplEllipse, FancyArrowPatch
from PySide6.QtCore import Qt
from script_modules.app_styles import AppStyles


class TwoDimCanvas(FigureCanvasQTAgg):
    """
    A Qt-compatible matplotlib canvas for 2D plotting.
    Provides methods for common 2D plot operations.
    """

    def __init__(self, parent=None, width=5, height=5, dpi=110):
        """
        Initialize the 2D visualization canvas.

        Args:
            parent: Parent widget
            width: Figure width in inches
            height: Figure height in inches
            dpi: Dots per inch (resolution)
        """
        self.fig = Figure(
            figsize=(width, height),
            dpi=dpi,
            facecolor=AppStyles.Colors.MAIN_BG,
            constrained_layout=True,
        )
        self.ax = self.fig.add_subplot(111)
        super().__init__(self.fig)
        self.setParent(parent)
        # Disable antialiasing on figure/axes patches to prevent
        # blurry edges at non-integer DPI scaling.
        self.fig.patch.set_antialiased(False)
        self.ax.patch.set_antialiased(False)
        # Set widget background to match figure — prevents the
        # default grey from bleeding through during resize.
        self.setStyleSheet(
            f"background-color: {AppStyles.Colors.MAIN_BG};"
        )
        self._apply_canvas_plot_style()
        self.setFocusPolicy(Qt.ClickFocus)

    def _apply_canvas_plot_style(self):
        """Apply consistent dark theme styling to the canvas."""
        self.ax.set_facecolor(AppStyles.Colors.MAIN_BG)
        # Spine colors — hide top/right, style left/bottom
        self.ax.spines["left"].set_color(
            AppStyles.Colors.PLOT_SPINE_COLOR
        )
        self.ax.spines["bottom"].set_color(
            AppStyles.Colors.PLOT_SPINE_COLOR
        )
        self.ax.spines["top"].set_visible(False)
        self.ax.spines["right"].set_visible(False)
        # Label and title colors
        self.ax.xaxis.label.set_color(AppStyles.Colors.TEXT_PRIMARY)
        self.ax.yaxis.label.set_color(AppStyles.Colors.TEXT_PRIMARY)
        self.ax.title.set_color(AppStyles.Colors.TEXT_PRIMARY)
        # Tick colors
        self.ax.tick_params(
            axis="x", colors=AppStyles.Colors.PLOT_SPINE_COLOR
        )
        self.ax.tick_params(
            axis="y", colors=AppStyles.Colors.PLOT_SPINE_COLOR
        )

    # =========================================================================
    # Basic Plotting Methods
    # =========================================================================

    def plot_line(self, x, y, color="#a1c7ea", linestyle="-", linewidth=1.5,
                  label=None, **kwargs):
        """
        Plot a 2D line.
        Args:
            x, y: Coordinate arrays
            color: Line color
            linestyle: Line style ('-', '--', '-.', ':')
            linewidth: Line width
            label: Legend label
            **kwargs: Additional arguments passed to plot
        """
        self.ax.plot(x, y, color=color, linestyle=linestyle, linewidth=linewidth,
                     label=label, **kwargs)

    def plot_scatter(self, x, y, color="blue", s=100, **kwargs):
        """
        Plot 2D scatter points.
        Args:
            x, y: Coordinate arrays or lists
            color: Point color
            s: Point size
            **kwargs: Additional arguments passed to scatter
        """
        self.ax.scatter(x, y, color=color, s=s, **kwargs)

    def plot_ellipse(self, center, width, height, angle=0, color="blue",
                     fill=False, linewidth=1.5, **kwargs):
        """
        Plot an ellipse.
        Args:
            center: (x, y) tuple for ellipse center
            width: Ellipse width
            height: Ellipse height
            angle: Rotation angle in degrees
            color: Edge color
            fill: Whether to fill the ellipse
            linewidth: Edge line width
            **kwargs: Additional arguments passed to Ellipse patch
        """
        ellipse = MplEllipse(center, width, height, angle=angle,
                             edgecolor=color, facecolor='none' if not fill else color,
                             linewidth=linewidth, **kwargs)
        self.ax.add_patch(ellipse)

    def plot_arc(self, center, width, height, angle=0, theta1=0, theta2=90,
                 color="blue", linewidth=1.5, **kwargs):
        """
        Plot an arc.
        Args:
            center: (x, y) tuple for arc center
            width: Arc width
            height: Arc height
            angle: Rotation of the ellipse in degrees
            theta1: Starting angle of the arc in degrees
            theta2: Ending angle of the arc in degrees
            color: Arc color
            linewidth: Line width
            **kwargs: Additional arguments passed to Arc patch
        """
        arc = Arc(center, width, height, angle=angle, theta1=theta1, theta2=theta2,
                  color=color, linewidth=linewidth, **kwargs)
        self.ax.add_patch(arc)

    def plot_arrow(self, x_start, y_start, x_end, y_end, color="black",
                   arrowstyle='->', linewidth=1.5, **kwargs):
        """
        Plot an arrow.
        Args:
            x_start, y_start: Starting coordinates
            x_end, y_end: Ending coordinates
            color: Arrow color
            arrowstyle: Arrow style
            linewidth: Line width
            **kwargs: Additional arguments passed to FancyArrowPatch
        """
        arrow = FancyArrowPatch((x_start, y_start), (x_end, y_end),
                                arrowstyle=arrowstyle, color=color,
                                linewidth=linewidth, **kwargs)
        self.ax.add_patch(arrow)

    def plot_quiver(self, x, y, u, v, color="black", scale=1.0, width=0.006,
                    headwidth=3.0, headlength=5.0, **kwargs):
        """
        Plot a 2D vector/arrow using quiver.
        Args:
            x, y: Starting point coordinates
            u, v: Vector components (direction)
            color: Arrow color
            scale: Scale for arrow length (smaller = longer arrows)
            width: Shaft width
            headwidth: Arrow head width
            headlength: Arrow head length
            **kwargs: Additional arguments passed to quiver
        """
        self.ax.quiver(x, y, u, v, color=color, scale=scale, scale_units='xy',
                      angles='xy', width=width, headwidth=headwidth,
                      headlength=headlength, **kwargs)

    # =========================================================================
    # Plot Configuration Methods
    # =========================================================================

    def set_title(self, title, fontsize=12, color=AppStyles.Colors.TEXT_PRIMARY, **kwargs):
        """Set the plot title."""
        self.ax.set_title(title, fontsize=fontsize, color=color, **kwargs)

    def set_labels(self, xlabel=None, ylabel=None, fontsize=10,
                   color=AppStyles.Colors.THREE_DIM_LABEL_COLOR):
        """
        Set axis labels.
        Args:
            xlabel, ylabel: Axis label strings (None to skip)
            fontsize: Label font size
            color: Label text color
        """
        if xlabel is not None:
            self.ax.set_xlabel(xlabel, fontsize=fontsize, color=color)
        if ylabel is not None:
            self.ax.set_ylabel(ylabel, fontsize=fontsize, color=color)

    def set_limits(self, xlim=None, ylim=None):
        """
        Set axis limits.
        Args:
            xlim, ylim: Tuples of (min, max) or None to skip
        """
        if xlim is not None:
            self.ax.set_xlim(*xlim)
        if ylim is not None:
            self.ax.set_ylim(*ylim)

    def set_aspect_equal(self):
        """Set equal aspect ratio for both axes."""
        self.ax.set_aspect('equal', adjustable='box')

    def set_grid(self, visible=True, alpha=0.3, color=AppStyles.Colors.THREE_DIM_LABEL_COLOR):
        """
        Set grid visibility and style.
        Args:
            visible: Whether grid is visible
            alpha: Grid transparency
            color: Grid color
        """
        if visible:
            self.ax.grid(visible=True, alpha=alpha, color=color)
        else:
            self.ax.grid(visible=False)

    # =========================================================================
    # Utility Methods
    # =========================================================================

    def clear(self):
        """Clear the plot and re-apply dark theme styling."""
        self.ax.clear()
        self._apply_canvas_plot_style()
        self.ax.grid(False)

    def refresh(self):
        """Redraw the canvas (efficient for static plots)."""
        self.draw_idle()

    # =========================================================================
    # High-Level Specialized Methods for FIB Geometry
    # =========================================================================

    def plot_ccd_view(self, calculated_angle, diameter,
                      sem_color=AppStyles.Colors.THREE_DIM_SEM_COLOR,
                      fib_color=AppStyles.Colors.THREE_DIM_FIB_COLOR,
                      aoi_color=AppStyles.Colors.THREE_DIM_ELLIPSE_COLOR,
                      dimension_color=AppStyles.Colors.THREE_DIM_LABEL_COLOR):
        """
        Plot the CCD view showing SEM, FIB, and AOI lines with milling angle.

        Args:
            calculated_angle: The calculated milling angle in degrees
            diameter: AOI diameter to scale the AOI line length
            sem_color: Color for SEM line
            fib_color: Color for FIB line
            aoi_color: Color for AOI line
            dimension_color: Color for dimension annotations
        """
        self.clear()

        # AOI line length (half of diameter, as specified)
        aoi_line_length = diameter / 2

        # Calculate FIB line endpoint to set proper limits
        fib_angle_rad = np.radians(38)

        # Set line length based on diameter with some padding
        line_length = diameter * 0.6

        fib_x = line_length * np.cos(fib_angle_rad)
        fib_z = line_length * np.sin(fib_angle_rad)

        padding_factor = 1.08
        max_x = fib_x * padding_factor
        max_z = fib_z * padding_factor

        self.set_limits(xlim=(0, max_x), ylim=(0, max_z))
        self.set_aspect_equal()

        # SEM vector (vertical, along z-axis) - pointing upward
        sem_length = max_z * 0.98
        self.plot_quiver(0, 0, 0, sem_length, color=sem_color,
                        scale=1.0, width=0.008, headwidth=4.0, headlength=6.0)

        # FIB vector (at 38° from x-axis, or 52° from z-axis)
        self.plot_quiver(0, 0, fib_x, fib_z, color=fib_color,
                        scale=1.0, width=0.008, headwidth=4.0, headlength=6.0)

        # AOI line (at 38° - milling_angle from x-axis)
        aoi_angle_deg = 38 - calculated_angle
        aoi_angle_rad = np.radians(aoi_angle_deg)
        aoi_x = aoi_line_length * np.cos(aoi_angle_rad)
        aoi_z = aoi_line_length * np.sin(aoi_angle_rad)
        self.plot_line([0, aoi_x], [0, aoi_z], color=aoi_color,
                       linestyle='-', linewidth=2, label='AOI')

        # Arc showing milling angle (between AOI and FIB)
        arc_radius = diameter * 0.4
        self.plot_arc((0, 0), arc_radius * 2, arc_radius * 2,
                      angle=0, theta1=aoi_angle_deg, theta2=38,
                      color=dimension_color, linewidth=1.5)

        # Use a point along the AOI line instead of arc midpoint
        annotation_distance = aoi_line_length * 0.8
        text_x = annotation_distance * np.cos(aoi_angle_rad)
        text_z = annotation_distance * np.sin(aoi_angle_rad)

        # Offset the text perpendicular to the AOI line for better visibility
        offset_angle = aoi_angle_rad + np.radians(90)  # Perpendicular
        offset_distance = diameter * 0.06
        text_x += offset_distance * np.cos(offset_angle)
        text_z += offset_distance * np.sin(offset_angle)

        # Add angle text annotation
        self.ax.text(text_x, text_z, f'{calculated_angle:.2f}°',
                     ha='center', va='center', fontsize=10,
                     color=AppStyles.Colors.TEXT_PRIMARY)

        # Configure display
        self.set_labels('X', 'Z', color=AppStyles.Colors.TEXT_PRIMARY)
        self.set_title('CCD View', fontsize=12, color=AppStyles.Colors.TEXT_PRIMARY)
        self.set_grid(False)

        self.refresh()

    def plot_fib_view(self, diameter, measured_minor,
                      ellipse_color=AppStyles.Colors.THREE_DIM_ELLIPSE_COLOR,
                      dimension_color=AppStyles.Colors.THREE_DIM_LABEL_COLOR):
        """
        Plot the FIB view showing the ellipse as seen from the FIB perspective.

        Args:
            diameter: AOI diameter (ellipse width)
            measured_minor: Measured ellipse height (minor axis)
            ellipse_color: Color for the ellipse
            dimension_color: Color for dimension lines
        """
        self.clear()

        # Use the same calculation as CCD view for both axes
        fib_angle_rad = np.radians(38)
        line_length = diameter * 0.6
        fib_x = line_length * np.cos(fib_angle_rad)
        fib_z = line_length * np.sin(fib_angle_rad)
        padding_factor = 1.2
        max_x = fib_x * padding_factor
        max_z = fib_z * padding_factor

        # X-axis: from -max_x to +max_x (centered, symmetric)
        # Y-axis: from 0 to max_z (matches CCD's z-axis)
        self.set_limits(xlim=(-max_x, max_x), ylim=(0, max_z))
        self.set_aspect_equal()

        # Plot the ellipse centered at y = max_z/2 to center it vertically
        ellipse_center_y = max_z / 2
        self.plot_ellipse((0, ellipse_center_y), diameter, measured_minor,
                          color=ellipse_color, linewidth=2)

        # Calculate padding for dimension lines relative to ellipse size
        padding = diameter * 0.3

        # Dimension line for width (horizontal) - positioned below ellipse
        width_y = ellipse_center_y - measured_minor / 2 - padding * 0.3
        self.plot_arrow(-diameter / 2, width_y, diameter / 2, width_y,
                        color=dimension_color, arrowstyle='<->', linewidth=1.2)

        # Add width dimension text
        self.ax.text(0, width_y - padding * 0.1, f'{diameter:.1f} µm',
                     ha='center', va='top', fontsize=10,
                     color=AppStyles.Colors.TEXT_PRIMARY)

        # Position height dimension line centered in the ellipse (horizontally)
        height_x = 0  # Center of ellipse

        # Add vertical dimension line with arrows at both ends
        self.plot_arrow(height_x, ellipse_center_y - measured_minor / 2,
                        height_x, ellipse_center_y + measured_minor / 2,
                        color=dimension_color, arrowstyle='<->', linewidth=1.2)

        # Add dimension text horizontally (0 rotation) to the right of center
        text_x_offset = padding * 0.1
        self.ax.text(text_x_offset, ellipse_center_y + (text_x_offset * 2.2), f'{measured_minor:.1f} µm',
                     ha='left', va='center', fontsize=10, rotation=0,
                     color=AppStyles.Colors.TEXT_PRIMARY)

        # Configure display
        self.set_labels('X (µm)', 'Y (µm)', color=AppStyles.Colors.TEXT_PRIMARY)
        self.set_title('FIB View', fontsize=12, color=AppStyles.Colors.TEXT_PRIMARY)
        self.set_grid(False)

        self.refresh()