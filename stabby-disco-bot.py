import asyncio
import logging
import discord

from hypercorn.asyncio import serve
from hypercorn.config import Config as HyperConfig

import stabby
from stabby import conf, bot, schema
from stabby.bot import client
from stabby.handlers import app

config = conf.load_conf()
logger = logging.getLogger('main')

discord.utils.setup_logging()

schema.init_db()

shutdown_event = asyncio.Event()

async def cleanup():
    try:
        await shutdown_event.wait()
    except asyncio.CancelledError:
        logger.info("Cleanup requested")
    finally:
        logger.info("Starting cleanup")
        await stabby.close_http_client()


async def run_app():
    async with client:
        httpConfig = HyperConfig()
        httpConfig.accesslog = logging.getLogger("http.access")
        httpConfig.errorlog = logging.getLogger("http.error")

        httpConfig.bind = ["0.0.0.0:5000"]

        client.loop.create_task(serve(app, httpConfig, shutdown_trigger=shutdown_event.wait))

        client.loop.create_task(cleanup())

        await bot.client.start(config.token)

try:
    asyncio.run(run_app())
except KeyboardInterrupt:
    logger.info("Shutting down...")
    shutdown_event.set()
