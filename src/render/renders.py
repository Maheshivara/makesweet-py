from typing import List, Dict
from PIL.Image import Image
import threading

from render.render import Render as FrameRenderer, RenderQuality
from reader.template import Template
from reader.input import Input
from logger.logger import Logger


class Renders:
    def __init__(
        self,
        template: Template,
        inputs: List[Input],
        quality: RenderQuality = RenderQuality.SIMPLE,
        size: tuple[int, int] = (-1, -1),
        logger: Logger | None = None,
    ):
        self.inputs: List[Input] = inputs
        self.template: Template = template
        self.renders: Dict[int, Image] = {}
        self.w = size[0]
        self.h = size[1]
        self.peak_cache_count: int = 0
        self.quality = quality
        self.logger = logger if logger is not None else Logger()
        self._lock = threading.Lock()

    def get_render(self, index: int = 0) -> Image:
        with self._lock:
            if index in self.renders:
                return self.renders[index]
        renderer = FrameRenderer(quality=self.quality, logger=self.logger)
        img = renderer.apply_scaled(index, self.template, self.inputs, self.w, self.h)
        self.renders[index] = img
        self.peak_cache_count = max(self.peak_cache_count, len(self.renders))
        return img

    def get_all_renders(self) -> list[Image]:
        threads: list[threading.Thread] = []
        for index in range(len(self.template.frames)):
            with self._lock:
                if index in self.renders:
                    continue
            thread = threading.Thread(target=self.get_render, args=(index,))
            thread.start()
            threads.append(thread)
        # Wait for all threads to complete
        for thread in threads:
            thread.join()
        # Return renders in order of frame index
        return [self.renders[i] for i in range(len(self.template.frames))]

    def remove_render(self, index: int):
        with self._lock:
            if index in self.renders:
                del self.renders[index]

    def auto_zoom(self) -> bool:
        changed = False
        renderer = FrameRenderer(quality=self.quality, logger=self.logger)
        renderer.pre(0, self.template)
        for inp in self.inputs:
            changed = changed or renderer.auto_zoom(inp)
        return changed
