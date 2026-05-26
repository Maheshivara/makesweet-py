from PIL import Image
from math import radians, cos, sin

from constants.constants import RR


class Input:
    def __init__(
        self,
        path: str,
        layer: int,
        scale: tuple[float, float] = (1.0, 1.0),
        offset: tuple[int, int] = (0, 0),
        theta: float = 0,
    ):
        self.path = path
        img = Image.open(self.path)
        img.load()
        self.image = img.copy()
        self.layer = layer
        self.scale = scale
        self.offset = offset
        self.theta = radians(theta)
        self.angle_cos = cos(self.theta)
        self.angle_sin = sin(self.theta)
        square_size = max(self.image.width, self.image.height)
        self.map_size = (square_size, square_size)
        self.center_offset = (
            -(square_size - self.image.width) // 2,
            -(square_size - self.image.height) // 2,
        )
        self.map_units_offset = (
            self.offset[0] * 2.0 * RR / self.map_size[0],
            self.offset[1] * 2.0 * RR / self.map_size[1],
        )
