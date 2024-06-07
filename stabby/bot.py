from typing import Optional

import logging
import io
import aiohttp
import discord
from discord import File, app_commands

from stabby import conf, generation, grammar

session = None
config = conf.load_conf()
logger = logging.getLogger('discord')
karma_grammar = grammar.Grammar(config.karma_grammar)
prompt_grammar = grammar.Grammar(config.prompt_grammar)

async def generation_interaction(
        interaction: discord.Interaction,
        prompt: str,
        negative: Optional[str] = None,
        overlay: bool = True,
        spoiler: bool = False,
        tiling: bool = False,
        restore_faces: bool = True,
        use_refiner: bool = True,
        seed: int = -1,
        cfg_scale: float = 7.0,
        steps: int = 20
    ) -> None:
    await interaction.response.defer(ephemeral=True)
    try:
        file, reprompt_struct = await generation.generate_ai_image(
            session=session,
            prompt=prompt,
            negative_prompt=negative,
            overlay=overlay,
            spoiler=spoiler,
            tiling=tiling,
            restore_faces=restore_faces,
            seed=seed,
            cfg_scale=cfg_scale,
            steps=steps,
            use_refiner=use_refiner,
        )
        await interaction.followup.send(generation.prettify_params(**reprompt_struct), ephemeral=True)
        await interaction.followup.send(
            content='`{}` for {} via {}'.format(prompt, interaction.user.display_name, interaction.command.name),
            file=file,
            silent=True)
    except Exception as ex:
        logger.info(ex)
        display = generation.prettify_params(
            prompt=prompt,
            negative=negative,
            overlay=overlay,
        )
        await interaction.followup.send("Generation is offline right now, but I would have given you: {}".format(display), silent=True)

default_ratelimiter = app_commands.checks.cooldown(config.ratelimit_count, config.ratelimit_window)

async def default_error_handler(interaction: discord.Interaction, error: app_commands.AppCommandError):
    logger.error(str(error))

    if isinstance(error, app_commands.CommandOnCooldown):
        await interaction.response.send_message(str(error), ephemeral=True)

class StabbyDiscoBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self.tree.error(default_error_handler)

    async def setup_hook(self):
        for guild_id in config.guilds:
            guild = discord.Object(id=guild_id)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)

client = StabbyDiscoBot()

@client.event
async def on_ready():
    logger.info(f'Logged in as {client.user} (ID: {client.user.id})')
    global session
    session = aiohttp.ClientSession()
    logger.info('------')

@client.event
async def on_resumed():
    logger.info("Resuming session")
    global session
    session = aiohttp.ClientSession()

@client.event
async def on_disconnect():
    logger.info("Handling disconnect")
    await session.close()

@client.tree.command()
async def inspire(interaction: discord.Interaction):
    """Some old fashioned AI inspiration"""
    inspiration = prompt_grammar.generate()
    await interaction.response.send_message(content=inspiration, silent=True)

@client.tree.command()
@default_ratelimiter
async def bezos(interaction: discord.Interaction):
    """Right into the sun with ya'"""
    await generation_interaction(
        interaction,
        prompt="Jeff bezos on fire, falling into the sun, space flight, giant catapult,  fear, man engulfed in flames",
        negative_prompt="happy, excited, joy, cool, stoic, strong",
        overlay=False
    )


@client.tree.command(name="karma-wheel")
@default_ratelimiter
async def karma_wheel(interaction: discord.Interaction):
    """Spin the wheel, see what they get"""
    prompt = karma_grammar.generate()

    await generation_interaction(interaction, prompt=prompt)


@client.tree.command()
@app_commands.describe(
    prompt="The prompt to generate an image based off of",
    negative="The negative prompt to keep things out of the image",
    overlay="Should a text overlay be added with the image prompt?",
    tiling="Request that image tile",
    spoiler="Hide image behind spoiler filter",
    restore_faces="Fix faces in post processing"
)
@default_ratelimiter
async def generate(
        interaction: discord.Interaction,
        prompt: str,
        negative: Optional[str] = None,
        overlay: bool = True,
        spoiler: bool = False,
        tiling: bool = False,
        restore_faces: bool = True
    ):
    """Generates an image"""
    await generation_interaction(
        interaction,
        prompt=prompt,
        negative=negative,
        overlay=overlay,
        spoiler=spoiler,
        tiling=tiling,
        restore_faces=restore_faces,
    )


# This context menu command only works on messages
@client.tree.context_menu(name='AI-ify this bad boy')
@default_ratelimiter
async def ai_message_content(interaction: discord.Interaction, message: discord.Message):
    prompt = message.clean_content
    negative = "boring"

    await generation_interaction(interaction, prompt=prompt, negative=negative)

# This context menu command only works on messages
@client.tree.context_menu(name='Censor Generated Image')
async def censor_generated_image(interaction: discord.Interaction, message: discord.Message):
    if message.author.id != client.user.id:
        await interaction.response.send_message("Unfortunately, I didn't make that one...", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)

    new_files = []
    for file in message.attachments:
        buf = io.BytesIO()
        await file.save(buf)
        new_file = File(fp=buf, filename=file.filename, description=file.description, spoiler=True)
        new_files.append(new_file)

    await message.edit(attachments=new_files)

    await interaction.followup.send('Sorry about the upset!', ephemeral=True)

