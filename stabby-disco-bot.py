from typing import Optional
import random
import io
import base64
from PIL import Image, ImageDraw, ImageFont
import discord
from discord import File, app_commands
import re
import aiohttp
import yaml
import pydantic 

### In the future, should support using dream frame code to make up a random prompt
### also make it randomly say "do you ever just stop and thing about" and then some random weird shit from a special grammer file.

class Config(pydantic.BaseModel):
    invite_url: str
    token: str
    karma_grammar: str
    title_font: str = pydantic.Field(default='droid-sans-mono.ttf')
    artist_font: str = pydantic.Field(default='droid-sans-mono.ttf')
    sd_host: str = pydantic.Field(default='http://127.0.0.1:7860')
    guilds: list[int] = pydantic.Field(default_factory=lambda: list())

def load_config() -> Config:
    config = {}
    with open('conf.yaml') as file:
        config = yaml.load(file, Loader=yaml.FullLoader)

    return Config(**config)

config = load_config()


def add_text_to_image(draw, image_height, image_width, title_text="", artist_text="",
                        title_location= 25,
                        artist_location=5,
                        padding=5,
                        opacity=100,
                        title_size=25,
                        artist_size=15):

    title_font = ImageFont.truetype(config.title_font, size=title_size)
    artist_font = ImageFont.truetype(config.artist_font, size=artist_size)
    # proceed flag only to be set if set by prerequisite requirements
    proceed = False

    title_box = (0, image_height, 0, image_height)

    if title_text != "" and title_text is not None:
        title_box = draw.textbbox((image_width / 2, image_height - title_location),
                                    title_text, font=title_font, anchor="mb")
        proceed = True

    artist_box = title_box

    if artist_text != "" and artist_text is not None:
        artist_box = draw.textbbox((image_width / 2, image_height - artist_location),
                                    artist_text, font=artist_font, anchor="mb")
        proceed = True


    draw_box = max_area([artist_box, title_box])
    draw_box = tuple(sum(x) for x in zip(draw_box, (-padding, -padding, padding, padding)))
    
    draw_box = min_area([(0, 0, image_width, image_height), draw_box])

    # Only draw if we previously set proceed flag
    if proceed is True:
        while (title_box is None or title_box[0] < draw_box[0] or title_box[1] < draw_box[1]) and title_size > artist_size:
            title_font = ImageFont.truetype(config.title_font, size=title_size)
            title_box = draw.textbbox((image_width / 2, image_height - title_location),
                                        title_text, font=title_font, anchor="mb")
            title_size -= 1

        draw.rectangle(draw_box, fill=(255, 255, 255, opacity))

        title_outline = max(2, min(title_size//5, 4))
        artist_outline = max(2, min(artist_size//5, 4))

        draw.text((image_width / 2, image_height - title_location), title_text, font=title_font,
                    anchor="mb", fill=(255,255,255), stroke_width=title_outline, stroke_fill=(0,0,0))
        draw.text((image_width / 2, image_height - artist_location), artist_text, font=artist_font,
                    anchor="mb", fill=(255,255,255), stroke_width=artist_outline, stroke_fill=(0,0,0))

    return draw

def min_area(area_list):
    # initialise
    a, b, c, d = area_list[0]

    # find max for each element
    for t in area_list:
        at, bt, ct, dt = t
        a = max(a, at)
        b = max(b, bt)
        c = min(c, ct)
        d = min(d, dt)
    tup = (a, b, c, d)
    return tup

def max_area(area_list):
    # initialise
    a, b, c, d = area_list[0]

    # find max for each element
    for t in area_list:
        at, bt, ct, dt = t
        a = min(a, at)
        b = min(b, bt)
        c = max(c, ct)
        d = max(d, dt)
    tup = (a, b, c, d)
    return tup

def gen_description(prompt):
    for c in '[]()':
        prompt = prompt.replace(c, '')

    parts = prompt.split(',', 1)
    title = " ".join(parts[0].split())

    desc = ""
    if len(parts) > 1:
        desc = " ".join(parts[1].split())
    return (title, desc)


async def generate_ai_image(prompt: str, negative_prompt: str = None, steps: int = 20, width: int = 1024, height: int = 1024, overlay: bool = True):
    url = config.sd_host

    payload = {
        "prompt": prompt,
        "negative_prompt": negative_prompt,
        "steps": steps,
        "width": width,
        "height": height,
        "refiner_switch_at": 0.8,
        "refiner_checkpoint": "sd_xl_refiner_1.0",
        "sampler_index": "DPM++ 2M"
    }

    filtered_payload = {
        key: value for key, value in payload.items() if value is not None
    }

    async with session.post(url=f'{url}/sdapi/v1/txt2img', json=filtered_payload) as response:
        r = await response.json()

        image_data = r["images"][0]
        image = io.BytesIO(base64.b64decode(image_data.split(",",1)[0]))

        working_image = Image.open(image)

        if overlay:
            title, desc = gen_description(prompt)
            add_text_to_image(ImageDraw.Draw(working_image, 'RGBA'), height, width, title, desc)

        buf = io.BytesIO()
        working_image.save(buf, format='PNG')
        buf.seek(0)
        image = buf

        base_name = re.sub(r'[^\w\d]+', '-', prompt)
        return File(fp=image, filename="{}.png".format(base_name), description=prompt)


class Grammar():
    def __init__(self, grammar_definition) -> None:
        grammar = open(grammar_definition)

        lines = grammar.readlines()
        rules=[]
        non_terminal={} #stores total of odds of non-terminal symbol which is the key
        for l in lines:
            if l!='\n' and l[0]!='#':
                l_tokens = l.split()
                for token in l_tokens:
                    #ignore comments in grammar
                    if '#' in token:
                        l_tokens=l_tokens[0:l_tokens.index(token)]
                        break
                rules.append(l_tokens)
                #calculate cumulative probabilities
                if l_tokens[1] not in non_terminal.keys():
                    non_terminal[l_tokens[1]] = float(l_tokens[0])
                else:
                    non_terminal[l_tokens[1]] += float(l_tokens[0])

        self.rules = rules
        self.non_terminal = non_terminal

    def _sentence_generator(self, symbol, sentence) -> None:
        rand_count={}           #stores rule as value, key is the cumulative probability of the rule
        #for writing tree structure
        #base case
        if symbol not in self.non_terminal.keys():
            sentence.append(symbol)
        else:
            total_count = float(self.non_terminal[symbol])
            current_count=0
            #find all rules applicable for given non-terminal symbol
            for rule in self.rules:
                if rule[1]==symbol:
                    current_count = current_count + float(rule[0])/total_count
                    rand_count[current_count] = rule
            r = random.random()
            apply_rule = []
            #select rule according to the number generated and probabilities calculated
            for prob in sorted(rand_count.keys()):
                if prob >= r:
                    apply_rule = rand_count[prob]
                    break
            for s in apply_rule[2:len(apply_rule)]:
                self._sentence_generator(s, sentence)  #extra space for bracket

    def generate(self) -> str:
        sentence = []
        self._sentence_generator('ROOT', sentence)
        return ' '.join(sentence)


karma_grammar = Grammar(config.karma_grammar)

class MyClient(discord.Client):
    def __init__(self, *, intents: discord.Intents):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        for guild_id in config.guilds:
            guild = discord.Object(id=guild_id)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)


intents = discord.Intents.default()
client = MyClient(intents=intents)
session = None

@client.event
async def on_ready():
    print(f'Logged in as {client.user} (ID: {client.user.id})')
    global session
    session = aiohttp.ClientSession()
    print('------')

@client.event
async def on_resumed():
    print("Resuming session")
    global session
    session = aiohttp.ClientSession()


@client.event
async def on_disconnect():
    print("Handling disconnect")
    await session.close()


@client.tree.command()
async def bezos(interaction: discord.Interaction):
    """Right into the sun with ya'"""
    await interaction.response.defer(thinking=True)
    file = await generate_ai_image(prompt="Jeff bezos on fire, falling into the sun, space flight, giant catapult,  fear, man engulfed in flames", negative_prompt="happy, excited, joy, cool, stoic, strong")
    await interaction.followup.send(file=file, silent=True)

@client.tree.command(name="karma-wheel")
async def karma_wheel(interaction: discord.Interaction):
    """Spin the wheel, see what they get"""
    await interaction.response.defer(thinking=True)
    prompt = karma_grammar.generate()

    file = await generate_ai_image(prompt=prompt)
    await interaction.followup.send(file=file, silent=True)


@client.tree.command()
@app_commands.describe(
    prompt="The prompt to generate an image based off of",
    negative="The negative prompt to keep things out of the image",
    overlay="Should a text overlay be added with the image prompt?"
)
async def generate(interaction: discord.Interaction, prompt: str, negative: Optional[str] = None, overlay: bool = True):
    """Generates an image"""
    await interaction.response.defer(thinking=True)
    file = await generate_ai_image(prompt=prompt, negative_prompt=negative, overlay=overlay)
    await interaction.followup.send(file=file, silent=True)


# This context menu command only works on messages
@client.tree.context_menu(name='AI-ify this bad boy')
async def ai_message_content(interaction: discord.Interaction, message: discord.Message):
    await interaction.response.defer(thinking=True)
    prompt = message.clean_content
    negative = "boring"

    file = await generate_ai_image(prompt=prompt, negative_prompt=negative)
    await interaction.followup.send(file=file, silent=True)


client.run(config.token)
