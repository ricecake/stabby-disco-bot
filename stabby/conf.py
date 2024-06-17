from typing import Optional
import yaml
import pydantic 

conf = None

class GlobalDefaults(pydantic.BaseModel):
        negative_prompt: Optional[str] = None
        overlay: bool = True
        spoiler: bool = False
        tiling: bool = False
        restore_faces: bool = True
        use_refiner: bool = True
        width: int = 1024
        height: int = 1024
        seed: int = -1
        cfg_scale: float = 7.0
        steps: int = 20

class Conf(pydantic.BaseModel):
    invite_url: str
    token: str
    karma_grammar: str
    prompt_grammar: str
    title_font: str = pydantic.Field(default='droid-sans-mono.ttf')
    artist_font: str = pydantic.Field(default='droid-sans-mono.ttf')
    sd_host: str = pydantic.Field(default='http://127.0.0.1:7860')
    guilds: list[int] = pydantic.Field(default_factory=lambda: list())
    ratelimit_count: int = pydantic.Field(default=1)
    ratelimit_window: float = pydantic.Field(default=20.0)
    global_defaults: GlobalDefaults


def load_conf() -> Conf:
    global conf
    if conf is None:
        conf_data = {}
        with open('conf.yaml') as file:
            conf_data = yaml.load(file, Loader=yaml.FullLoader)

        conf = Conf(**conf_data)

    return conf
