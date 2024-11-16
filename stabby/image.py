import itertools
import math
import io
import base64

from typing import Optional
from PIL import Image
from PIL import ImageDraw
from PIL import ImageFont
from PIL import PngImagePlugin

from stabby import conf
config = conf.load_conf()


def add_text_to_image(
        image: Image.Image,
        image_height: int,
        image_width: int,
        title_text: Optional[str] = "",
        artist_text: Optional[str] = "",
        title_location=25,
        artist_location=5,
        padding=5,
        opacity=100,
        title_size=25,
        artist_size=15) -> ImageDraw.ImageDraw:
    draw = ImageDraw.Draw(image)

    title_font = ImageFont.truetype(config.title_font, size=title_size)
    artist_font = ImageFont.truetype(config.artist_font, size=artist_size)
    # proceed flag only to be set if set by prerequisite requirements
    proceed = False

    title_box = (0, image_height, 0, image_height)

    if title_text != "" and title_text is not None:
        title_box = draw.textbbox((image_width / 2, image_height - title_location),
                                  title_text, font=title_font, anchor="mb")
        proceed = True

    artist_box = title_box

    if artist_text != "" and artist_text is not None:
        artist_box = draw.textbbox((image_width / 2, image_height - artist_location),
                                   artist_text, font=artist_font, anchor="mb")
        proceed = True

    draw_box = max_area([artist_box, title_box])
    draw_box = tuple(sum(x) for x in zip(
        draw_box, (-padding, -padding, padding, padding)))

    draw_box = min_area([(0, 0, image_width, image_height), draw_box])

    # Only draw if we previously set proceed flag
    if proceed is True:
        while (title_box is None or title_box[0] < draw_box[0] or title_box[1] < draw_box[1]) and title_size > artist_size:
            title_font = ImageFont.truetype(config.title_font, size=title_size)
            title_box = draw.textbbox((image_width / 2, image_height - title_location),
                                      title_text, font=title_font, anchor="mb")
            title_size -= 1

        if opacity > 0 and image.has_transparency_data:
            draw.rectangle(draw_box, fill=(255, 255, 255, opacity))

        title_outline = max(2, min(title_size // 5, 4))
        artist_outline = max(2, min(artist_size // 5, 4))

        if title_text:
            draw.text(
                (image_width / 2, image_height - title_location),
                title_text,
                font=title_font,
                anchor="mb",
                fill=(255, 255, 255),
                stroke_width=title_outline,
                stroke_fill=(0, 0, 0)
            )

        if artist_text:
            draw.text(
                (image_width / 2, image_height - artist_location),
                artist_text,
                font=artist_font,
                anchor="mb",
                fill=(255, 255, 255),
                stroke_width=artist_outline,
                stroke_fill=(0, 0, 0)
            )

    return draw


def min_area(area_list):
    # initialise
    a, b, c, d = area_list[0]

    # find max for each element
    for t in area_list:
        at, bt, ct, dt = t
        a = max(a, at)
        b = max(b, bt)
        c = min(c, ct)
        d = min(d, dt)
    tup = (a, b, c, d)
    return tup


def max_area(area_list):
    # initialise
    a, b, c, d = area_list[0]

    # find max for each element
    for t in area_list:
        at, bt, ct, dt = t
        a = min(a, at)
        b = min(b, bt)
        c = max(c, ct)
        d = max(d, dt)
    tup = (a, b, c, d)
    return tup


ASPECT_RATIOS = sorted(itertools.chain.from_iterable([
    ((math.atan(h / w), (w, h)), (math.atan(w / h), (h, w)))
    for w, h in [
        (1024, 1024),
        (1024, 960),
        (1088, 896),
        (1088, 960),
        (1152, 832),
        (1152, 896),
        (1216, 832),
        (1280, 768),
        (1344, 704),
        (1344, 768),
        (1408, 704),
        (1472, 704),
        (1536, 640),
        (1600, 640),
        (1664, 576),
        (704, 1344),
        (704, 1408),
        (768, 1280),
        (768, 1344),
        (832, 1152),
        (832, 1216),
        (896, 1088),
        (896, 1152),
        (960, 1024),
        (960, 1088),
    ]
]))

def get_closest_dimensions(width: int, height: int) -> tuple[int, int]:
    aspect = math.atan(height / width)
    diffs = [
        (abs(aspect - other), dim)
        for other, dim in ASPECT_RATIOS
    ]

    _, closest = min(diffs, key=lambda i: i[0])

    return closest


def b64_img(image: Image.Image) -> str:
    return "data:image/png;base64," + raw_b64_img(image)


def raw_b64_img(image: Image.Image) -> str:
    with io.BytesIO() as output_bytes:
        metadata = None
        for key, value in image.info.items():
            if isinstance(key, str) and isinstance(value, str):
                if metadata is None:
                    metadata = PngImagePlugin.PngInfo()
                metadata.add_text(key, value)
        image.save(output_bytes, format="PNG", pnginfo=metadata)

        bytes_data = output_bytes.getvalue()

    return str(base64.b64encode(bytes_data), "utf-8")
