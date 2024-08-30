import re
import traceback
from typing import Callable, Literal, Optional, List, cast, Type

import logging
import io
import discord
from discord import File, app_commands
from discord.ext import tasks
from functools import wraps

from stabby import conf, generation, grammar, schema
from stabby import text_utils
from stabby.schema import Style, db_session, Preferences, Generation, ServerPreferences
from sqlalchemy import ColumnElement, func, select

import stabby.text_utils
from stabby.text_utils import union_prompts
from stabby.text_utils import subtract_prompts
from stabby.text_utils import apply_default_params

config = conf.load_conf()
logger = logging.getLogger('discord.stabby')
karma_grammar = grammar.Grammar(config.karma_grammar)
prompt_grammar = grammar.Grammar(config.prompt_grammar)
maker_grammar = grammar.Grammar(config.maker_grammar)

def generate_ratelimiter_with_contributor_whitelist(interaction: discord.Interaction) -> Optional[app_commands.Cooldown]:
    if interaction.user.id == config.owner_id:
        return None

    return app_commands.Cooldown(config.ratelimit_count, config.ratelimit_window)


generate_ratelimiter = app_commands.checks.dynamic_cooldown(generate_ratelimiter_with_contributor_whitelist)
db_ratelimiter = app_commands.checks.cooldown(config.ratelimit_count * 10, config.ratelimit_window)
ephemeral_ratelimiter = app_commands.checks.cooldown(config.ratelimit_count * 30, config.ratelimit_window)

server_status = generation.ServerStatus()

async def interaction_must_reply(interaction: discord.Interaction, message: str, ephemeral: bool = True, silent: bool = True):
    if not interaction.response.is_done():
        await interaction.response.send_message(message, ephemeral=ephemeral, silent=silent)
    else:
        await interaction.followup.send(message, ephemeral=ephemeral, silent=silent)


def apply_defaults(interaction: discord.Interaction, request_params: dict) -> dict:
    global_defaults = config.global_defaults.model_dump()

    server_prefs = None
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

    new_params = apply_default_params(request_params, default_params)

    new_params['negative_prompt'] = subtract_prompts(
        new_params.get('negative_prompt'),
        new_params.get('prompt')
    )

    if server_prefs is not None:
        new_params['prompt'] = subtract_prompts(
            new_params.get('prompt'),
            server_prefs.required_negative_prompt
        )

        new_params['negative_prompt'] = union_prompts(
            new_params.get('negative_prompt'),
            server_prefs.required_negative_prompt
        )

    return new_params

