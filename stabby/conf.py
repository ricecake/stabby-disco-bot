from abc import ABCMeta, abstractmethod
from enum import Enum
from typing import Annotated, Literal, Optional, Union
import urllib.parse
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

class DatabaseEngine(str, Enum):
    sqlite = 'sqlite'
    postgres = 'psql'

class CommonDatabaseSettings(pydantic.BaseModel, metaclass=ABCMeta):
    debug: bool = False

    @abstractmethod
    def connection_url(self) -> str:
        pass

class PostgresSettings(CommonDatabaseSettings):
    engine: Literal[DatabaseEngine.postgres] = DatabaseEngine.postgres
    host: str = '127.0.0.1'
    port: int = 5432
    database: str = 'stabby_disco'
    user: Optional[str] = None
    password: str

    def connection_url(self) -> str:
        return f'postgresql+psycopg://{self.user}:{urllib.parse.quote_plus(self.password)}@{self.host}:{self.port}/{self.database}'

class SqliteSettings(CommonDatabaseSettings):
    engine: Literal[DatabaseEngine.sqlite] = DatabaseEngine.sqlite
    filename: str = 'stabby-disco.db'

    def connection_url(self) -> str:
        return f'sqlite:///{self.filename}'


DatabaseSettings = Annotated[Union[
    Annotated[PostgresSettings, pydantic.Tag(DatabaseEngine.postgres)],
    Annotated[SqliteSettings, pydantic.Tag(DatabaseEngine.sqlite)],
], pydantic.Field(discriminator='engine')]

class Conf(pydantic.BaseModel):
    invite_url: str
    token: str
    karma_grammar: str
    prompt_grammar: str
    maker_grammar: str
    owner_id: int
    title_font: str = pydantic.Field(default='droid-sans-mono.ttf')
    artist_font: str = pydantic.Field(default='droid-sans-mono.ttf')
    sd_host: str = pydantic.Field(default='http://127.0.0.1:7860')
    guilds: list[int] = pydantic.Field(default_factory=lambda: list())
    status_notify: list[int] = pydantic.Field(default_factory=lambda: list())
    ratelimit_count: int = pydantic.Field(default=1)
    ratelimit_window: float = pydantic.Field(default=20.0)
    max_steps: int = pydantic.Field(default=50)
    global_defaults: GlobalDefaults
    db: DatabaseSettings


def load_conf() -> Conf:
    global conf
    if conf is None:
        conf_data = {}
        with open('conf.yaml') as file:
            conf_data = yaml.load(file, Loader=yaml.FullLoader)

        conf = Conf(**conf_data)

    return conf
