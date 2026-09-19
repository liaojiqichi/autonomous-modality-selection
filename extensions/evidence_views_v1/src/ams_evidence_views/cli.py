"""Isolated build and inspection commands."""

import argparse
import json
from pathlib import Path

from .adapter import build_content
from .builder import build_package
from .models import Settings


def main() -> None:
    """Build a fresh package or print an opt-in model content preview."""
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build")
    build.add_argument("--source", type=Path, required=True)
    build.add_argument("--output", type=Path, required=True)
    build.add_argument("--pixels", type=int, default=960)
    preview = commands.add_parser("preview")
    preview.add_argument("--package", type=Path, required=True)
    preview.add_argument("--question", required=True)
    preview.add_argument(
        "--selected",
        nargs="*",
        default=[],
        choices=["CRATER_CATALOG", "OPTICAL_IMAGE", "TOPOGRAPHY"],
    )
    args = parser.parse_args()
    if args.command == "build":
        result = build_package(args.source, args.output, Settings(pixels=args.pixels))
        print(
            json.dumps(
                {"package": str(args.output), "files": len(result.files), "llm_called": False}
            )
        )
    else:
        print(json.dumps(build_content(args.package, args.question, args.selected), indent=2))
