"""Seed two published plan templates for H5 / expand 联调（空库才写入）。"""

from __future__ import annotations

from sqlmodel import Session, select

from app.models import PlanBlock, PlanExercise, PlanTemplate, utcnow


def ensure_plan_seeds(session: Session) -> None:
    existing = session.exec(select(PlanTemplate.id).limit(1)).first()
    if existing:
        # 已有库：把旧文案里的「槽位」改成用户能懂的说法
        _patch_framework_copy(session)
        return

    now = utcnow()
    framework = PlanTemplate(
        id="three-split-classic",
        title="热门三分化",
        subtitle="胸肩 · 背臂 · 腿臀，进页即自动搭配动作",
        author="Gym Coach",
        badge_label="框架",
        template_type="framework",
        level="intermediate",
        days_per_week=3,
        minutes_min=50,
        minutes_max=75,
        muscle_tags=["胸", "背", "肩", "腿", "臂"],
        split_summary="胸肩 · 背臂 · 腿臀",
        gear_tags=["杠铃", "哑铃", "绳索", "固定器械"],
        description="经典三分化：每周三场结构固定，详情页已按部位自动搭配动作；点「练这场」可再按伤病与偏好微调，动作均可换。",
        is_published=True,
        sort_order=10,
        created_at=now,
        updated_at=now,
    )
    fixed = PlanTemplate(
        id="fixed-push-strength",
        title="推日力量成品",
        subtitle="卧推为主的胸肩三头成品课",
        author="Gym Coach",
        badge_label="成品",
        template_type="fixed",
        level="intermediate",
        days_per_week=1,
        minutes_min=55,
        minutes_max=70,
        muscle_tags=["胸", "肩", "臂"],
        split_summary="胸 · 肩 · 三头",
        gear_tags=["杠铃", "哑铃", "绳索"],
        description="动作与组次锁定的推日成品课，适合直接开练；伤病或缺器械时会尝试备选。",
        is_published=True,
        sort_order=20,
        created_at=now,
        updated_at=now,
    )
    session.add(framework)
    session.add(fixed)
    session.commit()

    fw_blocks = [
        ("胸肩三头", ["胸", "肩", "臂"], 55, 75),
        ("背二头", ["背", "臂"], 50, 70),
        ("腿臀", ["腿"], 55, 80),
    ]
    for i, (title, muscles, mn, mx) in enumerate(fw_blocks):
        block = PlanBlock(
            template_id=framework.id,
            order_index=i,
            title=title,
            muscles=muscles,
            minutes_min=mn,
            minutes_max=mx,
        )
        session.add(block)
        session.flush()
        slots = _framework_slots(title)
        for j, slot in enumerate(slots):
            session.add(
                PlanExercise(
                    block_id=block.id or 0,
                    order_index=j,
                    exercise_id=None,
                    exercise_name=None,
                    role=slot["role"],
                    lock_level="slot",
                    target_sets=slot["sets"],
                    target_reps=slot["reps"],
                    warmup_sets=slot.get("warmup_sets", 0),
                    alternatives=[],
                    note=slot.get("note"),
                )
            )

    push = PlanBlock(
        template_id=fixed.id,
        order_index=0,
        title="推日 · 胸肩三头",
        muscles=["胸", "肩", "臂"],
        minutes_min=55,
        minutes_max=70,
        note="成品锁定；伤病时按备选降级",
    )
    session.add(push)
    session.flush()
    for j, row in enumerate(_fixed_push_rows()):
        session.add(
            PlanExercise(
                block_id=push.id or 0,
                order_index=j,
                exercise_id=None,
                exercise_name=row["name"],
                role=row["role"],
                lock_level="fixed",
                target_sets=row["sets"],
                target_reps=row["reps"],
                warmup_sets=row.get("warmup_sets", 0),
                alternatives=row.get("alternatives", []),
                note=row.get("note"),
            )
        )
    session.commit()


def _patch_framework_copy(session: Session) -> None:
    tpl = session.get(PlanTemplate, "three-split-classic")
    if not tpl:
        return
    dirty = False
    if tpl.subtitle and "槽位" in tpl.subtitle:
        tpl.subtitle = "胸肩 · 背臂 · 腿臀，进页即自动搭配动作"
        dirty = True
    if tpl.description and "槽位" in tpl.description:
        tpl.description = (
            "经典三分化：每周三场结构固定，详情页已按部位自动搭配动作；"
            "点「练这场」可再按伤病与偏好微调，动作均可换。"
        )
        dirty = True
    if dirty:
        tpl.updated_at = utcnow()
        session.add(tpl)
        session.commit()


def _framework_slots(block_title: str) -> list[dict]:
    if "胸" in block_title:
        return [
            {"role": "main", "sets": 4, "reps": "6-8", "warmup_sets": 2, "note": "胸复合主项"},
            {"role": "main", "sets": 3, "reps": "8-10", "warmup_sets": 1, "note": "肩复合主项"},
            {"role": "assist", "sets": 3, "reps": "8-12", "note": "胸辅助，换器械面"},
            {"role": "isolation", "sets": 3, "reps": "10-15", "note": "胸孤立"},
            {"role": "isolation", "sets": 3, "reps": "10-15", "note": "三头孤立"},
        ]
    if "背" in block_title:
        return [
            {"role": "main", "sets": 4, "reps": "6-8", "warmup_sets": 2, "note": "背垂直或水平拉"},
            {"role": "main", "sets": 3, "reps": "8-10", "warmup_sets": 1, "note": "互补拉向"},
            {"role": "assist", "sets": 3, "reps": "8-12", "note": "背辅助"},
            {"role": "isolation", "sets": 3, "reps": "10-15", "note": "二头孤立"},
        ]
    return [
        {"role": "main", "sets": 4, "reps": "6-8", "warmup_sets": 2, "note": "腿复合主项"},
        {"role": "main", "sets": 3, "reps": "8-10", "warmup_sets": 1, "note": "髋主导互补"},
        {"role": "assist", "sets": 3, "reps": "8-12", "note": "单侧或器械辅助"},
        {"role": "isolation", "sets": 3, "reps": "10-15", "note": "腘绳 / 小腿"},
    ]


def _fixed_push_rows() -> list[dict]:
    return [
        {
            "name": "杠铃卧推",
            "role": "main",
            "sets": 4,
            "reps": "5-8",
            "warmup_sets": 2,
            "alternatives": ["哑铃卧推", "史密斯卧推"],
        },
        {
            "name": "哑铃上斜卧推",
            "role": "assist",
            "sets": 3,
            "reps": "8-12",
            "warmup_sets": 1,
            "alternatives": ["上斜哑铃飞鸟", "器械上斜推胸"],
        },
        {
            "name": "坐姿哑铃推举",
            "role": "main",
            "sets": 3,
            "reps": "8-10",
            "warmup_sets": 1,
            "alternatives": ["杠铃推举", "器械推肩"],
        },
        {
            "name": "绳索夹胸",
            "role": "isolation",
            "sets": 3,
            "reps": "12-15",
            "alternatives": ["哑铃飞鸟", "器械夹胸"],
        },
        {
            "name": "绳索下压",
            "role": "isolation",
            "sets": 3,
            "reps": "10-15",
            "alternatives": ["哑铃颈后臂屈伸", "窄距卧推"],
        },
    ]
