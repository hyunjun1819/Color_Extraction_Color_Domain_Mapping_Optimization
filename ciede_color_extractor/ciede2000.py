"""CIE color conversion and CIEDE2000 color-difference calculations.

The CIEDE2000 implementation follows the equations described in:

    G. Sharma, W. Wu, and E. N. Dalal,
    "The CIEDE2000 Color-Difference Formula: Implementation Notes,
    Supplementary Test Data, and Mathematical Observations,"
    Color Research and Application, 30(1), 21-30, 2005.

No source code from the reference implementation is included here.
"""

from __future__ import division

import math

import numpy as np
from skimage import color as skimage_color


_D65_WHITE = (0.95047, 1.00000, 1.08883)
_CIE_25_POW_7 = 25.0 ** 7


def _three_finite_values(values, value_name):
    """Return three finite floats or raise a descriptive exception."""
    try:
        if len(values) != 3:
            raise ValueError
        result = tuple(float(value) for value in values)
    except (TypeError, ValueError):
        raise ValueError(
            "{0} must contain exactly three numeric values.".format(value_name)
        )

    if not all(math.isfinite(value) for value in result):
        raise ValueError("{0} values must be finite.".format(value_name))
    return result


def _srgb_channel_to_linear(channel):
    """Convert an sRGB channel in the range 0..1 to linear RGB."""
    if channel <= 0.04045:
        return channel / 12.92
    return ((channel + 0.055) / 1.055) ** 2.4


def _xyz_pivot(value):
    """Apply the CIELAB XYZ pivot function."""
    delta = 6.0 / 29.0
    if value > delta ** 3:
        return value ** (1.0 / 3.0)
    return value / (3.0 * delta ** 2) + 4.0 / 29.0


def rgb_to_lab(rgb):
    """Convert an sRGB color with 0..255 channels to CIELAB using D65.

    Args:
        rgb: Three numeric channel values in R, G, B order.

    Returns:
        A ``(L*, a*, b*)`` tuple.
    """
    red, green, blue = _three_finite_values(rgb, "rgb")
    if any(channel < 0.0 or channel > 255.0 for channel in (red, green, blue)):
        raise ValueError("rgb channel values must be between 0 and 255.")

    rgb_array = np.asarray(
        [[[red, green, blue]]],
        dtype=np.float64,
    ) / 255.0
    lab = skimage_color.rgb2lab(
        rgb_array,
        illuminant="D65",
        observer="2",
    )[0, 0]
    return tuple(float(value) for value in lab)


def _hue_angle_degrees(b_value, a_prime):
    """Return a hue angle in degrees in the range 0 <= h < 360."""
    if a_prime == 0.0 and b_value == 0.0:
        return 0.0
    return math.degrees(math.atan2(b_value, a_prime)) % 360.0


def delta_e_ciede2000(lab1, lab2, k_l=1.0, k_c=1.0, k_h=1.0):
    """Calculate the CIEDE2000 color difference between two CIELAB colors.

    The default parametric weighting factors are appropriate for the
    reference viewing condition described by the CIEDE2000 standard.

    Args:
        lab1: Reference ``(L*, a*, b*)`` color.
        lab2: Sample ``(L*, a*, b*)`` color.
        k_l: Lightness weighting factor.
        k_c: Chroma weighting factor.
        k_h: Hue weighting factor.

    Returns:
        The non-negative Delta E 2000 value as a float.
    """
    l1, a1, b1 = _three_finite_values(lab1, "lab1")
    l2, a2, b2 = _three_finite_values(lab2, "lab2")
    k_l = float(k_l)
    k_c = float(k_c)
    k_h = float(k_h)
    if not all(
        math.isfinite(value) and value > 0.0 for value in (k_l, k_c, k_h)
    ):
        raise ValueError("k_l, k_c, and k_h must be positive finite values.")

    c1 = math.hypot(a1, b1)
    c2 = math.hypot(a2, b2)
    mean_c = (c1 + c2) / 2.0
    mean_c_pow_7 = mean_c ** 7
    g_factor = 0.5 * (
        1.0
        - math.sqrt(mean_c_pow_7 / (mean_c_pow_7 + _CIE_25_POW_7))
    )

    a1_prime = (1.0 + g_factor) * a1
    a2_prime = (1.0 + g_factor) * a2
    c1_prime = math.hypot(a1_prime, b1)
    c2_prime = math.hypot(a2_prime, b2)
    h1_prime = _hue_angle_degrees(b1, a1_prime)
    h2_prime = _hue_angle_degrees(b2, a2_prime)

    delta_l_prime = l2 - l1
    delta_c_prime = c2_prime - c1_prime

    if c1_prime * c2_prime == 0.0:
        delta_h_prime = 0.0
    else:
        raw_hue_difference = h2_prime - h1_prime
        if abs(raw_hue_difference) <= 180.0:
            delta_h_prime = raw_hue_difference
        elif raw_hue_difference > 180.0:
            delta_h_prime = raw_hue_difference - 360.0
        else:
            delta_h_prime = raw_hue_difference + 360.0

    delta_h_capital = (
        2.0
        * math.sqrt(c1_prime * c2_prime)
        * math.sin(math.radians(delta_h_prime / 2.0))
    )

    mean_l_prime = (l1 + l2) / 2.0
    mean_c_prime = (c1_prime + c2_prime) / 2.0

    if c1_prime * c2_prime == 0.0:
        mean_h_prime = h1_prime + h2_prime
    elif abs(h1_prime - h2_prime) <= 180.0:
        mean_h_prime = (h1_prime + h2_prime) / 2.0
    elif h1_prime + h2_prime < 360.0:
        mean_h_prime = (h1_prime + h2_prime + 360.0) / 2.0
    else:
        mean_h_prime = (h1_prime + h2_prime - 360.0) / 2.0

    t_factor = (
        1.0
        - 0.17 * math.cos(math.radians(mean_h_prime - 30.0))
        + 0.24 * math.cos(math.radians(2.0 * mean_h_prime))
        + 0.32 * math.cos(math.radians(3.0 * mean_h_prime + 6.0))
        - 0.20 * math.cos(math.radians(4.0 * mean_h_prime - 63.0))
    )

    delta_theta = 30.0 * math.exp(
        -((mean_h_prime - 275.0) / 25.0) ** 2
    )
    mean_c_prime_pow_7 = mean_c_prime ** 7
    r_c = 2.0 * math.sqrt(
        mean_c_prime_pow_7
        / (mean_c_prime_pow_7 + _CIE_25_POW_7)
    )

    l_offset = mean_l_prime - 50.0
    s_l = 1.0 + (0.015 * l_offset ** 2) / math.sqrt(
        20.0 + l_offset ** 2
    )
    s_c = 1.0 + 0.045 * mean_c_prime
    s_h = 1.0 + 0.015 * mean_c_prime * t_factor
    r_t = -math.sin(math.radians(2.0 * delta_theta)) * r_c

    l_term = delta_l_prime / (k_l * s_l)
    c_term = delta_c_prime / (k_c * s_c)
    h_term = delta_h_capital / (k_h * s_h)
    squared_distance = (
        l_term ** 2
        + c_term ** 2
        + h_term ** 2
        + r_t * c_term * h_term
    )
    return math.sqrt(max(0.0, squared_distance))
