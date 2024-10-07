from typing import Optional
from PIL import ImageFont
from PIL import ImageDraw

from stabby import conf
config = conf.load_conf()


def add_text_to_image(
        draw: ImageDraw.ImageDraw,
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