class ImageActions(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.running = False

    # @discord.ui.button(label="Love it!", emoji="💚")
    # async def like_button(self, interaction: discord.Interaction, button: discord.ui.Button):
    #     # await interaction.response.edit_message(content=f"This is an edited button response!")
    #     await interaction.response.send_message("D'aw, thanks!", ephemeral=True)

    @discord.ui.button(label="Again! Again!", emoji="🔁")
    async def again_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.running:
            return

        self.running = True
        button.disabled = self.running
        button.label = 'Running...'

        await interaction.response.edit_message(view=self)

        regen_params = None
        with db_session() as session:
            message_id = None
            if interaction.message:
                message_id = interaction.message.id

            saved_generation = None
            if message_id:
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

        self.running = False
        button.disabled = self.running
        button.label = "Again! Again!"

        if interaction.message:
            await interaction.message.edit(view=self)


async def generation_interaction(
    interaction: discord.Interaction,
    prompt: str,
    negative_prompt: Optional[str] = None,
    style: Optional[str] = None,
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

    if not interaction.response.is_done():
        await interaction.response.defer(ephemeral=True)
    try:
        with db_session() as session:
            saved_style = session.scalar(select(Style).where(Style.user_id == interaction.user.id).where(Style.name == style))
            if saved_style:
                if saved_style.prompt:
                    prompt = cast(str, union_prompts(prompt, saved_style.prompt))
                if saved_style.negative_prompt:
                    negative_prompt = cast(str, union_prompts(negative_prompt, saved_style.negative_prompt))
                if saved_style.tiling is not None and tiling is None:
                    tiling = saved_style.tiling
                if saved_style.overlay is not None and overlay is None:
                    overlay = saved_style.overlay
                if saved_style.restore_faces is not None and restore_faces is None:
                    restore_faces = saved_style.restore_faces

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

            if not server_status.available:
                display = stabby.text_utils.prettify_params(dict(
                    prompt=prompt,
                    negative_prompt=negative_prompt,
                    overlay=overlay,
                ))
                await interaction_must_reply(interaction, "Generation is offline right now. I've saved `{}` for later.".format(display), silent=True)
                return

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

            file, reprompt_struct = await generation.generate_ai_image(
                http_client=await stabby.get_http_client(),
                **new_params
            )
            await interaction.followup.send(stabby.text_utils.prettify_params(reprompt_struct), ephemeral=True)

            message = await interaction.followup.send(
                content='`{}` for {} via {}'.format(prompt, interaction.user.display_name, interaction.command.name if interaction.command else 'Magic!'),
                file=file,
                wait=True,
                silent=True,
                view=ImageActions(),
            )  # type: ignore[call-overload]
            # TODO add various buttons for regenerate, censor, get-params, add-overlay, without overlay and whatnot.
            # That should make it easier to cut down on context menu stuff

            session.add(gen_instance)
            gen_instance.message_id = message.id
            gen_instance.update_from_dict(reprompt_struct)
            session.commit()

    except Exception as ex:
        logger.exception(ex)
        display = stabby.text_utils.prettify_params(dict(
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

    async def on_guild_join(self, guild):
        logger.info("Joined guild")

    async def on_ready(self):
        assert client.user is not None
        logger.info(f'Logged in as {client.user} (ID: {client.user.id})')
        check_server_status.start()
        logger.info('------')

    async def on_resumed(self):
        logger.info("Resuming session")

    async def on_disconnect(self):
        logger.info("Handling disconnect")


client = StabbyDiscoBot()


@tasks.loop(seconds=5)
async def check_server_status():
    available = server_status.available
    online = await generation.ping_server(await stabby.get_http_client())
    if online != server_status.observed_online:
        logger.info(f"Server status changed: online={online}")
        server_status.observed_online = online

    if not online:
        server_status.offline_count += 1

    if server_status.available != available:
        logger.info(f"Server availability changed: available={server_status.available}")
        for channel_id in config.status_notify:
            channel = client.get_channel(channel_id)
            if channel and server_status.offline_count > 60:
                await channel.send("Generation is now {}".format("available" if server_status.available else "unavailable"), silent=True)  # type: ignore

    if server_status.observed_online:
        server_status.offline_count = 0

@client.tree.command()
@ephemeral_ratelimiter
async def inspire(interaction: discord.Interaction):
    """Some old fashioned AI inspiration"""
    inspiration = prompt_grammar.generate()
    await interaction.response.send_message(content=inspiration, silent=True)

@client.tree.command()
@app_commands.describe(
    random_fill="Fill in an missing fields with random data",
    quality="The general resolution or production quality of the generated image",
    subject="The primary focus of the image (e.g., person, animal, object).",
    action="Describes what the subject is doing, adding dynamism or narrative.",
    environment="The background or scene surrounding the subject.",
    object="Secondary items that enhance the subject or story.",
    color="Dominant colors or color schemes.",
    style="The artistic style or method of rendering.",
    mood="The emotional or atmospheric quality.",
    lighting="Specific lighting conditions or effects.",
    perspective="The angle or perspective from which the scene is viewed.",
    texture="Prominent textures or materials visible in the image.",
    time_period="A specific era or historical period.",
    cultural_elements="Elements that reflect specific cultures or traditions.",
    emotion="The expressed emotion if the subject is sentient.",
    medium="Specifies the artistic medium or level of detail.",
    auto_quality="automatically fill a quality specifier",
)
@ephemeral_ratelimiter
async def prompt_maker(
    interaction: discord.Interaction,
    random_fill: bool = True,
    quality: Optional[str] = None,
    subject: Optional[str] = None,
    action: Optional[str] = None,
    environment: Optional[str] = None,
    object: Optional[str] = None,
    color: Optional[str] = None,
    style: Optional[str] = None,
    mood: Optional[str] = None,
    lighting: Optional[str] = None,
    perspective: Optional[str] = None,
    texture: Optional[str] = None,
    time_period: Optional[str] = None,
    cultural_elements: Optional[str] = None,
    emotion: Optional[str] = None,
    medium: Optional[str] = None,
    auto_quality: Optional[bool] = True,
):
    """Builds a prompt based on your inputs"""
    if quality is None and auto_quality and not random_fill:
        quality = maker_grammar.generate(start='Quality')

    params = dict(
        quality=quality,
        subject=subject,
        action=action,
        environment=environment,
        object=object,
        color=color,
        style=style,
        mood=mood,
        lighting=lighting,
        perspective=perspective,
        texture=texture,
        time_period=time_period,
        cultural_elements=cultural_elements,
        emotion=emotion,
        medium=medium,
    )

    prompt = text_utils.template_grammar_fill(params, maker_grammar, random_fill)

    prompt_text = ''
    for joint_fields in [
        ['subject', 'object', 'action'],
        ['perspective', 'quality', 'medium', 'style'],
    ]:
        prompt_text += ' '.join([prompt.pop(field, '') for field in joint_fields])
        prompt_text += ', '

    prompt_text += ', '.join([v for v in prompt.values() if v])
    prompt_text = re.sub(r'[ ]+', ' ', prompt_text)

    await interaction.response.send_message(prompt_text, silent=True)


@client.tree.command()
@generate_ratelimiter
async def bezos(interaction: discord.Interaction):
    """Right into the sun with ya'"""
    await generation_interaction(
        interaction,
        prompt="Jeff bezos on fire, falling into the sun, space flight, giant catapult,  fear, man engulfed in flames",
        negative_prompt="happy, excited, joy, cool, stoic, strong",
        overlay=False
    )


@client.tree.command(name="karma-wheel")
@generate_ratelimiter
async def karma_wheel(interaction: discord.Interaction):
    """Spin the wheel, see what they get"""
    prompt = karma_grammar.generate()

    await generation_interaction(interaction, prompt=prompt)


def make_autocompleter(field: str, table: Type[schema.StabbyTable] = Generation, same_user: bool = False, limit: int = 25) -> discord.app_commands.commands.AutocompleteCallback:
    async def autocompleter(interaction: discord.Interaction, current: str) -> List[discord.app_commands.models.Choice]:
        column: ColumnElement = getattr(table, field)
        created_at: ColumnElement = getattr(table, 'created_at')
        with db_session() as session:
            query = (select(column)
                     .where(column.is_not(None))
                     .where(column != '')
                     .where(column.icontains(current, autoescape=True))
                     .where(func.char_length(column) < 100)
                     .group_by(column)
                     .limit(min(25, limit))
                     .order_by(func.max(created_at).desc()))

            if same_user and 'user_id' in table.__table__.columns:
                user_id = getattr(table, 'user_id')
                query = query.where(user_id == interaction.user.id)

            if 'server_id' in table.__table__.columns:
                server_id = getattr(table, 'server_id')
                clause = (server_id == interaction.guild_id)
                if 'user_id' in table.__table__.columns:
                    user_id = getattr(table, 'user_id')
                    clause = clause | (user_id == interaction.user.id)

                query = query.where(clause)

            results = []
            for (value,) in list(session.execute(query)):
                (name, after_value) = table.autocomplete_formatter(field=field, value=value)
                results.append(app_commands.Choice(name=name, value=after_value))

            return results

    return autocompleter


@client.tree.command()
@app_commands.describe(
    prompt="The prompt to generate an image based off of",
    negative_prompt="The negative prompt to keep things out of the image",
    style="The user defined style to apply to the image",
    overlay="Should a text overlay be added with the image prompt?",
    tiling="Request that image tile",
    spoiler="Hide image behind spoiler filter",
    restore_faces="Fix faces in post processing"
)
@app_commands.autocomplete(
    prompt=make_autocompleter('prompt', limit=5),
    negative_prompt=make_autocompleter('negative_prompt', limit=5),
    style=make_autocompleter('name', Style, same_user=True),
)
@generate_ratelimiter
async def generate(
    interaction: discord.Interaction,
    prompt: str,
    negative_prompt: Optional[str] = None,
    style: Optional[str] = None,
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
        style=style,
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
    prompt=make_autocompleter('prompt', limit=5),
    negative_prompt=make_autocompleter('negative_prompt', limit=5),
)
@generate_ratelimiter
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

    user_prefs = Preferences.get_user_preferences(user_id=interaction.user.id)

    if overlay is None and user_prefs.regen_preserves_overlay is not None and not user_prefs.regen_preserves_overlay:
        regen_params['overlay'] = False

    if recycle_seed is not None:
        if not recycle_seed:
            regen_params['seed'] = -1
    elif user_prefs.regen_recycles_seed is not None:
        if not user_prefs.regen_recycles_seed:
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
    default_negative_prompt=make_autocompleter('negative_prompt'),
    required_negative_prompt=make_autocompleter('negative_prompt'),
)
@app_commands.default_permissions(administrator=True)
@db_ratelimiter
async def set_server_preferences(
        interaction: discord.Interaction,
        required_negative_prompt: Optional[str] = None,
        default_negative_prompt: Optional[str] = None,
):
    """Set server specific defaults and policies for the bot to adhere to"""
    # TODO make all the preference stuff live in modals
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

    await interaction.followup.send(F"Server [{interaction.guild.name}] preferences saved as: {saved_server_prefs}")


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
    await interaction.followup.send(F"Server preferences saved as: {saved_server_prefs}")


@client.tree.command()
@app_commands.describe(
    negative_prompt='The default negative prompt you would like applied',
    overlay='If your images should by default have a title overlay',
    spoiler='If your images should be hidden by spoiler tags',
    tiling='If your images should attempt to create a clean tiling',
    restore_faces='If your images should run a face defect correction process',
    use_refiner='If the images should have a few itterations of a refiner network run to increase fidelity',
    regen_recycles_seed='If a regeneration request should default to using the same seed',
    regen_preserves_overlay='If a regeneration request should use the same settings for overlay as the original',
)
@db_ratelimiter
async def set_preferences(
    interaction: discord.Interaction,
    negative_prompt: Optional[str] = None,
    overlay: Optional[bool] = None,
    spoiler: Optional[bool] = None,
    tiling: Optional[bool] = None,
    restore_faces: Optional[bool] = None,
    use_refiner: Optional[bool] = None,
    regen_recycles_seed: Optional[bool] = None,
    regen_preserves_overlay: Optional[bool] = None,
):
    """Set user specific defaults and policies for the bot to adhere to"""
    await interaction.response.defer(thinking=True, ephemeral=True)
    params = {
        field: value for field, value in dict(
            negative_prompt=negative_prompt,
            overlay=overlay,
            spoiler=spoiler,
            tiling=tiling,
            restore_faces=restore_faces,
            use_refiner=use_refiner,
            regen_recycles_seed=regen_recycles_seed,
            regen_preserves_overlay=regen_preserves_overlay,
        ).items() if value is not None
    }

    user_prefs = Preferences.get_user_preferences(user_id=interaction.user.id)
    with db_session() as session:
        session.add(user_prefs)
        user_prefs.update_from_dict(params)
        session.commit()

    await interaction.followup.send("Preferences updated to [{}]".format(user_prefs), ephemeral=True)

@client.tree.command()
@app_commands.describe(
    clear_field='The server preference to clear'
)
@db_ratelimiter
async def unset_preferences(
        interaction: discord.Interaction,
        clear_field: Literal['negative_prompt',
                             'overlay',
                             'spoiler',
                             'tiling',
                             'restore_faces',
                             'use_refiner',
                             'regen_recycles_seed',
                             'regen_preserves_overlay']
) -> None:
    """Unset a user specific default or policies"""
    await interaction.response.defer(thinking=True, ephemeral=True)
    user_prefs = Preferences.get_user_preferences(user_id=interaction.user.id)
    with db_session() as session:
        session.add(user_prefs)
        setattr(user_prefs, clear_field, None)
        session.commit()
    await interaction.followup.send(F"User preferences saved as: {user_prefs}", ephemeral=True)


@client.tree.command()
@db_ratelimiter
async def toggle_server_online(interaction: discord.Interaction):
    """Toggle the availability of owned generation server"""
    uid = interaction.user.id
    if uid != config.owner_id:
        await interaction.response.send_message("You don't seem to have a generation server...", silent=True, ephemeral=True)
    else:
        available = server_status.available
        server_status.manually_disabled = not server_status.manually_disabled
        await interaction.response.send_message("Server status is now: disabled={}".format(server_status.manually_disabled), silent=True, ephemeral=True)
        if server_status.available != available:
            logger.info(f"Server availability changed: available={server_status.available}")
            for channel_id in config.status_notify:
                channel = client.get_channel(channel_id)
                if channel:
                    await channel.send("Generation is now {}".format("available" if server_status.available else "unavailable"), silent=True)  # type: ignore


@client.tree.command()
@app_commands.describe(
    name='The name for the style'
)
@app_commands.autocomplete(
    prompt=make_autocompleter('prompt'),
    negative_prompt=make_autocompleter('negative_prompt'),
)
@db_ratelimiter
async def create_style(
        interaction: discord.Interaction,
        name: str,
        prompt: Optional[str] = None,
        negative_prompt: Optional[str] = None,
        overlay: Optional[bool] = None,
        tiling: Optional[bool] = None,
        restore_faces: Optional[bool] = None,
) -> None:
    """Create a new user defined style"""
    await interaction.response.defer(thinking=True, ephemeral=True)
    with db_session() as session:
        style = Style(
            user_id=interaction.user.id,
            name=name,
            prompt=prompt,
            negative_prompt=negative_prompt,
            overlay=overlay,
            tiling=tiling,
            restore_faces=restore_faces,
        )
        session.add(style)
        session.commit()
    await interaction.followup.send(F"Style saved as: {style}", ephemeral=True)


# This context menu command only works on messages
@client.tree.context_menu(name='AI-ify this bad boy')
@generate_ratelimiter
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
@generate_ratelimiter
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
@client.tree.context_menu(name='Enhance')
@generate_ratelimiter
async def regen_with_more_steps(interaction: discord.Interaction, message: discord.Message):
    """Regenerate with a higher step-count"""
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

    if regen_params['steps'] >= config.max_steps:
        await interaction.followup.send("I'm afraid I won't put more than {} steps into an image.".format(config.max_steps), ephemeral=True)
        return

    regen_params['steps'] = min(2 * regen_params['steps'], config.max_steps)
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


class Tweak(discord.ui.Modal):
    prompt = discord.ui.TextInput(
        custom_id='prompt',
        label='Prompt',
        style=discord.TextStyle.long,
        required=True,
    )

    negative_prompt = discord.ui.TextInput(
        custom_id='negative_prompt',
        label='Negative Prompt',
        style=discord.TextStyle.paragraph,
        required=False,
    )

    seed = discord.ui.TextInput(
        custom_id='seed',
        label='Seed',
        style=discord.TextStyle.short,
        required=False,
    )

    overlay = discord.ui.TextInput(
        custom_id='overlay',
        label='Overlay',
        style=discord.TextStyle.short,
        required=False,
    )

    tiling = discord.ui.TextInput(
        custom_id='tiling',
        label='Tile',
        style=discord.TextStyle.short,
        required=False,
    )

    def __init__(
            self,
            interaction: discord.Interaction,
            message: discord.Message,
            title: str,
    ) -> None:
        super().__init__(
            title=title,
            timeout=None,
        )

        message_id = message.id

        with db_session() as session:
            generation = session.scalar(
                select(Generation).where(Generation.message_id == message_id))

            if generation is None:
                generation = Generation(prompt=message.clean_content)

            regen_params = generation.regen_params()

        params = apply_defaults(interaction=interaction, request_params=regen_params)

        for child in self.children:
            if isinstance(child, discord.ui.TextInput):
                child.default = params.get(child.custom_id)

        self.message_id = message_id
        self.params = params

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        params = text_utils.filter_params(dict(
            prompt=self.prompt.value,
            negative_prompt=self.negative_prompt.value or None,

            seed=int(self.seed.value) if self.seed.value.isdigit() else -1,

            overlay=text_utils.convert_to_bool(self.overlay.value),
            tiling=text_utils.convert_to_bool(self.tiling.value),
        ))

        params = apply_default_params(params, self.params)

        await generation_interaction(
            interaction,
            **params
        )

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        await interaction.response.send_message('Oops! Something went wrong.', ephemeral=True)

        # Make sure we know what the error actually is
        traceback.print_exception(type(error), error, error.__traceback__)


@client.tree.context_menu(name='Promptificate')
@generate_ratelimiter
async def promptificate(interaction: discord.Interaction, message: discord.Message):
    await interaction.response.send_modal(Tweak(interaction, message, 'Promptificate'))
