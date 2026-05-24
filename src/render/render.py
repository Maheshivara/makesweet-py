from PIL import Image
from typing import List
from math import sqrt
from enum import Enum

from render.pixer import Pixer
from reader.template import Template, Frame
from reader.input import Input
from constants.constants import RR
from logger.logger import Logger


class RenderQuality(Enum):
    SIMPLE = "simple"
    HIGH = "high"


class CloudPoint:
    def __init__(self, layer: int, x: float, y: float):
        self.layer = layer
        self.x = x
        self.y = y


class Render:
    def __init__(
        self,
        quality: RenderQuality = RenderQuality.SIMPLE,
        logger: Logger | None = None,
    ):
        self.quality = quality
        self.logger = logger if logger is not None else Logger()

        self.mapping: Frame | None = None
        self.out: Image.Image | None = None

    def _clamp_int(self, v: int, a: int, b: int) -> int:
        return max(a, min(b, int(v)))

    def _get_pixel(self, img: Image.Image, x: int, y: int):
        w, h = img.size
        if 0 <= x < w and 0 <= y < h:
            px = img.getpixel((x, y))
            if not isinstance(px, tuple) or len(px) != 4:
                raise ValueError(
                    f"Expected RGBA pixel, got {px} at ({x}, {y}) in image of size {img.size}"
                )
            return px
        else:
            self.logger.debug(
                f"Attempted to access pixel out of bounds at ({x}, {y}) in image of size {img.size}"
            )
            return (0, 0, 0, 0)

    def _get_pixel_from_pixel_access(
        self, pix_access: Image.core.PixelAccess, x: int, y: int
    ):
        px = pix_access[x, y]
        if not isinstance(px, tuple) or len(px) != 4:
            raise ValueError(f"Expected RGBA pixel, got {px} at ({x}, {y})")
        return px

    def _safe_pixel(self, img: Image.Image, x: int, y: int):
        w, h = img.size
        x = self._clamp_int(x, 0, w - 1)
        y = self._clamp_int(y, 0, h - 1)
        px = self._get_pixel(img, x, y)
        return px

    def _sample_linear(self, img: Image.Image, x: float, y: float) -> Pixer:
        if img.mode != "RGBA":
            img = img.convert("RGBA")
        xi = int(x)
        yi = int(y)
        fx = x - xi
        fy = y - yi

        p00 = self._safe_pixel(img, xi, yi)
        p01 = self._safe_pixel(img, xi, yi + 1)
        p10 = self._safe_pixel(img, xi + 1, yi)
        p11 = self._safe_pixel(img, xi + 1, yi + 1)

        a00 = p00[3]
        a10 = p10[3]
        a01 = p01[3]
        a11 = p11[3]
        aa = (
            (1 - fx) * (1 - fy) * a00
            + fx * (1 - fy) * a10
            + (1 - fx) * fy * a01
            + fx * fy * a11
        )
        if aa < 0.0001:
            aa = 0.0001

        r = (
            (1 - fx) * (1 - fy) * p00[0] * a00
            + fx * (1 - fy) * p10[0] * a10
            + (1 - fx) * fy * p01[0] * a01
            + fx * fy * p11[0] * a11
        ) / aa
        g = (
            (1 - fx) * (1 - fy) * p00[1] * a00
            + fx * (1 - fy) * p10[1] * a10
            + (1 - fx) * fy * p01[1] * a01
            + fx * fy * p11[1] * a11
        ) / aa
        b = (
            (1 - fx) * (1 - fy) * p00[2] * a00
            + fx * (1 - fy) * p10[2] * a10
            + (1 - fx) * fy * p01[2] * a01
            + fx * fy * p11[2] * a11
        ) / aa
        a = (
            (1 - fx) * (1 - fy) * a00
            + fx * (1 - fy) * a10
            + (1 - fx) * fy * a01
            + fx * fy * a11
        )

        return Pixer(r, g, b, a)

    def _prepare_input_state(self, inp: Input):
        # derive fields from the Python Input object (maps to C++ Input fields)
        # because i just doesn't understand how in the hells this work
        # (aka needed to copy and paste the math from original code)
        xs = float(inp.scale[0])
        ys = float(inp.scale[1])
        xa = float(inp.angle_cos)
        ya = float(inp.angle_sin)
        in_scale = float(inp.map_size[0])
        in_x0 = float(inp.center_offset[0])
        in_y0 = float(inp.center_offset[1])
        xo = float(inp.map_units_offset[0])
        yo = float(inp.map_units_offset[1])
        return {
            "xs": xs,
            "ys": ys,
            "xa": xa,
            "ya": ya,
            "in_scale": in_scale,
            "in_x0": in_x0,
            "in_y0": in_y0,
            "xo": xo,
            "yo": yo,
        }

    def pre(self, frame_index: int, template: Template):
        mapping = template.frames[frame_index]
        self.mapping = mapping
        w, h = mapping.light_data.size
        if mapping.neutral_data is not None:
            self.out = mapping.neutral_data.copy().convert("RGBA")
        else:
            self.out = Image.new("RGBA", (w, h), (255, 255, 255, 0))

    def post(self):
        if self.out is None or self.mapping is None:
            return
        pre = self.out.copy()
        w, h = self.out.size
        map2 = self.mapping.map2_data
        if map2.size != self.out.size:
            self.logger.debug(
                f"map2 size {map2.size} differs from output size {self.out.size}, cropping map2 to match"
            )
            map2 = map2.crop((0, 0, w, h)).convert("RGBA")
        pre_pix = pre.load()
        out_pix = self.out.load()
        map2_pix = map2.load()
        if map2_pix is None or pre_pix is None or out_pix is None:
            raise ValueError("Failed to load pixel data for post-processing")
        for y in range(h):
            for x in range(w):
                sel = self._get_pixel_from_pixel_access(map2_pix, x, y)
                if sel[2] > 0:
                    if 0 < x < w - 1 and 0 < y < h - 1:
                        total = Pixer(0.0, 0.0, 0.0, 0.0)
                        ct = 0
                        # left
                        idx1 = self._get_pixel_from_pixel_access(map2_pix, x - 1, y)
                        if idx1[2] < 127:
                            p = self._get_pixel_from_pixel_access(pre_pix, x - 1, y)
                            total = total + Pixer(p[0], p[1], p[2], p[3])
                            ct += 1
                        # right
                        idx2 = self._get_pixel_from_pixel_access(map2_pix, x + 1, y)
                        if idx2[2] < 127:
                            p = self._get_pixel_from_pixel_access(pre_pix, x + 1, y)
                            total = total + Pixer(p[0], p[1], p[2], p[3])
                            ct += 1
                        # up
                        idx3 = self._get_pixel_from_pixel_access(map2_pix, x, y - 1)
                        if idx3[2] < 127:
                            p = self._get_pixel_from_pixel_access(pre_pix, x, y - 1)
                            total = total + Pixer(p[0], p[1], p[2], p[3])
                            ct += 1
                        # down
                        idx4 = self._get_pixel_from_pixel_access(map2_pix, x, y + 1)
                        if idx4[2] < 127:
                            p = self._get_pixel_from_pixel_access(pre_pix, x, y + 1)
                            total = total + Pixer(p[0], p[1], p[2], p[3])
                            ct += 1
                        if ct > 0.5:
                            avg = total / ct
                            out_a = self._get_pixel_from_pixel_access(out_pix, x, y)[3]
                            out_pix[x, y] = (int(avg.r), int(avg.g), int(avg.b), out_a)

    def add_simple(self, inp: Input):
        if self.out is None or self.mapping is None:
            self.logger.warning(
                "add_simple called before pre() or with invalid mapping, skipping"
            )
            return
        mapping = self.mapping
        if mapping.map1_data.width < mapping.light_data.width:
            self.logger.debug(
                f"map1 width {mapping.map1_data.width} is less than light data width {mapping.light_data.width}, skipping add_simple"
            )
            return

        st = self._prepare_input_state(inp)
        active_scale = st["in_scale"] / 2.0
        off = (mapping.map2_data.size[1] - mapping.light_data.size[1]) // 2

        out_pix = self.out.load()
        map1_pix = mapping.map1_data.load()
        map2_pix = mapping.map2_data.load()
        light_pix = mapping.light_data.load()
        dark_pix = mapping.dark_data.load()
        in_img = inp.image.convert("RGBA")
        if (
            map1_pix is None
            or map2_pix is None
            or light_pix is None
            or dark_pix is None
            or out_pix is None
        ):
            self.logger.panic("Failed to load pixel data for add_simple")
            raise ValueError("Failed to load pixel data for add_simple")

        w, h = mapping.light_data.size
        for y in range(h):
            for x in range(w):
                map_pixel = self._get_pixel_from_pixel_access(map1_pix, x, y + off)
                sel_pixel = self._get_pixel_from_pixel_access(map2_pix, x, y + off)
                mod = map_pixel[2]
                ymod = mod // 16
                xmod = mod % 16
                act = map_pixel[3]
                x1 = map_pixel[0] + 256 * xmod - RR
                y1 = map_pixel[1] + 256 * ymod - RR
                x1 *= st["xs"]
                y1 *= st["ys"]
                xx = st["xa"] * x1 + st["ya"] * y1
                yy = -st["ya"] * x1 + st["xa"] * y1
                xx += RR + st["xo"]
                yy += RR + st["yo"]
                xx = st["in_x0"] + active_scale * xx / RR
                yy = st["in_y0"] + active_scale * yy / RR

                m = self._safe_pixel(in_img, int(xx), int(yy))
                d = sel_pixel[0] == inp.layer
                if d and act > 25:
                    light_pixel = self._get_pixel_from_pixel_access(light_pix, x, y)
                    dark_pixel = self._get_pixel_from_pixel_access(dark_pix, x, y)
                    result_r = int(
                        dark_pixel[0] + ((light_pixel[0] - dark_pixel[0]) * m[0]) / 255
                    )
                    result_g = int(
                        dark_pixel[1] + ((light_pixel[1] - dark_pixel[1]) * m[1]) / 255
                    )
                    result_b = int(
                        dark_pixel[2] + ((light_pixel[2] - dark_pixel[2]) * m[2]) / 255
                    )
                    result_a = m[3]
                    if dark_pixel[3] < result_a:
                        result_a = dark_pixel[3]
                    if result_a > 0:
                        out_r, out_g, out_b, out_a = self._get_pixel_from_pixel_access(
                            out_pix, x, y
                        )
                        if result_a > 250:
                            out_pix[x, y] = (result_r, result_g, result_b, out_a)
                        else:
                            nr = int(out_r + ((result_r - out_r) * result_a) / 255.0)
                            ng = int(out_g + ((result_g - out_g) * result_a) / 255.0)
                            nb = int(out_b + ((result_b - out_b) * result_a) / 255.0)
                            out_pix[x, y] = (nr, ng, nb, out_a)

    def add(self, inp: Input):
        if self.out is None or self.mapping is None:
            self.logger.warning(
                "add called before pre() or with invalid mapping, skipping"
            )
            return
        mapping = self.mapping
        w, h = mapping.light_data.size
        if mapping.map1_data.size[0] < w:
            self.logger.debug(
                f"map1 width {mapping.map1_data.width} is less than light data width {mapping.light_data.width}, skipping add"
            )
            return

        if mapping.map1_data.size[0] != (
            mapping.neutral_data.size[0]
            if mapping.neutral_data
            else mapping.map1_data.size[0]
        ):
            self.logger.debug(
                f"map1 width {mapping.map1_data.size[0]} does not match neutral data width {mapping.neutral_data.size[0] if mapping.neutral_data else 'N/A'}, skipping add"
            )
            return
        if mapping.map2_data.size[0] != (
            mapping.neutral_data.size[0]
            if mapping.neutral_data
            else mapping.map2_data.size[0]
        ):
            self.logger.debug(
                f"map2 width {mapping.map2_data.size[0]} does not match neutral data width {mapping.neutral_data.size[0] if mapping.neutral_data else 'N/A'}, skipping add"
            )
            return

        st = self._prepare_input_state(inp)
        active_scale = st["in_scale"] / 2.0
        off = (mapping.map2_data.size[1] - mapping.light_data.size[1]) // 2

        out_pix = self.out.load()
        map1_pix = mapping.map1_data.load()
        map2_pix = mapping.map2_data.load()
        light_pix = mapping.light_data.load()
        dark_pix = mapping.dark_data.load()
        in_img = inp.image.convert("RGBA")

        if (
            map1_pix is None
            or map2_pix is None
            or light_pix is None
            or dark_pix is None
            or out_pix is None
        ):
            self.logger.panic("Failed to load pixel data for add")
            raise ValueError("Failed to load pixel data for add")

        for y in range(h):
            for x in range(w):
                light_pixel = self._get_pixel_from_pixel_access(light_pix, x, y)
                dark_pixel = self._get_pixel_from_pixel_access(dark_pix, x, y)
                map_pixel = self._get_pixel_from_pixel_access(map1_pix, x, y + off)
                sel_pixel = self._get_pixel_from_pixel_access(map2_pix, x, y + off)
                d = sel_pixel[0] == inp.layer
                if not d:
                    continue
                act = map_pixel[3]
                if act <= 25:
                    continue

                mod = map_pixel[2]
                ymod = mod // 16
                xmod = mod % 16
                x1 = map_pixel[0] + 256 * xmod - RR
                y1 = map_pixel[1] + 256 * ymod - RR

                x12 = x1
                y12 = y1
                x13 = x1
                y13 = y1

                if x < w - 1 and y < h - 1:
                    mdx = self._get_pixel_from_pixel_access(map1_pix, x + 1, y + off)
                    mdy = self._get_pixel_from_pixel_access(map1_pix, x, y + 1 + off)
                    if mdx[3] > 127 and mdy[3] > 127:
                        idx2 = self._get_pixel_from_pixel_access(
                            map2_pix, x + 1, y + off
                        )
                        idx3 = self._get_pixel_from_pixel_access(
                            map2_pix, x, y + 1 + off
                        )
                        if idx2[0] == inp.layer and idx3[0] == inp.layer:
                            mod2 = mdx[2]
                            ymod2 = mod2 // 16
                            xmod2 = mod2 % 16
                            x12 = mdx[0] + 256 * xmod2 - RR
                            y12 = mdx[1] + 256 * ymod2 - RR

                            mod3 = mdy[2]
                            ymod3 = mod3 // 16
                            xmod3 = mod3 % 16
                            x13 = mdy[0] + 256 * xmod3 - RR
                            y13 = mdy[1] + 256 * ymod3 - RR

                        da = sqrt((x1 - x12) ** 2 + (y1 - y12) ** 2)
                        db = sqrt((x1 - x13) ** 2 + (y1 - y13) ** 2)
                        if da > 400.0 or db > 400.0:
                            x12 = x1
                            y12 = y1
                            x13 = x1
                            y13 = y1

                x1 *= st["xs"]
                y1 *= st["ys"]
                xx = st["xa"] * x1 + st["ya"] * y1
                yy = -st["ya"] * x1 + st["xa"] * y1
                xx += RR + st["xo"]
                yy += RR + st["yo"]
                xx = st["in_x0"] + active_scale * xx / RR
                yy = st["in_y0"] + active_scale * yy / RR

                x12 *= st["xs"]
                y12 *= st["ys"]
                xxa = st["xa"] * x12 + st["ya"] * y12
                yya = -st["ya"] * x12 + st["xa"] * y12
                xxa += RR + st["xo"]
                yya += RR + st["yo"]
                xxa = st["in_x0"] + active_scale * xxa / RR
                yya = st["in_y0"] + active_scale * yya / RR

                x13 *= st["xs"]
                y13 *= st["ys"]
                xxb = st["xa"] * x13 + st["ya"] * y13
                yyb = -st["ya"] * x13 + st["xa"] * y13
                xxb += RR + st["xo"]
                yyb += RR + st["yo"]
                xxb = st["in_x0"] + active_scale * xxb / RR
                yyb = st["in_y0"] + active_scale * yyb / RR

                xxa -= xx
                yya -= yy
                xxb -= xx
                yyb -= yy

                mo = self._sample_linear(in_img, xx, yy)
                m2 = self._sample_linear(in_img, xx + xxa / 2.0, yy + yya / 2.0)
                m3 = self._sample_linear(in_img, xx - xxa / 2.0, yy - yya / 2.0)
                m4 = self._sample_linear(in_img, xx + xxb / 2.0, yy + yyb / 2.0)
                m5 = self._sample_linear(in_img, xx - xxb / 2.0, yy - yyb / 2.0)

                m2b = self._sample_linear(
                    in_img, xx + (xxa + xxb) / 2.0, yy + (yya + yyb) / 2.0
                )
                m3b = self._sample_linear(
                    in_img, xx + (xxa - xxb) / 2.0, yy + (yya - yyb) / 2.0
                )
                m4b = self._sample_linear(
                    in_img, xx - (xxa + xxb) / 2.0, yy - (yya + yyb) / 2.0
                )
                m5b = self._sample_linear(
                    in_img, xx - (xxa - xxb) / 2.0, yy - (yya - yyb) / 2.0
                )

                mo.preblend()
                m2.preblend()
                m3.preblend()
                m4.preblend()
                m5.preblend()
                m2b.preblend()
                m3b.preblend()
                m4b.preblend()
                m5b.preblend()

                sc = (
                    mo.a * 4.0
                    + (m2.a + m3.a + m4.a + m5.a) * 2.0
                    + (m2b.a + m3b.a + m4b.a + m5b.a)
                ) / 16.0
                compound = (
                    (mo * 4.0) + ((m2 + m3 + m4 + m5) * 2.0) + (m2b + m3b + m4b + m5b)
                )
                mo = compound / 16.0
                if sc > 0.0001:
                    mo.postblend(sc)
                else:
                    mo.r = mo.g = mo.b = mo.a = 0.0

                m_r = mo.r
                m_g = mo.g
                m_b = mo.b
                m_a = mo.a

                if d and act > 25:
                    result_r = int(
                        dark_pixel[0] + ((light_pixel[0] - dark_pixel[0]) * m_r) / 255.0
                    )
                    result_g = int(
                        dark_pixel[1] + ((light_pixel[1] - dark_pixel[1]) * m_g) / 255.0
                    )
                    result_b = int(
                        dark_pixel[2] + ((light_pixel[2] - dark_pixel[2]) * m_b) / 255.0
                    )
                    result_a = int(m_a)
                    if dark_pixel[3] < result_a:
                        result_a = dark_pixel[3]
                    if result_a > 0:
                        out_r, out_g, out_b, out_a = self._get_pixel_from_pixel_access(
                            out_pix, x, y
                        )
                        if result_a > 250:
                            out_pix[x, y] = (result_r, result_g, result_b, out_a)
                        else:
                            nr = int(out_r + ((result_r - out_r) * result_a) / 255.0)
                            ng = int(out_g + ((result_g - out_g) * result_a) / 255.0)
                            nb = int(out_b + ((result_b - out_b) * result_a) / 255.0)
                            out_pix[x, y] = (nr, ng, nb, out_a)

    def getCloud(self, inp: Input, cloud: List[CloudPoint]):
        if self.mapping is None:
            self.logger.warning(
                "getCloud called before pre() or with invalid mapping, skipping"
            )
            return
        st = self._prepare_input_state(inp)
        active_scale = st["in_scale"] / 2.0
        off = (self.mapping.map2_data.size[1] - self.mapping.light_data.size[1]) // 2
        if self.mapping.map1_data.size[0] < self.mapping.light_data.size[0]:
            self.logger.warning(
                f"map1 width {self.mapping.map1_data.size[0]} is less than light data width {self.mapping.light_data.size[0]}, skipping getCloud"
            )
            return

        for y in range(self.mapping.light_data.size[1]):
            for x in range(self.mapping.light_data.size[0]):
                light_pixel = self._get_pixel(self.mapping.light_data, x, y)
                dark_pixel = self._get_pixel(self.mapping.dark_data, x, y)
                map_pixel = self._get_pixel(self.mapping.map1_data, x, y + off)
                sel_pixel = self._get_pixel(self.mapping.map2_data, x, y + off)
                mod = map_pixel[2]
                ymod = mod // 16
                xmod = mod % 16
                act = map_pixel[3]
                x1 = map_pixel[0] + 256 * xmod - RR
                y1 = map_pixel[1] + 256 * ymod - RR
                x1 *= st["xs"]
                y1 *= st["ys"]
                xx = st["xa"] * x1 + st["ya"] * y1
                yy = -st["ya"] * x1 + st["xa"] * y1
                xx += RR + st["xo"]
                yy += RR + st["yo"]
                xx = st["in_x0"] + active_scale * xx / RR
                yy = st["in_y0"] + active_scale * yy / RR
                if sel_pixel[0] != 0 and act > 25:
                    delv = 5
                    if (
                        (
                            abs(light_pixel[0] - dark_pixel[0]) > delv
                            or abs(light_pixel[1] - dark_pixel[1]) > delv
                            or abs(light_pixel[2] - dark_pixel[2]) > delv
                        )
                        and dark_pixel[3] > 100
                        and light_pixel[3] > 100
                    ):
                        cloud.append(CloudPoint(sel_pixel[0], xx, yy))

    def auto_zoom(self, inp: Input) -> bool:
        if self.mapping is None:
            return False
        st = self._prepare_input_state(inp)
        active_scale = st["in_scale"] / 2.0
        off = (self.mapping.map2_data.size[1] - self.mapping.light_data.size[1]) // 2
        if self.mapping.map1_data.size[0] < self.mapping.light_data.size[0]:
            self.logger.warning(
                f"map1 width {self.mapping.map1_data.size[0]} is less than light data width {self.mapping.light_data.size[0]}, skipping auto_zoom"
            )
            return False

        x_min = inp.image.width
        x_max = 0
        y_min = inp.image.height
        y_max = 0
        for y in range(self.mapping.light_data.size[1]):
            for x in range(self.mapping.light_data.size[0]):
                map_pixel = self._get_pixel(self.mapping.map1_data, x, y + off)
                sel_pixel = self._get_pixel(self.mapping.map2_data, x, y + off)
                mod = map_pixel[2]
                ymod = mod // 16
                xmod = mod % 16
                act = map_pixel[3]
                x1 = map_pixel[0] + 256 * xmod - RR
                y1 = map_pixel[1] + 256 * ymod - RR
                x1 *= st["xs"]
                y1 *= st["ys"]
                xx = st["xa"] * x1 + st["ya"] * y1
                yy = -st["ya"] * x1 + st["xa"] * y1
                xx += RR + st["xo"]
                yy += RR + st["yo"]
                xx = st["in_x0"] + active_scale * xx / RR
                yy = st["in_y0"] + active_scale * yy / RR

                d = sel_pixel[0] == 1
                if d and act > 25:
                    if xx < x_min:
                        x_min = xx
                    if xx > x_max:
                        x_max = xx
                    if yy < y_min:
                        y_min = yy
                    if yy > y_max:
                        y_max = yy

        hh = inp.image.height
        if (y_max - y_min) < (hh * 0.75):
            inp.scale = (inp.scale[0] * 2.0, inp.scale[1] * 2.0)
            return True
        return False

    def apply_scaled(
        self,
        frame_index: int,
        template: Template,
        inputs: List[Input],
        w: int = -1,
        h: int = -1,
    ) -> Image.Image:
        self.pre(frame_index, template)
        mapping = self.mapping
        if mapping is None:
            self.logger.panic("Mapping not set after pre(), cannot apply_scaled")
            raise ValueError("Mapping not set after pre(), cannot apply_scaled")

        for inp in inputs:
            if self.quality == RenderQuality.SIMPLE:
                self.logger.debug(f"Adding input with simple quality: {inp}")
                self.add_simple(inp)
            else:
                self.logger.debug(f"Adding input with high quality: {inp}")
                self.add(inp)
        self.post()
        if self.out is None:
            self.logger.panic("Output image not set after rendering")
            raise ValueError("Output image not set after rendering")

        if w > 0 and h > 0 and (w != self.out.width or h != self.out.height):
            wi, hi = self.out.size
            fi = wi / hi
            f = w / h
            xo = 0
            yo = 0
            wo = w
            ho = h
            if fi > f + 0.001:
                wo = w
                ho = int(wo / fi)
                yo = (h - ho) // 2
            elif fi < f - 0.001:
                ho = h
                wo = int(h * fi)
                xo = (w - wo) // 2
            out_scaled = Image.new("RGBA", (w, h), (255, 255, 255, 0))
            resized = self.out.resize((wo, ho), resample=Image.Resampling.LANCZOS)
            out_scaled.paste(resized, (xo, yo), resized)
            # ensure full alpha
            px = out_scaled.load()
            if px is None:
                self.logger.panic("Failed to load pixel data for out_scaled")
                raise ValueError("Failed to load pixel data for out_scaled")
            for yy in range(h):
                for xx in range(w):
                    r, g, b, _ = self._get_pixel_from_pixel_access(px, xx, yy)
                    px[xx, yy] = (r, g, b, 255)
            self.out = out_scaled
        return self.out
