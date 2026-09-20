from sqlalchemy import ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column
from src.db.db_connection import Base


class ConfigBundleSkill(Base):
    __tablename__ = "config_bundle_skills"

    config_bundle_id: Mapped[int] = mapped_column(
        ForeignKey("config_bundles.id", ondelete="CASCADE"),
        primary_key=True,
    )
    skill_id: Mapped[int] = mapped_column(
        ForeignKey("skills.id", ondelete="CASCADE"),
        primary_key=True,
    )


Index("ix_config_bundle_skills_skill_id", ConfigBundleSkill.skill_id)