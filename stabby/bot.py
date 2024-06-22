from typing import Callable, Iterable, Literal, Optional, OrderedDict, List, Text

import logging
import io
import aiohttp
import discord
from discord import File, app_commands
from functools import wraps

from stabby import conf, generation, grammar
from stabby.schema import db_session, Preferences, Generation, ServerPreferences
from sqlalchemy import select

http_client: Optional[aiohttp.ClientSession] = None
config = conf.load_conf()
logger = logging.getLogger('discord.stabby')
karma_grammar = grammar.Grammar(config.karma_grammar)
prompt_grammar = grammar.Grammar(config.prompt_grammar)

default_ratelimiter = app_commands.checks.cooldown(config.ratelimit_count, config.ratelimit_window)
db_ratelimiter = app_commands.checks.cooldown(config.ratelimit_count * 10, config.ratelimit_window)
ephemeral_ratelimiter = app_commands.checks.cooldown(config.ratelimit_count * 30, config.ratelimit_window)


async def interaction_must_reply(interaction: discord.Interaction, message: str, ephemeral: bool = True, silent: bool = True):
    if not interaction.response.is_done():
        await interaction.response.send_message(message, ephemeral=ephemeral, silent=silent)
    else:
        await interaction.followup.send(message, ephemeral=ephemeral, silent=silent)


def tokenize_prompt(prompt: Optional[str]) -> list[str]:
    if prompt is None:
        return []
    return [s.strip() for s in prompt.split(',')]

def rejoin_prompt_tokens(tokens: Optional[Iterable[Text]]) -> Optional[Text]:
    if tokens is None or not tokens:
        return None
    return ', '.join(tokens)

def union_prompts(first: Optional[str], second: Optional[str]) -> Optional[str]:
    first_tokens = tokenize_prompt(first)
    second_tokens = tokenize_prompt(second)

    return rejoin_prompt_tokens(dict.fromkeys(first_tokens + second_tokens))

def subtract_prompts(first: Optional[str], second: Optional[str]) -> Optional[str]:
    first_tokens = tokenize_prompt(first)
    second_tokens = tokenize_prompt(second)

    base_set = dict.fromkeys(first_tokens)
    for remove in second_tokens:
        base_set.pop(remove, None)

    return rejoin_prompt_tokens(base_set)

def apply_defaults(interaction: discord.Interaction, request_params: dict) -> dict:
    global_defaults = config.global_defaults.model_dump()

    if interaction.guild_id is not None:
        server_prefs = ServerPreferences.get_server_preferences(
            interaction.guild_id)
        server_defaults = server_prefs.get_defaults()
    else:
        server_defaults = {}

    user_prefs = Preferences.get_user_preferences(interaction.user.id)
    user_defaults = user_prefs.get_defaults()

    default_params = {}
    for defs in (global_defaults, server_defaults, user_defaults):
        default_params.update(defs)

    return apply_default_params(request_params, default_params)


def apply_default_params(request_params: dict, default_params: dict) -> dict:
    new_params = request_params.copy()
    for field, value in default_params.items():
        if new_params.get(field) is None:
            new_params[field] = value

    return new_params


