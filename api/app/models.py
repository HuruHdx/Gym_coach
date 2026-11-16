from __future__ import annotations

from datetime import date, datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import NaiveDatetime
from sqlalchemy import Column, ForeignKey, Integer, JSON, String
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


class User(SQLModel, table=True):
    """手机号 + 密码账号。"""

    id: Optional[int] = Field(default=None, primary_key=True)
    phone: str = Field(index=True, unique=True, max_length=20)
    password_hash: str
    display_name: Optional[str] = Field(default=None, max_length=40)
    created_at: NaiveDatetime = Field(default_factory=utcnow)


class AuthSession(SQLModel, table=True):
    """登录会话：Bearer 为不透明 token，可吊销。"""

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(index=True)
    token: str = Field(index=True, unique=True, max_length=64)
    expires_at: NaiveDatetime = Field(index=True)
    created_at: NaiveDatetime = Field(default_factory=utcnow)


class Profile(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: Optional[int] = Field(default=None, index=True, unique=True)
    goal: Goal = Goal.BULK
    experience: Experience = Experience.NOVICE
    weight_kg: Optional[float] = None
    height_cm: Optional[float] = None
    days_per_week: int = 4
    session_minutes: Optional[int] = None
    # 器械/场景偏好：目录 category 白名单（器械|自由重量|绳索|自重）
    injuries: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    preferences: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    # 以后都不排的动作或店里没有的器械，聊天确认后写入
    avoid_exercises: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    avoid_foods: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    protein_target_g: Optional[float] = None
    calorie_target: Optional[float] = None
    # 正在跟练的计划模板（周进度由本周 TrainingSession 推算，不另建进度表）
    active_plan_id: Optional[str] = Field(default=None, index=True, max_length=32)
    active_plan_started_at: Optional[NaiveDatetime] = Field(default=None)
    created_at: NaiveDatetime = Field(default_factory=utcnow)
    updated_at: NaiveDatetime = Field(default_factory=utcnow)


class ProfileHistory(SQLModel, table=True):
    """Scalar field change history (weight, goal, experience, days)."""

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: Optional[int] = Field(default=None, index=True)
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
    # 可归属的中文肌群列表（如硬拉 ["背","腿","全身"]）；AI 排课按部位过滤用，勿改语义
    roles: list[Any] = Field(default_factory=list, sa_column=Column(JSON))
    # 计划槽位角色：main / assist / isolation / warmup（与 roles 肌群语义独立）
    slot_roles: list[Any] = Field(default_factory=list, sa_column=Column(JSON))
    modality: str = Field(default="抗阻", index=True)
    gear: str = Field(default="器械", index=True)
    coach_core: bool = Field(default=False, index=True)
    # Enriched / admin fields (additive only)
    sub_region: Optional[str] = Field(default=None, index=True)
    movement_pattern: Optional[str] = Field(default=None, index=True)
    joint_stress: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    cues_zh: list[Any] = Field(default_factory=list, sa_column=Column(JSON))
    common_mistakes_zh: list[Any] = Field(default_factory=list, sa_column=Column(JSON))
    is_valid_exercise: bool = Field(default=True, index=True)
    needs_review: bool = Field(default=False, index=True)
    updated_at: NaiveDatetime = Field(default_factory=utcnow)


class ExerciseMedia(SQLModel, table=True):
    """Per-slot media for an exercise. Same exercise+role keeps at most one published row."""

    __tablename__ = "exercise_media"

    id: Optional[int] = Field(default=None, primary_key=True)
    exercise_id: str = Field(index=True, max_length=32)
    role: str = Field(index=True, max_length=32)  # start|end|demo|highlight_video|tip
    url: str = Field(max_length=512)
    status: str = Field(default="published", index=True, max_length=16)  # draft|published|archived
    source: str = Field(default="seed", max_length=32)  # seed|upload|video_studio
    meta: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: NaiveDatetime = Field(default_factory=utcnow)


class ExerciseAlias(SQLModel, table=True):
    """Spoken / alternate names mapped to an exercise SKU."""

    __tablename__ = "exercise_aliases"

    id: Optional[int] = Field(default=None, primary_key=True)
    exercise_id: str = Field(index=True, max_length=32)
    alias: str = Field(index=True, max_length=120)
    status: str = Field(default="published", index=True, max_length=16)  # draft|published
    created_at: NaiveDatetime = Field(default_factory=utcnow)


class MediaUnmatchedPool(SQLModel, table=True):
    """A3：批量上传未自动匹配到动作的素材池。"""

    __tablename__ = "media_unmatched_pool"

    id: Optional[int] = Field(default=None, primary_key=True)
    filename: str = Field(max_length=260)
    relative_path: Optional[str] = Field(default=None, max_length=512)
    stored_path: str = Field(max_length=512)
    file_type: str = Field(default="image", max_length=32)  # image|gif|video|other
    size_bytes: int = Field(default=0)
    guessed_role: Optional[str] = Field(default=None, max_length=32)
    candidates: list[Any] = Field(default_factory=list, sa_column=Column(JSON))
    status: str = Field(default="pending", index=True, max_length=16)  # pending|bound|ignored
    bound_exercise_id: Optional[str] = Field(default=None, index=True, max_length=32)
    bound_media_id: Optional[int] = Field(default=None)
    created_at: NaiveDatetime = Field(default_factory=utcnow)
    updated_at: NaiveDatetime = Field(default_factory=utcnow)


class TrainingSession(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: Optional[int] = Field(default=None, index=True)
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
    # 计划模板溯源（采纳模板板块时写入；AI/自定义可空）
    plan_template_id: Optional[str] = Field(default=None, index=True, max_length=32)
    plan_block_id: Optional[int] = Field(default=None, index=True)
    plan_type: Optional[str] = Field(default=None, max_length=16)  # custom | framework | fixed
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
    is_warmup: bool = False  # 热身组不计入 1RM / 有效容量（旧数据默认 False）


class ExerciseStats(SQLModel, table=True):
    """Derived cache — recomputable from logs。按 user_id 隔离。"""

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: Optional[int] = Field(default=None, index=True)
    exercise_name: str = Field(index=True)
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
    """当前打开的对话段。「新对话」只换 conversation_id，不删流水。"""

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: Optional[int] = Field(default=None, index=True)
    conversation_id: str = Field(index=True)
    updated_at: NaiveDatetime = Field(default_factory=utcnow)


class ChatTurn(SQLModel, table=True):
    """完整会话流水。按 conversation_id 分段；进模型默认只用「今天 + 当前段」。"""

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: Optional[int] = Field(default=None, index=True)
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


# ---------- Plan templates（后台配置 → H5 展开成今日草稿） ----------

# 计划封面器械标签约定（中文枚举；映射到 Exercise.equipment / gear 见后续 expand 服务）
PLAN_GEAR_TAGS = (
    "杠铃",
    "哑铃",
    "壶铃",
    "绳索",
    "史密斯",
    "固定器械",
    "自重",
    "弹力带",
)

# 动作槽位角色（存 Exercise.slot_roles / PlanExercise.role）
PLAN_SLOT_ROLES = ("main", "assist", "isolation", "warmup")


class PlanTemplate(SQLModel, table=True):
    """可上下架的训练计划模板主表。"""

    __tablename__ = "plan_templates"

    id: str = Field(primary_key=True, max_length=32)  # slug，如 three-split-chest-back-legs
    title: str = Field(max_length=80)
    subtitle: Optional[str] = Field(default=None, max_length=160)
    author: Optional[str] = Field(default=None, max_length=80)  # 详情署名，如「凯圣王 × 谭成义」
    badge_label: Optional[str] = Field(default=None, max_length=40)  # 卡片角标，如「谭成义」「加强版·新手勿练」
    template_type: str = Field(default="framework", max_length=16, index=True)  # framework | fixed
    level: Optional[str] = Field(default=None, max_length=16)  # beginner | intermediate | advanced
    days_per_week: int = Field(default=3, ge=1, le=7)
    minutes_min: Optional[int] = Field(default=None, ge=1, le=300)
    minutes_max: Optional[int] = Field(default=None, ge=1, le=300)
    muscle_tags: list[Any] = Field(default_factory=list, sa_column=Column(JSON))  # 筛选用：胸/背/腿…
    split_summary: Optional[str] = Field(default=None, max_length=80)  # 卡片副文案：胸 · 背 · 腿
    gear_tags: list[Any] = Field(default_factory=list, sa_column=Column(JSON))  # 见 PLAN_GEAR_TAGS
    description: Optional[str] = None
    cover_url: Optional[str] = Field(default=None, max_length=512)
    # H5 人话筛选：三分化|四分化|五分化|博主同款|单部位专项|新手入门（可空，列表可兜底派生）
    scene_tag: Optional[str] = Field(default=None, index=True, max_length=32)
    is_published: bool = Field(default=False, index=True)
    sort_order: int = Field(default=0, index=True)
    created_at: NaiveDatetime = Field(default_factory=utcnow)
    updated_at: NaiveDatetime = Field(default_factory=utcnow)


class PlanBlock(SQLModel, table=True):
    """模板内一个训练日 / 板块（如「胸肩三头」）。"""

    __tablename__ = "plan_blocks"

    id: Optional[int] = Field(default=None, primary_key=True)
    template_id: str = Field(
        sa_column=Column(
            String(32),
            ForeignKey("plan_templates.id", ondelete="CASCADE"),
            index=True,
            nullable=False,
        )
    )
    order_index: int = Field(default=0, index=True)
    title: str = Field(max_length=80)
    muscles: list[Any] = Field(default_factory=list, sa_column=Column(JSON))
    minutes_min: Optional[int] = Field(default=None, ge=1, le=300)
    minutes_max: Optional[int] = Field(default=None, ge=1, le=300)
    cover_url: Optional[str] = Field(default=None, max_length=512)
    note: Optional[str] = None


class PlanExercise(SQLModel, table=True):
    """板块内一行动作：成品型挂 SKU；框架型可留槽位。"""

    __tablename__ = "plan_exercises"

    id: Optional[int] = Field(default=None, primary_key=True)
    block_id: int = Field(
        sa_column=Column(
            Integer,
            ForeignKey("plan_blocks.id", ondelete="CASCADE"),
            index=True,
            nullable=False,
        )
    )
    order_index: int = Field(default=0, index=True)
    exercise_id: Optional[str] = Field(default=None, index=True, max_length=32)
    exercise_name: Optional[str] = Field(default=None, max_length=120)
    role: str = Field(default="main", max_length=16)  # main | assist | isolation | warmup
    lock_level: str = Field(default="slot", max_length=16)  # fixed | slot
    target_sets: Optional[int] = Field(default=None, ge=1, le=20)
    target_reps: Optional[str] = Field(default=None, max_length=32)  # 如 8-12 / 10
    warmup_sets: int = Field(default=0, ge=0, le=10)  # 正式组前的热身组数；独立热身动作用 role=warmup
    alternatives: list[Any] = Field(default_factory=list, sa_column=Column(JSON))
    note: Optional[str] = None  # 给人看的训练提示；禁止塞拆解 JSON
    # 单行目标肌群（胸/背/肩/腿/臂/核心）；框架配课与换动作按此检索，勿与板块 muscles 混抽
    target_muscle: Optional[str] = Field(default=None, index=True, max_length=16)
    # 内容工坊拆解溯源（独立列，勿写进 note）
    source_kind: Optional[str] = Field(default=None, max_length=16)  # spoken|visual|manual|missing
    match_confidence: Optional[float] = Field(default=None)
    source_snippet: Optional[dict[str, Any]] = Field(default=None, sa_column=Column(JSON))


class StudioTask(SQLModel, table=True):
    """内容工坊异步任务：下载/字幕/拆计划/动作素材。"""

    __tablename__ = "studio_tasks"

    id: Optional[int] = Field(default=None, primary_key=True)
    batch_id: Optional[str] = Field(default=None, index=True, max_length=32)
    batch_order: int = Field(default=0)
    source_type: str = Field(default="link", max_length=16)  # link | upload
    source_text: Optional[str] = None  # 原始分享口令
    source_url: Optional[str] = Field(default=None, max_length=1024)
    stored_path: Optional[str] = Field(default=None, max_length=512)
    mode: str = Field(
        default="plan_single", max_length=24, index=True
    )  # plan_single | plan_merge | exercise_only
    domain: str = Field(default="training", max_length=16)  # training | nutrition | general
    status: str = Field(
        default="queued", max_length=32, index=True
    )  # queued|downloading|transcribing|parsing|done|needs_manual_upload|failed|canceled
    progress: int = Field(default=0, ge=0, le=100)
    transcript_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    draft_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    score: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    review_state: str = Field(
        default="needs_review", max_length=24, index=True
    )  # auto_pass | needs_review | ignored
    result_ref: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    error: Optional[str] = None
    created_at: NaiveDatetime = Field(default_factory=utcnow)
    updated_at: NaiveDatetime = Field(default_factory=utcnow)
