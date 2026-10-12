from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

from app.models import Experience, Goal


# ---------- Profile ----------


class ProfileCreate(BaseModel):
    goal: Goal = Goal.BULK
    experience: Experience = Experience.NOVICE
    weight_kg: float = Field(gt=30, lt=300)
    height_cm: Optional[float] = Field(default=None, gt=100, lt=250)
    days_per_week: int = Field(ge=1, le=7, default=4)
    session_minutes: int = Field(ge=15, le=180, default=45)
    injuries: list[str] = Field(default_factory=list)
    preferences: list[str] = Field(default_factory=list)
    avoid_foods: list[str] = Field(default_factory=list)
    protein_target_g: Optional[float] = None
    calorie_target: Optional[float] = None


class ProfileUpdate(BaseModel):
    goal: Optional[Goal] = None
    experience: Optional[Experience] = None
    weight_kg: Optional[float] = Field(default=None, gt=30, lt=300)
    height_cm: Optional[float] = Field(default=None, gt=100, lt=250)
    days_per_week: Optional[int] = Field(default=None, ge=1, le=7)
    session_minutes: Optional[int] = Field(default=None, ge=15, le=180)
    # set fields: merge semantics
    injuries_add: list[str] = Field(default_factory=list)
    injuries_remove: list[str] = Field(default_factory=list)
    preferences_add: list[str] = Field(default_factory=list)
    preferences_remove: list[str] = Field(default_factory=list)
    # 绝对覆盖（前端整表编辑时用；与 add/remove 二选一优先本字段）
    preferences: Optional[list[str]] = None
    injuries: Optional[list[str]] = None
    avoid_foods_add: list[str] = Field(default_factory=list)
    avoid_foods_remove: list[str] = Field(default_factory=list)
    protein_target_g: Optional[float] = None
    calorie_target: Optional[float] = None


class ProfileOut(BaseModel):
    id: int
    goal: Goal
    experience: Experience
    weight_kg: float
    height_cm: Optional[float]
    days_per_week: int
    session_minutes: int
    injuries: list[str]
    preferences: list[str]
    avoid_foods: list[str]
    protein_target_g: Optional[float]
    calorie_target: Optional[float]
    created_at: datetime
    updated_at: datetime


class WeightLogIn(BaseModel):
    weight_kg: float = Field(gt=30, lt=300)


class WeightPoint(BaseModel):
    weight_kg: float
    recorded_at: datetime


# ---------- Blocks (AI output contract) ----------


class BlockKind(str, Enum):
    TEXT = "text"
    CARD = "card"


class CardStatus(str, Enum):
    DRAFT = "draft"
    CONFIRMED = "confirmed"


class CardType(str, Enum):
    TRAINING_DRAFT = "training_draft"
    TRAINING_PLAN = "training_plan"
    MEAL_DRAFT = "meal_draft"
    PROFILE_CONFIRM = "profile_confirm"
    WEEKLY_REPORT = "weekly_report"


class CardItem(BaseModel):
    id: str
    title: str
    subtitle: Optional[str] = None
    meta: dict[str, Any] = Field(default_factory=dict)
    selected: bool = False


class CardBlock(BaseModel):
    kind: Literal[BlockKind.CARD] = BlockKind.CARD
    card_type: CardType
    title: str
    status: CardStatus = CardStatus.DRAFT
    items: list[CardItem] = Field(default_factory=list)
    actions: list[str] = Field(default_factory=lambda: ["adopt", "customize"])
    meta: dict[str, Any] = Field(default_factory=dict)


class TextBlock(BaseModel):
    kind: Literal[BlockKind.TEXT] = BlockKind.TEXT
    text: str


class Suggestion(BaseModel):
    label: str
    prompt: str


class AgentReply(BaseModel):
    blocks: list[TextBlock | CardBlock]
    suggestions: list[Suggestion] = Field(default_factory=list)
    trace_id: Optional[int] = None


class ChatDraftItem(BaseModel):
    title: str
    selected: bool = True
    meta: dict[str, Any] = Field(default_factory=dict)


class ChatRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    draft_title: Optional[str] = None
    draft_items: list[ChatDraftItem] = Field(default_factory=list)


# ---------- Training (Phase 1) ----------


class DraftItemIn(BaseModel):
    id: Optional[str] = None
    title: str
    subtitle: Optional[str] = None
    meta: dict[str, Any] = Field(default_factory=dict)
    selected: bool = True


class AdoptRequest(BaseModel):
    title: str = "今日计划"
    split_label: Optional[str] = None
    items: list[DraftItemIn] = Field(min_length=1)
    replace_today: bool = True
    # 今日已完成后再次采纳需显式确认，避免悄悄覆盖已结算场次
    force_replace_done: bool = False