async def generation_interaction(
    interaction: discord.Interaction,
    prompt: str,
    negative_prompt: Optional[str] = None,
    overlay: Optional[bool] = None,
    spoiler: Optional[bool] = None,
    tiling: Optional[bool] = None,
    restore_faces: Optional[bool] = None,
    use_refiner: Optional[bool] = None,
    width: Optional[int] = None,
    height: Optional[int] = None,
    seed: Optional[int] = None,
    cfg_scale: Optional[float] = None,
    steps: Optional[int] = None,
) -> None:
    assert interaction.guild is not None
    assert http_client is not None
    assert interaction.command is not None

    if not interaction.response.is_done():
        await interaction.response.defer(ephemeral=True)
    try:
        saved_server_prefs = ServerPreferences.get_server_preferences(interaction.guild.id)
        with db_session() as session:
            session.add(saved_server_prefs)

            gen_instance = Generation(
                user_id=interaction.user.id,
                prompt=prompt,
                negative_prompt=negative_prompt,
                overlay=overlay,
                spoiler=spoiler,
                tiling=tiling,
                restore_faces=restore_faces,
                seed=seed,
                width=width,
                height=height,
                cfg_scale=cfg_scale,
                steps=steps,
                use_refiner=use_refiner,
            )
            session.add(gen_instance)
            session.commit()

            params = dict(
                prompt=prompt,
                negative_prompt=negative_prompt,
                overlay=overlay,
                spoiler=spoiler,
                tiling=tiling,
                restore_faces=restore_faces,
                seed=seed,
                width=width,
                height=height,
                cfg_scale=cfg_scale,
                steps=steps,
                use_refiner=use_refiner,
            )
            new_params = apply_defaults(interaction, params)

            new_params['negative_prompt'] = subtract_prompts(
                new_params.get('negative_prompt'),
                new_params.get('prompt')
            )

            new_params['prompt'] = subtract_prompts(
                new_params.get('prompt'),
                saved_server_prefs.required_negative_prompt
            )

            new_params['negative_prompt'] = union_prompts(
                new_params.get('negative_prompt'),
                saved_server_prefs.required_negative_prompt
            )

            file, reprompt_struct = await generation.generate_ai_image(
                http_client=http_client,
                **new_params
            )
            await interaction.followup.send(generation.prettify_params(reprompt_struct), ephemeral=True)

            message = await interaction.followup.send(
                content='`{}` for {} via {}'.format(prompt, interaction.user.display_name, interaction.command.name),
                file=file,
                wait=True,
                silent=True,
            )  # type: ignore[call-overload]

            session.add(gen_instance)
            gen_instance.message_id = message.id
            gen_instance.update_from_dict(reprompt_struct)
            session.commit()

    except Exception as ex:
        logger.exception(ex)
        display = generation.prettify_params(dict(
            prompt=prompt,
            negative_prompt=negative_prompt,
            overlay=overlay,
        ))
        await interaction_must_reply(interaction, "Generation is offline right now, but I would have given you: {}".format(display), silent=True)


async def default_error_handler(interaction: discord.Interaction, error: app_commands.AppCommandError):
    logger.error(error)

    match type(error):
        case app_commands.CommandOnCooldown:
            await interaction_must_reply(interaction, str(error), ephemeral=True)
        case _:
            await interaction_must_reply(interaction, "Something went wrong...", ephemeral=True)


class StabbyDiscoBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self.tree.error(default_error_handler)

    async def setup_hook(self):
        for guild_id in config.guilds:
            logger.info("Configuring guild {}".format(guild_id))
            guild = discord.Object(id=guild_id)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)


client = StabbyDiscoBot()


@client.event
async def on_guild_join(guild):
    logger.info("Joined guild")


@client.event
async def on_ready():
    assert client.user is not None
    logger.info(f'Logged in as {client.user} (ID: {client.user.id})')
    global http_client
    http_client = aiohttp.ClientSession()
    logger.info('------')


@client.event
async def on_resumed():
    logger.info("Resuming session")
    global http_client
    http_client = aiohttp.ClientSession()


@client.event
async def on_disconnect():
    logger.info("Handling disconnect")
    if http_client is not None:
        await http_client.close()


@client.tree.command()
@ephemeral_ratelimiter
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


def make_autocompleter(field: str) -> discord.app_commands.commands.AutocompleteCallback:
    async def autocompleter(interaction: discord.Interaction, current: str) -> List[discord.app_commands.models.Choice]:
        logger.info("Autocomplete [{}] [{}]".format(field, current))
        column = getattr(Generation, field)
        with db_session() as session:
            query = (select(Generation)
                     .where(column.is_not(None))
                     .where(column != '')
                     .where(column.icontains(current, autoescape=True))
                     .order_by(Generation.created_at.desc()))

            saved_generations = session.scalars(query)
            matches = OrderedDict()

            for curr_generation in saved_generations:
                value = getattr(curr_generation, field)
                if len(value) > 100:
                    continue

                matches[value] = app_commands.Choice(name=value, value=value)

                if len(matches) >= 25:
                    break

            return list(matches.values())

    return autocompleter


