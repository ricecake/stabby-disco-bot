import asyncio
import logging

from stabby import conf, bot, schema
from stabby.handlers import app

config = conf.load_conf()
logger = logging.getLogger('main')

schema.init_db()

async def run_bot():
    try:
        await bot.client.start(config.token)
    except Exception as ex:
        logger.error(ex)
        bot.client.dispatch('disconnect')

if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    loop.create_task(run_bot())

    app.run(
        host='0.0.0.0',
        port=5000,
        loop=loop,
        debug=True,
    )
