import io
from typing import Any, cast
from datetime import datetime, timezone

from quart import Quart, request, jsonify, send_file
from quart.json.provider import DefaultJSONProvider

import stabby
from stabby import grammar
from stabby import conf
from stabby.schema import StabbyTable
from stabby.generation import generate_ai_image

from logging import getLogger
from quart.logging import default_handler

config = conf.load_conf()

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

getLogger(app.name).removeHandler(default_handler)

prompt_grammar = grammar.Grammar(config.prompt_grammar)

@app.get("/api/generate")
async def generate_image():
    height = request.args.get('height') or 1024
    width = request.args.get("width") or 1024
    prompt = request.args.get("prompt") or prompt_grammar.generate()
    file, _ = await generate_ai_image(http_client=await stabby.get_http_client(), prompt=prompt, steps=10)
    return await send_file(
        cast(io.BytesIO, file.fp),
        mimetype='image/png',
    )
