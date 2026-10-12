from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.auth import require_token
from app.db import get_session
from app.exercises_catalog import alternatives, alternatives_rich
from app.models import DebugTrace, ExerciseStats, MyExercise, Profile, TrainingSession, TrainingSetLog
from app.schemas import (
    AdoptRequest,
    AlternativesOut,
    ExerciseOption,
    ExerciseStatOut,
    ReorderRequest,
    SessionOut,
    SetOut,
    SetPatch,
    TimerRequest,
    CompleteRequest,
    TrainingDashboardOut,
)
from app.services import session_service as svc
from app.services.analytics_service import build_dashboard

log = logging.getLogger("gym.session")

router = APIRouter(prefix="/api/training", tags=["training"])


@router.get("/today", response_model=SessionOut | None)
def today_session(
    session: Session = Depends(get_session),
    _: str = Depends(require_token),
):
    return svc.get_today_active(session)


@router.post("/adopt", response_model=SessionOut)
def adopt(
    body: AdoptRequest,
    session: Session = Depends(get_session),
    _: str = Depends(require_token),
):
    return svc.adopt_draft(session, body)


@router.post("/sessions/{session_id}/reorder", response_model=SessionOut)
def reorder_session(
    session_id: int,
    body: ReorderRequest,
    session: Session = Depends(get_session),
    _: str = Depends(require_token),
):
    try:
        return svc.reorder_exercises(session, session_id, body.names)
    except KeyError:
        raise HTTPException(404, "session not found") from None


@router.patch("/sets/{set_id}", response_model=SetOut)
def patch_set(
    set_id: int,
    body: SetPatch,
    session: Session = Depends(get_session),
    _: str = Depends(require_token),
):
    try:
        return svc.patch_set(session, set_id, body)
    except KeyError:
        raise HTTPException(404, "set not found") from None


async def _attach_coach(session: Session, session_id: int, facts: str) -> SessionOut:
    rich_context = svc.build_coach_session_context(session, session_id)
    prompt_facts = rich_context or facts
    extra, coach_error, coach_called = await _coach_note(prompt_facts)
    print(
        f"[完成训练] session={session_id} 调用模型={coach_called} 补充={extra or '无'} 原因={coach_error or '无'}",
        flush=True,
    )
    row = session.get(TrainingSession, session_id)
    if row:
        # 页面只展示模型这句话。代码写的事实摘要只当作兜底或输入。
        row.summary = extra or facts or None
        session.add(row)
    session.add(
        DebugTrace(
            user_text=f"完成训练 #{session_id}",
            payload={
                "kind": "session_summary",
                "session_id": session_id,
                "facts": prompt_facts,
                "coach_called": coach_called,
                "coach_text": extra,
                "coach_error": coach_error,
            },
        )
    )
    session.commit()
    if not row:
        raise KeyError("session not found")
    session.refresh(row)
    sets = list(session.exec(select(TrainingSetLog).where(TrainingSetLog.session_id == session_id)).all())
    return svc.session_to_out(row, sets)


@router.post("/sessions/{session_id}/timer", response_model=SessionOut)
def session_timer(
    session_id: int,
    body: TimerRequest,
    session: Session = Depends(get_session),
    _: str = Depends(require_token),
):
    try:
        return svc.set_timer(session, session_id, body.action)
    except KeyError:
        raise HTTPException(404, "session not found") from None
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None


@router.post("/sessions/{session_id}/duration", response_model=SessionOut)
def record_duration(
    session_id: int,
    body: CompleteRequest,
    session: Session = Depends(get_session),
    _: str = Depends(require_token),
):
    if body.duration_minutes is None:
        raise HTTPException(400, "duration_minutes required")
    try:
        return svc.set_recorded_duration(session, session_id, body.duration_minutes)
    except KeyError:
        raise HTTPException(404, "session not found") from None
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None


@router.post("/sessions/{session_id}/complete", response_model=SessionOut)
async def complete(
    session_id: int,
    body: CompleteRequest | None = None,
    session: Session = Depends(get_session),
    _: str = Depends(require_token),
):
    try:
        out = svc.complete_session(
            session,
            session_id,
            duration_minutes=body.duration_minutes if body else None,
        )
    except KeyError:
        raise HTTPException(404, "session not found") from None
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None
    return await _attach_coach(session, session_id, out.summary or "")


@router.post("/sessions/{session_id}/resummarize", response_model=SessionOut)
async def resummarize(
    session_id: int,
    session: Session = Depends(get_session),
    _: str = Depends(require_token),
):
    """用现有打卡记录重跑总结，不改组数、重量和备注。"""
    try:
        out = svc.complete_session(session, session_id)
    except KeyError:
        raise HTTPException(404, "session not found") from None
    return await _attach_coach(session, session_id, out.summary or "")


