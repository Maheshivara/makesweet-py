import os

from render.renders import Renders
from logger.logger import Logger


class FramesWriter:
    def __init__(self, renders: Renders, logger: Logger | None = None):
        self.renders = renders
        self.logger = logger if logger is not None else Logger()

    def save_frames(self, output_dir: str):
        if not os.path.exists(output_dir):
            self.logger.debug(
                f"Output directory {output_dir} does not exist, creating it"
            )
            os.makedirs(output_dir)
        frames = self.renders.get_all_renders()
        total_frames = len(frames)
        pad_size = len(str(total_frames - 1))
        self.logger.debug(f"Saving {total_frames} frames to {output_dir}")
        for i, img in enumerate(frames):
            padded_index = f"{str(i).zfill(pad_size)}"
            output_path = f"{output_dir}/frame_{padded_index}.png"
            img.save(output_path)
        self.logger.info(f"Saved frames to {output_dir}")
