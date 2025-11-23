"""
Module handles FIB geometry calculations.
"""
import numpy as np


class FIBGeometryCalculator:
    """Handles geometric calculations for FIB milling angle determination."""

    @staticmethod
    def calculate_milling_geometry(diameter, measured_minor, fib_angle_deg=52):
        """
        Calculate FIB milling geometry including ellipse and plane angle.
        Args:
            diameter: AOI circle diameter in micrometers
            measured_minor: Measured ellipse height (minor axis) in micrometers
            fib_angle_deg: FIB angle from vertical in degrees (default 52)
        Returns:
            dict containing:
                - radius: Circle radius
                - ellipse: Nx3 array of ellipse coordinates
                - fib_unit: Unit vector for FIB direction
                - plane_angle: Calculated milling angle in degrees
                - phi: Tilt angle in radians
        """
        # FIB direction vector
        fib_angle = np.radians(fib_angle_deg)
        fib = np.array([np.sin(fib_angle), 0, np.cos(fib_angle)])
        # Calculate radius and tilt angle
        r = diameter / 2
        ratio = measured_minor / diameter
        phi = np.arccos(np.clip(ratio, -1.0, 1.0))
        # Create orthonormal basis perpendicular to FIB
        fib_unit = fib / np.linalg.norm(fib)
        if abs(fib_unit[0]) < 0.9:
            arbitrary = np.array([1, 0, 0])
        else:
            arbitrary = np.array([0, 1, 0])
        e1 = np.cross(arbitrary, fib_unit)
        e1 /= np.linalg.norm(e1)
        e2 = np.cross(fib_unit, e1)
        # Generate circle in plane perpendicular to FIB
        t = np.linspace(0, 2 * np.pi, 200)
        circle = np.outer(np.cos(t) * r, e1) + np.outer(np.sin(t) * r, e2)
        # Rotation matrix using Rodrigues formula
        K = np.array([[0, -e1[2], e1[1]],
                      [e1[2], 0, -e1[0]],
                      [-e1[1], e1[0], 0]])
        R_tilt = np.eye(3) + np.sin(phi) * K + (1 - np.cos(phi)) * K.dot(K)
        # Apply rotation to get ellipse
        ellipse = (R_tilt.dot(circle.T)).T
        # Calculate ellipse normal and angle
        ellipse_normal = R_tilt.dot(fib_unit)
        angle_between = np.degrees(np.arccos(np.clip(np.dot(fib_unit, ellipse_normal), -1.0, 1.0)))
        plane_angle = 90.0 - angle_between
        return {
            'radius': r,
            'ellipse': ellipse,
            'fib_unit': fib_unit,
            'plane_angle': plane_angle,
            'phi': phi,
            'phi_deg': np.degrees(phi)
        }

    @staticmethod
    def calculate_stage_tilt(target_angle, calculated_angle):
        """
        Calculate how much to tilt the stage.
        Args:
            target_angle: Target milling angle in degrees
            calculated_angle: Calculated milling angle in degrees
        Returns:
            Stage tilt correction in degrees
        """
        return target_angle - calculated_angle
