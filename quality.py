# -*- coding: utf-8 -*-
"""
طبقة جودة البيانات
==================
كل ما ييجي من الأخبار/الفيديوهات بيمر عليها قبل ما يوصل للـ AI أو الصفحة.
بيصلح ٤ مشاكل أساسية كانت بتخلي الموقع "ضعيف":

  1. روابط Google News (`news.google.com/rss/articles/CBMi...`)
     دي مش الروابط الأصلية للمقال — بنفك تشفير Base64 ونطلع الرابط الحقيقي.

  2. تكرار الأخبار (نفس القصة من ٨ مصادر مختلفة).
     Fuzzy dedup على العناوين + دمج المصادر تحت عنوان واحد.

  3. مصادر ضعيفة معاملة زي الأهرام.
     ٤ طبقات: رسمي جدًا / موثوق / عادي / مستبعد (بلوجز مش معروفة).

  4. أخبار غير مصرية داخلة في التحليل (السعودية، الإسترليني، إلخ).
     فلتر بلد على العنوان والمصدر.

كل حاجة هنا Pure Python — بدون مكتبات إضافية.
"""

import os
import re
import json
import base64
import unicodedata
from urllib.parse import urlparse, parse_qs, unquote


# ============================================================
#  ١) فك تشفير روابط Google News
# ============================================================

def decode_google_news_url(url):
    """
    Google News RSS URLs بيبقى شكلها:
        https://news.google.com/rss/articles/CBMi<base64>?oc=5

    الـ Base64 payload فيه protobuf بيحتوي على URL المقال الأصلي.
    الدالة دي بتستخرج الـ URL الحقيقي بدون Network I/O.

    لو فشلت (تنسيق جديد أو encoded بشكل مختلف)، بترجّع None.
    """
    if not url or "news.google.com" not in url:
        return None

    m = re.search(r"/articles/([^/?#]+)", url)
    if not m:
        return None
    encoded = m.group(1)
    # Base64 URL-safe مع padding
    encoded += "=" * (-len(encoded) % 4)
    try:
        raw = base64.urlsafe_b64decode(encoded)
    except Exception:
        return None

    # نبحث عن أي HTTP(S) URL في البايتات
    # الأنماط:
    #   http://... حتى أول null byte أو حرف تحكم
    #   https://... نفسه
    urls = re.findall(rb"https?://[\w\-\./?=&%#+~:,;@!*'()\[\]]+", raw)
    if not urls:
        return None

    for cand in urls:
        try:
            cleaned = cand.decode("utf-8", errors="ignore").rstrip("\\/")
        except Exception:
            continue
        # ما ناخدش روابط Google نفسها (news.google أو accounts.google...)
        if any(bad in cleaned for bad in ("news.google.com",
                                          "accounts.google.com",
                                          "google.com/url")):
            continue
        # لازم يكون URL معقول (فيه . وطوله كافي)
        if "." in cleaned and 10 < len(cleaned) < 800:
            return cleaned
    return None


# كاش الروابط المفكوكة — بيتحفظ في state/
_URL_CACHE_PATH = "state/url_cache.json"
_URL_CACHE = None
_URL_CACHE_DIRTY = False


def _load_url_cache():
    global _URL_CACHE
    if _URL_CACHE is not None:
        return _URL_CACHE
    if os.path.exists(_URL_CACHE_PATH):
        try:
            with open(_URL_CACHE_PATH, encoding="utf-8") as f:
                _URL_CACHE = json.load(f)
        except Exception:
            _URL_CACHE = {}
    else:
        _URL_CACHE = {}
    return _URL_CACHE


