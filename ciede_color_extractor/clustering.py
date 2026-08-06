"""Representative-color extraction using NumPy, Pillow, and extcolors."""

from __future__ import division

from collections import Counter
import math

import extcolors
import numpy as np
from PIL import Image

from .preprocessing import prepare_image_pixels


def _validate_rgb(rgb):
    try:
        if len(rgb) != 3:
            raise ValueError
        values = tuple(int(value) for value in rgb)
    except (TypeError, ValueError):
        raise ValueError("RGB colors must contain exactly three integers.")
    if any(value < 0 or value > 255 for value in values):
        raise ValueError("RGB channel values must be between 0 and 255.")
    return values


class ColorCluster(object):
    """A weighted RGB cluster with an incrementally updated centroid."""

    def __init__(self, rgb, count=1):
        rgb = _validate_rgb(rgb)
        count = int(count)
        if count <= 0:
            raise ValueError("Cluster counts must be positive.")
        self._sum = [float(channel * count) for channel in rgb]
        self.count = count

    @property
    def average_color(self):
        return tuple(
            max(0, min(255, int(round(total / self.count))))
            for total in self._sum
        )

    def add(self, rgb, count=1):
        rgb = _validate_rgb(rgb)
        count = int(count)
        if count <= 0:
            raise ValueError("Cluster counts must be positive.")
        for index, channel in enumerate(rgb):
            self._sum[index] += channel * count
        self.count += count


def rgb_euclidean_distance(rgb1, rgb2):
    """Return Euclidean distance in the 8-bit RGB cube."""
    rgb1 = _validate_rgb(rgb1)
    rgb2 = _validate_rgb(rgb2)
    return math.sqrt(
        sum((left - right) ** 2 for left, right in zip(rgb1, rgb2))
    )


def image_color_counts(image, alpha_threshold=0, exclude_black=True):
    """Count visible RGB colors in a Pillow image.

    Pixels whose alpha value is less than or equal to ``alpha_threshold`` are
    excluded. With the default threshold, fully transparent pixels are
    excluded regardless of the RGB values stored beneath their alpha channel.
    """
    if not isinstance(image, Image.Image):
        raise TypeError("image must be a PIL.Image.Image instance.")
    alpha_threshold = int(alpha_threshold)
    if alpha_threshold < 0 or alpha_threshold > 254:
        raise ValueError("alpha_threshold must be between 0 and 254.")

    rgba_image = image.convert("RGBA")
    if hasattr(rgba_image, "get_flattened_data"):
        pixels = rgba_image.get_flattened_data()
    else:
        # Compatibility with Pillow versions released before 12.1.
        pixels = rgba_image.getdata()
    return Counter(
        (red, green, blue)
        for red, green, blue, alpha in pixels
        if alpha > alpha_threshold
        and (not exclude_black or (red, green, blue) != (0, 0, 0))
    )


def cluster_color_counts(color_counts, tolerance=10.0, limit=20):
    """Cluster weighted RGB colors into a deterministic representative set.

    Colors are processed by descending pixel frequency and then RGB tuple,
    which makes the output independent of image scan order.
    """
    tolerance = float(tolerance)
    limit = int(limit)
    if not math.isfinite(tolerance) or tolerance < 0.0:
        raise ValueError("tolerance must be a non-negative finite value.")
    if limit < 1:
        raise ValueError("limit must be at least 1.")

    weighted_colors = []
    for rgb, count in color_counts.items():
        rgb = _validate_rgb(rgb)
        count = int(count)
        if count <= 0:
            raise ValueError("Color counts must be positive.")
        weighted_colors.append((rgb, count))
    weighted_colors.sort(key=lambda item: (-item[1], item[0]))

    clusters = []
    for rgb, count in weighted_colors:
        closest_cluster = None
        closest_distance = float("inf")
        for cluster in clusters:
            distance = rgb_euclidean_distance(rgb, cluster.average_color)
            if distance < closest_distance:
                closest_cluster = cluster
                closest_distance = distance

        if closest_cluster is not None and (
            closest_distance <= tolerance or len(clusters) >= limit
        ):
            closest_cluster.add(rgb, count)
        else:
            clusters.append(ColorCluster(rgb, count))

    results = [
        (cluster.average_color, cluster.count) for cluster in clusters
    ]
    results.sort(key=lambda item: (-item[1], item[0]))
    return results


def extract_dominant_rgb(
    image,
    tolerance=10.0,
    limit=20,
    alpha_threshold=0,
    exclude_black=True,
    apply_color_correction=True,
    neutral_saturation_threshold=0.25,
    neutral_min_pixels=16,
):
    """Return representative RGB clusters, pixel count, and preprocessing data.

    Valid pixels are corrected first and quantized to a bounded Pillow palette.
    ``extcolors`` then extracts perceptually compressed colors from that image.
    If more than ``limit`` colors remain, the smaller colors are assigned to
    the nearest representative cluster so every valid pixel remains included
    in the final percentage calculation.
    """
    tolerance = float(tolerance)
    limit = int(limit)
    if not math.isfinite(tolerance) or tolerance < 0.0:
        raise ValueError("tolerance must be a non-negative finite value.")
    if limit < 1:
        raise ValueError("limit must be at least 1.")

    pixels, preprocessing_report = prepare_image_pixels(
        image,
        alpha_threshold=alpha_threshold,
        exclude_black=exclude_black,
        apply_color_correction=apply_color_correction,
        neutral_saturation_threshold=neutral_saturation_threshold,
        neutral_min_pixels=neutral_min_pixels,
    )
    total_pixels = int(pixels.shape[0])
    preprocessing_report["representative_color_backend"] = "extcolors"
    if total_pixels == 0:
        preprocessing_report["quantized_palette_size"] = 0
        return [], 0, preprocessing_report

    palette_size = min(256, max(64, limit * 4))
    packed_image = Image.fromarray(
        pixels.reshape((total_pixels, 1, 3)),
        mode="RGB",
    )
    median_cut = getattr(Image, "MEDIANCUT", 0)
    no_dither = getattr(Image, "NONE", 0)
    quantized_image = packed_image.quantize(
        colors=palette_size,
        method=median_cut,
        dither=no_dither,
    ).convert("RGB")

    extracted, unused_pixel_count = extcolors.extract_from_image(
        quantized_image,
        tolerance=tolerance,
        limit=None,
    )
    del unused_pixel_count
    counts = Counter(
        {
            tuple(int(channel) for channel in rgb): int(count)
            for rgb, count in extracted
        }
    )
    clusters = cluster_color_counts(
        counts,
        tolerance=0.0,
        limit=limit,
    )
    preprocessing_report["quantized_palette_size"] = min(
        palette_size,
        len(counts),
    )
    return clusters, total_pixels, preprocessing_report
