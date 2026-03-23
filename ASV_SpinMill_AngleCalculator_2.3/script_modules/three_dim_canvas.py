"""
Module creates a class for 3D plotting.

Uses the modern ``backend_qtagg`` backend for clean PySide6
rendering.  The 3D projection is incompatible with
``constrained_layout``, so ``subplots_adjust`` is used with
fixed margins instead.
"""
import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
from PySide6.QtCore import Qt
from script_modules.app_styles import AppStyles


class ThreeDimCanvas(FigureCanvasQTAgg):
    """
    A Qt-compatible matplotlib canvas for 3D plotting.
    Provides methods for common 3D plot operations and view controls.
    """

    def __init__(self, parent=None, width=5, height=5, dpi=110):
        """
        Initialize the 3D visualization canvas.

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
        )
        self.ax = self.fig.add_subplot(111, projection="3d")
        super().__init__(self.fig)
        self.setParent(parent)
        # Disable antialiasing on figure patch to prevent
        # blurry edges at non-integer DPI scaling.
        self.fig.patch.set_antialiased(False)
        # Set widget background to match figure — prevents the
        # default grey from bleeding through during resize.
        self.setStyleSheet(
            f"background-color: {AppStyles.Colors.MAIN_BG};"
        )
        self._apply_canvas_plot_style()
        # Use subplots_adjust instead of tight_layout/constrained_layout
        # which conflict with 3D projections.
        self.fig.subplots_adjust(
            left=0.02, right=0.98, bottom=0.02, top=0.98
        )
        self.setFocusPolicy(Qt.ClickFocus)

    def _apply_canvas_plot_style(self):
        """Apply consistent dark theme styling to the 3D canvas."""
        self.ax.set_facecolor(AppStyles.Colors.MAIN_BG)

    def _apply_3d_pane_style(self, pane_color=AppStyles.Colors.GROUPBOX_BG,
                             pane_alpha=0.5):
        """Apply dark theme styling to 3D panes, edges, and spines.

        Called by high-level plot methods after ``clear_and_reset()``
        to ensure styling is re-applied consistently.

        Args:
            pane_color: Background color for the 3D wall panes.
            pane_alpha: Transparency of the panes (0-1).
        """
        # Pane face colors
        self.ax.xaxis.pane.set_facecolor(pane_color)
        self.ax.yaxis.pane.set_facecolor(pane_color)
        self.ax.zaxis.pane.set_facecolor(pane_color)
        self.ax.xaxis.pane.set_alpha(pane_alpha)
        self.ax.yaxis.pane.set_alpha(pane_alpha)
        self.ax.zaxis.pane.set_alpha(pane_alpha)
        # Pane edge colors (borders of the 3D walls)
        label_color = AppStyles.Colors.THREE_DIM_LABEL_COLOR
        self.ax.xaxis.pane.set_edgecolor(label_color)
        self.ax.yaxis.pane.set_edgecolor(label_color)
        self.ax.zaxis.pane.set_edgecolor(label_color)
        # Axis spine colors (the actual X, Y, Z axis lines)
        self.ax.xaxis.line.set_color(label_color)
        self.ax.yaxis.line.set_color(label_color)
        self.ax.zaxis.line.set_color(label_color)

    # =========================================================================
    # Basic Plotting Methods
    # =========================================================================

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

    # =========================================================================
    # Plot Configuration Methods
    # =========================================================================

    def set_title(self, title, fontsize=12, **kwargs):
        """Set the plot title."""
        self.ax.set_title(title, fontsize=fontsize, **kwargs)

    def set_labels(self, xlabel=None, ylabel=None, zlabel=None, fontsize=10,
                   color=AppStyles.Colors.THREE_DIM_LABEL_COLOR):
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

    # =========================================================================
    # View Control Methods
    # =========================================================================

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
        self.ax.view_init(elev=30, azim=0, roll=0)
        self.draw()

    def view_ccd(self):
        """Set view to CCD perspective (side view)."""
        self.ax.view_init(elev=0, azim=-90, roll=0)
        self.draw()

    def view_sem(self):
        """Set view to SEM perspective (top-down)."""
        self.ax.view_init(elev=90, azim=-90, roll=0)
        self.draw()

    # =========================================================================
    # Utility Methods
    # =========================================================================

    def clear(self):
        """Clear the plot."""
        self.ax.clear()

    def clear_and_reset(self, xlim=None, ylim=None, zlim=None, autoscale=False):
        """
        Clear the plot, reset axis properties, and re-apply styling.
        Args:
            xlim, ylim, zlim: Axis limits as tuples (min, max)
            autoscale: Whether to enable autoscaling
        """
        self.ax.clear()
        self._apply_canvas_plot_style()
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

    # =========================================================================
    # High-Level Specialized Methods
    # =========================================================================

    def plot_fib_geometry(self, radius, ellipse, fib_unit,
                          sem_color=AppStyles.Colors.THREE_DIM_SEM_COLOR,
                          fib_color=AppStyles.Colors.THREE_DIM_FIB_COLOR,
                          ellipse_color=AppStyles.Colors.THREE_DIM_ELLIPSE_COLOR,
                          pane_color=AppStyles.Colors.GROUPBOX_BG,
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
        self._apply_3d_pane_style(pane_color, pane_alpha)

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

    def plot_sem_alignment(self, current_normal, current_u, current_v, corrected_normal,
                           corrected_u, corrected_v, plane_width=800,
                           sem_color=AppStyles.Colors.THREE_DIM_SEM_COLOR,
                           fib_color=AppStyles.Colors.THREE_DIM_FIB_COLOR,
                           current_color="#FF6B6B",
                           corrected_color="#4ECDC4",
                           pane_color=AppStyles.Colors.GROUPBOX_BG,
                           pane_alpha=0.5):
        """
        Plot SEM alignment visualization with current and corrected plane orientations.
        """
        r = plane_width / 2
        # clear and setup
        self.clear_and_reset(xlim=(-r, r), ylim=(-r, r), zlim=(-r, r))
        self._apply_3d_pane_style(pane_color, pane_alpha)

        # plot SEM and FIB vectors
        self.plot_quiver(0, 0, 0, 0, 0, 1, length=r, normalize=True,
                         color=sem_color, arrow_length_ratio=0.2, label='SEM')
        fib_angle = np.radians(38)
        fib_unit = np.array([0, np.sin(fib_angle), np.cos(fib_angle)])
        self.plot_quiver(0, 0, 0, fib_unit[0], fib_unit[1], fib_unit[2],
                         length=r, normalize=True, color=fib_color,
                         arrow_length_ratio=0.2, label='FIB')
        # create and plot current plane
        half = plane_width / 2
        current_corners = np.array([
            -half * current_u - half * current_v,
            half * current_u - half * current_v,
            half * current_u + half * current_v,
            -half * current_u + half * current_v
        ])
        current_plane = Poly3DCollection([current_corners], alpha=0.2,
                                         facecolor=current_color,
                                         edgecolor=current_color, linewidth=2)
        self.ax.add_collection3d(current_plane)
        self.plot_quiver(0, 0, 0, current_normal[0], current_normal[1], current_normal[2],
                         length=r * 0.8, normalize=True, color=current_color,
                         arrow_length_ratio=0.2, label='Current Plane', linewidth=2)
        # Create and plot corrected plane
        corrected_corners = np.array([
            -half * corrected_u - half * corrected_v,
            half * corrected_u - half * corrected_v,
            half * corrected_u + half * corrected_v,
            -half * corrected_u + half * corrected_v
        ])
        corrected_plane = Poly3DCollection([corrected_corners], alpha=0.2,
                                           facecolor=corrected_color,
                                           edgecolor=corrected_color, linewidth=2)
        self.ax.add_collection3d(corrected_plane)
        self.plot_quiver(0, 0, 0, corrected_normal[0], corrected_normal[1], corrected_normal[2],
                         length=r * 0.8, normalize=True, color=corrected_color,
                         arrow_length_ratio=0.2, label='Corrected Plane', linewidth=2)
        # configure display
        self.set_labels('X', 'Y', 'Z')
        self.set_ticks(xticks=[], yticks=[], zticks=[])
        self.refresh()