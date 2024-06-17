from typing import Optional
import base64
import json
import re
import io
import aiohttp
from PIL import Image, ImageDraw
from hashlib import sha512
from discord import File
import logging

from stabby import conf, image
config = conf.load_conf()
logger = logging.getLogger('discord.stabby.generator')


def gen_description(prompt):
    for c in '[]()':
        prompt = prompt.replace(c, '')

    parts = prompt.split(',', 1)
    title = " ".join(parts[0].split())

    desc = ""
    if len(parts) > 1:
        desc = " ".join(parts[1].split())
    return (title, desc)

def prettify_params(params) -> str:
    filtered_kwargs = [
        (key, value) for key, value in params.items() if value is not None
    ]

    display = []
    for key, value in filtered_kwargs:
        display_key = key.replace('_', ' ').capitalize()
        display.append('{}: {}'.format(display_key, value))

    return ', '.join(display)


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
    ):
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

        raw_image = base64.b64decode(image_data.split(",",1)[0])
        image_hash = sha512(raw_image).hexdigest()
        image_bytes = io.BytesIO(raw_image)

        working_image = Image.open(image_bytes)

        if overlay:
            title, desc = gen_description(prompt)
            image.add_text_to_image(ImageDraw.Draw(working_image, 'RGBA'), height, width, title, desc)

        buf = io.BytesIO()
        working_image.save(buf, format='PNG')
        buf.seek(0)

        base_name = re.sub(r'[^\w\d]+', '-', prompt)
        return File(fp=buf, filename="{}-{}.png".format(base_name, image_hash[0:6]), description=prompt, spoiler=spoiler), reprompt_struct
