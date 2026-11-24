"""Seed two published plan templates for H5 / expand 联调；已有库则补字段与文案。"""

from __future__ import annotations

from sqlmodel import Session, col, select

from app.models import PlanBlock, PlanExercise, PlanTemplate, utcnow


def ensure_plan_seeds(session: Session) -> None:
    existing = session.exec(select(PlanTemplate.id).limit(1)).first()
    if existing:
        _patch_existing_plans(session)
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
        description=(
            "经典三分化：每周三场结构固定，详情页已按部位自动搭配动作；"
            "点「练这场」可再按伤病与偏好微调，动作均可换。"
        ),
        scene_tag="热门计划",
        is_published=True,
        sort_order=10,
        created_at=now,
        updated_at=now,
    )
    five = _five_split_template(now)
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
        scene_tag="增肌专项",
        is_published=True,
        sort_order=20,
        created_at=now,
        updated_at=now,
    )
    session.add(framework)
    session.add(five)
    session.add(fixed)
    session.commit()

    _seed_three_split_blocks(session, framework.id)
    _seed_five_split_blocks(session, five.id)

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
                target_muscle=row.get("target_muscle"),
            )
        )
    session.commit()


def _five_split_template(now) -> PlanTemplate:
    return PlanTemplate(
        id="five-split-classic",
        title="经典五分化",
        subtitle="胸 · 背 · 腿 · 肩 · 臂，一周五练自动搭配",
        author="Gym Coach",
        badge_label="框架",
        template_type="framework",
        level="intermediate",
        days_per_week=5,
        minutes_min=45,
        minutes_max=70,
        muscle_tags=["胸", "背", "腿", "肩", "臂"],
        split_summary="胸 · 背 · 腿 · 肩 · 臂",
        gear_tags=["杠铃", "哑铃", "绳索", "固定器械"],
        description=(
            "经典五分化：每周五场按部位拆开练，详情页已自动搭配常用动作；"
            "点「练这场」可再按伤病与偏好微调。"
        ),
        scene_tag="热门计划",
        is_published=True,
        sort_order=15,
        created_at=now,
        updated_at=now,
    )


def _seed_three_split_blocks(session: Session, template_id: str) -> None:
    fw_blocks = [
        ("胸肩三头", ["胸", "肩", "臂"], 55, 75),
        ("背二头", ["背", "臂"], 50, 70),
        ("腿臀", ["腿"], 55, 80),
    ]
    for i, (title, muscles, mn, mx) in enumerate(fw_blocks):
        block = PlanBlock(
            template_id=template_id,
            order_index=i,
            title=title,
            muscles=muscles,
            minutes_min=mn,
            minutes_max=mx,
        )
        session.add(block)
        session.flush()
        for j, slot in enumerate(_framework_slots(title)):
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
                    target_muscle=slot.get("target_muscle"),
                )
            )


def _seed_five_split_blocks(session: Session, template_id: str) -> None:
    fw_blocks = [
        ("胸日", ["胸"], 50, 70),
        ("背日", ["背"], 50, 70),
        ("腿日", ["腿"], 55, 80),
        ("肩日", ["肩"], 45, 65),
        ("臂日", ["臂"], 40, 60),
    ]
    for i, (title, muscles, mn, mx) in enumerate(fw_blocks):
        block = PlanBlock(
            template_id=template_id,
            order_index=i,
            title=title,
            muscles=muscles,
            minutes_min=mn,
            minutes_max=mx,
        )
        session.add(block)
        session.flush()
        for j, slot in enumerate(_five_split_slots(muscles[0])):
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
                    target_muscle=slot.get("target_muscle"),
                )
            )


# 旧「分化方式」词表 → 人群/场景分组（重启 init 时自动迁）
_LEGACY_SCENE_REMAP = {
    "三分化": "热门计划",
    "四分化": "热门计划",
    "五分化": "热门计划",
    "单部位专项": "增肌专项",
}


