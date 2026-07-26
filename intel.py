# -*- coding: utf-8 -*-
"""
رادار الإشارات المبكرة
=======================
ده المحرك اللي بيخلي النظام يعرف من **كلام الناس** حاجات لسه منزلتش في الأخبار.

الفكرة الأساسية:
    حد كلّم الهيئة بالتليفون. حد راح المقر. حد شاف الرابط اتفتح للحظة.
    حد شغّال جوه بيقول لصاحبه. الكلام ده بيتقال في الكومنتات قبل الجرايد
    بأيام أحيانًا. المشكلة إنه غرقان وسط آلاف التعليقات الفاضية والشائعات.

المنهج (٦ مراحل):

  ١. الحصاد     — سحب كل كلام الناس من يوتيوب/تليجرام/Reddit/سوشيال
  ٢. الغربلة    — فلتر ذكي بدون AI يستبعد الآراء والدعاء والكلام الفاضي،
                   ويرفع اللي فيه أرقام أو مواعيد أو "أنا قدمت/كلمت/شفت"
  ٣. الاستخراج  — الـ AI يحوّل النص لادعاء ذري: "الحجز هيفتح ١٥ أغسطس"
  ٤. التجميع    — الادعاءات المتشابهة بتتلم في إشارة واحدة (تطبيع عربي +
                   تشابه Jaccard — بدون AI عشان يفضل شغال حتى لو الـ AI وقع)
  ٥. التقييم    — كام شخص؟ من كام **قناة مستقلة**؟ كام واحد شاف بنفسه؟
                   والأهم: هل الكلام ده موجود في الأخبار ولا **جديد تمامًا**؟
  ٦. المتابعة   — لما مصدر رسمي يأكد الإشارة، بنحسب **الجمهور سبق الأخبار بكام يوم**

المخرج النهائي: قايمة إشارات مرتبة بالقوة، كل واحدة معاها:
    مين قالها · من فين · إمتى · إيه دليلها · قد إيه نثق فيها
"""

import os
import re
import json
import math
import hashlib
from datetime import datetime, timezone, timedelta

import config
from ai_engine import SYSTEM_JSON, SYSTEM_AR


# ============================================================
#  تطبيع النص العربي
# ============================================================

_TASHKEEL = re.compile(r"[ً-ْـٰ]")
_AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")

STOPWORDS = {
    "في", "من", "على", "الى", "إلى", "عن", "مع", "هو", "هي", "ان", "أن",
    "ال", "اللي", "دي", "ده", "كده", "يعني", "بس", "علشان", "عشان", "لو",
    "كان", "هيكون", "هو", "انا", "أنا", "احنا", "إحنا", "انت", "هل", "ما",
    "لا", "كل", "بعد", "قبل", "الان", "الآن", "و", "ف", "ب", "ل", "ك",
    "هذا", "هذه", "ذلك", "التي", "الذي", "there", "the", "and", "for",
}


