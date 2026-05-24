import argparse
from typing import Optional
from dataclasses import dataclass
from logger.logger import Logger


@dataclass
class Args:
    input_paths: list[str]
    zip_path: str
    width: int
    height: int
    first_frame: int
    simple: bool
    last_frame: int
    single: bool
    auto_zoom: bool
    stats: bool
    debug: bool
    silent: bool
    gif_path: Optional[str]
    save_dir_path: Optional[str]

    def __init__(self):
        parser = argparse.ArgumentParser(
            description="Animate a MakeSweet style GIF based on a ZIP template."
        )
        parser.add_argument("zip", type=str, help="Path to ZIP template")
        parser.add_argument(
            "--inputs",
            nargs="+",
            help="Input file paths",
            default=[],
        )
        parser.add_argument("--width", type=int, default=-1, help="Width of the output")
        parser.add_argument(
            "--height", type=int, default=-1, help="Height of the output"
        )
        parser.add_argument(
            "--first-frame", type=int, default=0, help="First frame to process"
        )
        parser.add_argument(
            "--last-frame",
            type=int,
            default=-1,
            help="Last frame to process (-1 for last frame)",
        )
        parser.add_argument(
            "--simple",
            "-s",
            action="store_true",
            default=False,
            help="Use simple rendering (faster, lower quality)",
        )
        parser.add_argument(
            "--auto-zoom",
            "-z",
            action="store_true",
            default=False,
            help="Enable auto-zoom heuristic (can, and will increase processing time)",
        )
        parser.add_argument(
            "--debug",
            "-D",
            action="store_true",
            default=False,
            help="Enable debug logging",
        )
        parser.add_argument(
            "--silent",
            "-S",
            action="store_true",
            default=False,
            help="Suppress all logging",
        )
        parser.add_argument(
            "--single",
            "-1",
            action="store_true",
            help="Process a single frame (first frame only)",
        )
        parser.add_argument(
            "--stats",
            "-t",
            action="store_true",
            help="Calculate and display statistics",
        )
        parser.add_argument(
            "--gif", type=str, default=None, help="Path to save GIF output"
        )
        parser.add_argument(
            "--save",
            type=str,
            default=None,
            help="Directory path to save separated frames",
        )

        args = parser.parse_args()

        self.zip_path = args.zip
        self.input_paths = args.inputs
        self.width = args.width
        self.height = args.height
        self.first_frame = args.first_frame
        self.last_frame = args.last_frame
        self.single = args.single
        self.stats = args.stats
        self.gif_path = args.gif
        self.save_dir_path = args.save
        self.simple = args.simple
        self.debug = args.debug
        self.silent = args.silent
        self.auto_zoom = args.auto_zoom
        self._check_args()

    def _check_args(self):
        logger = Logger(debug=self.debug, silent=self.silent)
        if self.first_frame < 0:
            logger.panic("First frame must be a non-negative integer")

        if self.single:
            self.last_frame = self.first_frame

        if self.last_frame != -1 and self.last_frame < self.first_frame:
            logger.panic("Last frame must be greater than or equal to first frame")

        if (
            not self.zip_path
            or self.zip_path.strip() == ""
            or not self.zip_path.lower().endswith(".zip")
        ):
            logger.panic(
                "ZIP template path must be a non-empty string ending with .zip"
            )

        for path in self.input_paths:
            valid_extensions = (".png", ".jpg", ".jpeg")

            if not path or path.strip() == "":
                logger.panic("Input file paths cannot be empty")

            if not any(path.lower().endswith(ext) for ext in valid_extensions):
                logger.panic(
                    f"Input file paths must have a valid image extension: {valid_extensions}"
                )

        if self.width != -1 and self.width <= 0:
            logger.panic("Width must be a positive integer or -1 for auto")

        if self.height != -1 and self.height <= 0:
            logger.panic("Height must be a positive integer or -1 for auto")

        if self.debug and self.silent:
            logger.panic("Cannot enable both debug and silent modes")

        if not self.gif_path and not self.save_dir_path:
            logger.panic("Must specify at least one output option: --gif or --save")
