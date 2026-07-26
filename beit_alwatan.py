# -*- coding: utf-8 -*-
"""
وحدة "بيت الوطن" — المتابعة المخصّصة
=====================================
دي الوحدة اللي بتخلي النظام "فاهم" ملف بيت الوطن مش بس قارئ عناوينه.

بتعمل إيه:
  1. تفلتر كل العناصر (أخبار + فيديو + مصادر رسمية) وتطلع اللي يخص بيت الوطن.
  2. تستخرج بالـ AI حقائق منظّمة: المرحلة، حالة الحجز، المواعيد، الأسعار،
     المساحات، المدن، الجدية، الشروط.
  3. تحوّل المواعيد لتواريخ حقيقية (ISO) عشان نحسب عدّاد تنازلي.
  4. تقارن بالحالة المحفوظة وتطلع **إيه اللي اتغير فعلًا** فقط.
  5. تبني خط زمني تراكمي للملف كله.
  6. تلخّص كلام الناس (كومنتات) وتطلع المخاوف والمعلومات العملية.
  7. تكتب توقّع للمرحلة الجاية + خطوات عملية.
"""

import os
import re
import json
from datetime import datetime, timezone, timedelta

import config
from ai_engine import SYSTEM_AR, SYSTEM_JSON

BEIT = config.BEIT_ALWATAN


# ============================================================
#  الحالة المحفوظة
# ============================================================

def _blank():
    return {
        "facts": {},         # حقل → {"value","since","source_title","source_link"}
        "timeline": [],      # الأحداث بالترتيب الزمني
        "dates": [],         # المواعيد المستخرجة بصيغة قابلة للحساب
        "cities": {},        # مدينة → عدد مرات الذكر
        "people": None,      # تحليل كلام الناس
        "forecast": None,    # توقع المرحلة الجاية
        "checklist": None,   # خطوات عملية
        "summary": None,     # ملخص تنفيذي مخصّص للملف
        "sources": [],       # آخر المصادر اللي البيانات اتبنت عليها
        "updated": None,
    }


def load():
    path = config.BEIT_STATE
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            base = _blank()
            base.update(data or {})
            return base
        except Exception:
            pass
    return _blank()


def save(state):
    state["updated"] = datetime.now(timezone.utc).isoformat()
    state["timeline"] = (state.get("timeline") or [])[-300:]
    path = config.BEIT_STATE
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


# ============================================================
#  الفلترة
# ============================================================

def matches(item):
    """هل العنصر ده يخص بيت الوطن؟"""
    blob = f"{item.get('title', '')} {item.get('snippet', '')}"
    return any(w in blob for w in BEIT["match_words"])


def filter_items(all_items):
    """يرجّع عناصر بيت الوطن مرتبة من الأحدث."""
    hits = [it for it in all_items if matches(it)]
    hits.sort(key=lambda x: x.get("published_ts", 0), reverse=True)
    return hits


def mentioned_cities(items):
    """عدّ المدن المذكورة — يدي فكرة عن الأماكن المطروحة."""
    counts = {}
    for it in items:
        blob = f"{it.get('title', '')} {it.get('snippet', '')}"
        for city in BEIT["cities"]:
            if city in blob:
                counts[city] = counts.get(city, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: kv[1], reverse=True))


# ============================================================
#  تحويل المواعيد العربية لتواريخ حقيقية
# ============================================================

AR_MONTHS = {
    "يناير": 1, "فبراير": 2, "مارس": 3, "أبريل": 4, "ابريل": 4, "مايو": 5,
    "يونيو": 6, "يونية": 6, "يوليو": 7, "يوليه": 7, "يولية": 7, "أغسطس": 8,
    "اغسطس": 8, "سبتمبر": 9, "أكتوبر": 10, "اكتوبر": 10, "نوفمبر": 11,
    "ديسمبر": 12,
    "كانون الثاني": 1, "شباط": 2, "آذار": 3, "نيسان": 4, "أيار": 5,
    "حزيران": 6, "تموز": 7, "آب": 8, "أيلول": 9, "تشرين الأول": 10,
    "تشرين الثاني": 11, "كانون الأول": 12,
}

_AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")


def parse_date(text, ref=None):
    """
    يحاول يطلع تاريخ حقيقي من نص عربي.
    بيرجع ISO ("2026-08-15") أو None.
    """
    if not text:
        return None
    s = str(text).translate(_AR_DIGITS).strip()
    ref = ref or datetime.now(timezone.utc)

    # 2026-08-15 أو 2026/8/15
    m = re.search(r"\b(20\d{2})[-/](\d{1,2})[-/](\d{1,2})\b", s)
    if m:
        y, mo, d = map(int, m.groups())
        return _safe_iso(y, mo, d)

    # 15/8/2026 أو 15-8-2026
    m = re.search(r"\b(\d{1,2})[-/](\d{1,2})[-/](20\d{2})\b", s)
    if m:
        d, mo, y = map(int, m.groups())
        return _safe_iso(y, mo, d)

    # 15 أغسطس 2026  /  15 أغسطس
    month_names = "|".join(sorted(AR_MONTHS, key=len, reverse=True))
    m = re.search(rf"\b(\d{{1,2}})\s+({month_names})\s*(20\d{{2}})?", s)
    if m:
        d = int(m.group(1))
        mo = AR_MONTHS[m.group(2)]
        y = int(m.group(3)) if m.group(3) else ref.year
        iso = _safe_iso(y, mo, d)
        # لو الشهر عدّى بأكتر من 6 شهور والسنة مش مكتوبة → غالبًا السنة الجاية
        if iso and not m.group(3):
            dt = datetime.fromisoformat(iso).replace(tzinfo=timezone.utc)
            if dt < ref - timedelta(days=180):
                iso = _safe_iso(y + 1, mo, d)
        return iso

    # أغسطس 2026 (شهر بس)
    m = re.search(rf"\b({month_names})\s+(20\d{{2}})\b", s)
    if m:
        return _safe_iso(int(m.group(2)), AR_MONTHS[m.group(1)], 1)

    return None


def _safe_iso(y, mo, d):
    try:
        return datetime(y, mo, d).date().isoformat()
    except ValueError:
        return None


def build_dates(facts):
    """
    يطلع قائمة المواعيد من الحقائق مع حالتها (قادم / اليوم / فات).
    """
    labels = {
        "موعد_فتح_الحجز": ("فتح باب الحجز", "open"),
        "موعد_غلق_الحجز": ("غلق باب الحجز", "close"),
        "موعد_السداد": ("سداد الجدية / المقدم", "pay"),
        "موعد_القرعة": ("القرعة / إعلان النتيجة", "draw"),
    }
    today = datetime.now(timezone.utc).date()
    out = []

    for field, (label, kind) in labels.items():
        raw = (facts.get(field) or {}).get("value")
        if not raw:
            continue
        iso = parse_date(raw)
        entry = {"label": label, "kind": kind, "raw": raw, "iso": iso}
        if iso:
            d = datetime.fromisoformat(iso).date()
            delta = (d - today).days
            entry["days_left"] = delta
            entry["status"] = ("فات" if delta < 0
                               else "النهاردة" if delta == 0
                               else "قادم")
        else:
            entry["days_left"] = None
            entry["status"] = "غير محدد بدقة"
        out.append(entry)

    out.sort(key=lambda e: (e["days_left"] is None,
                            e["days_left"] if e["days_left"] is not None else 0))
    return out


def next_deadline(dates):
    """أقرب موعد قادم — ده اللي بيظهر في العدّاد التنازلي."""
    upcoming = [d for d in dates
                if d.get("days_left") is not None and d["days_left"] >= 0]
    return upcoming[0] if upcoming else None


# ============================================================
#  الاستخراج بالـ AI
# ============================================================

