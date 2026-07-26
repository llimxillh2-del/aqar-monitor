# -*- coding: utf-8 -*-
"""
ذاكرة السوق
============
بيحتفظ بحالة كل موضوع متابَع (المرحلة، المواعيد، آخر تطور) ويقارن كل دورة
عشان يعرف إيه **اللي اتغير فعلًا** — مش إيه اللي اتقال.

إصلاح: كان بيعتبر أي إعادة صياغة من الـ AI "تغيير" ويبعت تنبيه.
دلوقتي فيه فلتر تشابه بيمنع الإنذارات الكاذبة دي.
"""

import os
import re
import json
import html
from datetime import datetime, timezone

import config
from ai_engine import SYSTEM_JSON


def load():
    path = config.MARKET_STATE
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            return {"topics": data.get("topics") or {},
                    "history": data.get("history") or [],
                    "updated": data.get("updated")}
        except Exception:
            pass
    return {"topics": {}, "history": [], "updated": None}


def save(state):
    state["updated"] = datetime.now(timezone.utc).isoformat()
    state["history"] = (state.get("history") or [])[-150:]
    path = config.MARKET_STATE
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def extract_facts(ai, items):
    """يستخرج حالة كل موضوع من الأخبار الحالية."""
    if not ai.available or not items:
        return None

    listing = "\n".join(f"- {it['title']}" for it in items[:30])
    topics_json = ",\n".join(
        f'  "{t}": {{"المرحلة_الحالية": null, "آخر_تطور": null, '
        f'"موعد_قادم": null, "الحالة": "غير معروف"}}'
        for t in config.TRACKED_TOPICS
    )

    prompt = f"""من العناوين دي:

{listing}

استخرج حالة كل موضوع. رجّع JSON بالشكل ده بالظبط:
{{
{topics_json}
}}

قواعد:
- "الحالة" لازم تكون واحدة من: مفتوح / مغلق / منتظر / غير معروف
- "آخر_تطور" جملة واحدة قصيرة
- لو العناوين مافيهاش معلومة عن موضوع، حط null في حقوله. **ماتخمّنش**."""

    return ai.ask_json(prompt, SYSTEM_JSON)


def _clean(v):
    if v is None:
        return None
    s = re.sub(r"\s+", " ", str(v)).strip()
    if s.lower() in ("null", "none", "غير معروف", "لا يوجد", "-", "—", ""):
        return None
    return s


def _too_similar(a, b):
    norm = re.sub(r"[^\w؀-ۿ]+", "", str(a)), re.sub(r"[^\w؀-ۿ]+", "", str(b))
    na, nb = norm
    if na == nb:
        return True
    if not na or not nb:
        return False
    shorter, longer = (na, nb) if len(na) <= len(nb) else (nb, na)
    return shorter in longer and len(shorter) / len(longer) > 0.75


def diff_and_update(state, facts):
    """يقارن الحالة الجديدة بالقديمة ويرجع التغييرات الحقيقية."""
    if not facts or not isinstance(facts, dict):
        return []

    changes = []
    now = datetime.now(timezone.utc).isoformat()
    topics = state.setdefault("topics", {})

    for topic, data in facts.items():
        if not isinstance(data, dict):
            continue
        old = topics.get(topic, {})
        new = {k: _clean(v) for k, v in data.items()}

        for field, new_val in new.items():
            if new_val is None:
                continue
            old_val = old.get(field)
            if old_val == new_val:
                continue
            if old_val and _too_similar(old_val, new_val):
                continue
            changes.append({"topic": topic, "field": field,
                            "from": old_val, "to": new_val, "when": now})

        merged = dict(old)
        for k, v in new.items():
            if v is not None:
                merged[k] = v
        merged["آخر_تحديث"] = now
        topics[topic] = merged

    if changes:
        state.setdefault("history", []).extend(changes)
    return changes


def format_changes(changes):
    """صياغة التغييرات لرسالة تليجرام."""
    if not changes:
        return None
    lines = ["📌 <b>تغييرات في حالة السوق</b>", ""]
    by_topic = {}
    for ch in changes:
        by_topic.setdefault(ch["topic"], []).append(ch)
    for topic, items in by_topic.items():
        lines.append(f"<b>▸ {html.escape(topic)}</b>")
        for ch in items:
            field = ch["field"].replace("_", " ")
            to = html.escape(str(ch["to"])[:180])
            if ch.get("from"):
                frm = html.escape(str(ch["from"])[:110])
                lines.append(f"  • {field}: <s>{frm}</s> ← <b>{to}</b>")
            else:
                lines.append(f"  • {field}: <b>{to}</b>")
        lines.append("")
    return "\n".join(lines).strip()


def summary_rows(state):
    """صفوف جاهزة للعرض في الصفحة / البوت."""
    rows = []
    for topic, data in (state.get("topics") or {}).items():
        rows.append({
            "topic": topic,
            "stage": data.get("المرحلة_الحالية") or "—",
            "status": data.get("الحالة") or "—",
            "next": data.get("موعد_قادم") or "—",
            "last": data.get("آخر_تطور") or "—",
        })
    return rows
