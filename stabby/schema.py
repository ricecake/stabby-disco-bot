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
from sqlalchemy.orm.decl_api import DCTransformDeclarative

from stabby import conf
config = conf.load_conf()
logger = logging.getLogger('discord.stabby.schema')


engine = create_engine('sqlite:///stabby-disco.db', echo=False)
db_session = scoped_session(sessionmaker(autocommit=False,
                                         autoflush=True,
                                         expire_on_commit=False,
                                         bind=engine))

T = TypeVar('T')
NullMapped = Mapped[Optional[T]]

StabbyTable = DCTransformDeclarative

class Base(MappedAsDataclass, DeclarativeBase):
    query = db_session.query_property()

    def as_dict(self, omit=None):
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}

    # def as_display_dict(self):
    #     [c.is_not_distinct_from() for c in self.__table__.schema.]
    #     pass

    def update_from_dict(self, updates: dict):
        for field, value in updates.items():
            setattr(self, field, value)


def init_db():
    Base.metadata.create_all(bind=engine)


class Preferences(Base):
    __tablename__ = "preferences"
    id: Mapped[int] = mapped_column(
        init=False, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), default=None,
    )

    user_id: Mapped[int] = mapped_column(
        nullable=False, default=None, unique=True)

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


class ServerPreferences(Base):
    __tablename__ = "server_preferences"
    id: Mapped[int] = mapped_column(
        init=False, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), default=None,
    )

    server_id: Mapped[int] = mapped_column(
        nullable=False, default=None, unique=True)

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


class Generation(Base):
    __tablename__ = "generation"
    id: Mapped[int] = mapped_column(
        init=False, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), default=None,
    )

    user_id: Mapped[int] = mapped_column(nullable=False, default=None)
    message_id: Mapped[int] = mapped_column(nullable=True, default=None)

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


class Style(Base):
    __tablename__ = "style"
    id: Mapped[int] = mapped_column(
        init=False, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), default=None,
    )

    user_id: Mapped[int] = mapped_column(nullable=False, default=None)

    name: Mapped[str] = mapped_column(nullable=False, default=None)
    prompt: NullMapped[str] = mapped_column(nullable=True, default=None)
    negative_prompt: NullMapped[str] = mapped_column(nullable=True, default=None)
    overlay: NullMapped[bool] = mapped_column(nullable=True, default=None)
    tiling: NullMapped[bool] = mapped_column(nullable=True, default=None)
    restore_faces: NullMapped[bool] = mapped_column(nullable=True, default=None)

    __table_args__ = (UniqueConstraint(user_id, name, name="style_user_name_idx"), )