def extract(ai, items, video_summaries=None, official_lines=None):
    """يستخرج حقائق بيت الوطن من العناوين والملخصات والمصادر الرسمية."""
    if not ai.available or not items:
        return None

    news = "\n".join(
        f"- {it['title']}" + (f" | {it['snippet'][:160]}" if it.get("snippet") else "")
        for it in items[:35]
    )
    vids = "\n".join(f"- {t}: {s[:500]}" for t, s in (video_summaries or [])[:3])
    official = "\n".join(f"- {ln}" for ln in (official_lines or [])[:25])

    prompt = f"""دي كل المعلومات المتاحة عن مشروع **بيت الوطن** (أراضي المصريين بالخارج) من آخر فترة:

### عناوين وأخبار:
{news}

{"### ملخصات فيديوهات تحليلية:" if vids else ""}
{vids}

{"### نصوص من صفحات رسمية (أعلى موثوقية — قدّمها على غيرها عند التعارض):" if official else ""}
{official}

استخرج الحقائق دي بالظبط. رجّع JSON فقط:

{{
  "المرحلة_الحالية": "اسم/رقم المرحلة المطروحة دلوقتي أو null",
  "حالة_الحجز": "مفتوح / مغلق / لم يُفتح بعد / منتهي / غير معروف",
  "موعد_فتح_الحجز": "التاريخ كما ورد نصًا أو null",
  "موعد_غلق_الحجز": "التاريخ كما ورد نصًا أو null",
  "موعد_السداد": "موعد سداد الجدية أو المقدم أو null",
  "موعد_القرعة": "موعد القرعة أو إعلان النتائج أو null",
  "سعر_المتر": "السعر بالجنيه أو الدولار كما ورد أو null",
  "المساحات_المتاحة": "المساحات المطروحة أو null",
  "المدن_المطروحة": "المدن المذكورة مفصولة بفاصلة أو null",
  "قيمة_الجدية": "قيمة جدية الحجز أو null",
  "شروط_التقديم": "أهم الشروط في جملة أو جملتين أو null",
  "طريقة_السداد": "بالدولار / بالجنيه / تحويل بنكي... أو null",
  "آخر_تطور": "أحدث تطور في جملة واحدة أو null",
  "درجة_الثقة": "عالية / متوسطة / منخفضة — حسب وضوح المصادر"
}}

قواعد صارمة:
- لو المعلومة مش موجودة صراحة في النص، حط null. **ماتخمّنش وماتفترضش**.
- المصادر الرسمية تغلب الأخبار عند التعارض.
- انقل التواريخ والأرقام كما وردت بالظبط بدون تقريب."""

    return ai.ask_json(prompt, SYSTEM_JSON)


def _clean(v):
    if v is None:
        return None
    s = re.sub(r"\s+", " ", str(v)).strip()
    if s.lower() in ("null", "none", "n/a", "-", "—", "", "غير معروف",
                     "غير محدد", "لا يوجد", "لم يذكر", "لم يُذكر"):
        return None
    return s


def diff_and_update(state, facts, items):
    """
    يقارن الحقائق الجديدة بالمحفوظة ويرجّع التغييرات الحقيقية فقط،
    ويضيفها للخط الزمني.
    """
    if not facts or not isinstance(facts, dict):
        return []

    now = datetime.now(timezone.utc).isoformat()
    stored = state.setdefault("facts", {})
    changes = []

    # أحدث مصدر — بنربط بيه أي تغيير
    src = items[0] if items else {}
    src_title = src.get("title", "")
    src_link = src.get("link", "")

    for field in BEIT["tracked_fields"] + ["طريقة_السداد", "درجة_الثقة"]:
        new_val = _clean(facts.get(field))
        if new_val is None:
            continue

        old_rec = stored.get(field) or {}
        old_val = old_rec.get("value")

        if old_val == new_val:
            continue

        # تجاهل التغييرات التافهة (نفس المعنى بصياغة مختلفة)
        if old_val and _too_similar(old_val, new_val):
            stored[field] = {**old_rec, "value": new_val, "seen": now}
            continue

        changes.append({
            "field": field,
            "from": old_val,
            "to": new_val,
            "when": now,
            "source_title": src_title,
            "source_link": src_link,
        })
        stored[field] = {
            "value": new_val,
            "since": now,
            "source_title": src_title,
            "source_link": src_link,
        }

    if changes:
        state.setdefault("timeline", []).extend(changes)

    state["dates"] = build_dates(stored)
    state["cities"] = mentioned_cities(items)
    state["sources"] = [
        {"title": it["title"], "link": it["link"],
         "source": it.get("source", ""), "published": it.get("published", "")}
        for it in items[:12]
    ]
    return changes