def save_url_cache():
    """يستدعى في نهاية الدورة لحفظ الروابط المفكوكة."""
    global _URL_CACHE_DIRTY
    if not _URL_CACHE_DIRTY or _URL_CACHE is None:
        return
    try:
        d = os.path.dirname(_URL_CACHE_PATH)
        if d:
            os.makedirs(d, exist_ok=True)
        # نمنع الكاش يكبر بلا حدود
        if len(_URL_CACHE) > 3000:
            keep = list(_URL_CACHE.items())[-2000:]
            _URL_CACHE.clear()
            _URL_CACHE.update(keep)
        with open(_URL_CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(_URL_CACHE, f, ensure_ascii=False, indent=1)
        _URL_CACHE_DIRTY = False
    except Exception:
        pass


def _resolve_by_redirect(url, timeout=15):
    """
    fallback: يتّبع إعادة التوجيه للحصول على الـ URL الأصلي.
    بطيء لكن موثوق. مع كاش عشان مانعملش نفس الطلب مرتين.
    """
    global _URL_CACHE_DIRTY
    cache = _load_url_cache()
    if url in cache:
        return cache[url] or None

    try:
        from sources import session
        # HEAD أول، ولو ما نفعش نجرب GET
        try:
            r = session().head(url, allow_redirects=True, timeout=timeout)
            final = r.url
        except Exception:
            r = session().get(url, allow_redirects=True, timeout=timeout,
                              stream=True)
            final = r.url
            try:
                r.close()
            except Exception:
                pass
        if final and "news.google.com" not in final:
            cache[url] = final
            _URL_CACHE_DIRTY = True
            return final
    except Exception:
        pass

    cache[url] = ""     # علّم إنه فشل عشان مانحاولش تاني
    _URL_CACHE_DIRTY = True
    return None


def unwrap_url(url, use_network=True):
    """
    يفك أي wrapper شائع (Google News, Feedburner, ...) للحصول على الرابط الأصلي.

    الطبقات:
      1. Base64 decode (سريع، بدون شبكة)
      2. اتّباع Redirect (شبكة، مع كاش)
      3. إرجاع الأصلي
    """
    if not url:
        return url

    # (١) Base64
    decoded = decode_google_news_url(url)
    if decoded:
        return decoded

    # (٢) feedproxy / feedburner
    if "feedproxy.google.com" in url or "feeds.feedburner.com" in url:
        try:
            parsed = urlparse(url)
            for key in ("url", "u"):
                q = parse_qs(parsed.query).get(key)
                if q:
                    return unquote(q[0])
        except Exception:
            pass

    # (٣) اتباع redirect
    if use_network and "news.google.com" in url:
        real = _resolve_by_redirect(url)
        if real:
            return real

    return url


# ============================================================
#  ٢) تصنيف المصادر (Tier system)
# ============================================================
#
# Tier 1 = صحف رسمية كبرى مصرية (يعتمد عليها كمصدر أول)
# Tier 2 = مصادر إخبارية مصرية موثوقة
# Tier 3 = مصادر مصرية مقبولة
# Tier 4 = مستبعد (بلوجز مغمورة، غير مصرية)

TIER_1 = {
    "الأهرام", "بوابة الأهرام", "الأهرام العربي", "ahram",
    "اليوم السابع", "youm7", "youm 7",
    "المصري اليوم", "almasryalyoum", "al-masry al-youm",
    "الشروق", "shorouk", "shorouknews",
    "البورصة", "جريدة البورصة", "borsa",
    "المال", "جريدة المال", "almalnews",
    "الوطن", "el-watan", "elwatannews",
    "Masrawy", "مصراوي", "masrawy",
    "صدى البلد", "sada elbalad", "sadaelbalad",
    "بوابة الحكومة المصرية", "الهيئة العامة للاستعلامات", "sis.gov.eg",
    "وزارة الإسكان", "وزارة الاسكان",
    "هيئة المجتمعات العمرانية", "nuca",
}

TIER_2 = {
    "العين الإخبارية", "al-ain", "aletihad",
    "بانكير", "banker", "bankeronline",
    "Zawya", "زاوية",
    "أخبار اليوم", "akhbar-alyoum",
    "الدستور", "dostor",
    "روزاليوسف", "rosaelyoussef",
    "أموال الغد", "amwalalghad",
    "إرم بزنس", "erem", "erembusiness",
    "arabfinance",
    "youtube.com", "youtube", "يوتيوب",   # كمصدر بديل، تحت التقييم بالمصداقية
}

TIER_3_HINTS = {
    ".gov.eg", ".edu.eg", "cairoportal", "cairo24", "elbalad",
    "arabnews5", "أخبار مصر", "egypt", "cairo",
}

TIER_4_BLACKLIST = {
    "almotawwer.com",       # بلوج غير معروف
    "followict",             # ركيك
    "footballzz", "goal.com",  # مش مجالنا
    # اضف هنا أي مصدر ضعيف/spam بيظهر
}

# مصادر غير مصرية (تُستبعد من قسم "تحليل السوق المصري")
NON_EGYPT_HINTS = {
    "السعودي", "السعودية", "الإماراتي", "الإمارات", "دبي", "أبوظبي",
    "قطري", "قطر", "الكويتي", "الكويت", "بحريني", "البحرين",
    "مغربي", "المغرب", "تونسي", "تونس", "جزائري", "الجزائر",
    "لبناني", "لبنان", "سوري", "سوريا", "أردني", "الأردن",
    "sterling", "إسترليني",
}


def _normalize(text):
    """نص عربي منظّف: بدون تشكيل، بدون رموز، lowercase."""
    if not text:
        return ""
    t = unicodedata.normalize("NFKC", str(text))
    # نشيل التشكيل العربي
    t = re.sub(r"[ً-ٰٟۖ-ۭ]", "", t)
    # نوّحد الألف والياء
    t = t.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
    t = t.replace("ى", "ي").replace("ة", "ه")
    t = t.lower().strip()
    return re.sub(r"\s+", " ", t)


def source_tier(source_name, url=""):
    """يرجّع 1..4 حسب مصداقية المصدر. الأقل = أفضل."""
    if not source_name and not url:
        return 3
    name = _normalize(source_name)
    host = ""
    if url:
        try:
            host = urlparse(url).netloc.lower().replace("www.", "")
        except Exception:
            pass

    # Blacklist
    for bad in TIER_4_BLACKLIST:
        if bad in name or bad in host:
            return 4

    # Tier 1
    for good in TIER_1:
        g = _normalize(good)
        if g and (g in name or g in host):
            return 1

    # Tier 2
    for good in TIER_2:
        g = _normalize(good)
        if g and (g in name or g in host):
            return 2

    # Tier 3 إذا فيه مؤشر مصري
    for hint in TIER_3_HINTS:
        h = _normalize(hint)
        if h and (h in name or h in host):
            return 3

    # افتراضي: مصدر غير معروف → تير 3
    return 3


def is_probably_egyptian(item):
    """
    يقرر لو الخبر مصري أم لا. القرار بيعتمد على:
      • الكلمات المفتاحية في العنوان (السعودية / الإسترليني → لأ)
      • Tier المصدر (Tier 1/2 عادةً مصري)
    """
    title = _normalize((item.get("title") or "") + " " + (item.get("snippet") or ""))
    source = item.get("source") or ""
    link = item.get("link") or ""

    # لو فيه أي مؤشر غير مصري → استبعد
    for hint in NON_EGYPT_HINTS:
        if _normalize(hint) in title:
            return False

    # لو مصدر Tier 1 مصري → قبول مباشر
    if source_tier(source, link) == 1:
        return True

    # لو فيه كلمة مصر / القاهرة / وزارة الإسكان → قبول
    if any(w in title for w in ("مصر", "مصري", "القاهر", "الإسكان",
                                 "المجتمعات العمرانية", "بيت الوطن",
                                 "الاسكان", "مسكن ", "المرحلة")):
        return True

    # لو مصدر مصري معروف → قبول
    if source_tier(source, link) in (1, 2):
        return True

    return False


# ============================================================
#  ٣) Deduplication بالـ fuzzy matching
# ============================================================

# كلمات شائعة بنشيلها قبل المقارنة (stop words)
_STOP_WORDS = {
    "في", "من", "على", "الي", "الى", "عن", "مع", "بعد", "قبل",
    "هذا", "هذه", "ذلك", "التي", "الذي", "و", "أو", "او",
    "لكن", "لأن", "لان", "بس", "كل", "بعض", "أي", "اي",
    "هل", "ما", "ماذا", "كيف", "متى", "أين", "اين",
    "قال", "قالت", "أعلن", "اعلن", "أعلنت", "اعلنت",
    "نشر", "نشرت", "كتب", "كتبت",
    "..", "...", ".", ",", "،", ":", "؛", "-", "—", "|",
}


def _title_tokens(title):
    """يحوّل عنوان لمجموعة كلمات مطهّرة."""
    norm = _normalize(title)
    # نشيل علامات الترقيم
    norm = re.sub(r"[^\w\s؀-ۿ]", " ", norm)
    tokens = [w for w in norm.split() if len(w) > 2 and w not in _STOP_WORDS]
    return set(tokens)


def _key_numbers(title):
    """
    أرقام مميّزة في العنوان (زي 2898، 17، مسكن 7).
    ملاحظة: الأرقام الصغيرة (1-9) بتتحسب بس لو جوة سياق مميّز
    (مسكن 7، مرحلة 11، إعلان 15) — عشان مانخلطش أرقام عشوائية.
    """
    t = str(title or "")
    # (١) أرقام كبيرة مباشرة
    big = set(re.findall(r"\b\d{2,5}\b", t))
    # (٢) أرقام صغيرة (1-9) بس مع اسم مميّز قبلها
    small = set()
    for m in re.finditer(r"(?:مسكن|مرحله|مرحلة|الاعلان|إعلان|طرح|قطاع)\s*(\d{1,2})",
                          _normalize(t)):
        small.add(m.group(1))
    return big | small


def _jaccard(a, b):
    """درجة تشابه Jaccard بين مجموعتين (٠ - ١)."""
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def _similarity(item_a, item_b):
    """
    تشابه شامل: Jaccard على الكلمات + bonus لو الأرقام متطابقة.
    الأرقام مهمة جدًا في الأخبار العقارية (مسكن 7، 2898 قطعة، 17 مدينة).
    """
    base = _jaccard(item_a["_tokens"], item_b["_tokens"])
    nums_a, nums_b = item_a.get("_nums") or set(), item_b.get("_nums") or set()
    if nums_a and nums_b:
        shared = nums_a & nums_b
        # لو ٢+ أرقام مشتركة = علامة قوية جدًا على تشابه القصة
        if len(shared) >= 2:
            base += 0.30
        elif len(shared) >= 1:
            base += 0.15
    return min(base, 1.0)


def dedupe_items(items, threshold=0.55):
    """
    يجمّع الأخبار المتشابهة تحت عنصر واحد ومصادره تحته.
    الترتيب: أفضل Tier أول، وأحدث تاريخًا.

    كل عنصر جديد فيه:
      - نفس حقول العنصر الأصلي (title, link, source, ...)
      - "aliases": [{source, link, tier, title}]  ← اللي اندمج معاه
      - "source_count": عدد المصادر
    """
    if not items:
        return []

    enriched = []
    for it in items:
        title = it.get("title", "")
        source = it.get("source", "")
        link = it.get("link", "")
        enriched.append({
            **it,
            "_tokens": _title_tokens(title),
            "_nums": _key_numbers(title),
            "_tier": source_tier(source, link),
            "_ts": it.get("published_ts") or 0,
        })

    # نرتب الأصل بالأولوية: أفضل tier أول، وبعده الأحدث
    enriched.sort(key=lambda x: (x["_tier"], -float(x["_ts"] or 0)))

    clusters = []          # كل cluster: {primary: item, aliases: [items]}
    for it in enriched:
        matched = None
        for c in clusters:
            if _similarity(it, c["primary"]) >= threshold:
                matched = c
                break
        if matched:
            matched["aliases"].append(it)
        else:
            clusters.append({"primary": it, "aliases": []})

    # نرجع للأصل بشكل نظيف
    out = []
    for c in clusters:
        p = c["primary"]
        aliases = c["aliases"]
        clean = {k: v for k, v in p.items() if not k.startswith("_")}
        clean["source_count"] = 1 + len(aliases)
        clean["source_tier"] = p["_tier"]
        clean["aliases"] = [{
            "source": a.get("source", ""),
            "link": a.get("link", ""),
            "title": a.get("title", ""),
            "tier": a["_tier"],
        } for a in aliases]
        out.append(clean)
    return out


# ============================================================
#  ٤) الواجهة الرئيسية — طبّق كل الجودة على قائمة items
# ============================================================

def enrich_items(items, filter_egypt=False, dedupe=True, dedupe_threshold=0.55):
    """
    الدالة الرئيسية — بتطبّق كل خطوات الجودة بالترتيب:

      1. فك تشفير روابط Google News
      2. حساب tier المصدر (بيتحفظ في source_tier)
      3. استبعاد Tier 4 (blacklist)
      4. لو filter_egypt=True: استبعاد الأخبار الغير مصرية
      5. Fuzzy dedup: دمج الأخبار المتشابهة
      6. ترتيب: Tier أفضل ثم الأحدث

    ترجّع قائمة جديدة (ما بتعدّلش items الأصلية).
    """
    if not items:
        return []

    processed = []
    for it in items:
        new_it = dict(it)
        real_url = unwrap_url(new_it.get("link", ""))
        if real_url and real_url != new_it.get("link"):
            new_it["link"] = real_url
            new_it["_wrapped"] = True

        tier = source_tier(new_it.get("source", ""), new_it.get("link", ""))
        new_it["source_tier"] = tier
        if tier >= 4:
            continue     # blacklisted

        if filter_egypt and not is_probably_egyptian(new_it):
            continue

        processed.append(new_it)

    if dedupe:
        processed = dedupe_items(processed, threshold=dedupe_threshold)

    processed.sort(key=lambda x: (
        x.get("source_tier", 3),
        -float(x.get("published_ts") or 0),
    ))
    return processed


# ============================================================
#  ٥) أدوات مساعدة للـ UI (عرض المصادر المدموجة)
# ============================================================

def format_source_line(item):
    """
    يرجّع نص المصدر جاهز للعرض — مع عدد المصادر المكررة لو موجودة.
    مثال: "الأهرام + 7 مصادر تانية"
    """
    src = (item.get("source") or "").strip()
    n = int(item.get("source_count") or 1)
    if n <= 1:
        return src
    return f"{src} · <b>+{n - 1}</b> مصادر تانية"


def is_urgent_by_content(title, snippet=""):
    """
    Rule-based classification سريع (بدون AI) لتحديد العاجل.
    """
    text = (title or "") + " " + (snippet or "")
    urgent_kw = [
        "عاجل", "الآن", "الان", "الساعة", "توًا",
        "فتح باب الحجز", "بدء الحجز", "موعد الحجز", "بدء التقديم",
        "كراسة الشروط", "نتيجة القرعة", "إعلان رسمي",
        "طرح ", "مد فترة", "تأجيل",
    ]
    return any(kw in text for kw in urgent_kw)