def _patch_existing_plans(session: Session) -> None:
    """已有库：文案去「槽位」、迁 scene_tag、动作行补 target_muscle；缺则补五分化。"""
    dirty = False

    fw = session.get(PlanTemplate, "three-split-classic")
    if fw:
        local_dirty = False
        if fw.subtitle and "槽位" in fw.subtitle:
            fw.subtitle = "胸肩 · 背臂 · 腿臀，进页即自动搭配动作"
            local_dirty = True
        if fw.description and "槽位" in fw.description:
            fw.description = (
                "经典三分化：每周三场结构固定，详情页已按部位自动搭配动作；"
                "点「练这场」可再按伤病与偏好微调，动作均可换。"
            )
            local_dirty = True
        if not fw.scene_tag or fw.scene_tag in _LEGACY_SCENE_REMAP:
            fw.scene_tag = _LEGACY_SCENE_REMAP.get(fw.scene_tag or "", "热门计划")
            local_dirty = True
        if local_dirty:
            fw.updated_at = utcnow()
            session.add(fw)
            dirty = True

    if not session.get(PlanTemplate, "five-split-classic"):
        five = _five_split_template(utcnow())
        session.add(five)
        session.flush()
        _seed_five_split_blocks(session, five.id)
        dirty = True
    else:
        five = session.get(PlanTemplate, "five-split-classic")
        if five and (not five.scene_tag or five.scene_tag in _LEGACY_SCENE_REMAP):
            five.scene_tag = _LEGACY_SCENE_REMAP.get(five.scene_tag or "", "热门计划")
            five.updated_at = utcnow()
            session.add(five)
            dirty = True

    fixed = session.get(PlanTemplate, "fixed-push-strength")
    if fixed and (not fixed.scene_tag or fixed.scene_tag in _LEGACY_SCENE_REMAP):
        fixed.scene_tag = _LEGACY_SCENE_REMAP.get(fixed.scene_tag or "", "增肌专项")
        fixed.updated_at = utcnow()
        session.add(fixed)
        dirty = True

    # 其它模板：旧分化词迁新分组；空则按规则兜底
    for tpl in session.exec(select(PlanTemplate)).all():
        if tpl.id in ("three-split-classic", "five-split-classic", "fixed-push-strength"):
            continue
        if tpl.scene_tag in _LEGACY_SCENE_REMAP:
            tpl.scene_tag = _LEGACY_SCENE_REMAP[tpl.scene_tag]
            tpl.updated_at = utcnow()
            session.add(tpl)
            dirty = True
        elif not tpl.scene_tag:
            derived = _derive_scene_tag(session, tpl)
            if derived:
                tpl.scene_tag = derived
                tpl.updated_at = utcnow()
                session.add(tpl)
                dirty = True

    if _backfill_target_muscles(session):
        dirty = True

    if dirty:
        session.commit()


def _derive_scene_tag(session: Session, tpl: PlanTemplate) -> str | None:
    if tpl.scene_tag:
        return tpl.scene_tag
    author = (tpl.author or "").strip()
    if author and author not in ("Gym Coach", "GymCoach"):
        return "博主同款"
    if tpl.level == "beginner":
        return "新手入门"
    if tpl.level in ("intermediate", "advanced"):
        return "进阶强化"
    blocks = session.exec(select(PlanBlock).where(PlanBlock.template_id == tpl.id)).all()
    if len(blocks) == 1:
        return "增肌专项"
    return "热门计划"


def _backfill_target_muscles(session: Session) -> bool:
    """按板块标题 + 行序给空 target_muscle 补齐（不覆盖已有值）。"""
    changed = False
    blocks = session.exec(select(PlanBlock)).all()
    for block in blocks:
        expected = _expected_muscles_for_block(block.title)
        if not expected:
            continue
        rows = session.exec(
            select(PlanExercise)
            .where(PlanExercise.block_id == block.id)
            .order_by(col(PlanExercise.order_index), col(PlanExercise.id))
        ).all()
        for idx, row in enumerate(rows):
            if row.target_muscle:
                continue
            muscle = expected[idx] if idx < len(expected) else expected[-1]
            # 成品课：有动作名时也可按名兜底
            if not muscle and row.exercise_name:
                muscle = _guess_muscle_from_name(row.exercise_name)
            if not muscle:
                continue
            row.target_muscle = muscle
            session.add(row)
            changed = True
    return changed