def _too_similar(a, b):
    """صياغة مختلفة لنفس المعلومة → مش تغيير حقيقي."""
    norm = lambda s: re.sub(r"[^\w؀-ۿ]+", "", str(s))
    na, nb = norm(a), norm(b)
    if na == nb:
        return True
    if not na or not nb:
        return False
    shorter, longer = (na, nb) if len(na) <= len(nb) else (nb, na)
    return shorter in longer and len(shorter) / len(longer) > 0.75


# ============================================================
#  كلام الناس
# ============================================================

def people_pulse(ai, comments, extra_context=""):
    """
    تحليل مجمّع لكلام الناس عن بيت الوطن — من كل الكومنتات مش فيديو واحد.
    """
    if not ai.available or not comments:
        return None

    ranked = sorted(comments, key=lambda c: c.get("likes", 0), reverse=True)[:60]
    listing = "\n".join(
        f'- ({c.get("likes", 0)}👍) {c.get("text", "")[:260]}' for c in ranked
    )

    prompt = f"""دي تعليقات مصريين بالخارج على محتوى يخص **بيت الوطن** وأراضي المصريين بالخارج.
(الرقم = عدد الإعجابات، يعني كام واحد موافق على الكلام ده)

{listing}

{extra_context}

اكتب تحليل منظّم بالأقسام دي بالظبط وبنفس العناوين:

## المزاج العام
(2-3 جمل: الناس مبسوطة؟ متوترة؟ فاقدة ثقة؟ مستنية إيه؟ — واذكر إيه اللي مخليهم كده)

## أكتر 5 شكاوى ومخاوف
(مرتبة حسب التكرار وعدد الإعجابات — كل واحدة سطر)

## أسئلة الناس اللي مالهاش إجابة
(الحاجات اللي بيسألوا عنها ومحدش رد عليهم — دي بتوضّح فين الغموض في المشروع)

## معلومات عملية من خبرات الناس
(حاجات ذكرها ناس عملوا الإجراء فعلًا — خطوات، مشاكل واجهتهم، حلول)
⚠️ نبّه إن ده كلام أفراد على الإنترنت ومحتاج تأكيد رسمي.

## مؤشرات من كلام الناس
(لو كلامهم بيوحي بحاجة عن المرحلة الجاية أو مشكلة قادمة، قولها — ووضّح إنها قراءة مش خبر)

قواعد: ماتخترعش. لو قسم مافيهوش كلام كافي، اكتب "مفيش إشارات واضحة في التعليقات المتاحة"."""

    return ai.ask(prompt, SYSTEM_AR)


# ============================================================
#  التوقعات والخطوات
# ============================================================

