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
    # 以后都不排的动作或店里没有的器械，聊天确认后写入
    avoid_exercises: list[str] = Field(default_factory=list, sa_column=Column(JSON))
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


class Exercise(SQLModel, table=True):
    """Global openGym catalogue (shared, not per-user)."""

    __tablename__ = "exercises"

    id: str = Field(primary_key=True, max_length=32)
    name_en: str = Field(index=True)
    name_zh: str = Field(index=True)
    body_part: Optional[str] = Field(default=None, index=True)
    equipment: Optional[str] = Field(default=None, index=True)
    target: Optional[str] = Field(default=None, index=True)
    secondary_muscles: list[Any] = Field(default_factory=list, sa_column=Column(JSON))
    category: Optional[str] = Field(default=None, index=True)
    description_en: Optional[str] = None
    description_zh: Optional[str] = None
    instructions_en: list[Any] = Field(default_factory=list, sa_column=Column(JSON))
    instructions_zh: list[Any] = Field(default_factory=list, sa_column=Column(JSON))
    image_start: Optional[str] = None
    image_end: Optional[str] = None
    fdb_id: Optional[str] = None
    text_source: Optional[str] = None
    female_variant: Optional[str] = None
    variant_of: Optional[str] = None
    # Derived coach fields
    muscle: str = Field(default="全身", index=True)
    roles: list[Any] = Field(default_factory=list, sa_column=Column(JSON))
    modality: str = Field(default="抗阻", index=True)
    gear: str = Field(default="器械", index=True)
    coach_core: bool = Field(default=False, index=True)


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
    # 1RM 估算（Epley 反推，不用用户填）
    estimate_1rm: Optional[float] = None  # 动态基准：最近5次反推平均值
    best_estimate_1rm: Optional[float] = None  # 进步锚点：历史最高反推值，只涨不跌
    recent_1rm_samples: Optional[str] = None  # JSON list[float]，最近5次反推值
    updated_at: NaiveDatetime = Field(default_factory=utcnow)


class ActiveChat(SQLModel, table=True):
    """当前打开的对话段（单用户单活跃会话）。「新对话」只换 conversation_id，不删流水。"""

    id: Optional[int] = Field(default=None, primary_key=True)
    conversation_id: str = Field(index=True)
    updated_at: NaiveDatetime = Field(default_factory=utcnow)


class ChatTurn(SQLModel, table=True):
    """完整会话流水。按 conversation_id 分段；进模型默认只用「今天 + 当前段」。"""

    id: Optional[int] = Field(default=None, primary_key=True)
    conversation_id: str = Field(default="", index=True)
    session_day: date = Field(index=True)
    role: str  # user | assistant
    text: str = ""
    card_title: Optional[str] = None
    card_items: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    # 完整卡片 JSON，供前端从库还原草稿勾选/重量
    card: Optional[dict[str, Any]] = Field(default=None, sa_column=Column(JSON))
    suggestions: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    created_at: NaiveDatetime = Field(default_factory=utcnow)


class PendingMemory(SQLModel, table=True):
    """单值档案变更：先问一句，确认后再覆盖。同一时间只留一条待确认。"""

    id: Optional[int] = Field(default=None, primary_key=True)
    field: str
    old_value: str = ""
    new_value: str = ""
    created_at: NaiveDatetime = Field(default_factory=utcnow)


class DebugTrace(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: NaiveDatetime = Field(default_factory=utcnow)
    user_text: str
    payload: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))


class FeedbackEvent(SQLModel, table=True):
    """聊天气泡点赞/点踩。差评带反规范化快照，供导出评测 inbox。"""

    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: NaiveDatetime = Field(default_factory=utcnow)
    rating: str  # up | down
    tags: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    note: str = ""
    conversation_id: str = Field(default="", index=True)
    assistant_turn_id: Optional[int] = Field(default=None, index=True)
    trace_id: Optional[int] = Field(default=None, index=True)
    question: str = ""
    answer: str = ""
    snapshot: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    export_status: str = Field(default="pending", index=True)  # pending | exported | discarded