async def _coach_note(facts: str) -> tuple[str | None, str | None, bool]:
    """有真实模型时补一句。返回 (补充文字, 失败原因, 是否调用了模型)。"""
    from app.brain.llm import get_llm
    from app.config import settings

    if not facts:
        return None, "没有事实摘要", False
    if settings.llm_provider != "openai_compatible" or not settings.llm_api_key:
        return None, f"未接模型 provider={settings.llm_provider}", False

    sys_prompt = """你是一位专业、敏锐且有温度的专属私人健身教练。
你的任务是根据学员的个人画像和本场训练表现（特别是与以往历史的纵向对比），写一段 2 到 4 句中肯、精炼、像私教当面发给学员的训练复盘。

只输出 JSON：{"text": "..."}

请遵循以下核心原则：
1. 【纵向对比与敏锐洞察（重中之重）】：
   - 敏锐捕捉学员今天与以往的差异：哪些动作突破了历史最好成绩（PR）、哪些动作相比以往加重或次数提升了；
   - 敏锐发现异常：哪些动作退步了/没稳住、哪些动作提前力竭了，或者是否全程都在舒适区缺乏负荷（摸鱼/划水）；
   - 如果是全新尝试的动作，看其初始负荷和完成质量。
2. 【结合目标理性复盘】：
   - 结合学员的训练目标（如增肌/力量/减脂）和经验水平，对整场训练质量给出一个理性的定性判断；
   - 时长只有在事实里写明「计时器记录」时，才能用来评价节奏和组间。写成「事后补记」或「未开计时」时，这个数字没有参考意义：不要说练得仓促、组间太短，也不要在复盘里强调这段时长。补记的分钟只留给以后算热量。
3. 【给出明确的建议或鼓励】：
   - 表现优异/有突破时给予有力量的肯定；
   - 遇到力竭或弱项时，给出下次具体的执行建议（如保持该重量提升控制力、下周尝试冲击更高次数、控制离心等）。
4. 【行文口吻与禁忌】：
   - 像一个真正懂铁、懂学员日常训练的真人教练，说话真诚中肯、一针见血，言之有物；
   - 严禁机械复述事实清单（不要出现“今天主要是...”、“总容量是...”、“系统综合状态是...”等死板套话）；
   - 严禁空洞套话或前后矛盾，所有结论必须严谨基于输入中的事实。"""

    try:
        raw = await get_llm().complete_json(
            sys_prompt,
            facts,
        )
    except Exception as e:  # noqa: BLE001
        log.exception("session summary llm failed")
        return None, str(e), True
    text = str(raw.get("text") or "").strip()
    if not text:
        return None, "模型没有返回 text", True
    from difflib import SequenceMatcher

    if SequenceMatcher(None, facts, text).ratio() > 0.72:
        return None, "模型和记录过于相似，已丢弃", True
    return text, None, True


@router.get("/dashboard", response_model=TrainingDashboardOut)
def training_dashboard(
    session: Session = Depends(get_session),
    _: str = Depends(require_token),
):
    """Pure-code week / 30d / same-muscle compare — no LLM."""
    return TrainingDashboardOut.model_validate(build_dashboard(session))


@router.get("/sessions", response_model=list[SessionOut])
def list_sessions(
    limit: int = 20,
    session: Session = Depends(get_session),
    _: str = Depends(require_token),
):
    return svc.list_sessions(session, limit=min(limit, 50))


@router.get("/sessions/{session_id}", response_model=SessionOut)
def get_session_detail(
    session_id: int,
    session: Session = Depends(get_session),
    _: str = Depends(require_token),
):
    try:
        return svc.get_session_detail(session, session_id)
    except KeyError:
        raise HTTPException(404, "session not found") from None


@router.get("/alternatives", response_model=AlternativesOut)
def get_alternatives(
    muscle: str = "胸",
    exclude: str | None = None,
    session: Session = Depends(get_session),
    _: str = Depends(require_token),
):
    profile = session.exec(select(Profile).limit(1)).first()
    injuries = profile.injuries if profile else []
    rich = alternatives_rich(muscle, exclude=exclude, injuries=injuries)
    names = [r["name"] for r in rich]
    items = [
        ExerciseOption(
            name=r["name"],
            muscle=r["muscle"],
            category=r["category"],
            tips=r.get("tips"),
        )
        for r in rich
    ]
    return AlternativesOut(
        muscle=muscle,
        options=names,
        items=items,
        banned_injuries=injuries,
    )


@router.get("/exercises", response_model=list[ExerciseStatOut])
def list_exercises(
    session: Session = Depends(get_session),
    _: str = Depends(require_token),
):
    mine = {m.name: m for m in session.exec(select(MyExercise)).all()}
    stats = {s.exercise_name: s for s in session.exec(select(ExerciseStats)).all()}
    names = sorted(set(mine) | set(stats))
    out: list[ExerciseStatOut] = []
    for name in names:
        s = stats.get(name)
        m = mine.get(name)
        out.append(
            ExerciseStatOut(
                name=name,
                muscle=m.muscle if m else None,
                last_weight=s.last_weight if s else None,
                last_reps=s.last_reps if s else None,
                last_feeling=s.last_feeling if s else None,
                last_outcome=s.last_outcome if s else None,
                best_weight=s.best_weight if s else None,
                trend=s.trend if s else "→",
            )
        )
    return out