def forecast(ai, state, items, people_text=None):
    """توقع المرحلة الجاية بناءً على التاريخ المرصود."""
    if not ai.available:
        return None

    facts = state.get("facts") or {}
    fact_lines = "\n".join(
        f"- {k.replace('_', ' ')}: {v.get('value')}"
        for k, v in facts.items() if v.get("value")
    ) or "لا توجد حقائق مؤكدة محفوظة بعد."

    timeline = state.get("timeline") or []
    hist = "\n".join(
        f"- {t['when'][:10]}: {t['field'].replace('_', ' ')} "
        f"{'اتغير من ' + str(t['from']) + ' لـ ' if t.get('from') else 'اتسجل: '}{t['to']}"
        for t in timeline[-25:]
    ) or "لا يوجد تاريخ محفوظ بعد (أول تشغيل)."

    news = "\n".join(f"- {it['title']}" for it in items[:20])

    prompt = f"""ملف **بيت الوطن** — البيانات المرصودة:

### الحالة المؤكدة الآن:
{fact_lines}

### الخط الزمني للتغييرات المرصودة:
{hist}

### أحدث العناوين:
{news}

{"### خلاصة كلام الناس:" if people_text else ""}
{(people_text or "")[:1500]}

اكتب قراءة استشرافية لملف بيت الوطن بالأقسام دي بالظبط وبنفس العناوين:

## أين نحن الآن
(3 جمل: الملف واقف فين بالظبط دلوقتي)

## المتوقع في الأسابيع القادمة
(إيه الخطوة الجاية المرجّحة ومتى تقريبًا — مع توضيح إن ده ترجيح مش خبر)

## سيناريوهات
(3 سيناريوهات: الأرجح / متفائل / متحفظ — وإيه المؤشر اللي يأكد كل واحد)

## أماكن ومدن تستحق الانتباه
(بناءً على المدن المذكورة في الأخبار — ليه كل مدينة مرشحة وإيه اللي يعطّلها)

## إشارات إنذار
(علامات لو ظهرت تبقى تحذير حقيقي: تأجيل، تغيير شروط، تعديل أسعار...)

قواعد صارمة:
- كل استنتاج لازم يكون مبني على معطى من فوق — لو مش موجود قول "المعطيات مش كفاية".
- ماتخترعش تواريخ ولا أرقام.
- ماتقولش "اشتري" أو "متشتريش" — اعرض الاعتبارات."""

    return ai.ask(prompt, SYSTEM_AR)


def checklist(ai, state):
    """خطوات عملية بناءً على الحالة الحالية."""
    if not ai.available:
        return None

    facts = state.get("facts") or {}
    status = (facts.get("حالة_الحجز") or {}).get("value") or "غير معروف"
    stage = (facts.get("المرحلة_الحالية") or {}).get("value") or "غير محددة"
    conds = (facts.get("شروط_التقديم") or {}).get("value") or "غير مذكورة"
    pay = (facts.get("طريقة_السداد") or {}).get("value") or "غير مذكورة"
    dates = "\n".join(
        f"- {d['label']}: {d['raw']}" for d in (state.get("dates") or [])
    ) or "- لا توجد مواعيد مؤكدة"

    prompt = f"""حالة ملف بيت الوطن دلوقتي:
- المرحلة: {stage}
- حالة الحجز: {status}
- الشروط المعروفة: {conds}
- طريقة السداد: {pay}
- المواعيد:
{dates}

اكتب **خطوات عملية مرقّمة** لمصري مقيم بالخارج عايز يتابع أو يقدّم في المرحلة دي.
لكل خطوة: إيه المطلوب بالظبط، وفين يتعمل (الجهة أو المنصة).

قسّمها كده:
## لو الحجز مفتوح دلوقتي
## لو لسه مفتحش
## أوراق ومتطلبات لازم تكون جاهزة
## أخطاء شائعة تتجنبها

قواعد: اعتمد على المعلومات فوق فقط. أي حاجة مش مؤكدة اكتب جنبها "(يحتاج تأكيد من كراسة الشروط الرسمية)".
ماتخترعش رسوم ولا أرقام ولا روابط."""

    return ai.ask(prompt, SYSTEM_AR)


