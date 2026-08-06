"""Command-line entry point for the representative color extractor."""

from __future__ import print_function

import argparse
import json
import os

from PIL import Image

from .extractor import ColorExtractor, PROGRAM_NAME


def _default_domain_path():
    package_parent = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(package_parent, "configs", "color_domain.json")


def build_parser():
    parser = argparse.ArgumentParser(
        description=PROGRAM_NAME
    )
    parser.add_argument("image", help="Path to the input image.")
    parser.add_argument(
        "--domain",
        default=_default_domain_path(),
        help="Path to color_domain.json.",
    )
    parser.add_argument(
        "--clusters",
        type=int,
        default=20,
        help="Maximum RGB cluster count (default: 20).",
    )
    parser.add_argument(
        "--tolerance",
        type=float,
        default=10.0,
        help="RGB clustering tolerance (default: 10).",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=3,
        help="Number of representative groups to return (default: 3).",
    )
    parser.add_argument(
        "--alpha-threshold",
        type=int,
        default=0,
        help="Exclude pixels with alpha at or below this value (default: 0).",
    )
    parser.add_argument(
        "--include-black",
        action="store_true",
        help="Include pure black pixels instead of treating them as background.",
    )
    parser.add_argument(
        "--no-color-correction",
        action="store_true",
        help="Disable illumination and neutral-pixel color correction.",
    )
    parser.add_argument(
        "--neutral-saturation-threshold",
        type=float,
        default=0.25,
        help="Low-saturation cutoff used for neutral correction (default: 0.25).",
    )
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        extractor = ColorExtractor(args.domain)
        with Image.open(args.image) as image:
            report = extractor.analyze(
                image,
                limit=args.clusters,
                tolerance=args.tolerance,
                top_n=args.top,
                alpha_threshold=args.alpha_threshold,
                exclude_black=not args.include_black,
                apply_color_correction=not args.no_color_correction,
                neutral_saturation_threshold=(
                    args.neutral_saturation_threshold
                ),
            )
    except (OSError, TypeError, ValueError) as exc:
        parser.exit(1, "Error: {0}\n".format(exc))

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    main()
