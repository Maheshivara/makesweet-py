from PIL import Image
import cv2
import numpy as np
from typing import List
from enum import Enum

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
        # internal numpy RGBA arrays for speed
        self.out_arr: np.ndarray | None = None
        self.map1_arr: np.ndarray | None = None
        self.map2_arr: np.ndarray | None = None
        self.light_arr: np.ndarray | None = None
        self.dark_arr: np.ndarray | None = None
        self.neutral_arr: np.ndarray | None = None
        self.off: int = 0

    def _clamp_int(self, v: int, a: int, b: int) -> int:
        return max(a, min(b, int(v)))

    def _to_rgba_arr(self, img: Image.Image) -> np.ndarray:
        if img.mode != "RGBA":
            img = img.convert("RGBA")
        return np.array(img, dtype=np.uint8)

    def _array_get(self, arr: np.ndarray, x: int, y: int):
        h, w = arr.shape[:2]
        if 0 <= x < w and 0 <= y < h:
            px = arr[y, x]
            if px.shape[0] != 4:
                raise ValueError(
                    f"Expected RGBA pixel, got shape {px.shape} at ({x}, {y})"
                )
            return tuple(int(v) for v in px.tolist())
        else:
            self.logger.debug(
                f"Attempted to access pixel out of bounds at ({x}, {y}) in array of size {(w, h)}"
            )
            return (0, 0, 0, 0)

    def _safe_arr_pixel(self, arr: np.ndarray, x: int, y: int):
        h, w = arr.shape[:2]
        x = self._clamp_int(x, 0, w - 1)
        y = self._clamp_int(y, 0, h - 1)
        return tuple(int(v) for v in arr[y, x].tolist())

    def _remap_sample(
        self,
        in_arr: np.ndarray,
        map_x: np.ndarray,
        map_y: np.ndarray,
        interp=cv2.INTER_LINEAR,
    ) -> np.ndarray:
        # use replicate border to mimic clamping behavior
        return cv2.remap(
            in_arr,
            map_x.astype(np.float32),
            map_y.astype(np.float32),
            interpolation=interp,
            borderMode=cv2.BORDER_REPLICATE,
        )

    def _prepare_input_state(self, inp: Input):
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
        # prepare numpy arrays
        self.map1_arr = self._to_rgba_arr(mapping.map1_data)
        self.map2_arr = self._to_rgba_arr(mapping.map2_data)
        self.light_arr = self._to_rgba_arr(mapping.light_data)
        self.dark_arr = self._to_rgba_arr(mapping.dark_data)
        self.neutral_arr = (
            self._to_rgba_arr(mapping.neutral_data)
            if mapping.neutral_data is not None
            else None
        )
        self.off = (self.map2_arr.shape[0] - self.light_arr.shape[0]) // 2
        if mapping.neutral_data is not None:
            self.out_arr = self._to_rgba_arr(mapping.neutral_data.copy())
        else:
            self.out_arr = np.zeros((h, w, 4), dtype=np.uint8)
            self.out_arr[..., :3] = 255
            self.out_arr[..., 3] = 0

    def post(self):
        if self.out_arr is None or self.mapping is None:
            return
        pre = self.out_arr.copy()
        h, w = self.out_arr.shape[:2]
        map2 = self.map2_arr
        if map2 is None:
            self.logger.debug("map2_arr is None in post(), skipping post-processing")
            return
        if map2.shape[1] != w or map2.shape[0] != h:
            self.logger.debug(
                f"map2 size {(map2.shape[1], map2.shape[0])} differs from output size {(w, h)}, cropping map2 to match"
            )
            map2_crop = map2[0:h, 0:w, :]
        else:
            map2_crop = map2

        if h <= 2 or w <= 2:
            return

        center = map2_crop[1:-1, 1:-1, :]
        left = map2_crop[1:-1, 0:-2, :]
        right = map2_crop[1:-1, 2:, :]
        up = map2_crop[0:-2, 1:-1, :]
        down = map2_crop[2:, 1:-1, :]

        mask_left = left[..., 2] < 127
        mask_right = right[..., 2] < 127
        mask_up = up[..., 2] < 127
        mask_down = down[..., 2] < 127

        sum_rgba = np.zeros(center.shape, dtype=np.float64)
        cnt = np.zeros(center.shape[:2], dtype=np.int32)

        if mask_left.any():
            sum_rgba[mask_left] += pre[1:-1, 0:-2][mask_left].astype(np.float64)
            cnt[mask_left] += 1
        if mask_right.any():
            sum_rgba[mask_right] += pre[1:-1, 2:][mask_right].astype(np.float64)
            cnt[mask_right] += 1
        if mask_up.any():
            sum_rgba[mask_up] += pre[0:-2, 1:-1][mask_up].astype(np.float64)
            cnt[mask_up] += 1
        if mask_down.any():
            sum_rgba[mask_down] += pre[2:, 1:-1][mask_down].astype(np.float64)
            cnt[mask_down] += 1

        valid = cnt > 0
        center_sel = center[..., 2] > 0
        apply_mask = valid & center_sel
        if apply_mask.any():
            avg = np.zeros_like(sum_rgba)
            avg[apply_mask] = sum_rgba[apply_mask] / cnt[apply_mask][..., None]
            rows, cols = np.where(apply_mask)
            for ry, rx in zip(rows, cols):
                self.out_arr[ry + 1, rx + 1, 0:3] = np.clip(
                    avg[ry, rx, 0:3], 0, 255
                ).astype(np.uint8)

    def add_simple(self, inp: Input):
        if self.out_arr is None or self.mapping is None:
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
        off = self.off

        if (
            self.map1_arr is None
            or self.map2_arr is None
            or self.light_arr is None
            or self.dark_arr is None
            or self.out_arr is None
        ):
            self.logger.panic("Failed to load pixel data for add_simple")
            raise ValueError("Failed to load pixel data for add_simple")

        h, w = self.light_arr.shape[:2]
        mp = self.map1_arr[off : off + h, 0:w, :].astype(np.int32)
        sel = self.map2_arr[off : off + h, 0:w, :].astype(np.int32)
        light = self.light_arr.astype(np.int32)
        dark = self.dark_arr.astype(np.int32)
        in_arr = self._to_rgba_arr(inp.image)

        mod = mp[..., 2].astype(np.int32)
        ymod = mod // 16
        xmod = mod % 16
        x1 = (mp[..., 0].astype(np.int32) + 256 * xmod - RR).astype(np.float64)
        y1 = (mp[..., 1].astype(np.int32) + 256 * ymod - RR).astype(np.float64)
        x1 *= st["xs"]
        y1 *= st["ys"]
        xx = st["xa"] * x1 + st["ya"] * y1
        yy = -st["ya"] * x1 + st["xa"] * y1
        xx += RR + st["xo"]
        yy += RR + st["yo"]
        xx = st["in_x0"] + active_scale * xx / RR
        yy = st["in_y0"] + active_scale * yy / RR

        map_x = xx.astype(np.float32)
        map_y = yy.astype(np.float32)
        sampled = self._remap_sample(
            in_arr, map_x, map_y, interp=cv2.INTER_NEAREST
        ).astype(np.int32)

        d_mask = sel[..., 0] == inp.layer
        act_mask = mp[..., 3] > 25
        use_mask = d_mask & act_mask
        if not use_mask.any():
            return

        result_r = (
            dark[..., 0] + ((light[..., 0] - dark[..., 0]) * sampled[..., 0]) / 255.0
        )
        result_g = (
            dark[..., 1] + ((light[..., 1] - dark[..., 1]) * sampled[..., 1]) / 255.0
        )
        result_b = (
            dark[..., 2] + ((light[..., 2] - dark[..., 2]) * sampled[..., 2]) / 255.0
        )
        result_a = sampled[..., 3]
        result_a = np.minimum(result_a, dark[..., 3])

        out = self.out_arr.astype(np.int32)
        ys_idx, xs_idx = np.where(use_mask)
        for yy_i, xx_i in zip(ys_idx, xs_idx):
            ra = int(result_a[yy_i, xx_i])
            if ra <= 0:
                continue
            rr = int(result_r[yy_i, xx_i])
            rg = int(result_g[yy_i, xx_i])
            rb = int(result_b[yy_i, xx_i])
            out_r, out_g, out_b, out_a = out[yy_i, xx_i]
            if ra > 250:
                out[yy_i, xx_i, 0] = rr
                out[yy_i, xx_i, 1] = rg
                out[yy_i, xx_i, 2] = rb
            else:
                nr = int(out_r + ((rr - out_r) * ra) / 255.0)
                ng = int(out_g + ((rg - out_g) * ra) / 255.0)
                nb = int(out_b + ((rb - out_b) * ra) / 255.0)
                out[yy_i, xx_i, 0] = nr
                out[yy_i, xx_i, 1] = ng
                out[yy_i, xx_i, 2] = nb
        self.out_arr[..., :3] = np.clip(out[..., :3], 0, 255).astype(np.uint8)

    def add(self, inp: Input):
        if self.out_arr is None or self.mapping is None:
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
        off = self.off

        if (
            self.map1_arr is None
            or self.map2_arr is None
            or self.light_arr is None
            or self.dark_arr is None
            or self.out_arr is None
        ):
            self.logger.panic("Failed to load pixel data for add")
            raise ValueError("Failed to load pixel data for add")

        mp = self.map1_arr[off : off + h, 0:w, :].astype(np.int32)
        sel = self.map2_arr[off : off + h, 0:w, :].astype(np.int32)
        light = self.light_arr.astype(np.int32)
        dark = self.dark_arr.astype(np.int32)
        in_arr = self._to_rgba_arr(inp.image)

        mod = mp[..., 2].astype(np.int32)
        ymod = mod // 16
        xmod = mod % 16
        x1 = (mp[..., 0].astype(np.int32) + 256 * xmod - RR).astype(np.float64)
        y1 = (mp[..., 1].astype(np.int32) + 256 * ymod - RR).astype(np.float64)

        x12 = x1.copy()
        y12 = y1.copy()
        x13 = x1.copy()
        y13 = y1.copy()

        if h > 1 and w > 1:
            mdx = mp[0 : h - 1, 1:w, :].astype(np.int32)
            mdy = mp[1:h, 0 : w - 1, :].astype(np.int32)
            idx2 = sel[0 : h - 1, 1:w, 0].astype(np.int32)
            idx3 = sel[1:h, 0 : w - 1, 0].astype(np.int32)
            valid = (
                (mdx[..., 3] > 127)
                & (mdy[..., 3] > 127)
                & (idx2 == inp.layer)
                & (idx3 == inp.layer)
            )
            if valid.any():
                mod2 = mdx[..., 2].astype(np.int32)
                ymod2 = mod2 // 16
                xmod2 = mod2 % 16
                x12_temp = (mdx[..., 0].astype(np.int32) + 256 * xmod2 - RR).astype(
                    np.float64
                )
                y12_temp = (mdx[..., 1].astype(np.int32) + 256 * ymod2 - RR).astype(
                    np.float64
                )

                mod3 = mdy[..., 2].astype(np.int32)
                ymod3 = mod3 // 16
                xmod3 = mod3 % 16
                x13_temp = (mdy[..., 0].astype(np.int32) + 256 * xmod3 - RR).astype(
                    np.float64
                )
                y13_temp = (mdy[..., 1].astype(np.int32) + 256 * ymod3 - RR).astype(
                    np.float64
                )

                x1_in = x1[0 : h - 1, 0 : w - 1]
                y1_in = y1[0 : h - 1, 0 : w - 1]
                da = np.sqrt((x1_in - x12_temp) ** 2 + (y1_in - y12_temp) ** 2)
                db = np.sqrt((x1_in - x13_temp) ** 2 + (y1_in - y13_temp) ** 2)
                keep = valid & (da <= 400.0) & (db <= 400.0)
                x12[0 : h - 1, 0 : w - 1][keep] = x12_temp[keep]
                y12[0 : h - 1, 0 : w - 1][keep] = y12_temp[keep]
                x13[0 : h - 1, 0 : w - 1][keep] = x13_temp[keep]
                y13[0 : h - 1, 0 : w - 1][keep] = y13_temp[keep]

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

        map_mo_x = xx.astype(np.float32)
        map_mo_y = yy.astype(np.float32)
        map_m2_x = (xx + xxa / 2.0).astype(np.float32)
        map_m2_y = (yy + yya / 2.0).astype(np.float32)
        map_m3_x = (xx - xxa / 2.0).astype(np.float32)
        map_m3_y = (yy - yya / 2.0).astype(np.float32)
        map_m4_x = (xx + xxb / 2.0).astype(np.float32)
        map_m4_y = (yy + yyb / 2.0).astype(np.float32)
        map_m5_x = (xx - xxb / 2.0).astype(np.float32)
        map_m5_y = (yy - yyb / 2.0).astype(np.float32)

        map_m2b_x = (xx + (xxa + xxb) / 2.0).astype(np.float32)
        map_m2b_y = (yy + (yya + yyb) / 2.0).astype(np.float32)
        map_m3b_x = (xx + (xxa - xxb) / 2.0).astype(np.float32)
        map_m3b_y = (yy + (yya - yyb) / 2.0).astype(np.float32)
        map_m4b_x = (xx - (xxa + xxb) / 2.0).astype(np.float32)
        map_m4b_y = (yy - (yya + yyb) / 2.0).astype(np.float32)
        map_m5b_x = (xx - (xxa - xxb) / 2.0).astype(np.float32)
        map_m5b_y = (yy - (yya - yyb) / 2.0).astype(np.float32)

        mo = self._remap_sample(
            in_arr, map_mo_x, map_mo_y, interp=cv2.INTER_LINEAR
        ).astype(np.float64)
        m2 = self._remap_sample(
            in_arr, map_m2_x, map_m2_y, interp=cv2.INTER_LINEAR
        ).astype(np.float64)
        m3 = self._remap_sample(
            in_arr, map_m3_x, map_m3_y, interp=cv2.INTER_LINEAR
        ).astype(np.float64)
        m4 = self._remap_sample(
            in_arr, map_m4_x, map_m4_y, interp=cv2.INTER_LINEAR
        ).astype(np.float64)
        m5 = self._remap_sample(
            in_arr, map_m5_x, map_m5_y, interp=cv2.INTER_LINEAR
        ).astype(np.float64)
        m2b = self._remap_sample(
            in_arr, map_m2b_x, map_m2b_y, interp=cv2.INTER_LINEAR
        ).astype(np.float64)
        m3b = self._remap_sample(
            in_arr, map_m3b_x, map_m3b_y, interp=cv2.INTER_LINEAR
        ).astype(np.float64)
        m4b = self._remap_sample(
            in_arr, map_m4b_x, map_m4b_y, interp=cv2.INTER_LINEAR
        ).astype(np.float64)
        m5b = self._remap_sample(
            in_arr, map_m5b_x, map_m5b_y, interp=cv2.INTER_LINEAR
        ).astype(np.float64)

        def pre_rgb(mat):
            return (
                mat[..., 0] * mat[..., 3],
                mat[..., 1] * mat[..., 3],
                mat[..., 2] * mat[..., 3],
                mat[..., 3],
            )

        mo_rp, mo_gp, mo_bp, mo_ap = pre_rgb(mo)
        m2_rp, m2_gp, m2_bp, m2_ap = pre_rgb(m2)
        m3_rp, m3_gp, m3_bp, m3_ap = pre_rgb(m3)
        m4_rp, m4_gp, m4_bp, m4_ap = pre_rgb(m4)
        m5_rp, m5_gp, m5_bp, m5_ap = pre_rgb(m5)
        m2b_rp, m2b_gp, m2b_bp, m2b_ap = pre_rgb(m2b)
        m3b_rp, m3b_gp, m3b_bp, m3b_ap = pre_rgb(m3b)
        m4b_rp, m4b_gp, m4b_bp, m4b_ap = pre_rgb(m4b)
        m5b_rp, m5b_gp, m5b_bp, m5b_ap = pre_rgb(m5b)

        sum_a = (
            4.0 * mo_ap
            + 2.0 * (m2_ap + m3_ap + m4_ap + m5_ap)
            + (m2b_ap + m3b_ap + m4b_ap + m5b_ap)
        )
        sum_r = (
            4.0 * mo_rp
            + 2.0 * (m2_rp + m3_rp + m4_rp + m5_rp)
            + (m2b_rp + m3b_rp + m4b_rp + m5b_rp)
        )
        sum_g = (
            4.0 * mo_gp
            + 2.0 * (m2_gp + m3_gp + m4_gp + m5_gp)
            + (m2b_gp + m3b_gp + m4b_gp + m5b_gp)
        )
        sum_b = (
            4.0 * mo_bp
            + 2.0 * (m2_bp + m3_bp + m4_bp + m5_bp)
            + (m2b_bp + m3b_bp + m4b_bp + m5b_bp)
        )

        eps = 1e-8
        m_a = sum_a / 16.0
        denom = sum_a
        mask_valid = denom > eps
        m_r = np.zeros_like(sum_r)
        m_g = np.zeros_like(sum_g)
        m_b = np.zeros_like(sum_b)
        m_r[mask_valid] = sum_r[mask_valid] / denom[mask_valid]
        m_g[mask_valid] = sum_g[mask_valid] / denom[mask_valid]
        m_b[mask_valid] = sum_b[mask_valid] / denom[mask_valid]

        d_mask = sel[..., 0] == inp.layer
        act_mask = mp[..., 3] > 25
        use_mask = d_mask & act_mask & (m_a > 0)
        if not use_mask.any():
            return

        result_r = dark[..., 0] + ((light[..., 0] - dark[..., 0]) * m_r) / 255.0
        result_g = dark[..., 1] + ((light[..., 1] - dark[..., 1]) * m_g) / 255.0
        result_b = dark[..., 2] + ((light[..., 2] - dark[..., 2]) * m_b) / 255.0
        result_a = m_a.astype(np.int32)
        result_a = np.minimum(result_a, dark[..., 3])

        out = self.out_arr.astype(np.int32)
        ys_idx, xs_idx = np.where(use_mask)
        for yy_i, xx_i in zip(ys_idx, xs_idx):
            ra = int(result_a[yy_i, xx_i])
            if ra <= 0:
                continue
            rr = int(result_r[yy_i, xx_i])
            rg = int(result_g[yy_i, xx_i])
            rb = int(result_b[yy_i, xx_i])
            out_r, out_g, out_b, out_a = out[yy_i, xx_i]
            if ra > 250:
                out[yy_i, xx_i, 0] = rr
                out[yy_i, xx_i, 1] = rg
                out[yy_i, xx_i, 2] = rb
            else:
                nr = int(out_r + ((rr - out_r) * ra) / 255.0)
                ng = int(out_g + ((rg - out_g) * ra) / 255.0)
                nb = int(out_b + ((rb - out_b) * ra) / 255.0)
                out[yy_i, xx_i, 0] = nr
                out[yy_i, xx_i, 1] = ng
                out[yy_i, xx_i, 2] = nb
        self.out_arr[..., :3] = np.clip(out[..., :3], 0, 255).astype(np.uint8)

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

        if (
            self.map1_arr is None
            or self.map2_arr is None
            or self.light_arr is None
            or self.dark_arr is None
        ):
            return
        h, w = self.light_arr.shape[:2]
        mp = self.map1_arr[off : off + h, 0:w, :].astype(np.int32)
        sel = self.map2_arr[off : off + h, 0:w, :].astype(np.int32)
        light = self.light_arr.astype(np.int32)
        dark = self.dark_arr.astype(np.int32)

        mod = mp[..., 2]
        ymod = mod // 16
        xmod = mod % 16
        x1 = (mp[..., 0] + 256 * xmod - RR).astype(np.float64)
        y1 = (mp[..., 1] + 256 * ymod - RR).astype(np.float64)
        x1 *= st["xs"]
        y1 *= st["ys"]
        xx = st["xa"] * x1 + st["ya"] * y1
        yy = -st["ya"] * x1 + st["xa"] * y1
        xx += RR + st["xo"]
        yy += RR + st["yo"]
        xx = st["in_x0"] + active_scale * xx / RR
        yy = st["in_y0"] + active_scale * yy / RR

        sel_nonzero = sel[..., 0] != 0
        act_mask = mp[..., 3] > 25
        delv = 5
        color_diff = (
            (np.abs(light[..., 0] - dark[..., 0]) > delv)
            | (np.abs(light[..., 1] - dark[..., 1]) > delv)
            | (np.abs(light[..., 2] - dark[..., 2]) > delv)
        )
        alpha_ok = (dark[..., 3] > 100) & (light[..., 3] > 100)
        mask = sel_nonzero & act_mask & color_diff & alpha_ok
        ys, xs = np.where(mask)
        for ry, rx in zip(ys, xs):
            cloud.append(
                CloudPoint(int(sel[ry, rx, 0]), float(xx[ry, rx]), float(yy[ry, rx]))
            )

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

        if self.map1_arr is None or self.map2_arr is None or self.light_arr is None:
            self.logger.debug(
                "One or more required arrays are None in auto_zoom(), skipping"
            )
            return False
        h, w = self.light_arr.shape[:2]
        mp = self.map1_arr[off : off + h, 0:w, :].astype(np.int32)
        sel = self.map2_arr[off : off + h, 0:w, :].astype(np.int32)

        mod = mp[..., 2]
        ymod = mod // 16
        xmod = mod % 16
        x1 = (mp[..., 0] + 256 * xmod - RR).astype(np.float64)
        y1 = (mp[..., 1] + 256 * ymod - RR).astype(np.float64)
        x1 *= st["xs"]
        y1 *= st["ys"]
        xx = st["xa"] * x1 + st["ya"] * y1
        yy = -st["ya"] * x1 + st["xa"] * y1
        xx += RR + st["xo"]
        yy += RR + st["yo"]
        xx = st["in_x0"] + active_scale * xx / RR
        yy = st["in_y0"] + active_scale * yy / RR

        mask = (sel[..., 0] == 1) & (mp[..., 3] > 25)
        if not mask.any():
            return False
        y_min = float(np.min(yy[mask]))
        y_max = float(np.max(yy[mask]))

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
        if self.out_arr is None:
            self.logger.panic("Output image not set after rendering")
            raise ValueError("Output image not set after rendering")

        if w > 0 and h > 0:
            out_pil = Image.fromarray(self.out_arr, mode="RGBA")
            wi, hi = out_pil.size
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
            resized = out_pil.resize((wo, ho), resample=Image.Resampling.LANCZOS)
            out_scaled.paste(resized, (xo, yo), resized)
            out_arr = np.array(out_scaled)
            out_arr[..., 3] = 255
            out_scaled = Image.fromarray(out_arr, mode="RGBA")
            self.out_arr = np.array(out_scaled)
            return out_scaled
        return Image.fromarray(self.out_arr, mode="RGBA")