class ReorderRequest(BaseModel):
    names: list[str] = Field(min_length=1)


class TimerRequest(BaseModel):
    action: Literal["start", "pause"]


class CompleteRequest(BaseModel):
    """没开计时时，由用户补一段实际分钟，供以后算热量。"""

    duration_minutes: Optional[int] = Field(default=None, ge=1, le=300)


class SetPatch(BaseModel):
    completed: Optional[bool] = None
    actual_weight: Optional[float] = Field(default=None, ge=0, le=500)
    actual_reps: Optional[int] = Field(default=None, ge=0, le=100)
    feeling: Optional[str] = Field(default=None, max_length=20)
    note: Optional[str] = Field(default=None, max_length=500)
    muscle: Optional[str] = Field(default=None, max_length=20)
    target_weight: Optional[float] = Field(default=None, ge=0, le=500)


class SetOut(BaseModel):
    id: int
    session_id: int
    exercise_name: str
    muscle: Optional[str]
    set_index: int
    target_reps: Optional[str]
    target_weight: Optional[float]
    actual_weight: Optional[float]
    actual_reps: Optional[int]
    completed: bool
    feeling: Optional[str] = None
    note: Optional[str]


class SessionOut(BaseModel):
    id: int
    session_date: str
    split_label: Optional[str]
    source: str
    status: str
    note: Optional[str]
    total_volume: Optional[float] = None
    session_outcome: Optional[str] = None
    summary: Optional[str] = None
    duration_seconds: int = 0
    timer_started_at: Optional[str] = None
    duration_minutes: Optional[int] = None
    sets: list[SetOut] = Field(default_factory=list)
    progress: dict[str, int] = Field(default_factory=dict)


class ExerciseStatOut(BaseModel):
    name: str
    muscle: Optional[str] = None
    last_weight: Optional[float] = None
    last_reps: Optional[int] = None
    last_feeling: Optional[str] = None
    last_outcome: Optional[str] = None
    best_weight: Optional[float] = None
    trend: str = "→"


class ExerciseOption(BaseModel):
    name: str
    muscle: str
    category: str = "自由重量"
    tips: Optional[str] = None


class AlternativesOut(BaseModel):
    muscle: str
    options: list[str]
    items: list[ExerciseOption] = Field(default_factory=list)
    banned_injuries: list[str] = Field(default_factory=list)


# ---------- Training dashboard (deterministic analytics) ----------


class WeekDayOut(BaseModel):
    date: str
    label: str
    is_today: bool
    trained: bool
    muscles: list[str] = Field(default_factory=list)
    session_id: Optional[int] = None
    split: Optional[str] = None
    duration_minutes: Optional[int] = None
    completion_pct: Optional[int] = None


class WeekRhythmOut(BaseModel):
    days: list[WeekDayOut]
    trained_days: int
    target_days: int
    sessions: int


class MusclePulseOut(BaseModel):
    muscle: str
    days_since: Optional[int] = None
    count_30d: int = 0
    last_date: Optional[str] = None
    last_session_id: Optional[int] = None
    trend: str = "→"
    status: str = "idle"  # fresh | ok | overdue | idle


class LiftDeltaOut(BaseModel):
    exercise_name: str
    load: str
    weight: Optional[float] = None
    reps: Optional[int] = None
    prev_load: Optional[str] = None
    delta_kind: str  # up | down | flat | new
    delta_label: str
    weight_delta: Optional[float] = None
    reps_delta: Optional[int] = None


class SessionCompareOut(BaseModel):
    session_id: int
    session_date: str
    split_label: Optional[str] = None
    muscle: Optional[str] = None
    duration_minutes: Optional[int] = None
    done_sets: int = 0
    total_sets: int = 0
    quality: str
    prev_session_id: Optional[int] = None
    prev_date: Optional[str] = None
    lifts: list[LiftDeltaOut] = Field(default_factory=list)


class KeyLiftOut(BaseModel):
    exercise_name: str
    muscle: Optional[str] = None
    load: str
    weight: Optional[float] = None
    reps: Optional[int] = None
    delta_kg: float = 0
    delta_label: str
    trend: str = "→"
    is_pr: bool = False
    last_date: Optional[str] = None


class TrainingDashboardOut(BaseModel):
    as_of: str
    headline: str
    week: WeekRhythmOut
    muscle_pulse: list[MusclePulseOut] = Field(default_factory=list)
    session_compare: Optional[SessionCompareOut] = None
    key_lifts: list[KeyLiftOut] = Field(default_factory=list)