def norm(text):
    """تطبيع عربي: يشيل التشكيل ويوحّد الألف والياء والتاء المربوطة."""
    s = str(text or "")
    s = s.translate(_AR_DIGITS)
    s = _TASHKEEL.sub("", s)
    s = re.sub(r"[إأآٱا]", "ا", s)
    s = s.replace("ى", "ي").replace("ة", "ه").replace("ؤ", "و").replace("ئ", "ي")
    s = re.sub(r"[^\w\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip().lower()


def tokens(text):
    return {t for t in norm(text).split() if len(t) > 2 and t not in STOPWORDS}


def numbers_in(text):
    """الأرقام والتواريخ — دي أقوى دليل على إن ادعاءين نفس الحاجة."""
    return set(re.findall(r"\d+", norm(text)))


def similarity(a, b):
    """
    تشابه ادعاءين. Jaccard على الكلمات + وزن إضافي لتطابق الأرقام.
    مافيش AI هنا عن قصد — التجميع لازم يفضل شغال حتى لو كل المزوّدين وقعوا.
    """
    ta, tb = tokens(a), tokens(b)
    if not ta or not tb:
        return 0.0
    jac = len(ta & tb) / len(ta | tb)

    na, nb = numbers_in(a), numbers_in(b)
    if na and nb:
        if na & nb:
            jac = min(1.0, jac + 0.22)      # نفس الرقم = مؤشر قوي
        elif not (na & nb):
            jac = max(0.0, jac - 0.18)      # أرقام مختلفة = غالبًا ادعاء مختلف
    return jac


# ============================================================
#  الغربلة — بدون AI
# ============================================================

def informativeness(utt):
    """
    كام ده يستاهل نبعته للـ AI؟ 0 = كلام فاضي، 10+ = يستاهل جدًا.
    الفلتر ده بيوفّر ٩٠٪ من استهلاك الـ AI.
    """
    text = utt.get("text", "")
    if len(text) < 25:
        return 0

    low = norm(text)
    score = 0

    def has(markers):
        """norm() ممكن ترجّع نص فاضي لعلامة ترقيم — والفاضي بيطابق أي حاجة."""
        return [m for m in (norm(x) for x in markers) if m and m in low]

    # شاف بنفسه — أقوى مؤشر على الإطلاق
    if has(config.FIRSTHAND_MARKERS):
        score += 6

    # فيه كلمات معلوماتية
    score += min(len(has(config.INFO_MARKERS)) * 2, 6)

    # فيه أرقام (مواعيد/أسعار/مساحات)
    nums = re.findall(r"\d+", text)
    if nums:
        score += 2
        if any(len(n) >= 4 for n in nums):        # سنة أو سعر
            score += 1

    # تفاعل الناس عليه
    likes = utt.get("likes", 0)
    if likes > 0:
        score += min(int(math.log10(likes + 1) * 1.6), 4)

    # رد على سؤال — غالبًا فيه إجابة حقيقية
    if utt.get("parent"):
        score += 1

    # كلام فاضي معروف
    if re.fullmatch(r"[\s\W]*", text):
        return 0
    noise = ("ربنا يوفق", "الله المستعان", "اشتركوا", "لايك", "متابع",
             "جزاك الله", "شكرا", "تسلم", "الله يكرمك", "ما شاء الله")
    if has(noise) and score < 5:
        score -= 3

    return max(score, 0)


def is_question(text):
    raw = str(text or "")
    if "؟" in raw or "?" in raw:
        return True
    low = norm(raw)
    # مهم: norm() بتشيل علامات الترقيم، فعلامة زي "؟" بتبقى نص فاضي
    # و "" in low بترجع True دايمًا — فلازم نستبعد الفاضي.
    for marker in config.QUESTION_MARKERS:
        m = norm(marker)
        if m and m in low:
            return True
    return False


def shortlist(utterances, limit=None):
    """
    يرتّب ويرجّع أحسن الكلام اللي يستاهل استخراج.
    الأسئلة بتعدّي بحد أدنى أقل — رخيصة في التحليل ومفيدة جدًا
    في كشف فجوات المعلومات الرسمية.
    """
    limit = limit or config.INTEL_MAX_CLAIMS_PER_CYCLE
    scored = []
    for u in utterances:
        s = informativeness(u)
        floor = 2 if is_question(u.get("text", "")) else 4
        if s >= floor:
            scored.append((s, u))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [u for _, u in scored[:limit]]


# ============================================================
#  الحالة
# ============================================================

def _blank():
    return {
        "signals": {},        # id → signal
        "seen": [],           # بصمات الكلام اللي اتعالج
        "questions": [],      # أسئلة الناس اللي مالهاش إجابة
        "digest": None,       # سرد الـ AI للرادار
        "stats": {"cycles": 0, "utterances": 0, "confirmed": 0,
                  "avg_lead_days": None},
        "updated": None,
    }


def load():
    if os.path.exists(config.INTEL_STATE):
        try:
            with open(config.INTEL_STATE, encoding="utf-8") as f:
                data = json.load(f) or {}
            base = _blank()
            base.update(data)
            return base
        except Exception:
            pass
    return _blank()


def save(state):
    state["updated"] = datetime.now(timezone.utc).isoformat()
    state["seen"] = list(dict.fromkeys(state.get("seen") or []))[-8000:]
    state["questions"] = (state.get("questions") or [])[-120:]
    path = config.INTEL_STATE
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


# ============================================================
#  الاستخراج بالـ AI
# ============================================================

CLAIM_TYPES = ["موعد", "سعر", "إجراء", "شرط", "مكان", "مشكلة", "سؤال", "شائعة"]


def extract_claims(ai, utterances):
    """
    يحوّل كلام الناس لادعاءات ذرية قابلة للمقارنة.
    بيشتغل على دفعات صغيرة عشان الدقة.
    """
    if not ai.available or not utterances:
        return []

    claims = []
    batch_size = 20

    for start in range(0, len(utterances), batch_size):
        batch = utterances[start:start + batch_size]
        listing = "\n".join(
            f'{i + 1}. [{u["platform"]}·{u.get("likes", 0)}👍] {u["text"][:420]}'
            for i, u in enumerate(batch)
        )

        prompt = f"""دي تعليقات ومنشورات ناس بيتكلموا عن مشروع **بيت الوطن** (أراضي المصريين بالخارج).

مهمتك: تطلّع من كل واحدة **الادعاء الواقعي** الموجود فيها — يعني المعلومة اللي بيقولها، مش رأيه ولا شعوره.

{listing}

رجّع JSON فقط:
{{
  "claims": [
    {{
      "n": رقم التعليق,
      "statement": "الادعاء في جملة واحدة قصيرة وواضحة ومحايدة",
      "type": "واحد من: موعد / سعر / إجراء / شرط / مكان / مشكلة / سؤال / شائعة",
      "firsthand": true لو بيتكلم عن تجربة شخصية عملها بنفسه (قدّم، كلّم، راح، شاف) وإلا false,
      "specific": true لو فيه رقم أو تاريخ أو اسم مكان محدد وإلا false
    }}
  ]
}}

قواعد صارمة جدًا:
- **تجاهل تمامًا**: الآراء، الدعاء، الشكر، الشتائم، التعليقات العامة، طلبات الاشتراك، والكلام اللي مافيهوش معلومة.
  لو تعليق مافيهوش ادعاء واقعي، **متحطهوش في الرد خالص**.
- الادعاء لازم يكون **قابل للتصديق أو التكذيب**. "السوق وحش" مش ادعاء. "سعر المتر بقى 5000" ادعاء.
- اكتب الادعاء بصيغة محايدة موحّدة: "فتح الحجز يوم ١٥ أغسطس" مش "هو قال إن ممكن يفتح ١٥ أغسطس".
- **ماتضفش أي معلومة مش مكتوبة في التعليق**. لو التعليق ناقص، خلي الادعاء ناقص زيه.
- لو التعليق سؤال، حطه type="سؤال" والـ statement يكون السؤال نفسه."""

        result = ai.ask_json(prompt, SYSTEM_JSON, fast=False)
        if not isinstance(result, dict):
            continue

        for c in (result.get("claims") or []):
            if not isinstance(c, dict):
                continue
            statement = re.sub(r"\s+", " ", str(c.get("statement") or "")).strip()
            if len(statement) < 12:
                continue
            try:
                idx = int(re.sub(r"\D", "", str(c.get("n", "")))) - 1
            except (ValueError, TypeError):
                continue
            if not (0 <= idx < len(batch)):
                continue

            ctype = str(c.get("type") or "").strip()
            if ctype not in CLAIM_TYPES:
                ctype = "شائعة"

            claims.append({
                "statement": statement,
                "type": ctype,
                "firsthand": bool(c.get("firsthand")),
                "specific": bool(c.get("specific")),
                "utterance": batch[idx],
            })

    return claims


_CLAUSE_SPLIT = re.compile(r"[.،؛!?؟\n]+|\s+(?:و|بس|لكن|علشان|عشان)\s+")

# صيغ تمهيدية بتفرق بين شخص وشخص وهما بيقولوا نفس المعلومة —
# شيلها عشان "أنا كلمت الهيئة والحجز ١٥ أغسطس" و"صاحبي قال الحجز ١٥ أغسطس"
# يتلموا في إشارة واحدة بدل ما يفضلوا اتنين منفصلين.
_PREAMBLE = re.compile(
    r"^\s*(?:و|ف|بص|يا جماعة|للعلم|معلومة|ملحوظة|"
    r"أنا|انا|احنا|إحنا|صاحبي|أخويا|اخويا|قريبي|واحد|حد|ناس)\s+"
    r"(?:\S+\s+){0,3}?(?:قال|قالوا|قالولي|بيقول|بيقولوا|سمعت|عرفت|"
    r"شفت|كلمت|اتصلت|رحت|قدمت|حجزت)\s*(?:إن|ان|إنه|انه|ب)?\s*",
    re.U)


def _core_statement(text):
    """
    يستخرج الجملة اللي فيها المعلومة الفعلية من تعليق طويل.
    بيدوّر على الجزء اللي فيه رقم أو كلمة معلوماتية، وبيشيل التمهيد الشخصي.
    """
    clauses = [c.strip() for c in _CLAUSE_SPLIT.split(text) if c and c.strip()]
    best, best_score = text, -1

    for clause in clauses:
        if len(clause) < 12:
            continue
        low = norm(clause)
        score = 0
        if re.search(r"\d", clause):
            score += 3
        score += sum(1 for m in config.INFO_MARKERS
                     if norm(m) and norm(m) in low)
        score += sum(1 for w in config.BEIT_ALWATAN["match_words"]
                     if w in clause)
        if score > best_score:
            best, best_score = clause, score

    core = _PREAMBLE.sub("", best).strip()
    return (core if len(core) >= 12 else best)[:200]


def fallback_claims(utterances):
    """
    لو مفيش AI: بنبني الادعاء من النص نفسه بعد تنظيفه.
    أضعف من استخراج الـ AI، بس النظام يفضل شغال وبيلمّ المتشابه.
    """
    out = []
    for u in utterances:
        text = u["text"]
        score = informativeness(u)

        # الأسئلة رخيصة ومهمة — حد أدنى أقل
        if is_question(text):
            if score >= 3:
                out.append({
                    "statement": text[:200],
                    "type": "سؤال",
                    "firsthand": False,
                    "specific": bool(re.search(r"\d", text)),
                    "utterance": u,
                })
            continue

        if score < 7:
            continue

        out.append({
            "statement": _core_statement(text),
            "type": "شائعة",
            "firsthand": bool([m for m in (norm(x) for x in
                                           config.FIRSTHAND_MARKERS)
                               if m and m in norm(text)]),
            "specific": bool(re.search(r"\d", text)),
            "utterance": u,
        })
    return out


# ============================================================
#  التجميع والتقييم
# ============================================================

def _sig_id(statement):
    return hashlib.sha1(norm(statement).encode("utf-8")).hexdigest()[:12]


def merge(state, claims):
    """
    يضم كل ادعاء لإشارة موجودة أو يعمل إشارة جديدة.
    بيرجع (إشارات جديدة، إشارات اتقوّت).
    """
    signals = state.setdefault("signals", {})
    seen = set(state.setdefault("seen", []))
    now = datetime.now(timezone.utc).isoformat()

    fresh, strengthened = [], []

    for claim in claims:
        u = claim["utterance"]

        if claim["type"] == "سؤال":
            state.setdefault("questions", []).append({
                "text": claim["statement"], "when": now,
                "platform": u["platform"], "url": u.get("url", ""),
                "likes": u.get("likes", 0),
            })
            seen.add(u["id"])
            continue

        # ندوّر على إشارة مشابهة
        best_id, best_score = None, 0.0
        for sid, sig in signals.items():
            score = similarity(claim["statement"], sig["statement"])
            if score > best_score:
                best_id, best_score = sid, score

        source = {
            "platform": u["platform"],
            "channel": u["channel"],
            "author": u.get("author", ""),
            "url": u.get("url", ""),
            "likes": u.get("likes", 0),
            "when": u.get("published", "") or now,
            "firsthand": claim["firsthand"],
            "quote": u["text"][:300],
        }

        if best_id and best_score >= config.INTEL_SIMILARITY:
            sig = signals[best_id]
            # نفس الشخص مايتحسبش مرتين
            known = {(s["channel"], s["author"], s["quote"][:60])
                     for s in sig["sources"]}
            if (source["channel"], source["author"], source["quote"][:60]) in known:
                seen.add(u["id"])
                continue

            before = independence(sig)
            sig["sources"].append(source)
            sig["last_seen"] = now
            if claim["specific"]:
                sig["specific"] = True
            after = independence(sig)
            rescore(sig)
            if after > before:
                strengthened.append(sig)
        else:
            sid = _sig_id(claim["statement"])
            if sid in signals:
                signals[sid]["sources"].append(source)
                rescore(signals[sid])
                seen.add(u["id"])
                continue
            sig = {
                "id": sid,
                "statement": claim["statement"],
                "type": claim["type"],
                "specific": claim["specific"],
                "sources": [source],
                "status": "جديدة",
                "novel": None,
                "first_seen": now,
                "last_seen": now,
                "confirmed_at": None,
                "confirmed_by": None,
                "lead_days": None,
                "weight": 0,
            }
            rescore(sig)
            signals[sid] = sig
            fresh.append(sig)

        seen.add(u["id"])

    state["seen"] = list(seen)
    return fresh, strengthened


def independence(sig):
    """كام **قناة مستقلة** قالت الكلام ده؟ ده المقياس الحقيقي مش عدد الناس."""
    return len({s["channel"] for s in sig["sources"]})


def firsthand_count(sig):
    return sum(1 for s in sig["sources"] if s.get("firsthand"))


def rescore(sig):
    """
    وزن الإشارة. الاستقلالية أهم حاجة — ١٠ ناس في نفس القناة ممكن
    يكونوا بيرددوا نفس الشائعة، بس شخصين من قناتين مختلفين إشارة حقيقية.
    """
    ind = independence(sig)
    fh = firsthand_count(sig)
    likes = sum(s.get("likes", 0) for s in sig["sources"])
    n = len(sig["sources"])

    weight = (ind * 4) + (fh * 3) + min(n, 8)
    if likes > 0:
        weight += min(math.log10(likes + 1) * 2, 5)
    if sig.get("specific"):
        weight += 2
    if len({s["platform"] for s in sig["sources"]}) > 1:
        weight += 3                      # منصتين مختلفتين = أقوى بكتير

    sig["weight"] = round(weight, 1)
    sig["independence"] = ind
    sig["firsthand"] = fh
    sig["mentions"] = n
    sig["total_likes"] = likes
    sig["tier"] = tier(sig)
    return sig


def tier(sig):
    """تصنيف الثقة — ده اللي بيظهر للمستخدم عشان يعرف يعتمد قد إيه."""
    if sig.get("status") == "مؤكدة رسميًا":
        return "مؤكدة رسميًا"
    if sig.get("status") == "مكذّبة":
        return "مكذّبة"
    ind, fh = independence(sig), firsthand_count(sig)
    if ind >= 3 or (ind >= 2 and fh >= 2):
        return "إشارة قوية"
    if ind >= 2:
        return "إشارة متقاطعة"
    if fh >= 1:
        return "شهادة فردية"
    return "إشارة فردية"


TIER_ORDER = {"مؤكدة رسميًا": 0, "إشارة قوية": 1, "إشارة متقاطعة": 2,
              "شهادة فردية": 3, "إشارة فردية": 4, "مكذّبة": 5}


# ============================================================
#  الجدّة والتأكيد الرسمي
# ============================================================

def assess_novelty(state, news_items, official_lines, known_facts):
    """
    أهم سؤال: هل الكلام ده **موجود في الأخبار** ولا الناس بيقولوا حاجة
    محدش نشرها؟ لو مش موجود → دي بالظبط اللي المستخدم عايز يعرفها.
    """
    corpus = []
    for it in (news_items or []):
        corpus.append(f"{it.get('title', '')} {it.get('snippet', '')}")
    corpus += list(official_lines or [])
    for v in (known_facts or {}).values():
        if isinstance(v, dict) and v.get("value"):
            corpus.append(str(v["value"]))

    corpus_tokens = [tokens(c) for c in corpus if c]

    for sig in state.get("signals", {}).values():
        st = tokens(sig["statement"])
        if not st:
            continue
        best = 0.0
        for ct in corpus_tokens:
            if not ct:
                continue
            overlap = len(st & ct) / len(st)
            best = max(best, overlap)
        sig["coverage"] = round(best, 2)
        sig["novel"] = best < 0.5        # أقل من نص الكلمات موجودة = جديد


def check_confirmation(state, news_items, official_lines):
    """
    لو مصدر رسمي أو خبر أكّد إشارة قديمة → بنعلّمها ونحسب
    **الجمهور سبق الأخبار بكام يوم**. ده مقياس ثقة النظام نفسه.
    """
    official_blob = [(ln, "مصدر رسمي", "") for ln in (official_lines or [])]
    news_blob = [(f"{it.get('title', '')} {it.get('snippet', '')}",
                  it.get("source", "خبر"), it.get("link", ""))
                 for it in (news_items or [])]
    all_blob = official_blob + news_blob

    newly = []
    now = datetime.now(timezone.utc)

    for sig in state.get("signals", {}).values():
        if sig.get("status") in ("مؤكدة رسميًا", "مكذّبة"):
            continue
        st = tokens(sig["statement"])
        if not st:
            continue

        for text, source, link in all_blob:
            ct = tokens(text)
            if not ct:
                continue
            if len(st & ct) / len(st) < 0.65:
                continue
            # الأرقام لازم تتطابق لو موجودة
            ns, nc = numbers_in(sig["statement"]), numbers_in(text)
            if ns and nc and not (ns & nc):
                continue

            sig["status"] = "مؤكدة رسميًا"
            sig["confirmed_at"] = now.isoformat()
            sig["confirmed_by"] = {"source": source, "link": link,
                                   "text": text[:200]}
            try:
                first = datetime.fromisoformat(sig["first_seen"])
                sig["lead_days"] = max((now - first).days, 0)
            except (TypeError, ValueError):
                sig["lead_days"] = None
            sig["tier"] = "مؤكدة رسميًا"
            newly.append(sig)
            break

    if newly:
        stats = state.setdefault("stats", {})
        stats["confirmed"] = int(stats.get("confirmed", 0)) + len(newly)
        leads = [s["lead_days"] for s in state["signals"].values()
                 if s.get("lead_days") is not None]
        if leads:
            stats["avg_lead_days"] = round(sum(leads) / len(leads), 1)
            stats["max_lead_days"] = max(leads)
    return newly


def expire(state):
    """الإشارات اللي محدش كررها من زمان بتتحط على الرف."""
    cutoff = datetime.now(timezone.utc) - timedelta(
        days=config.INTEL_SIGNAL_TTL_DAYS)
    for sig in state.get("signals", {}).values():
        if sig.get("status") in ("مؤكدة رسميًا", "مكذّبة", "منتهية"):
            continue
        try:
            last = datetime.fromisoformat(sig.get("last_seen", ""))
        except (TypeError, ValueError):
            continue
        if last < cutoff:
            sig["status"] = "منتهية"
            sig["tier"] = "منتهية"


# ============================================================
#  السرد بالـ AI
# ============================================================

def write_digest(ai, state, top_n=18):
    """يحوّل الرادار لسرد بشري مفهوم."""
    if not ai.available:
        return None
    sigs = ranked(state)[:top_n]
    if not sigs:
        return None

    listing = "\n".join(
        f'- [{s["tier"]}] {s["statement"]} '
        f'(قالها {s["mentions"]} شخص من {s["independence"]} مصدر مستقل، '
        f'{s["firsthand"]} منهم تجربة شخصية'
        f'{"، **مش موجودة في الأخبار**" if s.get("novel") else ""})'
        for s in sigs
    )
    questions = "\n".join(
        f'- {q["text"]}' for q in (state.get("questions") or [])[-15:]
    )

    prompt = f"""دي إشارات مستخرجة من كلام الناس (تعليقات يوتيوب، قنوات تليجرام، Reddit) عن مشروع **بيت الوطن**.
الإشارة = معلومة قالها ناس، مش خبر رسمي.

### الإشارات المرصودة:
{listing}

{"### أسئلة الناس اللي مالهاش إجابة:" if questions else ""}
{questions}

اكتب تقرير استخباراتي قصير بالأقسام دي بالظبط وبنفس العناوين:

## إيه اللي الناس بتقوله ومش في الأخبار
(أهم ٣-٥ معلومات ظهرت في كلام الناس ولسه منزلتش رسميًا — دي أهم حاجة في التقرير.
 لكل واحدة قول قد إيه نثق فيها بناءً على عدد المصادر المستقلة)

## إشارات تستاهل متابعة
(حاجات لسه ضعيفة بس لو اتأكدت تبقى مهمة)

## تناقضات
(لو فيه ناس بتقول حاجات متعارضة — وضّح التعارض من غير ما ترجّح)

## فجوات المعلومات
(الأسئلة اللي الناس بتسألها ومحدش رد عليها — دي بتوضّح فين الغموض الرسمي)

## قراءة عامة
(٣ جمل: كلام الناس ده بيوحي بإيه؟)

قواعد صارمة:
- **كل جملة لازم توضّح إن ده كلام ناس مش خبر مؤكد.**
- ماتزوّدش أي معلومة مش في القايمة فوق.
- ماتحوّلش الإشارة الضعيفة لحقيقة. لو حاجة قالها شخص واحد، قول كده صراحة.
- ماتديش نصيحة استثمارية."""

    return ai.ask(prompt, SYSTEM_AR)


# ============================================================
#  العرض والتنبيه
# ============================================================

def ranked(state, include_expired=False):
    """الإشارات مرتبة: الأعلى ثقة الأول، وجوه كل فئة الأقوى وزنًا."""
    sigs = list((state.get("signals") or {}).values())
    if not include_expired:
        sigs = [s for s in sigs if s.get("status") != "منتهية"]
    sigs.sort(key=lambda s: (TIER_ORDER.get(s.get("tier", ""), 9),
                             -s.get("weight", 0)))
    return sigs


def board(state):
    """نموذج عرض جاهز للصفحة والبوت."""
    sigs = ranked(state)
    stats = state.get("stats") or {}
    return {
        "signals": sigs,
        "novel": [s for s in sigs if s.get("novel")
                  and s.get("status") != "مؤكدة رسميًا"],
        "confirmed": [s for s in sigs if s.get("status") == "مؤكدة رسميًا"],
        "questions": list(reversed(state.get("questions") or []))[:20],
        "digest": state.get("digest"),
        "stats": stats,
        "updated": state.get("updated"),
        "counts": {
            "total": len(sigs),
            "strong": sum(1 for s in sigs
                          if s.get("tier") in ("إشارة قوية", "إشارة متقاطعة")),
            "novel": sum(1 for s in sigs if s.get("novel")
                         and s.get("status") != "مؤكدة رسميًا"),
            "confirmed": sum(1 for s in sigs
                             if s.get("status") == "مؤكدة رسميًا"),
        },
    }


TIER_ICON = {"مؤكدة رسميًا": "✅", "إشارة قوية": "🟠", "إشارة متقاطعة": "🟡",
             "شهادة فردية": "🔵", "إشارة فردية": "⚪", "مكذّبة": "❌"}


def _passes_alert_level(sig):
    level = config.INTEL_ALERT_LEVEL
    if level == "confirmed":
        return sig.get("status") == "مؤكدة رسميًا"
    if level == "cross":
        return independence(sig) >= 2 or sig.get("status") == "مؤكدة رسميًا"
    return True                                     # "any"


def format_alert(sig, is_new=True):
    """رسالة تليجرام لإشارة واحدة."""
    import html as _html

    icon = TIER_ICON.get(sig.get("tier"), "🔍")
    head = ("🔍 <b>إشارة مبكرة من كلام الناس</b>" if is_new
            else "📈 <b>إشارة اتقوّت</b>")
    if sig.get("status") == "مؤكدة رسميًا":
        head = "✅ <b>إشارة اتأكدت رسميًا</b>"

    lines = [head, ""]
    lines.append(f"{icon} <b>{_html.escape(sig['statement'])}</b>")
    lines.append("")
    lines.append(f"<b>الثقة:</b> {_html.escape(sig.get('tier', '—'))}")
    lines.append(f"<b>قالها:</b> {sig.get('mentions', 0)} شخص من "
                 f"{sig.get('independence', 0)} مصدر مستقل")
    if sig.get("firsthand"):
        lines.append(f"<b>تجربة شخصية:</b> {sig['firsthand']} منهم")
    if sig.get("novel"):
        lines.append("<b>⚠️ مش موجودة في الأخبار الرسمية حتى الآن</b>")

    if sig.get("lead_days") is not None:
        lines.append(f"<b>سبقت الأخبار بـ:</b> {sig['lead_days']} يوم")
    if sig.get("confirmed_by"):
        cb = sig["confirmed_by"]
        lines.append(f"<b>أكّدها:</b> {_html.escape(str(cb.get('source', '')))}")

    lines.append("")
    lines.append("<b>الاقتباسات:</b>")
    for s in sig["sources"][:3]:
        who = s.get("author") or s.get("channel", "")
        mark = " 👁" if s.get("firsthand") else ""
        quote = _html.escape(s.get("quote", "")[:180])
        if s.get("url"):
            lines.append(f'• <a href="{_html.escape(s["url"])}">'
                         f'{_html.escape(who)}</a>{mark}: «{quote}»')
        else:
            lines.append(f"• {_html.escape(who)}{mark}: «{quote}»")

    lines.append("")
    lines.append("<i>⚠️ ده كلام ناس على الإنترنت — مش مصدر رسمي. "
                 "راجع كراسة الشروط قبل أي إجراء.</i>")
    return "\n".join(lines)


def alerts(fresh, strengthened, confirmed):
    """يرجّع رسائل التنبيه حسب مستوى الحساسية المضبوط."""
    msgs = []

    for sig in confirmed:
        msgs.append(format_alert(sig, is_new=False))

    picked = [s for s in fresh if _passes_alert_level(s)]
    picked.sort(key=lambda s: -s.get("weight", 0))
    # الجديد غير المنشور في الأخبار له الأولوية المطلقة
    picked.sort(key=lambda s: 0 if s.get("novel") else 1)
    for sig in picked[:config.INTEL_MAX_ALERTS_PER_CYCLE]:
        msgs.append(format_alert(sig, is_new=True))

    for sig in strengthened:
        if sig.get("tier") in ("إشارة قوية", "إشارة متقاطعة") \
                and sig not in confirmed:
            msgs.append(format_alert(sig, is_new=False))

    return msgs[:config.INTEL_MAX_ALERTS_PER_CYCLE + 5]


# ============================================================
#  الدورة الكاملة للرادار
# ============================================================

def run(ai, utterances, news_items, official_lines, known_facts,
        use_ai=True, verbose=True):
    """
    الدورة الكاملة: من كلام خام لإشارات مقيّمة.
    بيرجع (state, fresh, strengthened, confirmed).
    """
    state = load()
    stats = state.setdefault("stats", {})
    stats["cycles"] = int(stats.get("cycles", 0)) + 1

    seen = set(state.get("seen") or [])
    new_utts = [u for u in utterances if u["id"] not in seen]
    stats["utterances"] = int(stats.get("utterances", 0)) + len(new_utts)

    if verbose:
        print(f"    - {len(new_utts)} كلمة جديدة من {len(utterances)}")

    picked = shortlist(new_utts)
    if verbose:
        print(f"    - {len(picked)} تستاهل استخراج (بعد الغربلة)")

    if picked:
        if use_ai and ai.available:
            claims = extract_claims(ai, picked)
        else:
            claims = fallback_claims(picked)
        if verbose:
            print(f"    - {len(claims)} ادعاء مستخرج")
    else:
        claims = []

    fresh, strengthened = merge(state, claims)

    # الكلام اللي مادخلش الاستخراج نعلّمه كمشاهَد برضه
    state["seen"] = list(set(state.get("seen") or []) |
                         {u["id"] for u in new_utts})

    assess_novelty(state, news_items, official_lines, known_facts)
    confirmed = check_confirmation(state, news_items, official_lines)
    expire(state)

    for sig in state.get("signals", {}).values():
        rescore(sig)

    if use_ai and ai.available and state.get("signals"):
        state["digest"] = write_digest(ai, state)

    save(state)

    if verbose:
        b = board(state)["counts"]
        print(f"    → {b['total']} إشارة · {b['strong']} قوية · "
              f"{b['novel']} مش في الأخبار · {b['confirmed']} مؤكدة")

    return state, fresh, strengthened, confirmed
