"""
Module creates a class for 3D plotting.
"""
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PySide6.QtCore import Qt
from script_modules.script_styles import AppStyles


class ThreeDimCanvas(FigureCanvasQTAgg):
    """
    A Qt-compatible matplotlib canvas for 3D plotting.
    Provides methods for common 3D plot operations and view controls.
    """

    def __init__(self, parent=None, width=5, height=5, dpi=100):
        """
        Initialize the 3D visualization canvas.

        Args:
            parent: Parent widget
            width: Figure width in inches
            height: Figure height in inches
            dpi: Dots per inch (resolution)
        """
        self.fig = Figure(figsize=(width, height), dpi=dpi)
        self.ax = self.fig.add_subplot(111, projection="3d")
        super().__init__(self.fig)
        self.setParent(parent)
        self._apply_canvas_plot_style()
        # Use tight_layout with padding to prevent cutoff
        self.fig.tight_layout(pad=1.0)
        # set focus policy to click focus
        self.setFocusPolicy(Qt.ClickFocus)

    def _apply_canvas_plot_style(self):
        # Set canvas (figure) background
        self.fig.patch.set_facecolor(AppStyles.Colors.MAIN_BG)
        # Set axes background (for completeness, though hidden in 3D)
        self.ax.set_facecolor(AppStyles.Colors.MAIN_BG)

    # basic plotting methods

    def plot_3d_line(self, x, y, z, color="#a1c7ea", linestyle="-", linewidth=1.5,
                     label=None):
        """
        Plot a 3D line.
        Args:
            x, y, z: Coordinate arrays
            color: Line color
            linestyle: Line style ('-', '--', '-.', ':')
            linewidth: Line width
            label: Legend label
        """
        self.ax.plot3D(x, y, z, color=color, linestyle=linestyle, linewidth=linewidth,
                       label=label)

    def plot_surface(self, x, y, z, alpha=0.5, color="blue", **kwargs):
        """
        Plot a 3D surface.
        Args:
            x, y, z: Coordinate arrays (2D meshgrid format)
            alpha: Transparency (0-1)
            color: Surface color
            **kwargs: Additional arguments passed to plot_surface
        """
        self.ax.plot_surface(x, y, z, alpha=alpha, color=color, **kwargs)

    def plot_scatter(self, x, y, z, color="blue", s=100, **kwargs):
        """
        Plot 3D scatter points.
        Args:
            x, y, z: Coordinate arrays or lists
            color: Point color
            s: Point size
            **kwargs: Additional arguments passed to scatter
        """
        self.ax.scatter(x, y, z, color=color, s=s, **kwargs)

    def plot_trisurf(self, x, y, z, color="blue", alpha=0.5, **kwargs):
        """
        Plot a triangulated surface.
        Args:
            x, y, z: Coordinate arrays
            color: Surface color
            alpha: Transparency (0-1)
            **kwargs: Additional arguments passed to plot_trisurf
        """
        self.ax.plot_trisurf(x, y, z, color=color, alpha=alpha, **kwargs)

    def plot_quiver(self, x, y, z, u, v, w, length=1.0, normalize=True,
                    color="black", arrow_length_ratio=0.2, label=None, **kwargs):
        """
        Plot a 3D vector/arrow.
        Args:
            x, y, z: Starting point coordinates
            u, v, w: Vector components
            length: Arrow length
            normalize: Whether to normalize the vector
            color: Arrow color
            arrow_length_ratio: Ratio of arrow head to shaft
            label: Legend label
            **kwargs: Additional arguments passed to quiver
        """
        self.ax.quiver(x, y, z, u, v, w, length=length, normalize=normalize,
                       color=color, arrow_length_ratio=arrow_length_ratio,
                       label=label, **kwargs)

    # plot configuration methods

    def set_title(self, title, fontsize=12, **kwargs):
        """Set the plot title."""
        self.ax.set_title(title, fontsize=fontsize, **kwargs)

    def set_labels(self, xlabel=None, ylabel=None, zlabel=None, fontsize=10, color=AppStyles.Colors.THREE_DIM_LABEL_COLOR):
        """
        Set axis labels.
        Args:
            xlabel, ylabel, zlabel: Axis label strings (None to skip)
            fontsize: Label font size
            color: color of the axis label text
        """
        if xlabel is not None:
            self.ax.set_xlabel(xlabel, fontsize=fontsize, color=color)
        if ylabel is not None:
            self.ax.set_ylabel(ylabel, fontsize=fontsize, color=color)
        if zlabel is not None:
            self.ax.set_zlabel(zlabel, fontsize=fontsize, color=color)

    def set_limits(self, xlim=None, ylim=None, zlim=None):
        """
        Set axis limits.
        Args:
            xlim, ylim, zlim: Tuples of (min, max) or None to skip
        """
        if xlim is not None:
            self.ax.set_xlim(*xlim)
        if ylim is not None:
            self.ax.set_ylim(*ylim)
        if zlim is not None:
            self.ax.set_zlim(*zlim)

    def set_ticks(self, xticks=None, yticks=None, zticks=None):
        """
        Set axis ticks.
        Args:
            xticks, yticks, zticks: Tick arrays or None to skip
        """
        if xticks is not None:
            self.ax.set_xticks(xticks)
        if yticks is not None:
            self.ax.set_yticks(yticks)
        if zticks is not None:
            self.ax.set_zticks(zticks)

    def set_aspect_equal(self):
        """Set equal aspect ratio for all axes."""
        self.ax.set_box_aspect([1, 1, 1])

    # view control methods

    def set_view(self, elev=32, azim=-60, roll=0):
        """
        Set the 3D view angles.
        Args:
            elev: Elevation angle in degrees
            azim: Azimuthal angle in degrees
            roll: Roll angle in degrees
        """
        self.ax.view_init(elev=elev, azim=azim, roll=roll)
        self.draw()

    def view_fib(self):
        """Set view to FIB perspective (52° from vertical)."""
        self.ax.view_init(elev=30, azim=0, roll=0)  # 38 is mathematically correct, 30 looks better
        self.draw()

    def view_ccd(self):
        """Set view to CCD perspective (side view)."""
        self.ax.view_init(elev=0, azim=-90, roll=0)
        self.draw()

    def view_sem(self):
        """Set view to SEM perspective (top-down)."""
        self.ax.view_init(elev=90, azim=-90, roll=0)
        self.draw()

    # utility methods

    def clear(self):
        """Clear the plot."""
        self.ax.clear()

    def clear_and_reset(self, xlim=None, ylim=None, zlim=None, autoscale=False):
        """
        Clear the plot and reset axis properties.
        Args:
            xlim, ylim, zlim: Axis limits as tuples (min, max)
            autoscale: Whether to enable autoscaling
        """
        self.ax.clear()
        self.ax.set_autoscale_on(autoscale)
        if xlim is not None:
            self.ax.set_xlim(*xlim)
        if ylim is not None:
            self.ax.set_ylim(*ylim)
        if zlim is not None:
            self.ax.set_zlim(*zlim)

    def refresh(self):
        """Redraw the canvas (efficient for static plots)."""
        self.draw_idle()

    # high-level specialized methods
    def plot_fib_geometry(self, radius, ellipse, fib_unit,
                          sem_color=AppStyles.Colors.THREE_DIM_SEM_COLOR,
                          fib_color=AppStyles.Colors.THREE_DIM_FIB_COLOR,
                          ellipse_color=AppStyles.Colors.THREE_DIM_ELLIPSE_COLOR,
                          pane_color=AppStyles.Colors.GROUPBOX_GB,
                          pane_alpha=0.5):
        """
        Plot FIB geometry visualization with SEM, FIB vectors and ellipse.
        Args:
            radius: Sphere/circle radius for scaling
            ellipse: Nx3 array of ellipse coordinates
            fib_unit: 3-element unit vector for FIB direction
            sem_color: Color for SEM vector
            fib_color: Color for FIB vector
            ellipse_color: Color for ellipse
            pane_color: Color for the background panes (hex or named color)
            pane_alpha: Transparency of the panes (0-1)
        """
        r = radius
        # Clear and setup
        self.clear_and_reset(xlim=(-r, r), ylim=(-r, r), zlim=(-r, r))

        # Set pane colors and opacity
        self.ax.xaxis.pane.set_facecolor(pane_color)
        self.ax.yaxis.pane.set_facecolor(pane_color)
        self.ax.zaxis.pane.set_facecolor(pane_color)
        self.ax.xaxis.pane.set_alpha(pane_alpha)
        self.ax.yaxis.pane.set_alpha(pane_alpha)
        self.ax.zaxis.pane.set_alpha(pane_alpha)

        # Set pane edge colors (the borders of the 3D walls)
        self.ax.xaxis.pane.set_edgecolor(AppStyles.Colors.THREE_DIM_LABEL_COLOR)
        self.ax.yaxis.pane.set_edgecolor(AppStyles.Colors.THREE_DIM_LABEL_COLOR)
        self.ax.zaxis.pane.set_edgecolor(AppStyles.Colors.THREE_DIM_LABEL_COLOR)

        # Set axis spine colors (the actual X, Y, Z axis lines)
        self.ax.xaxis.line.set_color(AppStyles.Colors.THREE_DIM_LABEL_COLOR)
        self.ax.yaxis.line.set_color(AppStyles.Colors.THREE_DIM_LABEL_COLOR)
        self.ax.zaxis.line.set_color(AppStyles.Colors.THREE_DIM_LABEL_COLOR)

        # Plot SEM vector (pointing up in Z)
        self.plot_quiver(0, 0, 0, 0, 0, 1, length=r, normalize=True,
                         color=sem_color, arrow_length_ratio=0.2, label='SEM')
        # Plot FIB vector
        self.plot_quiver(0, 0, 0, fib_unit[0], fib_unit[1], fib_unit[2],
                         length=r, normalize=True, color=fib_color,
                         arrow_length_ratio=0.2, label='FIB')
        # Plot ellipse
        self.plot_3d_line(ellipse[:, 0], ellipse[:, 1], ellipse[:, 2],
                          color=ellipse_color, linestyle="-",
                          label='Tilted AOI Circle')
        # Configure display
        self.set_labels('X', 'Y', 'Z')
        self.set_ticks(xticks=[], yticks=[], zticks=[])
        # Refresh
        self.refresh()
