# MakeSweet-py

Python port of [MakeSweet](https://github.com/paulfitz/makesweet) for generating animated GIFs and rendered frames from MakeSweet ZIP templates.

Render animated GIFs from a MakeSweet template and one or more input images, directly from Python.

## Features

- Render animated GIFs from MakeSweet ZIP templates
- Export individual rendered frames
- Support for templates with multiple image inputs
- Optional fast rendering mode
- Auto-zoom support
- Debug and statistics modes
- Packaged binary support with PyInstaller

## What to expect

Like the original MakeSweet tool, this project generates animated GIFs using a template and one or more images.

Examples:

| Original Image(s)                                                                                 | Template Used                                                                                | Result                                         |
|:-------------------------------------------------------------------------------------------------:|:--------------------------------------------------------------------------------------------:|:----------------------------------------------:|
| <img src="./docs/images/neko_arc.png" width=30%>                                                  | [flag](https://github.com/paulfitz/makesweet/blob/master/templates/flag.zip)                 | <img src="./docs/results/neko_arc_flag.gif">   |
| <img src="./docs/images/neko_arc.png" width=30%> + <img src="./docs/images/neko_arc_bubbles.png"> | [heart-locket](https://github.com/paulfitz/makesweet/blob/master/templates/heart-locket.zip) | <img src="./docs/results/neko_arcs_heart.gif"> |

## Configuration

> [!IMPORTANT]
> This project uses [uv](https://docs.astral.sh/uv/) as the package manager.  
> All commands below assume that `uv` is already installed and configured on your system.

1. Clone the repository:
    ```bash
    git clone <repo-url>
    cd makesweet-py
    ```

2. Create the virtual environment and install dependencies:
    ```bash
    uv sync --frozen
    ```

## Usage

Run the tool with:

```bash
uv run src/main.py <template_path> --inputs <path_image_1> <path_image_2> --gif <output_path>
```

Example:

```bash
uv run src/main.py ./cool_template.zip \
  --inputs ./docs/images/neko_arc.png \
  --gif ./output.gif
```

### Arguments

The CLI uses `argparse` for argument parsing.

| Argument            | Attribute       |          Type | Default | Purpose                                                          |
| ------------------- | --------------- | ------------: | ------: | ---------------------------------------------------------------- |
| `zip` (positional)  | `zip_path`      |           str |       - | Path to the MakeSweet ZIP template (required)                    |
| `--inputs`          | `input_paths`   |     list[str] |    `[]` | One or more input image paths to composite into the template     |
| `--width`           | `width`         |           int |    `-1` | Output width (`-1` = auto / keep template width)                 |
| `--height`          | `height`        |           int |    `-1` | Output height (`-1` = auto / keep template height)               |
| `--first-frame`     | `first_frame`   |           int |     `0` | First frame index to process                                     |
| `--last-frame`      | `last_frame`    |           int |    `-1` | Last frame index to process (`-1` = last available frame)        |
| `--single`, `-1`    | `single`        |          bool | `False` | Process only `first_frame`                                       |
| `--simple`, `-s`    | `simple`        |          bool | `False` | Use faster, lower-quality rendering (`add_simple`)               |
| `--auto-zoom`, `-z` | `auto_zoom`     |          bool | `False` | Enable auto-zoom heuristic (may increase processing time)        |
| `--stats`, `-t`     | `stats`         |          bool | `False` | Display rendering statistics                                     |
| `--debug`, `-D`     | `debug`         |          bool | `False` | Enable debug logging                                             |
| `--silent`, `-S`    | `silent`        |          bool | `False` | Suppress all logging output                                      |
| `--gif`             | `gif_path`      | Optional[str] |  `None` | Path to save the generated GIF                                   |
| `--save`            | `save_dir_path` | Optional[str] |  `None` | Directory used to save rendered frames                           |

## Building

If you want a standalone binary, the project includes a PyInstaller spec file.

Build with:

```bash
uv run pyinstaller makesweet-py.spec
```

The generated executable will be available in the `dist/` directory.

All arguments cam be used on the bin.

### Running the binary on Unix systems

Make the binary executable:

```bash
chmod +x ./dist/makesweet-py
```

Then run it normally:

```bash
./dist/makesweet-py
```

## Credits

A huge thank you to [Paul Fitzpatrick](https://github.com/paulfitz) for creating the original [MakeSweet](https://github.com/paulfitz/makesweet) project.

The math and rendering techniques behind MakeSweet are incredibly impressive (and honestly i do not understand the most part of this), and this project would not have been possible without the original implementation.

Also thanks to everyone who contributed to the open-source libraries used by this project.