@client.tree.command()
@app_commands.describe(
    prompt="The prompt to generate an image based off of",
    negative_prompt="The negative prompt to keep things out of the image",
    overlay="Should a text overlay be added with the image prompt?",
    tiling="Request that image tile",
    spoiler="Hide image behind spoiler filter",
    restore_faces="Fix faces in post processing"
)
@app_commands.autocomplete(
    prompt=make_autocompleter('prompt'),
    negative_prompt=make_autocompleter('negative_prompt'),
)
@default_ratelimiter
async def generate(
    interaction: discord.Interaction,
    prompt: str,
    negative_prompt: Optional[str] = None,
    overlay: Optional[bool] = None,
    spoiler: Optional[bool] = None,
    tiling: Optional[bool] = None,
    restore_faces: Optional[bool] = None,
):
    """Generates an image"""
    await generation_interaction(
        interaction,
        prompt=prompt,
        negative_prompt=negative_prompt,
        overlay=overlay,
        spoiler=spoiler,
        tiling=tiling,
        restore_faces=restore_faces,
    )


@client.tree.command()
@app_commands.describe(
    prompt="The prompt to generate an image based off of",
    negative_prompt="The negative prompt to keep things out of the image",
    recycle_seed='Use the same seed as the prompt being regenerated',
    restore_faces="Fix faces in post processing",
    spoiler="Hide image behind spoiler filter",
    overlay="Should a text overlay be added with the image prompt?",
    tiling="Request that image tile",
    message_id='The ID of the message to regenerate',
)
@app_commands.autocomplete(
    prompt=make_autocompleter('prompt'),
    negative_prompt=make_autocompleter('negative_prompt'),
)
@default_ratelimiter
async def regen(
        interaction: discord.Interaction,
        prompt: Optional[str] = None,
        negative_prompt: Optional[str] = None,
        recycle_seed: Optional[bool] = None,
        restore_faces: Optional[bool] = None,
        spoiler: Optional[bool] = None,
        overlay: Optional[bool] = None,
        tiling: Optional[bool] = None,
        message_id: Optional[str] = None,
):
    """Regenerate an image from a previous generation"""
    await interaction.response.defer(thinking=True, ephemeral=True)
    image_message_id = None
    if message_id is not None:
        image_message_id = int(message_id)

    params = {
        field: value for field, value in dict(
            prompt=prompt,
            negative_prompt=negative_prompt,
            restore_faces=restore_faces,
            spoiler=spoiler,
            overlay=overlay,
            tiling=tiling,
        ).items() if value is not None
    }

    stmnt = None
    if image_message_id:
        stmnt = select(Generation).where(Generation.message_id == image_message_id).order_by(Generation.created_at.desc())
    else:
        stmnt = select(Generation).where(Generation.user_id == interaction.user.id).order_by(Generation.created_at.desc())

    regen_params = None
    with db_session() as session:
        previous_gen = session.scalar(stmnt)
        if previous_gen is None:
            await interaction.followup.send("I can't seem to find a message to regenerate...")
            return

        regen_params = previous_gen.regen_params()
        regen_params = apply_default_params(params, regen_params)

    # This is also where more preference merging would go
    if recycle_seed is not None and not recycle_seed:
        regen_params['seed'] = -1

    await generation_interaction(
        interaction,
        **regen_params
    )


@client.tree.command()
@app_commands.describe(
    default_negative_prompt="A negative prompt to apply if none is provided",
    required_negative_prompt="A negative prompt to append to all prompts",
)
@app_commands.autocomplete(
    default_negative_prompt=make_autocompleter('default_negative_prompt'),
    required_negative_prompt=make_autocompleter('required_negative_prompt'),
)
@app_commands.default_permissions(administrator=True)
@db_ratelimiter
async def set_server_preferences(
        interaction: discord.Interaction,
        required_negative_prompt: Optional[str] = None,
        default_negative_prompt: Optional[str] = None,
):
    """Set server specific defaults and policies for the bot to adhere to"""
    await interaction.response.defer(thinking=True, ephemeral=True)
    settings = {
        'required_negative_prompt': required_negative_prompt,
        'default_negative_prompt': default_negative_prompt,
    }
    settings_keys = list(settings.keys())
    for key in settings_keys:
        if settings[key] is None:
            settings.pop(key, None)

    assert interaction.guild is not None
    saved_server_prefs = ServerPreferences.get_server_preferences(server_id=interaction.guild.id)
    with db_session() as session:
        session.add(saved_server_prefs)
        saved_server_prefs.update_from_dict(settings)
        session.commit()

    await interaction.followup.send(F"Server [{interaction.guild.name}] preferences saved as: {saved_server_prefs.as_dict()}")


