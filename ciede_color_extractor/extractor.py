"""Representative color extraction and CIEDE2000 domain matching."""

from __future__ import division

from collections import OrderedDict
import json
import math
import os

from .ciede2000 import delta_e_ciede2000, rgb_to_lab
from .clustering import extract_dominant_rgb


_GROUP_ALIASES = {
    "ORENGE": "ORANGE",
}

PROGRAM_NAME = (
    "Color Extraction-based Color Domain Mapping Optimization Program"
    "(색상 추출 기반 컬러 도메인 매핑 최적화 프로그램)"
)


def _normalize_group_name(group_name):
    normalized = " ".join(str(group_name).strip().upper().split())
    if not normalized:
        raise ValueError("Color group names must not be empty.")
    return _GROUP_ALIASES.get(normalized, normalized)


def _validate_domain_rgb(rgb, color_name):
    try:
        if len(rgb) != 3:
            raise ValueError
        values = tuple(int(value) for value in rgb)
    except (TypeError, ValueError):
        raise ValueError(
            "Color '{0}' must define three RGB integers.".format(color_name)
        )
    if any(value < 0 or value > 255 for value in values):
        raise ValueError(
            "Color '{0}' has an RGB value outside 0..255.".format(color_name)
        )
    return values


class ColorExtractor(object):
    """Extract representative image colors and map them with CIEDE2000."""

    def __init__(self, color_domain_path):
        self.color_domain_path = os.path.abspath(color_domain_path)
        self._domain = self._load_color_domain(self.color_domain_path)

    @staticmethod
    def _load_color_domain(color_domain_path):
        try:
            with open(color_domain_path, "r", encoding="utf-8") as stream:
                raw_domain = json.load(
                    stream,
                    object_pairs_hook=OrderedDict,
                )
        except OSError as exc:
            raise ValueError(
                "Unable to read color domain '{0}': {1}".format(
                    color_domain_path,
                    exc,
                )
            )
        except ValueError as exc:
            raise ValueError(
                "Color domain is not valid JSON: {0}".format(exc)
            )

        if not isinstance(raw_domain, dict) or not raw_domain:
            raise ValueError("Color domain must be a non-empty JSON object.")

        domain = []
        for color_name, record in raw_domain.items():
            if not isinstance(record, dict):
                raise ValueError(
                    "Color '{0}' must contain an object.".format(color_name)
                )
            if "rgb" not in record:
                raise ValueError(
                    "Color '{0}' is missing its RGB value.".format(color_name)
                )
            rgb = _validate_domain_rgb(record["rgb"], color_name)
            group = _normalize_group_name(record.get("group", color_name))
            domain.append(
                {
                    "name": str(color_name),
                    "group": group,
                    "rgb": rgb,
                    "lab": rgb_to_lab(rgb),
                }
            )
        return domain

    @property
    def domain_size(self):
        """Return the number of named colors in the loaded domain."""
        return len(self._domain)

    def match_color(self, rgb):
        """Find the nearest domain color using neutral priority and CIEDE2000."""
        input_lab = rgb_to_lab(rgb)
        lightness, a_value, b_value = input_lab
        chroma = math.hypot(a_value, b_value)
        neutral_priority_group = None
        if lightness <= 22.0 and chroma <= 18.0:
            neutral_priority_group = "BLACK"
        elif lightness >= 88.0 and chroma <= 14.0:
            neutral_priority_group = "WHITE"
        elif chroma <= 12.0:
            neutral_priority_group = "GREY"

        candidates = self._domain
        if neutral_priority_group is not None:
            neutral_candidates = [
                entry
                for entry in self._domain
                if entry["group"] == neutral_priority_group
            ]
            if neutral_candidates:
                candidates = neutral_candidates

        best_entry = None
        best_distance = float("inf")
        for entry in candidates:
            distance = delta_e_ciede2000(input_lab, entry["lab"])
            if distance < best_distance:
                best_entry = entry
                best_distance = distance

        return OrderedDict(
            [
                ("name", best_entry["name"]),
                ("group", best_entry["group"]),
                ("domain_rgb", list(best_entry["rgb"])),
                ("delta_e_2000", round(best_distance, 6)),
                ("neutral_priority_group", neutral_priority_group),
            ]
        )

    @staticmethod
    def _validate_analysis_options(top_n):
        top_n = int(top_n)
        if top_n < 1:
            raise ValueError("top_n must be at least 1.")
        return top_n

    def analyze(
        self,
        image,
        limit=20,
        tolerance=10.0,
        top_n=3,
        alpha_threshold=0,
        exclude_black=True,
        apply_color_correction=True,
        neutral_saturation_threshold=0.25,
        neutral_min_pixels=16,
    ):
        """Return a detailed representative-color analysis report."""
        top_n = self._validate_analysis_options(top_n)
        clusters, total_pixels, preprocessing_report = extract_dominant_rgb(
            image,
            tolerance=tolerance,
            limit=limit,
            alpha_threshold=alpha_threshold,
            exclude_black=exclude_black,
            apply_color_correction=apply_color_correction,
            neutral_saturation_threshold=neutral_saturation_threshold,
            neutral_min_pixels=neutral_min_pixels,
        )

        report = OrderedDict(
            [
                ("program_name", PROGRAM_NAME),
                ("method", "CIEDE2000"),
                ("color_space", "CIE Lab (D65/2-degree)"),
                ("domain_color_count", self.domain_size),
                ("visible_pixel_count", total_pixels),
                ("cluster_count", len(clusters)),
                ("preprocessing", preprocessing_report),
                ("top_groups", []),
                ("clusters", []),
            ]
        )
        if total_pixels == 0:
            return report

        group_counts = {}
        cluster_records = []
        for rgb, count in clusters:
            match = self.match_color(rgb)
            group = match["group"]
            group_counts[group] = group_counts.get(group, 0) + count
            cluster_records.append(
                OrderedDict(
                    [
                        ("rgb", list(rgb)),
                        ("pixel_count", count),
                        (
                            "percentage",
                            round(count / total_pixels * 100.0, 2),
                        ),
                        ("matched_color", match["name"]),
                        ("group", group),
                        ("delta_e_2000", match["delta_e_2000"]),
                        (
                            "neutral_priority_group",
                            match["neutral_priority_group"],
                        ),
                    ]
                )
            )

        sorted_groups = sorted(
            group_counts.items(),
            key=lambda item: (-item[1], item[0]),
        )
        top_groups = [
            OrderedDict(
                [
                    ("color", group),
                    ("percentage", round(count / total_pixels * 100.0, 2)),
                ]
            )
            for group, count in sorted_groups[:top_n]
        ]
        report["top_groups"] = top_groups
        report["clusters"] = cluster_records
        return report

    def extract_colors(
        self,
        image,
        limit=20,
        tolerance=10.0,
        top_n=3,
        alpha_threshold=0,
        exclude_black=True,
        apply_color_correction=True,
        neutral_saturation_threshold=0.25,
        neutral_min_pixels=16,
    ):
        """Return the top representative groups for compatibility."""
        report = self.analyze(
            image,
            limit=limit,
            tolerance=tolerance,
            top_n=top_n,
            alpha_threshold=alpha_threshold,
            exclude_black=exclude_black,
            apply_color_correction=apply_color_correction,
            neutral_saturation_threshold=neutral_saturation_threshold,
            neutral_min_pixels=neutral_min_pixels,
        )
        return report["top_groups"]
