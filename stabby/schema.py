from __future__ import annotations

import logging
from datetime import datetime
from sqlalchemy import func
from sqlalchemy import DateTime
from sqlalchemy import create_engine
from sqlalchemy import select
from sqlalchemy.orm import DeclarativeBase, MappedAsDataclass
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import scoped_session, sessionmaker

from stabby import conf
config = conf.load_conf()
logger = logging.getLogger('discord.stabby.schema')


engine = create_engine('sqlite:///stabby-disco.db', echo=False)
db_session = scoped_session(sessionmaker(autocommit=False,
                                         autoflush=False,
                                         expire_on_commit=False,
                                         bind=engine))


class Base(MappedAsDataclass, DeclarativeBase):
    query = db_session.query_property()

    def as_dict(self):
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}
    
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

    user_id: Mapped[int] = mapped_column(nullable=False, default=None, unique=True)

    overlay: Mapped[bool] = mapped_column(default=True)
    spoiler: Mapped[bool] = mapped_column(default=False)
    tiling: Mapped[bool] = mapped_column(default=False)
    restore_faces: Mapped[bool] = mapped_column(default=True)
    use_refiner: Mapped[bool] = mapped_column(default=True)
    regen_recycles_seed: Mapped[bool] = mapped_column(default=True)
    regen_preserves_overlay: Mapped[bool] = mapped_column(default=False)

    @classmethod
    def get_user_preferences(cls, user_id:int) -> Preferences:
        with db_session() as session:
            saved_preferences = session.scalar(select(Preferences).where(Preferences.user_id == user_id))
            if saved_preferences is None:
                saved_preferences = Preferences(user_id=user_id)
                session.add(saved_preferences)
                session.commit()
            
            return saved_preferences

class ServerPreferences(Base):
    __tablename__ = "server_preferences"
    id: Mapped[int] = mapped_column(
        init=False, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), default=None,
    )

    server_id: Mapped[int] = mapped_column(nullable=False, default=None, unique=True)

    default_negative_prompt: Mapped[str] = mapped_column(default=None, nullable=True)
    required_negative_prompt: Mapped[str] = mapped_column(default=None, nullable=True)

    @classmethod
    def get_server_preferences(cls, server_id:int) -> ServerPreferences:
        with db_session() as session:
            saved_preferences = session.scalar(select(ServerPreferences).where(ServerPreferences.server_id == server_id))
            if saved_preferences is None:
                saved_preferences = ServerPreferences(server_id=server_id)
                session.add(saved_preferences)
                session.commit()
            
            return saved_preferences


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
    negative_prompt: Mapped[str] = mapped_column(nullable=True, default=None)
    overlay: Mapped[bool] = mapped_column(nullable=True, default=None)
    spoiler: Mapped[bool] = mapped_column(nullable=True, default=None)
    tiling: Mapped[bool] = mapped_column(nullable=True, default=None)
    restore_faces: Mapped[bool] = mapped_column(nullable=True, default=None)
    use_refiner: Mapped[bool] = mapped_column(nullable=True, default=None)
    width: Mapped[int] = mapped_column(nullable=True, default=None)
    height: Mapped[int] = mapped_column(nullable=True, default=None)
    cfg_scale: Mapped[float] = mapped_column(nullable=True, default=None)
    steps: Mapped[int] = mapped_column(nullable=True, default=None)
    seed: Mapped[int] = mapped_column(nullable=True, default=None)

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