@client.tree.command()
@app_commands.describe(
    clear_field='The server preference to clear'
)
@app_commands.default_permissions(administrator=True)
@db_ratelimiter
async def unset_server_preferences(
        interaction: discord.Interaction,
        clear_field: Literal['default_negative_prompt',
                             'required_negative_prompt']
) -> None:
    """Unset a server specific default or policies"""
    await interaction.response.defer(thinking=True, ephemeral=True)
    assert interaction.guild is not None
    saved_server_prefs = ServerPreferences.get_server_preferences(server_id=interaction.guild.id)
    with db_session() as session:
        session.add(saved_server_prefs)
        setattr(saved_server_prefs, clear_field, None)
        session.commit()
    await interaction.followup.send(F"Server preferences saved as: {saved_server_prefs.as_dict()}")


@client.tree.command()
@app_commands.describe()
@db_ratelimiter
async def preferences(interaction: discord.Interaction):
    """Function"""
    await interaction.response.send_message('Poop', ephemeral=True)


# This context menu command only works on messages
@client.tree.context_menu(name='AI-ify this bad boy')
@default_ratelimiter
async def ai_message_content(interaction: discord.Interaction, message: discord.Message):
    prompt = message.clean_content
    negative = "boring, dull, NSFW, porn, nudity"

    await generation_interaction(interaction, prompt=prompt, negative_prompt=negative)


def only_self_messages(f: Callable):
    @wraps(f)
    async def wrapper(interaction: discord.Interaction, message: discord.Message):
        assert client.user is not None
        if message.author.id != client.user.id:
            await interaction.response.send_message("Unfortunately, I didn't make that one...", ephemeral=True)
            return
        return await f(interaction, message)

    return wrapper


# This context menu command only works on messages
@client.tree.context_menu(name='Again! Again!')
@default_ratelimiter
async def regen_with_new_seed(interaction: discord.Interaction, message: discord.Message):
    await interaction.response.defer(ephemeral=True)

    regen_params = None
    with db_session() as session:
        message_id = message.id
        saved_generation = session.scalar(
            select(Generation).where(Generation.message_id == message_id))
        if saved_generation is None:
            await interaction.followup.send("Unfortunately, that one isn't in my database", ephemeral=True)
            return
        regen_params = saved_generation.regen_params()

    regen_params['seed'] = -1
    await generation_interaction(
        interaction,
        **regen_params
    )


# This context menu command only works on messages
@client.tree.context_menu(name='Sans overlay')
@default_ratelimiter
async def regen_without_overlay(interaction: discord.Interaction, message: discord.Message):
    await interaction.response.defer(ephemeral=True)

    regen_params = None
    with db_session() as session:
        message_id = message.id
        saved_generation = session.scalar(
            select(Generation).where(Generation.message_id == message_id))
        if saved_generation is None:
            await interaction.followup.send("Unfortunately, that one isn't in my database", ephemeral=True)
            return
        regen_params = saved_generation.regen_params()

    regen_params['overlay'] = False
    await generation_interaction(
        interaction,
        **regen_params
    )


# This context menu command only works on messages
@client.tree.context_menu(name='Censor Generated Image')
@only_self_messages
@ephemeral_ratelimiter
async def censor_generated_image(interaction: discord.Interaction, message: discord.Message):
    await interaction.response.defer(ephemeral=True)

    new_files = []
    for file in message.attachments:
        buf = io.BytesIO()
        await file.save(buf)
        new_file = File(fp=buf, filename=file.filename,
                        description=file.description, spoiler=True)
        new_files.append(new_file)

    await message.edit(attachments=new_files)

    await interaction.followup.send('Sorry about the upset!', ephemeral=True)

# This context menu command only works on messages


@client.tree.context_menu(name='Get Generation Parameters')
@only_self_messages
@db_ratelimiter
async def fetch_generation_params(interaction: discord.Interaction, message: discord.Message):
    await interaction.response.defer(ephemeral=True)

    with db_session() as session:
        message_id = message.id
        saved_generation = session.scalar(
            select(Generation).where(Generation.message_id == message_id))
        if saved_generation is None:
            await interaction.followup.send("Unfortunately, that one isn't in my database", ephemeral=True)
            return

        display = generation.prettify_params(saved_generation.regen_params())
        await interaction.followup.send(display)
