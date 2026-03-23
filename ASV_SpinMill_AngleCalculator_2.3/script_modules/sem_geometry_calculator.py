"""
Module handles SEM geometry calculations for sample alignment.
"""
import numpy as np


class SEMGeometryCalculator:
    """Handles geometric calculations for SEM sample alignment."""

    @staticmethod
    def rotation_matrix_z(angle_rad):
        """
        Rotation matrix around Z axis (clockwise when viewed from +Z).

        Args:
            angle_rad: Rotation angle in radians

        Returns:
            3x3 rotation matrix
        """
        return np.array([
            [np.cos(angle_rad), -np.sin(angle_rad), 0],
            [np.sin(angle_rad), np.cos(angle_rad), 0],
            [0, 0, 1]
        ])

    @staticmethod
    def rotation_matrix_x(angle_rad):
        """
        Rotation matrix around X axis (counter-clockwise when viewed from +X).

        Args:
            angle_rad: Rotation angle in radians

        Returns:
            3x3 rotation matrix
        """
        return np.array([
            [1, 0, 0],
            [0, np.cos(angle_rad), -np.sin(angle_rad)],
            [0, np.sin(angle_rad), np.cos(angle_rad)]
        ])

    @staticmethod
    def rotation_matrix_fib_axis(angle_rad):
        """
        Rotation matrix around FIB axis (38° from Y axis in Y-Z plane).
        This gives 52° from Z axis (SEM beam).
        FIB direction: (0, cos(38°), sin(38°))

        Args:
            angle_rad: Rotation angle in radians

        Returns:
            3x3 rotation matrix
        """
        fib_angle = np.radians(38)
        axis = np.array([0, np.cos(fib_angle), np.sin(fib_angle)])
        axis = axis / np.linalg.norm(axis)

        # Rodrigues' rotation formula
        K = np.array([
            [0, -axis[2], axis[1]],
            [axis[2], 0, -axis[0]],
            [-axis[1], axis[0], 0]
        ])

        R = np.eye(3) + np.sin(angle_rad) * K + (1 - np.cos(angle_rad)) * K @ K
        return R

    @staticmethod
    def calculate_sample_normal_from_fib_metadata(stage_r_rad, stage_t_rad,
                                                  scan_rotation_rad, milling_angle_deg):
        """
        Calculate the true sample surface normal from FIB metadata.

        The milling angle is the angle between the sample surface normal
        and the FIB beam direction. We know:
        1. The FIB beam direction in global coordinates
        2. The sample was rotated/tilted (R, T, Scan) to achieve this milling angle
        3. Therefore, we can back-calculate what the surface normal must be

        Args:
            stage_r_rad: Stage rotation in radians
            stage_t_rad: Stage tilt in radians
            scan_rotation_rad: Scan rotation in radians
            milling_angle_deg: Measured milling angle in degrees

        Returns:
            sample_normal: 3D unit vector of sample surface normal in global coordinates
        """
        # FIB beam direction in global coordinates
        # 38° from Y axis = 52° from Z axis (SEM)
        fib_angle = np.radians(38)
        fib_direction = np.array([0, np.cos(fib_angle), np.sin(fib_angle)])
        fib_direction = fib_direction / np.linalg.norm(fib_direction)

        # Build the transformation matrix (what was applied to the sample)
        R_r = SEMGeometryCalculator.rotation_matrix_z(stage_r_rad)
        R_t = SEMGeometryCalculator.rotation_matrix_x(stage_t_rad)
        R_scan = SEMGeometryCalculator.rotation_matrix_fib_axis(scan_rotation_rad)

        # Combined transformation: Scan is applied last
        R_total = R_scan @ R_t @ R_r

        # We need to solve: angle(R_total @ n_initial, fib_direction) = milling_angle
        # This gives us: n_initial · (R_total^T @ fib_direction) = cos(milling_angle)

        target_dot_product = np.cos(np.radians(milling_angle_deg))
        transformed_fib = R_total.T @ fib_direction

        z_axis = np.array([0, 0, 1])

        # Find the point on the constraint cone closest to +Z
        # The cone has axis transformed_fib and half-angle = arccos(target_dot_product)

        # Unit vector from transformed_fib toward +Z (in the plane)
        v_to_z = z_axis - np.dot(z_axis, transformed_fib) * transformed_fib
        v_to_z_norm = np.linalg.norm(v_to_z)

        if v_to_z_norm > 1e-10:
            v_to_z = v_to_z / v_to_z_norm
        else:
            # transformed_fib is parallel to +Z, any perpendicular direction works
            v_to_z = np.array([1, 0, 0])

        # The initial normal that's closest to +Z and satisfies the constraint
        sin_component = np.sqrt(1 - target_dot_product ** 2)
        n_initial_calculated = target_dot_product * transformed_fib + sin_component * v_to_z
        n_initial_calculated = n_initial_calculated / np.linalg.norm(n_initial_calculated)

        return n_initial_calculated

    @staticmethod
    def calculate_sem_alignment_corrections(sample_normal, scan_rotation_rad):
        """
        Calculate Stage R and T corrections to align sample normal with SEM (+Z).

        Args:
            sample_normal: True sample surface normal (before any transformations)
            scan_rotation_rad: Scan rotation in radians (kept constant)

        Returns:
            dict containing:
                - target_r_rad: Required Stage R in radians (0.0001 rad precision)
                - target_t_rad: Required Stage T in radians (0.0001 rad precision)
                - target_r_deg: Required Stage R in degrees (0.01° display precision)
                - target_t_deg: Required Stage T in degrees (0.01° display precision)
                - final_normal: Achieved normal vector
                - deviation_deg: Deviation from perfect +Z alignment in degrees
        """
        # Goal: Find R and T such that R_scan @ R_t @ R_r @ sample_normal = [0, 0, 1]
        # This means: R_t @ R_r @ sample_normal = R_scan^(-1) @ [0, 0, 1]

        target_sem = np.array([0, 0, 1])

        # Apply inverse of scan rotation to find what we need after R and T
        R_scan_inv = SEMGeometryCalculator.rotation_matrix_fib_axis(-scan_rotation_rad)
        target_after_rt = R_scan_inv @ target_sem

        # Now we need: R_t @ R_r @ sample_normal = target_after_rt
        # We want the X component after R_z to equal target_after_rt[0]
        # So: sample_normal[0]*cos(R) - sample_normal[1]*sin(R) = target_after_rt[0]

        nx, ny, nz = sample_normal
        tx, ty, tz = target_after_rt

        # Solve: nx*cos(R) - ny*sin(R) = tx
        A = nx
        B = -ny
        C = tx

        magnitude = np.sqrt(A ** 2 + B ** 2)

        # Clamp if no exact solution exists
        if abs(C) > magnitude:
            C = np.clip(C, -magnitude, magnitude)

        base_angle = np.arctan2(B, A)
        offset_angle = np.arccos(C / magnitude)

        # Two possible solutions
        R_solution_1 = base_angle + offset_angle
        R_solution_2 = base_angle - offset_angle

        # Try both and see which gives a valid T solution
        solutions = []

        for R_candidate in [R_solution_1, R_solution_2]:
            R_r = SEMGeometryCalculator.rotation_matrix_z(R_candidate)
            after_r = R_r @ sample_normal

            # Solve for T using 2D rotation in YZ plane
            T_candidate = np.arctan2(target_after_rt[2], target_after_rt[1]) - \
                          np.arctan2(after_r[2], after_r[1])

            # Verify this solution
            R_t = SEMGeometryCalculator.rotation_matrix_x(T_candidate)
            result = R_t @ after_r

            error = np.linalg.norm(result - target_after_rt)
            solutions.append((R_candidate, T_candidate, error, result))

        # Choose the solution with smallest error
        best_idx = np.argmin([s[2] for s in solutions])
        target_r_rad, target_t_rad, error, result = solutions[best_idx]

        # Round to 0.0001 radian precision for internal calculations
        # This gives us ~0.0057° precision internally
        target_r_rad_rounded = np.round(target_r_rad, 4)
        target_t_rad_rounded = np.round(target_t_rad, 4)

        # Convert to degrees with 0.01° display precision for user
        target_r_deg = np.round(np.degrees(target_r_rad_rounded), 2)
        target_t_deg = np.round(np.degrees(target_t_rad_rounded), 2)

        # Verify rounded solution
        R_r_rounded = SEMGeometryCalculator.rotation_matrix_z(target_r_rad_rounded)
        R_t_rounded = SEMGeometryCalculator.rotation_matrix_x(target_t_rad_rounded)
        result_rounded = R_t_rounded @ R_r_rounded @ sample_normal

        # Final verification: Apply scan rotation
        R_scan = SEMGeometryCalculator.rotation_matrix_fib_axis(scan_rotation_rad)
        final_result_rounded = R_scan @ result_rounded

        deviation_deg = np.degrees(np.arccos(np.clip(final_result_rounded[2], -1, 1)))

        return {
            'target_r_rad': target_r_rad_rounded,
            'target_t_rad': target_t_rad_rounded,
            'target_r_deg': target_r_deg,
            'target_t_deg': target_t_deg,
            'final_normal': final_result_rounded,
            'deviation_deg': deviation_deg
        }

    @staticmethod
    def calculate_current_orientation(sample_normal, stage_r_rad, stage_t_rad, scan_rotation_rad):
        """
        Calculate the current sample orientation given stage positions.

        Args:
            sample_normal: True sample surface normal (before transformations)
            stage_r_rad: Current Stage R in radians
            stage_t_rad: Current Stage T in radians
            scan_rotation_rad: Scan rotation in radians

        Returns:
            dict containing:
                - current_normal: Current normal vector
                - current_u: Current U basis vector
                - current_v: Current V basis vector
                - deviation_deg: Current deviation from +Z in degrees
        """
        R_r = SEMGeometryCalculator.rotation_matrix_z(stage_r_rad)
        R_t = SEMGeometryCalculator.rotation_matrix_x(stage_t_rad)
        R_scan = SEMGeometryCalculator.rotation_matrix_fib_axis(scan_rotation_rad)
        R_total = R_scan @ R_t @ R_r

        current_normal = R_total @ sample_normal
        current_u = R_total @ np.array([1, 0, 0])
        current_v = R_total @ np.array([0, 1, 0])

        deviation_deg = np.degrees(np.arccos(np.clip(current_normal[2], -1, 1)))

        return {
            'current_normal': current_normal,
            'current_u': current_u,
            'current_v': current_v,
            'deviation_deg': deviation_deg
        }