def summarize(ai, state, items):
    """ملخص تنفيذي قصير مخصّص لبيت الوطن."""
    if not ai.available or not items:
        return None

    facts = state.get("facts") or {}
    fact_lines = "\n".join(
        f"- {k.replace('_', ' ')}: {v.get('value')}"
        for k, v in facts.items() if v.get("value")
    ) or "لا توجد حقائق مؤكدة."
    news = "\n".join(f"- {it['title']}" for it in items[:25])

    prompt = f"""### الحالة المرصودة لملف بيت الوطن:
{fact_lines}

### أحدث الأخبار:
{news}

اكتب ملخصًا تنفيذيًا لملف **بيت الوطن** لمصري مقيم بالخارج، بالأقسام دي بالظبط:

## الخلاصة في سطرين
(أهم حاجة يعرفها دلوقتي — من غير لف)

## آخر المستجدات
(3-5 نقاط قصيرة بأحدث اللي حصل)

## المواعيد المهمة
(المواعيد المؤكدة بس — لو مفيش، اكتب "لا توجد مواعيد معلنة مؤكدة حتى الآن")

## غموض ومعلومات ناقصة
(إيه اللي لسه مش واضح ومحتاج إعلان رسمي)

قواعد: اعتمد على المعطيات فوق فقط، ماتخترعش أرقام أو تواريخ."""

    return ai.ask(prompt, SYSTEM_AR)


# ============================================================
#  للعرض
# ============================================================

def dashboard(state):
    """يحوّل الحالة لشكل جاهز للعرض في الصفحة والبوت."""
    facts = state.get("facts") or {}
    dates = state.get("dates") or build_dates(facts)

    def val(field):
        return (facts.get(field) or {}).get("value")

    return {
        "stage": val("المرحلة_الحالية"),
        "booking": val("حالة_الحجز"),
        "price": val("سعر_المتر"),
        "areas": val("المساحات_المتاحة"),
        "cities_text": val("المدن_المطروحة"),
        "deposit": val("قيمة_الجدية"),
        "conditions": val("شروط_التقديم"),
        "payment": val("طريقة_السداد"),
        "last": val("آخر_تطور"),
        "confidence": val("درجة_الثقة") or "غير محددة",
        "dates": dates,
        "next": next_deadline(dates),
        "cities": state.get("cities") or {},
        "timeline": list(reversed(state.get("timeline") or []))[:40],
        "sources": state.get("sources") or [],
        "summary": state.get("summary"),
        "people": state.get("people"),
        "forecast": state.get("forecast"),
        "checklist": state.get("checklist"),
        "updated": state.get("updated"),
    }


FIELD_LABELS = {
    "المرحلة_الحالية": "المرحلة الحالية",
    "حالة_الحجز": "حالة الحجز",
    "موعد_فتح_الحجز": "موعد فتح الحجز",
    "موعد_غلق_الحجز": "موعد غلق الحجز",
    "موعد_السداد": "موعد السداد",
    "موعد_القرعة": "موعد القرعة",
    "سعر_المتر": "سعر المتر",
    "المساحات_المتاحة": "المساحات المتاحة",
    "المدن_المطروحة": "المدن المطروحة",
    "قيمة_الجدية": "قيمة الجدية",
    "شروط_التقديم": "شروط التقديم",
    "طريقة_السداد": "طريقة السداد",
    "آخر_تطور": "آخر تطور",
    "درجة_الثقة": "درجة الثقة في البيانات",
}


def format_changes(changes):
    """صياغة تغييرات بيت الوطن لرسالة تليجرام."""
    if not changes:
        return None
    import html as _html

    lines = ["🏘️ <b>تحديث في ملف بيت الوطن</b>", ""]
    for ch in changes:
        label = FIELD_LABELS.get(ch["field"], ch["field"].replace("_", " "))
        to = _html.escape(str(ch["to"])[:200])
        if ch.get("from"):
            frm = _html.escape(str(ch["from"])[:120])
            lines.append(f"▸ <b>{label}</b>\n   <s>{frm}</s>\n   ← <b>{to}</b>")
        else:
            lines.append(f"▸ <b>{label}</b>: {to}")
    if changes and changes[0].get("source_link"):
        lines += ["", f'<a href="{_html.escape(changes[0]["source_link"])}">المصدر ←</a>']
    return "\n".join(lines)
