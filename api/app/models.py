from __future__ import annotations

from datetime import date, datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import NaiveDatetime
from sqlalchemy import Column, JSON
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    # SQLite stores naive UTC; SQLModel accepts NaiveDatetime without tz enforcement.
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Goal(str, Enum):
    BULK = "增肌"
    CUT = "减脂"
    STRENGTH = "力量"
    SHAPE = "塑形"


class Experience(str, Enum):
    NOVICE = "新手"
    INTERMEDIATE = "进阶"
    ADVANCED = "老炮"


class Profile(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    goal: Goal = Goal.BULK
    experience: Experience = Experience.NOVICE
    weight_kg: float = 70.0
    height_cm: Optional[float] = None
    days_per_week: int = 4
    session_minutes: int = 45
    # 器械/场景偏好：目录 category 白名单（器械|自由重量|绳索|自重）
    injuries: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    preferences: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    avoid_foods: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    protein_target_g: Optional[float] = None
    calorie_target: Optional[float] = None
    created_at: NaiveDatetime = Field(default_factory=utcnow)
    updated_at: NaiveDatetime = Field(default_factory=utcnow)


class ProfileHistory(SQLModel, table=True):
    """Scalar field change history (weight, goal, experience, days)."""

    id: Optional[int] = Field(default=None, primary_key=True)
    field: str
    old_value: str
    new_value: str
    created_at: NaiveDatetime = Field(default_factory=utcnow)


class MyExercise(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True, unique=True)
    muscle: str = Field(index=True)
    video_url: Optional[str] = None
    created_at: NaiveDatetime = Field(default_factory=utcnow)


class TrainingSession(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    session_date: date = Field(index=True)
    split_label: Optional[str] = None
    source: str = "adopted"  # adopted | custom
    status: str = "draft"  # draft | active | done
    note: Optional[str] = None
    total_volume: Optional[float] = None
    session_outcome: Optional[str] = None  # 未记录 | 未完成 | 偏吃力 | 完成 | 有突破
    summary: Optional[str] = None
    duration_seconds: int = 0
    timer_started_at: Optional[NaiveDatetime] = None
    duration_minutes: Optional[int] = None
    duration_source: Optional[str] = None  # timer | manual
    created_at: NaiveDatetime = Field(default_factory=utcnow)


class TrainingSetLog(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    session_id: int = Field(index=True)
    exercise_name: str = Field(index=True)
    muscle: Optional[str] = None
    exercise_order: int = 0
    set_index: int
    target_reps: Optional[str] = None
    target_weight: Optional[float] = None
    actual_weight: Optional[float] = None
    actual_reps: Optional[int] = None
    completed: bool = False
    feeling: Optional[str] = None  # 轻松 | 合适 | 力竭
    note: Optional[str] = None


class ExerciseStats(SQLModel, table=True):
    """Derived cache — recomputable from logs."""

    id: Optional[int] = Field(default=None, primary_key=True)
    exercise_name: str = Field(index=True, unique=True)
    last_weight: Optional[float] = None
    last_reps: Optional[int] = None
    last_feeling: Optional[str] = None  # 轻松 | 合适 | 力竭；没打标则为空
    last_outcome: Optional[str] = None  # 达标 | 降重完成 | 没做完 | 加重完成
    best_weight: Optional[float] = None
    trend: str = "→"
    updated_at: NaiveDatetime = Field(default_factory=utcnow)


class DebugTrace(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: NaiveDatetime = Field(default_factory=utcnow)
    user_text: str
    payload: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
