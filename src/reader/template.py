from PIL import Image
import zipfile
import xml.etree.ElementTree as ElementTree
from logger.logger import Logger


class Frame:
    def __init__(
        self,
        number: int,
        map1_data: Image.Image,
        map2_data: Image.Image,
        light_data: Image.Image,
        dark_data: Image.Image,
        neutral_data: Image.Image | None = None,
        sample_data: Image.Image | None = None,
    ):
        self.number = number
        self.map1_data = map1_data
        self.map2_data = map2_data
        self.light_data = light_data
        self.dark_data = dark_data
        self.neutral_data = neutral_data
        self.sample_data = sample_data


class TemplateConfig:
    def __init__(
        self,
        frames: int,
        zoom: float = 1.0,
        width: int = 400,
        height: int = 300,
        version: int = 2,
        animation: bool = True,
        palette: list[int] = [],
        delay: float = 0.099999,
        speed_step: int = 1,
        hold: float = 0.0,
    ):
        self.frames = frames
        self.zoom = zoom
        self.width = width
        self.height = height
        self.version = version
        self.animation = animation
        if not self.animation:
            self.frames = 1
        self.palette = palette
        self.delay = delay
        self.speed_step = speed_step
        self.hold = hold


class Template:
    def __init__(self, path: str, logger: Logger | None = None):
        self.path = path
        self.logger = logger if logger is not None else Logger()
        self.height = 300
        self.width = 400
        self.framerate = 20
        self.background_color = (255, 255, 255)
        self.zip_file = zipfile.ZipFile(self.path)
        self.xml_content = self._read_xml_content()
        self.frames = self._parse_frames()
        self.config = self._load_config()

    def _read_xml_content(self) -> ElementTree.Element[str]:
        with self.zip_file.open("inventory.xml") as xml_file:
            content_str = xml_file.read().decode("utf-8")
        return ElementTree.fromstring(content_str)

    def _parse_frames(self) -> list[Frame]:
        root = self.xml_content
        frames: list[Frame] = []
        movie = root
        if movie is not None:
            self.width = int(movie.get("width", self.width))
            self.height = int(movie.get("height", self.height))
            self.framerate = int(movie.get("framerate", self.framerate))

            background = movie.find("background")
            if background is not None:
                try:
                    color_str = background.get("color", "#ffffff")
                    self.background_color = tuple(
                        int(color_str[i : i + 2], 16) for i in (1, 3, 5)
                    )
                except Exception as e:
                    self.logger.warning(
                        f"Error occurred while parsing background color: {e}"
                    )

            library = movie.find("./frame/library")
            if library is None:
                self.logger.panic("Invalid template structure: Missing library element")
                raise ValueError("Invalid template structure: Missing library element")

            valid_ids: set[str] = set()
            has_neutral = False
            has_sample = False
            for bitmap in library.findall("bitmap"):
                b_id = bitmap.get("id", "")
                if b_id.startswith("Disp"):
                    valid_ids.add(b_id)
                if b_id.startswith("DispTransparent"):
                    has_neutral = True
                if b_id.startswith("DispSamples"):
                    has_sample = True
            divisor = 4
            if has_neutral:
                self.logger.debug("Template contains transparent layer (neutral)")
                divisor += 1
            if has_sample:
                self.logger.debug("Template contains sample layer")
                divisor += 1
            total_frames = len(valid_ids) // divisor
            for i in range(total_frames):
                frames.append(self._load_frame(i))
        self.logger.debug(f"Parsed {len(frames)} frames from template")
        return frames

    def _load_frame(self, index: int) -> Frame:
        library = self.xml_content.find("./frame/library")
        if library is None:
            self.logger.panic("Invalid template structure: Missing library element")
            raise ValueError("Invalid template structure: Missing library element")

        map_image_el = library.find(f"bitmap[@id='DispMapData{index}']")
        sel_image_el = library.find(f"bitmap[@id='DispSelData{index}']")
        light_image_el = library.find(f"bitmap[@id='DispLightData{index}']")
        dark_image_el = library.find(f"bitmap[@id='DispDarkData{index}']")
        transparent_image_el = library.find(f"bitmap[@id='DispTransparentData{index}']")
        sample_image_el = library.find(f"bitmap[@id='DispSamples{index}']")
        if (
            map_image_el is None
            or sel_image_el is None
            or light_image_el is None
            or dark_image_el is None
        ):
            self.logger.panic(f"Missing images for frame {index} in template")
            raise ValueError(f"Missing images for frame {index} in template")

        transparent_data = None
        if transparent_image_el is not None:
            transparent_data = self._load_image(transparent_image_el.get("import", ""))

        sample_data = None
        if sample_image_el is not None:
            sample_data = self._load_image(sample_image_el.get("import", ""))

        return Frame(
            index,
            self._load_image(map_image_el.get("import", "")),
            self._load_image(sel_image_el.get("import", "")),
            self._load_image(light_image_el.get("import", "")),
            self._load_image(dark_image_el.get("import", "")),
            neutral_data=transparent_data,
            sample_data=sample_data,
        )

    def _load_image(self, image_name: str) -> Image.Image:
        try:
            with self.zip_file.open(image_name) as image_file:
                return Image.open(image_file).convert("RGBA")
        except KeyError:
            self.logger.panic(f"Image '{image_name}' not found in template zip file")
            raise ValueError(f"Image '{image_name}' not found in template zip file")

    def _load_config(self) -> TemplateConfig:
        try:
            with self.zip_file.open("MakeSweetConfig.hx") as config_file:
                config_str = config_file.read().decode("utf-8")
                return self._parse_config(config_str)
        except KeyError:
            self.logger.panic("MakeSweetConfig.hx not found in template zip file")
            raise ValueError("MakeSweetConfig.hx not found in template zip file")
        except Exception as e:
            self.logger.panic(f"Error parsing MakeSweetConfig.hx: {e}")
            raise ValueError(f"Error parsing MakeSweetConfig.hx: {e}")

    def _parse_config(self, config_str: str) -> TemplateConfig:
        lines = [
            line.strip()
            for line in config_str.splitlines()
            if line.strip() and not line.strip().startswith("//")
        ]
        config_dict = {}
        for line in lines:
            if line.startswith("public static var"):
                parts_space = line.split()
                parts_equal = line.split("=", 1)
                if len(parts_space) >= 5:
                    key = parts_space[3]
                    value_str = parts_equal[1].strip().rstrip(";")
                    config_dict[key] = self._parse_value(value_str)
        return TemplateConfig(
            zoom=config_dict.get("zoom", 1.0),
            width=config_dict.get("width", 400),
            height=config_dict.get("height", 300),
            version=config_dict.get("version", 2),
            animation=config_dict.get("animation", True),
            frames=config_dict.get("frames", 41),
            palette=config_dict.get("palette", [7, 17, 27, 34]),
            delay=config_dict.get("delay", 0.099999),
            speed_step=config_dict.get("speed_step", 1),
            hold=config_dict.get("hold", 0.0),
        )

    def remove_frame(self, index: int):
        for i, frame in enumerate(self.frames):
            if frame.number == index:
                del self.frames[i]
                return
        self.logger.warning(
            f"Attempted to remove non-existent frame {index} from template"
        )

    def _parse_value(self, value_str: str):
        if value_str.startswith("[") and value_str.endswith("]"):
            return [int(x.strip()) for x in value_str[1:-1].split(",")]
        elif value_str.lower() == "true":
            return True
        elif value_str.lower() == "false":
            return False
        else:
            try:
                if "." in value_str:
                    return float(value_str)
                else:
                    return int(value_str)
            except ValueError:
                return value_str.strip('"')
