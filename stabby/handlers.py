import io
import logging
import math
import re
from typing import Any, cast
from datetime import datetime, timezone

from quart import Quart, request, send_file
from quart.json.provider import DefaultJSONProvider

import stabby
from stabby import grammar
from stabby import conf
from stabby import text_utils
from stabby.schema import StabbyTable
from stabby.generation import generate_ai_image

config = conf.load_conf()

logger = logging.getLogger('http.stabby.api')

def datetime_to_string(obj):
    for key, value in obj.items():
        if isinstance(value, datetime):
            obj[key] = value.replace(tzinfo=timezone.utc).isoformat()

    return obj


def _default(obj: Any):
    if isinstance(obj, StabbyTable):
        return datetime_to_string(obj.as_dict())
    else:
        return DefaultJSONProvider.default(obj)


class ModelProvider(DefaultJSONProvider):
    default = staticmethod(_default)


app = Quart("StabbyDiscoBot")
app.json = ModelProvider(app)

maker_grammar = grammar.Grammar(config.maker_grammar)


def make_random_prompt(args: dict) -> str:
    params = dict(
        quality=None,
        subject=None,
        action=None,
        environment=None,
        object=None,
        color=None,
        style=None,
        mood=None,
        lighting=None,
        perspective=None,
        texture=None,
        time_period=None,
        cultural_elements=None,
        emotion=None,
        medium=None,
    )

    for arg in params:
        passed = args.get(arg)
        if passed is not None:
            params[arg] = passed

    prompt = text_utils.template_grammar_fill(params, maker_grammar, True)

    prompt_text = ''
    for joint_fields in [
        ['subject', 'object', 'action'],
        ['perspective', 'quality', 'medium', 'style'],
    ]:
        prompt_text += ' '.join([prompt.pop(field, '') for field in joint_fields])
        prompt_text += ', '

    prompt_text += ', '.join([v for v in prompt.values() if v])
    prompt_text = re.sub(r'[ ]+', ' ', prompt_text)

    return prompt_text


RATIOS = [
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

ASPECTS = sorted([
    (math.atan(h / w), (w, h))
    for w, h in RATIOS + [(h, w) for w, h in RATIOS]
])

def get_closest_dimensions(width: int, height: int) -> tuple[int, int]:
    aspect = math.atan(height / width)
    diffs = [
        (abs(aspect - other), dim)
        for other, dim in ASPECTS
    ]

    _, closest = min(diffs, key=lambda i: i[0])

    return closest

@app.get("/api/generate")
async def generate_image():
    logger.info(request.args)
    width = int(request.args.get('w') or 1024)
    height = int(request.args.get('h') or 1024)
    palette = request.args.get('palette')

    prompt = request.args.get("prompt") or make_random_prompt(request.args)

    gen_width, gen_height = get_closest_dimensions(width=width, height=height)

    file, _ = await generate_ai_image(
        http_client=await stabby.get_http_client(),
        prompt=prompt,
        steps=20,
        width=gen_width,
        height=gen_height,
        suppress_description=True,
        resize_dimensions=(width, height),
        palette=palette,
    )

    return await send_file(
        cast(io.BytesIO, file.fp),
        mimetype='image/png',
    )
