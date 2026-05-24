from render.renders import Renders
from logger.logger import Logger


class GifCreator:
    def __init__(self, renders: Renders, logger: Logger | None = None):
        self.renders = renders
        self.logger = logger if logger is not None else Logger()

    def create_gif(self, output_path: str):
        duration = (
            int(self.renders.template.config.delay * 1000)
            * self.renders.template.config.speed_step
        )
        self.logger.debug(f"Creating GIF with duration {duration}ms per frame")
        frames = self.renders.get_all_renders()
        self.logger.debug(f"Generated {len(frames)} frames for GIF")
        if not frames:
            self.logger.panic("No frames generated for GIF")
            raise ValueError("No frames generated for GIF")  # sanity check
        frames[0].save(
            output_path,
            save_all=True,
            append_images=frames[1:],
            duration=duration,
            loop=0,
        )
        self.logger.info(f"GIF saved to {output_path}")
