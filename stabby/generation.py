import dataclasses
from typing import Any, Optional
import base64
import json
import re
import io
import aiohttp
from PIL import Image, ImageDraw
from PIL.ImageEnhance import Contrast, Sharpness, Brightness, Color
from PIL.ImageFilter import EDGE_ENHANCE
from hashlib import sha512
from discord import File
import logging

from stabby import conf, image
from stabby.text_utils import prompt_to_overlay, prettify_params
config = conf.load_conf()
logger = logging.getLogger('discord.stabby.generator')

@dataclasses.dataclass
class ServerStatus:
    offline_count: int = 0
    observed_online: bool = True
    manually_disabled: bool = False

    @property
    def available(self) -> bool:
        return self.observed_online and not self.manually_disabled


async def ping_server(http_client: aiohttp.ClientSession) -> bool:
    url = config.sd_host
    try:
        async with http_client.head(url, timeout=10) as response:
            return response.status in (200, 204)
    except Exception:
        return False

async def generate_ai_image(
        http_client: aiohttp.ClientSession,
        prompt: str,
        negative_prompt: Optional[str] = None,
        overlay: bool = True,
        spoiler: bool = False,
        tiling: bool = False,
        restore_faces: bool = True,
        use_refiner: bool = True,
        width: int = 1024,
        height: int = 1024,
        seed: int = -1,
        cfg_scale: float = 7.0,
        steps: int = 20,
        suppress_description: bool = False,
        resize_dimensions: Optional[tuple[int, int]] = None,
        palette: Optional[str] = None,
) -> tuple[File, dict[str, Any]]:
    url = config.sd_host

    payload = {
        "prompt": prompt,
        "negative_prompt": negative_prompt,
        "sampler_index": "DPM++ 2M",
        "steps": steps,
        "width": width,
        "height": height,
        "tiling": tiling,
        "seed": seed,
        "cfg_scale": cfg_scale,
        "restore_faces": restore_faces,
    }

    if use_refiner:
        payload.update({
            "refiner_switch_at": 0.8,
            "refiner_checkpoint": "sd_xl_refiner_1.0",
        })

    filtered_payload = {
        key: value for key, value in payload.items() if value is not None
    }

    logger.info("Generating: {}".format(prettify_params(payload)))

    async with http_client.post(url=f'{url}/sdapi/v1/txt2img', json=filtered_payload) as response:
        r = await response.json()

        image_data = r["images"][0]

        gen_info = json.loads(r["info"])
        filtered_gen_info = {
            key: value for key, value in gen_info.items() if key is not None and key in [
                "prompt",
                "negative_prompt",
                "seed",
                "sampler_name",
                "scheduler",
                "steps",
                "cfg_scale",
                "width",
                "height",
                "restore_faces",
                "tiling",
                "refiner_checkpoint",
                "refiner_switch_at",
                "sampler_index",
            ]
        }
        reprompt_struct = filtered_payload
        reprompt_struct.update(filtered_gen_info)
        logger.info("Generated: {}".format(prettify_params(reprompt_struct)))

        raw_image = base64.b64decode(image_data.split(",", 1)[0])
        image_hash = sha512(raw_image).hexdigest()
        image_bytes = io.BytesIO(raw_image)

        working_image = Image.open(image_bytes)

        if palette is not None:
            palette_seq = list(base64.urlsafe_b64decode(palette))

            palette_image = Image.new('P', (1, 1))
            palette_image.putpalette(palette_seq)

            for filter in [EDGE_ENHANCE]:
                working_image = working_image.filter(filter)

            for enhancement, level in (
                (Brightness, 1.1),
                (Color, 1.1),
                (Sharpness, 2),
                (Contrast, 1.6),
            ):
                enhancer = enhancement(working_image)
                working_image = enhancer.enhance(level)

            working_image = working_image.convert('RGB').quantize(palette=palette_image)

        if resize_dimensions is not None:
            logger.info("Resizing to {}".format(resize_dimensions))
            working_image = working_image.resize(size=resize_dimensions)

        if overlay:
            title, desc = prompt_to_overlay(prompt)
            if suppress_description:
                desc = None

            if resize_dimensions is not None:
                width, height = resize_dimensions

            image.add_text_to_image(working_image, height, width, title, desc)

        buf = io.BytesIO()
        working_image.save(buf, format='PNG')
        buf.seek(0)

        base_name = re.sub(r'[^\w\d]+', '-', prompt)
        return File(fp=buf, filename="{}-{}.png".format(base_name, image_hash[0:6]), description=prompt, spoiler=spoiler), reprompt_struct