def _expected_muscles_for_block(title: str) -> list[str]:
    # 五分化单部位日优先精确匹配
    if title in ("胸日", "背日", "腿日", "肩日", "臂日"):
        muscle = title[0]
        return [muscle, muscle, muscle, muscle]
    if "胸" in title:
        return ["胸", "肩", "胸", "胸", "臂"]
    if "背" in title:
        return ["背", "背", "背", "臂"]
    if "腿" in title:
        return ["腿", "腿", "腿", "腿"]
    if "肩" in title:
        return ["肩", "肩", "肩"]
    if "臂" in title:
        return ["臂", "臂", "臂", "臂"]
    if "推" in title:
        return ["胸", "胸", "肩", "胸", "臂"]
    return []


def _guess_muscle_from_name(name: str) -> str | None:
    n = name or ""
    if any(k in n for k in ("卧推", "夹胸", "飞鸟", "俯卧撑")):
        return "胸"
    if any(k in n for k in ("推举", "侧平举", "前平举", "面拉")):
        return "肩"
    if any(k in n for k in ("下压", "臂屈伸", "三头", "窄距")):
        return "臂"
    if any(k in n for k in ("弯举", "二头", "锤式")):
        return "臂"
    if any(k in n for k in ("划船", "下拉", "引体", "硬拉")):
        return "背"
    if any(k in n for k in ("深蹲", "腿举", "腿屈伸", "腿弯举", "臀桥", "箭步")):
        return "腿"
    return None


def _five_split_slots(muscle: str) -> list[dict]:
    """五分化单部位日：主项 + 辅助 + 孤立（臂日拆二头/三头孤立）。"""
    if muscle == "臂":
        return [
            {
                "role": "assist",
                "target_muscle": "臂",
                "sets": 3,
                "reps": "8-12",
                "warmup_sets": 1,
                "note": "三头复合/辅助",
            },
            {
                "role": "isolation",
                "target_muscle": "臂",
                "sets": 3,
                "reps": "10-15",
                "note": "三头孤立",
            },
            {
                "role": "assist",
                "target_muscle": "臂",
                "sets": 3,
                "reps": "8-12",
                "note": "二头辅助",
            },
            {
                "role": "isolation",
                "target_muscle": "臂",
                "sets": 3,
                "reps": "10-15",
                "note": "二头孤立",
            },
        ]
    if muscle == "肩":
        return [
            {
                "role": "main",
                "target_muscle": "肩",
                "sets": 4,
                "reps": "6-8",
                "warmup_sets": 2,
                "note": "推肩主项",
            },
            {
                "role": "assist",
                "target_muscle": "肩",
                "sets": 3,
                "reps": "8-12",
                "note": "肩辅助",
            },
            {
                "role": "isolation",
                "target_muscle": "肩",
                "sets": 3,
                "reps": "10-15",
                "note": "侧平举/后束孤立",
            },
        ]
    if muscle == "腿":
        return [
            {
                "role": "main",
                "target_muscle": "腿",
                "sets": 4,
                "reps": "6-8",
                "warmup_sets": 2,
                "note": "腿复合主项",
            },
            {
                "role": "main",
                "target_muscle": "腿",
                "sets": 3,
                "reps": "8-10",
                "warmup_sets": 1,
                "note": "髋主导互补",
            },
            {
                "role": "assist",
                "target_muscle": "腿",
                "sets": 3,
                "reps": "8-12",
                "note": "单侧或器械辅助",
            },
            {
                "role": "isolation",
                "target_muscle": "腿",
                "sets": 3,
                "reps": "10-15",
                "note": "腘绳 / 小腿",
            },
        ]
    # 胸 / 背
    return [
        {
            "role": "main",
            "target_muscle": muscle,
            "sets": 4,
            "reps": "6-8",
            "warmup_sets": 2,
            "note": f"{muscle}复合主项",
        },
        {
            "role": "assist",
            "target_muscle": muscle,
            "sets": 3,
            "reps": "8-12",
            "warmup_sets": 1,
            "note": f"{muscle}辅助",
        },
        {
            "role": "assist",
            "target_muscle": muscle,
            "sets": 3,
            "reps": "8-12",
            "note": f"{muscle}换面辅助",
        },
        {
            "role": "isolation",
            "target_muscle": muscle,
            "sets": 3,
            "reps": "10-15",
            "note": f"{muscle}孤立",
        },
    ]


