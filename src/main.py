from time import time
import os

from args import Args
from render.renders import Renders
from render.render import RenderQuality
from reader.template import Template
from reader.input import Input
from writer.gif import GifCreator
from writer.frames import FramesWriter
from logger.logger import Logger


def main():
    args = Args()

    start_time = time()

    logger = Logger(debug=args.debug, silent=args.silent)
    try:
        template_path = os.path.abspath(args.zip_path)
        template = Template(template_path)
        loaded_template_time = time()

        logger.info(
            f"Loaded {os.path.basename(template_path)} template with {template.config.frames} frames"
        )

        inputs = [
            Input(os.path.abspath(path), i + 1)
            for i, path in enumerate(args.input_paths)
        ]
        loaded_inputs_time = time()

        start_frame = args.first_frame
        end_frame = (
            args.last_frame if args.last_frame >= 0 else template.config.frames - 1
        )

        if start_frame > end_frame:
            logger.panic("First frame cannot be greater than last frame")

        removed_frames: list[int] = []
        for i in range(0, start_frame):
            removed_frames.append(i)
            template.remove_frame(i)
        for i in range(end_frame + 1, template.config.frames):
            removed_frames.append(i)
            template.remove_frame(i)
        logger.debug(
            f"Removed frames outside of range [{start_frame}, {end_frame}]; removed frames: {removed_frames}"
        )
        removed_frames_time = time()

        renders = Renders(
            template,
            inputs,
            quality=RenderQuality.HIGH if not args.simple else RenderQuality.SIMPLE,
            size=(args.width, args.height),
            logger=logger,
        )
        constructed_renders_time = time()

        if args.auto_zoom:
            renders.auto_zoom()

        auto_zoom_time = time()

        if args.gif_path:
            gif_path = os.path.abspath(args.gif_path)
            gif_creator = GifCreator(renders, logger=logger)
            gif_creator.create_gif(gif_path)
        created_gif_time = time()

        if args.save_dir_path:
            frames_dir = os.path.abspath(args.save_dir_path)
            os.makedirs(frames_dir, exist_ok=True)
            frames_writer = FramesWriter(renders, logger=logger)
            frames_writer.save_frames(frames_dir)
        saved_frames_time = time()

        if args.stats:
            end_time = time()
            total_time = end_time - start_time
            logger.info(f"Total processing time: {total_time:.2f} seconds")
            logger.info(
                f"Time to load template: {loaded_template_time - start_time:.2f} seconds"
            )
            logger.info(
                f"Time to load inputs: {loaded_inputs_time - loaded_template_time:.2f} seconds"
            )
            if removed_frames:
                logger.info(
                    f"Time to remove frames: {removed_frames_time - loaded_inputs_time:.2f} seconds"
                )
            logger.info(
                f"Time to construct renders: {constructed_renders_time - removed_frames_time:.2f} seconds"
            )
            if args.auto_zoom:
                logger.info(
                    f"Time for auto-zoom: {auto_zoom_time - constructed_renders_time:.2f} seconds"
                )
            if args.gif_path:
                logger.info(
                    f"Time to create GIF: {created_gif_time - auto_zoom_time:.2f} seconds"
                )
            if args.save_dir_path:
                logger.info(
                    f"Time to save frames: {saved_frames_time - created_gif_time:.2f} seconds"
                )
            logger.info(f"Peak render cache size: {renders.peak_cache_count}")

    except Exception as e:
        logger.panic(f"An error occurred: {e}")


if __name__ == "__main__":
    main()
