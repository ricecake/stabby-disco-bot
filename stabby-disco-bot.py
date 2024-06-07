from stabby import conf, bot, schema
config = conf.load_conf()

schema.init_db()

bot.client.run(config.token)