def _framework_slots(block_title: str) -> list[dict]:
    if "胸" in block_title:
        return [
            {
                "role": "main",
                "target_muscle": "胸",
                "sets": 4,
                "reps": "6-8",
                "warmup_sets": 2,
                "note": "胸复合主项",
            },
            {
                "role": "main",
                "target_muscle": "肩",
                "sets": 3,
                "reps": "8-10",
                "warmup_sets": 1,
                "note": "肩复合主项",
            },
            {
                "role": "assist",
                "target_muscle": "胸",
                "sets": 3,
                "reps": "8-12",
                "note": "胸辅助，换器械面",
            },
            {
                "role": "isolation",
                "target_muscle": "胸",
                "sets": 3,
                "reps": "10-15",
                "note": "胸孤立",
            },
            {
                "role": "isolation",
                "target_muscle": "臂",
                "sets": 3,
                "reps": "10-15",
                "note": "三头孤立",
            },
        ]
    if "背" in block_title:
        return [
            {
                "role": "main",
                "target_muscle": "背",
                "sets": 4,
                "reps": "6-8",
                "warmup_sets": 2,
                "note": "背垂直或水平拉",
            },
            {
                "role": "main",
                "target_muscle": "背",
                "sets": 3,
                "reps": "8-10",
                "warmup_sets": 1,
                "note": "互补拉向",
            },
            {
                "role": "assist",
                "target_muscle": "背",
                "sets": 3,
                "reps": "8-12",
                "note": "背辅助",
            },
            {
                "role": "isolation",
                "target_muscle": "臂",
                "sets": 3,
                "reps": "10-15",
                "note": "二头孤立",
            },
        ]
    return [
        {
            "role": "main",
            "target_muscle": "腿",
            "sets": 4,
            "reps": "6-8",
            "warmup_sets": 2,
            "note": "腿复合主项",
        },
        {
            "role": "main",
            "target_muscle": "腿",
            "sets": 3,
            "reps": "8-10",
            "warmup_sets": 1,
            "note": "髋主导互补",
        },
        {
            "role": "assist",
            "target_muscle": "腿",
            "sets": 3,
            "reps": "8-12",
            "note": "单侧或器械辅助",
        },
        {
            "role": "isolation",
            "target_muscle": "腿",
            "sets": 3,
            "reps": "10-15",
            "note": "腘绳 / 小腿",
        },
    ]


def _fixed_push_rows() -> list[dict]:
    return [
        {
            "name": "杠铃卧推",
            "role": "main",
            "target_muscle": "胸",
            "sets": 4,
            "reps": "5-8",
            "warmup_sets": 2,
            "alternatives": ["哑铃卧推", "史密斯卧推"],
        },
        {
            "name": "哑铃上斜卧推",
            "role": "assist",
            "target_muscle": "胸",
            "sets": 3,
            "reps": "8-12",
            "warmup_sets": 1,
            "alternatives": ["上斜哑铃飞鸟", "器械上斜推胸"],
        },
        {
            "name": "坐姿哑铃推举",
            "role": "main",
            "target_muscle": "肩",
            "sets": 3,
            "reps": "8-10",
            "warmup_sets": 1,
            "alternatives": ["杠铃推举", "器械推肩"],
        },
        {
            "name": "绳索夹胸",
            "role": "isolation",
            "target_muscle": "胸",
            "sets": 3,
            "reps": "12-15",
            "alternatives": ["哑铃飞鸟", "器械夹胸"],
        },
        {
            "name": "绳索下压",
            "role": "isolation",
            "target_muscle": "臂",
            "sets": 3,
            "reps": "10-15",
            "alternatives": ["哑铃颈后臂屈伸", "窄距卧推"],
        },
    ]
