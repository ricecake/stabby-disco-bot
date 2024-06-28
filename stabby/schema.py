from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional, TypeVar
from sqlalchemy import UniqueConstraint, func
from sqlalchemy import DateTime
from sqlalchemy import create_engine
from sqlalchemy import select
from sqlalchemy.orm import DeclarativeBase, MappedAsDataclass
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import scoped_session, sessionmaker
from sqlalchemy.ext.declarative import declared_attr
from stabby import conf
# from sqlalchemy.orm import declarative_base

config = conf.load_conf()
logger = logging.getLogger('discord.stabby.schema')

engine = create_engine('sqlite:///stabby-disco.db', echo=False)
db_session = scoped_session(sessionmaker(autocommit=False,
                                         autoflush=True,
                                         expire_on_commit=False,
                                         bind=engine))

T = TypeVar('T')
NullMapped = Mapped[Optional[T]]

class StabbyTable(DeclarativeBase, MappedAsDataclass):
    @declared_attr.directive
    def __tablename__(cls) -> str:
        name = cls.__name__
        first = name[0].lower()
        return first + "".join("_" + c.lower() if c.isupper() else c for c in name[1:])

    id: Mapped[int] = mapped_column(
        init=False, primary_key=True, autoincrement=True, repr=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), default=None, repr=False
    )

    def as_dict(self, omit=None):
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}

    def update_from_dict(self, updates: dict):
        for field, value in updates.items():
            setattr(self, field, value)

    @classmethod
    def autocomplete_formatter(cls, field: str, value: T) -> tuple[T, T]:
        return value, value


def init_db():
    StabbyTable.metadata.create_all(bind=engine)


class Preferences(StabbyTable):
    user_id: Mapped[int] = mapped_column(
        nullable=False, default=None, unique=True, repr=False)

    negative_prompt: NullMapped[str] = mapped_column(default=None, nullable=True)
    overlay: NullMapped[bool] = mapped_column(default=None, nullable=True)
    spoiler: NullMapped[bool] = mapped_column(default=None, nullable=True)
    tiling: NullMapped[bool] = mapped_column(default=None, nullable=True)
    restore_faces: NullMapped[bool] = mapped_column(default=None, nullable=True)
    use_refiner: NullMapped[bool] = mapped_column(default=None, nullable=True)
    regen_recycles_seed: Mapped[bool] = mapped_column(default=True)
    regen_preserves_overlay: Mapped[bool] = mapped_column(default=False)

    @classmethod
    def get_user_preferences(cls, user_id: int) -> Preferences:
        with db_session() as session:
            saved_preferences = session.scalar(
                select(Preferences).where(Preferences.user_id == user_id))
            if saved_preferences is None:
                saved_preferences = Preferences(user_id=user_id)
                session.add(saved_preferences)
                session.commit()

            return saved_preferences

    def get_defaults(self) -> dict:
        values = self.as_dict()
        return {
            field: value for field, value in values.items() if value is not None and field in [
                'negative_prompt',
                'overlay',
                'spoiler',
                'tiling',
                'restore_faces',
                'use_refiner',
            ]
        }


class ServerPreferences(StabbyTable):
    server_id: Mapped[int] = mapped_column(
        nullable=False, default=None, unique=True, repr=False)

    default_negative_prompt: NullMapped[str] = mapped_column(
        default=None, nullable=True)
    required_negative_prompt: NullMapped[str] = mapped_column(
        default=None, nullable=True)

    @classmethod
    def get_server_preferences(cls, server_id: int) -> ServerPreferences:
        with db_session() as session:
            saved_preferences = session.scalar(select(ServerPreferences).where(
                ServerPreferences.server_id == server_id))
            if saved_preferences is None:
                saved_preferences = ServerPreferences(server_id=server_id)
                session.add(saved_preferences)
                session.commit()

            return saved_preferences

    def get_defaults(self) -> dict:
        if self.default_negative_prompt is not None:
            return {
                'negative_prompt': self.default_negative_prompt,
            }
        return {}


class Generation(StabbyTable):
    user_id: Mapped[int] = mapped_column(nullable=False, default=None, repr=False)
    message_id: Mapped[int] = mapped_column(nullable=True, default=None, repr=False)

    prompt: Mapped[str] = mapped_column(nullable=False, default=None)
    negative_prompt: NullMapped[str] = mapped_column(nullable=True, default=None)
    overlay: NullMapped[bool] = mapped_column(nullable=True, default=None)
    spoiler: NullMapped[bool] = mapped_column(nullable=True, default=None)
    tiling: NullMapped[bool] = mapped_column(nullable=True, default=None)
    restore_faces: NullMapped[bool] = mapped_column(nullable=True, default=None)
    use_refiner: NullMapped[bool] = mapped_column(nullable=True, default=None)
    width: NullMapped[int] = mapped_column(nullable=True, default=None)
    height: NullMapped[int] = mapped_column(nullable=True, default=None)
    cfg_scale: NullMapped[float] = mapped_column(nullable=True, default=None)
    steps: NullMapped[int] = mapped_column(nullable=True, default=None)
    seed: NullMapped[int] = mapped_column(nullable=True, default=None)

    def regen_params(self):
        fields = self.as_dict()
        return {
            field: value for field, value in fields.items() if field is not None and field in [
                'prompt',
                'negative_prompt',
                'overlay',
                'spoiler',
                'tiling',
                'restore_faces',
                'use_refiner',
                'width',
                'height',
                'cfg_scale',
                'steps',
                'seed',
            ]
        }


class Style(StabbyTable):
    user_id: Mapped[int] = mapped_column(nullable=False, default=None, repr=False)

    name: Mapped[str] = mapped_column(nullable=False, default=None)
    prompt: NullMapped[str] = mapped_column(nullable=True, default=None)
    negative_prompt: NullMapped[str] = mapped_column(nullable=True, default=None)
    overlay: NullMapped[bool] = mapped_column(nullable=True, default=None)
    tiling: NullMapped[bool] = mapped_column(nullable=True, default=None)
    restore_faces: NullMapped[bool] = mapped_column(nullable=True, default=None)

    __table_args__ = (UniqueConstraint(user_id, name, name="style_user_name_idx"), )
