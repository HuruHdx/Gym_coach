from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from typing import Any

import httpx

from app.config import settings


class LLMClient(ABC):
    @abstractmethod
    async def complete_json(self, system: str, user: str) -> dict[str, Any]:
        raise NotImplementedError


def _extract_json(content: str) -> dict[str, Any]:
    content = content.strip()
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", content)
    if fence:
        return json.loads(fence.group(1).strip())
    start, end = content.find("{"), content.rfind("}")
    if start >= 0 and end > start:
        return json.loads(content[start : end + 1])
    raise ValueError(f"Model did not return JSON: {content[:200]}")


class MockLLM(LLMClient):
    """Deterministic mock for local Phase 0/1 without API key."""

    async def complete_json(self, system: str, user: str) -> dict[str, Any]:
        # 意图改写槽：与规则解析对齐，便于本地 hybrid 稳定可测；接真模型后走真实语义
        if "【SESSION_SUMMARY】" in system:
            return {"text": "按你写下的备注和这次的重量来看，下次同一动作先用这次的最高重量。"}

        if "【INTENT_REWRITE】" in system:
            from app.brain.memory import parse_intent

            i = parse_intent(user)
            return {
                "expert": i.expert,
                "muscles": i.muscles,
                "split": i.params.get("split"),
                "equipment": i.params.get("equipment"),
                "fatigue": bool(i.params.get("fatigue")),
                "flexible": bool(i.params.get("flexible")),
                "rewrite": user.strip()[:80],
            }

        from app.exercises_catalog import EXERCISE_BY_NAME, is_banned_for_injuries, roles_of
        from app.taxonomy import canonicalize_exercise

        text = user
        if "用户说：" in user:
            text = user.split("用户说：", 1)[1].split("\n", 1)[0].strip()

        # 从结构化意图行解析部位 / 器械 / 疲劳 / 时长（pipeline 写入）
        intent_muscles: list[str] = []
        equipment_allow: list[str] | None = None
        fatigued = False
        session_minutes: int | None = None
        if "结构化意图：" in user:
            intent_line = user.split("结构化意图：", 1)[1].split("\n", 1)[0]
            if "部位=" in intent_line:
                frag = intent_line.split("部位=", 1)[1].split("；", 1)[0]
                intent_muscles = [x for x in frag.split("+") if x]
            if "用户点名部位=" in intent_line:
                frag = intent_line.split("用户点名部位=", 1)[1].split("；", 1)[0]
                intent_muscles = [x for x in frag.split("+") if x]
            if "器械限制=" in intent_line:
                frag = intent_line.split("器械限制=", 1)[1].split("（", 1)[0].split("；", 1)[0]
                equipment_allow = [x for x in frag.split(",") if x]
            if "单次时长≈" in intent_line:
                frag = intent_line.split("单次时长≈", 1)[1].split("分钟", 1)[0].strip()
                try:
                    session_minutes = int(float(frag))
                except ValueError:
                    session_minutes = None
            if "疲劳" in intent_line or "降阶" in intent_line:
                fatigued = True

        focus: list[str] = []
        exclusive = False
        if "结构化意图：" in user:
            if "点名动作=" in intent_line:
                frag = intent_line.split("点名动作=", 1)[1].split("；", 1)[0]
                focus = [x for x in frag.split("+") if x]
            exclusive = "只排点名动作" in intent_line

        muscle = intent_muscles[0] if intent_muscles else "胸"
        if not intent_muscles:
            for m in ("胸", "背", "肩", "腿", "臂", "核心"):
                if m in text:
                    muscle = m
                    break
            if "随便" in text:
                muscle = "全身"
        label = "+".join(focus) if focus else ("+".join(intent_muscles) if len(intent_muscles) > 1 else muscle)
        if "随便" in text and not intent_muscles:
            label = "全身"

        fatigued = fatigued or any(k in text for k in ("累", "疲劳", "没劲", "没力气"))

        # Parse last weights and feelings from memory block
        last_w: dict[str, float] = {}
        last_feel: dict[str, str] = {}
        last_outcome: dict[str, str] = {}
        for m in re.finditer(
            r"([^\s:：]+):\s*上次=([0-9.]+)kg(?:\s*体感=([^\s]+))?(?:\s*表现=([^\s]+))?",
            user,
        ):
            last_w[m.group(1)] = float(m.group(2))
            if m.group(3):
                last_feel[m.group(1)] = m.group(3)
            if m.group(4):
                last_outcome[m.group(1)] = m.group(4)

        injuries: list[str] = []
        if "伤痛=" in user:
            frag = user.split("伤痛=", 1)[1].split("；", 1)[0].split("\n", 1)[0].strip()
            if frag and frag != "无":
                injuries = [x for x in frag.replace("、", ",").split(",") if x]

        def item(
            eid: str,
            title: str,
            sets: int,
            reps: str,
            weight: float | None,
            selected: bool = True,
            muscle_tag: str | None = None,
        ) -> dict[str, Any]:
            tag = muscle_tag or muscle
            w = last_w.get(title, weight)
            if w is not None and title in last_w:
                feel = last_feel.get(title)
                outcome = last_outcome.get(title)
                hold = outcome in ("没做完", "次数未达标", "降重完成", "达标", "加重完成")
                if feel == "力竭" or outcome in ("没做完", "次数未达标") or fatigued:
                    w = round(last_w[title], 1)
                elif (feel == "轻松" or outcome == "超额完成") and not fatigued:
                    w = round(last_w[title] + 2.5, 1)
                elif feel == "合适" or hold:
                    w = round(last_w[title], 1)
                else:
                    w = round(last_w[title], 1)
            elif w is not None and fatigued:
                w = round(w * 0.9, 1)
            meta: dict[str, Any] = {"sets": sets, "reps": reps, "muscle": tag}
            if w is not None:
                meta["weight"] = w
            sub = f"{sets}×{reps}" + (f" · 建议 {w}kg" if w is not None else "")
            return {"id": eid, "title": title, "subtitle": sub, "meta": meta, "selected": selected}

        pools: dict[str, list[dict[str, Any]]] = {
            "胸": [
                item("c1", "哑铃卧推", 4, "8-10", 30, muscle_tag="胸"),
                item("c2", "器械夹胸", 3, "12", 40, muscle_tag="胸"),
                item("c3", "绳索飞鸟", 3, "12", 12.5, muscle_tag="胸"),
                item("c4", "上斜哑铃推", 3, "10", 20, muscle_tag="胸"),
                item("c5", "俯卧撑", 3, "12", None, muscle_tag="胸"),
            ],
            "背": [
                item("b1", "引体向上", 4, "AMRAP", None, muscle_tag="背"),
                item("b2", "坐姿划船", 4, "10", 45, muscle_tag="背"),
                item("b3", "面拉", 3, "15", None, muscle_tag="背"),
                item("b4", "单臂哑铃划船", 3, "10", 22.5, muscle_tag="背"),
            ],
            "肩": [
                item("s1", "哑铃侧平举", 3, "12", 8, muscle_tag="肩"),
                item("s2", "绳索面拉", 3, "15", None, muscle_tag="肩"),
            ],
            "腿": [
                item("l1", "腿举", 4, "10", 80, muscle_tag="腿"),
                item("l2", "腿屈伸", 3, "12", 35, muscle_tag="腿"),
                item("l3", "罗马尼亚硬拉", 3, "8", 60, muscle_tag="腿"),
                item("l4", "臀桥", 3, "12", 40, muscle_tag="腿"),
            ],
            "臂": [
                item("a1", "哑铃弯举", 3, "12", 12, muscle_tag="臂"),
                item("a2", "绳索下压", 3, "12", 20, muscle_tag="臂"),
            ],
            "核心": [
                item("k1", "平板支撑", 3, "40s", None, muscle_tag="核心"),
                item("k2", "死虫", 3, "12", None, muscle_tag="核心"),
            ],
        }

        targets = intent_muscles or ([muscle] if muscle != "全身" else ["胸", "背", "腿"])
        pool: list[dict[str, Any]] = []
        for mi, mname in enumerate(targets):
            chunk = pools.get(mname, [])
            # 多部位时每部位先取 1~2 个，拼成复合课
            take = 2 if len(targets) > 1 else len(chunk)
            for c in chunk[:take]:
                c = {**c, "id": f"{c['id']}_{mi}"}
                pool.append(c)
        if not pool:
            pool = [
                item("g1", "深蹲", 4, "8", 60),
                item("g2", "硬拉", 3, "5", 80),
            ]

        def allowed_equipment(title: str) -> bool:
            if not equipment_allow:
                return True
            detail = EXERCISE_BY_NAME.get(canonicalize_exercise(title))
            if not detail:
                # 未知动作：出差/居家场景 Fail-Closed，宁缺毋滥
                return False
            return detail["category"] in equipment_allow

        if focus:
            named: list[dict[str, Any]] = []
            for i, name in enumerate(focus):
                detail = EXERCISE_BY_NAME.get(canonicalize_exercise(name))
                roles = roles_of(name, detail)
                tag = detail["muscle"] if detail else muscle
                for wanted in intent_muscles:
                    if wanted in roles:
                        tag = wanted
                        break
                # 用户没点部位时：主动作硬拉默认后链展示用腿，避免整课看起来像背日
                if not intent_muscles and "硬拉" in name and "腿" in roles:
                    tag = "腿"
                category = detail["category"] if detail else "自由重量"
                weight = None if category == "自重" else (80.0 if "硬拉" in name else 60.0)
                named.append(item(f"f{i + 1}", name, 4 if i == 0 else 3, "6-8", weight, True, tag))
            pool = named

        candidates = [
            c
            for c in pool
            if not is_banned_for_injuries(c["title"], injuries) and allowed_equipment(c["title"])
        ]
        if exclusive and focus:
            # 用户说只要这几个时，不再用别的动作把草稿填满
            pass
        elif not candidates:
            # 器械受限时兜底自重
            fallback_title = "俯卧撑" if "胸" in targets or muscle == "胸" else "平板支撑"
            candidates = [item("safe1", fallback_title, 3, "12", None)]

        # 疲劳 / 短课时：少排动作（全部仍默认勾选）
        item_cap = 5
        if fatigued:
            item_cap = 2
        elif session_minutes is not None and session_minutes <= 35:
            item_cap = 3
        candidates = candidates[:item_cap]
        for c in candidates:
            c["selected"] = True

        def _mock_plan_title(lab: str) -> str:
            if "、" in lab or any(k in lab for k in ("深蹲", "硬拉", "卧推", "引体")):
                return lab.replace("+", "、")
            if lab == "全身":
                return "全身训"
            if "+" in lab:
                return lab
            return f"{lab}训"

        note = ""
        if fatigued:
            note = "检测到疲劳状态，已降阶不加重。"
        elif any(title in last_w for title in (c["title"] for c in candidates)):
            note = "已参考上次重量与体感做自适应。"
        if equipment_allow:
            note += f" 器械限制：{'/'.join(equipment_allow)}。"
        plan_title = _mock_plan_title(label)
        return {
            "text": f"按你的画像和「{text[:40]}」排好了「{plan_title}」。{note}不需要的动作取消勾选后再采纳。",
            "card": {
                "card_type": "training_draft",
                "title": plan_title,
                "items": candidates,
            },
        }


class OpenAICompatibleLLM(LLMClient):
    async def complete_json(self, system: str, user: str) -> dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {settings.llm_api_key}",
            "Content-Type": "application/json",
        }
        # DeepSeek Flash: disable thinking for faster structured JSON
        body: dict[str, Any] = {
            "model": settings.llm_model,
            "temperature": 0.4,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "thinking": {"type": "disabled"},
        }
        async with httpx.AsyncClient(base_url=settings.llm_base_url, timeout=90) as client:
            resp = await client.post("/chat/completions", headers=headers, json=body)
            if resp.status_code >= 400:
                # Retry without thinking / response_format for stricter gateways
                body.pop("thinking", None)
                body.pop("response_format", None)
                resp = await client.post("/chat/completions", headers=headers, json=body)
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"] or ""
            return _extract_json(content)


def get_llm() -> LLMClient:
    if settings.llm_provider == "openai_compatible" and settings.llm_api_key:
        return OpenAICompatibleLLM()
    return MockLLM()
