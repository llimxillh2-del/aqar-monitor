# -*- coding: utf-8 -*-
"""
ذاكرة السوق
============
ده اللي بيخلي النظام "فاهم السوق" بدل ما يبقى مجرد قارئ عناوين.
بيحتفظ بحالة كل موضوع متابَع (المرحلة الحالية، المواعيد، آخر تطور)
ويقارن كل دورة عشان يعرف إيه **اللي اتغير فعلًا**.
"""

import os
import json
from datetime import datetime, timezone

import config


def load():
    if os.path.exists(config.MARKET_STATE):
        try:
            with open(config.MARKET_STATE, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"topics": {}, "history": [], "updated": None}


def save(state):
    state["updated"] = datetime.now(timezone.utc).isoformat()
    # الاحتفاظ بآخر 120 حدث
    state["history"] = state.get("history", [])[-120:]
    with open(config.MARKET_STATE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=1)


EXTRACT_SYSTEM = (
    "أنت محرر بيانات دقيق. ترد بـ JSON صالح فقط، بدون أي نص قبله أو بعده. "
    "لا تخترع معلومات غير موجودة في النص المعطى لك. "
    "إذا لم تجد معلومة، استخدم null."
)


def extract_facts(ai, items):
    """يستخرج حالة كل موضوع من الأخبار الحالية."""
    if not ai.available or not items:
        return None

    listing = "\n".join(f"- {it['title']}" for it in items[:30])
    topics = "\n".join(f'  "{t}"' for t in config.TRACKED_TOPICS)

    prompt = f"""من العناوين دي:

{listing}

استخرج حالة كل موضوع من المواضيع دي:
{topics}

رجّع JSON بالشكل ده بالظبط:
{{
  "بيت الوطن": {{
     "المرحلة_الحالية": "نص أو null",
     "آخر_تطور": "جملة واحدة أو null",
     "موعد_قادم": "نص التاريخ أو null",
     "الحالة": "مفتوح/مغلق/منتظر/غير معروف"
  }},
  "بيتك في مصر": {{ ...نفس الحقول... }},
  "طروحات أراضي وزارة الإسكان": {{ ...نفس الحقول... }},
  "منصة مصر العقارية": {{ ...نفس الحقول... }}
}}

مهم: لو العناوين مافيهاش معلومة عن موضوع، حط null في حقوله. ماتخمّنش."""
    return ai.ask_json(prompt, EXTRACT_SYSTEM)


def _clean(v):
    if v is None:
        return None
    s = str(v).strip()
    if s.lower() in ("null", "none", "غير معروف", "لا يوجد", ""):
        return None
    return s


def diff_and_update(state, facts):
    """
    يقارن الحالة الجديدة بالقديمة ويرجع قائمة بالتغييرات الحقيقية.
    ده جوهر "فهم السوق" — نعرف إيه اللي اتغير مش إيه اللي اتقال.
    """
    if not facts:
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
            changes.append({
                "topic": topic,
                "field": field,
                "from": old_val,
                "to": new_val,
                "when": now,
            })

        # دمج: الجديد يغلب، بس ما نمسحش القديم بـ null
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
        lines.append(f"<b>▸ {topic}</b>")
        for ch in items:
            field = ch["field"].replace("_", " ")
            if ch["from"]:
                lines.append(f"  • {field}: <s>{ch['from']}</s> ← <b>{ch['to']}</b>")
            else:
                lines.append(f"  • {field}: <b>{ch['to']}</b>")
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
