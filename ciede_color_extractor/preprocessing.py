"""Image preprocessing and deterministic illumination color correction."""

from __future__ import division

from collections import OrderedDict

import numpy as np
from PIL import Image


def _validate_alpha_threshold(alpha_threshold):
    alpha_threshold = int(alpha_threshold)
    if alpha_threshold < 0 or alpha_threshold > 254:
        raise ValueError("alpha_threshold must be between 0 and 254.")
    return alpha_threshold


def _validate_saturation_threshold(threshold):
    threshold = float(threshold)
    if not np.isfinite(threshold) or threshold < 0.0 or threshold > 1.0:
        raise ValueError(
            "neutral_saturation_threshold must be between 0 and 1."
        )
    return threshold


def _gray_world_gains(channel_means):
    """Return bounded gains that move the three channel means toward neutral."""
    target = float(np.mean(channel_means))
    gains = np.ones(3, dtype=np.float64)
    nonzero = channel_means > 1e-12
    gains[nonzero] = target / channel_means[nonzero]
    return np.clip(gains, 0.67, 1.50)


def _rounded_list(values, digits=6):
    return [round(float(value), digits) for value in values]


def prepare_image_pixels(
    image,
    alpha_threshold=0,
    exclude_black=True,
    apply_color_correction=True,
    neutral_saturation_threshold=0.25,
    neutral_min_pixels=16,
):
    """Return valid RGB pixels after optional illumination correction.

    The correction combines two deterministic estimates:

    1. Gray-world gains calculated from the full valid-pixel channel
       distribution.
    2. Neutral-balance gains calculated from sufficiently bright,
       low-saturation pixels.

    The second estimate is blended in only when enough neutral candidates are
    present. Channel gains are bounded to prevent extreme correction.
    """
    if not isinstance(image, Image.Image):
        raise TypeError("image must be a PIL.Image.Image instance.")

    alpha_threshold = _validate_alpha_threshold(alpha_threshold)
    neutral_saturation_threshold = _validate_saturation_threshold(
        neutral_saturation_threshold
    )
    neutral_min_pixels = int(neutral_min_pixels)
    if neutral_min_pixels < 1:
        raise ValueError("neutral_min_pixels must be at least 1.")

    rgba = np.asarray(image.convert("RGBA"), dtype=np.uint8)
    rgb = rgba[:, :, :3]
    valid_mask = rgba[:, :, 3] > alpha_threshold
    if exclude_black:
        valid_mask &= np.any(rgb > 0, axis=2)

    valid_pixels = rgb[valid_mask].reshape((-1, 3))
    valid_count = int(valid_pixels.shape[0])
    report = OrderedDict(
        [
            ("color_correction_enabled", bool(apply_color_correction)),
            (
                "correction_method",
                "gray_world_and_low_saturation_neutral_balance",
            ),
            ("valid_pixel_count", valid_count),
            ("low_saturation_pixel_count", 0),
            ("source_channel_means", [0.0, 0.0, 0.0]),
            ("channel_gains", [1.0, 1.0, 1.0]),
        ]
    )
    if valid_count == 0:
        return valid_pixels.astype(np.uint8), report

    pixels_float = valid_pixels.astype(np.float64)
    channel_means = np.mean(pixels_float, axis=0)
    report["source_channel_means"] = _rounded_list(channel_means)

    maximum = np.max(pixels_float, axis=1)
    minimum = np.min(pixels_float, axis=1)
    saturation = np.zeros(valid_count, dtype=np.float64)
    nonzero = maximum > 0.0
    saturation[nonzero] = (
        maximum[nonzero] - minimum[nonzero]
    ) / maximum[nonzero]
    brightness = np.mean(pixels_float, axis=1)
    neutral_mask = (
        (saturation <= neutral_saturation_threshold)
        & (brightness >= 16.0)
        & (brightness <= 245.0)
    )
    neutral_count = int(np.count_nonzero(neutral_mask))
    report["low_saturation_pixel_count"] = neutral_count

    if not apply_color_correction:
        return valid_pixels.astype(np.uint8), report

    global_gains = _gray_world_gains(channel_means)
    final_gains = global_gains
    if neutral_count >= neutral_min_pixels:
        neutral_means = np.mean(pixels_float[neutral_mask], axis=0)
        neutral_gains = _gray_world_gains(neutral_means)
        neutral_ratio = neutral_count / float(valid_count)
        neutral_weight = min(0.75, max(0.25, neutral_ratio))
        final_gains = (
            (1.0 - neutral_weight) * global_gains
            + neutral_weight * neutral_gains
        )

    final_gains = np.clip(final_gains, 0.67, 1.50)
    corrected = np.rint(
        np.clip(pixels_float * final_gains.reshape((1, 3)), 0.0, 255.0)
    ).astype(np.uint8)
    report["channel_gains"] = _rounded_list(final_gains)
    return corrected, report
