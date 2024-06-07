from stabby import conf, bot
config = conf.load_conf()

bot.client.run(config.token)
