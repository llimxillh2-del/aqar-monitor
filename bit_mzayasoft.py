# -*- coding: utf-8 -*-
"""
لوحة bit.mzayasoft.com — مصدر مجتمعي (غير رسمي) لبيت الوطن
=============================================================
موقع طرف ثالث بيتابعه مغتربين بيت الوطن بأنفسهم. مش مصدر رسمي (الموقع
نفسه بيوضح كده صريح)، لكنه غالبًا أسرع وأدق من الجهات الرسمية في عكس
الحجز الفعلي والأسعار الحقيقية في السوق.

بيوفر 3 حاجات:
  1. fetch_summary()   — كروت الصفحة الرئيسية (إجمالي/محجوز/متبقي/اليوم)
  2. fetch_divisions() — "البرشامة": جدول المناطق مع أقل/أعلى مقدم وعدد
                          القطع ومتوسط المساحة لكل منطقة/مرحلة
  3. fetch_land_ads()  — أحدث إعلانات بيع/شراء قطع فعلية بأسعار حقيقية

كل الدوال دفاعية: لو شكل الصفحة اتغيّر أو الباترن مش واضح، بترجع
None/[] بدل ما تكسر الدورة كلها أو ترجع بيانات غلط.
"""

import os
import re
import json
import hashlib
from datetime import datetime, timezone

import config
from sources import session

try:
    from bs4 import BeautifulSoup
    _HAVE_BS4 = True
except ImportError:
    _HAVE_BS4 = False


MZAYASOFT_STATE = os.path.join("state", "bit_mzayasoft.json")


_TAG_RE = re.compile(r"<[^>]+>")
_NUM_RE = re.compile(r"[\d][\d,]{0,9}")
_WS_RE = re.compile(r"\s+")


def _clean(text):
    return _WS_RE.sub(" ", text or "").strip()


def _to_int(raw):
    """
    يحوّل نص لرقم صحيح. بيدعم فواصل الآلاف ("51,303") وكسور عشرية
    ("51,303.00" — بتتقطع لأقرب صحيح، مش بتتلقط كخطأ).
    """
    if raw is None:
        return None
    txt = str(raw).replace(",", "").strip()
    m = re.match(r"-?\d+", txt)
    if not m:
        return None
    try:
        return int(m.group(0))
    except (TypeError, ValueError):
        return None


def _get(url):
    r = session().get(url, timeout=config.REQUEST_TIMEOUT)
    r.raise_for_status()
    return r.text


# ============================================================
#  1) كروت الصفحة الرئيسية
# ============================================================

def _nearest_number(html_text, label, window=60):
    """
    يدوّر على أقرب رقم قبل التسمية مباشرة (بعد ما نشيل وسوم الـHTML —
    من غيرها أرقام في وسوم زي <h2> بتتلقط غلط كأنها البيانات).
    """
    idx = html_text.find(label)
    if idx == -1:
        return None
    before = _TAG_RE.sub(" ", html_text[max(0, idx - window):idx])
    nums = _NUM_RE.findall(before)
    return nums[-1] if nums else None


def fetch_summary():
    """
    يرجّع dict بأرقام لوحة بيت الوطن لو لقيها، وإلا None.
    {"total": 4428, "reserved": 0, "remaining": 4428, "today": 0}
    """
    if not config.BIT_MZAYASOFT_ENABLED:
        return None
    url = config.BIT_MZAYASOFT_URL
    try:
        html_text = _get(url)
    except Exception as exc:
        print(f"    - bit.mzayasoft (رئيسية): {str(exc)[:70]}")
        return None

    labels = {"total": "الإجمالي", "reserved": "المحجوز",
              "remaining": "المتبقي", "today": "اليوم"}
    out = {}
    for key, label in labels.items():
        raw = _nearest_number(html_text, label)
        if raw:
            v = _to_int(raw)
            if v is not None:
                out[key] = v

    if len(out) < 3:
        return None

    values = [v for k, v in out.items() if k != "source_url"]
    if len(set(values)) <= 1 and len(values) > 1:
        print("    - bit.mzayasoft: الأرقام كلها متطابقة — على الأغلب "
              "التقطنا حاجة غلط، بنتجاهلها")
        return None
    if "total" in out and "remaining" in out and out["remaining"] > out["total"]:
        print("    - bit.mzayasoft: المتبقي أكبر من الإجمالي — بيانات "
              "مش منطقية، بنتجاهلها")
        return None

    out["source_url"] = url
    return out


def format_line(summary):
    """سطر نصي جاهز للعرض/التنبيه."""
    if not summary:
        return None
    bits = []
    if "total" in summary:
        bits.append(f"الإجمالي {summary['total']:,}")
    if "reserved" in summary:
        bits.append(f"المحجوز {summary['reserved']:,}")
    if "remaining" in summary:
        bits.append(f"المتبقي {summary['remaining']:,}")
    if "today" in summary:
        bits.append(f"اليوم {summary['today']:,}")
    return " · ".join(bits) if bits else None


# ============================================================
#  2) البرشامة — جدول المناطق (Divisions/Divisions)
# ============================================================
#  الجدول عبارة عن <table> عادي بعناوين أعمدة:
#  المنطقة | المميزات | العيوب | متوسط المساحات | عدد الأراضي |
#  أقل مقدم | أعلى مقدم | اللوكيشن | رابط القطع
#
#  بنقرا بالاسم (مش بترتيب العمود) عشان لو التاب اتلف مكانه الكود
#  يفضل شغال، وبنرجع بس الصفوف اللي فيها اسم منطقة + رقم واحد
#  عالأقل (مقدم أو عدد أراضي) — أي صف ناقص تمامًا بيتجاهل.

DIVISIONS_URL = "https://bit.mzayasoft.com/Divisions/Divisions"

_COL_ALIASES = {
    "المنطقة": "name",
    "المميزات": "pros",
    "العيوب": "cons",
    "متوسط المساحات": "avg_area",
    "عدد الأراضي": "plot_count",
    "أقل مقدم": "min_deposit",
    "أعلى مقدم": "max_deposit",
    "اللوكيشن": "location",
    "رابط القطع": "link",
}


def _parse_divisions_table(html_text):
    if not _HAVE_BS4:
        return []
    soup = BeautifulSoup(html_text, "html.parser")
    table = soup.find("table")
    if table is None:
        return []

    header_cells = table.find("tr")
    if header_cells is None:
        return []
    headers = [_clean(th.get_text()) for th in header_cells.find_all(["th", "td"])]
    if not headers:
        return []
    keys = [_COL_ALIASES.get(h, None) for h in headers]
    if "name" not in keys:
        return []

    rows = []
    for tr in table.find_all("tr")[1:]:
        cells = tr.find_all("td")
        if not cells:
            continue
        row = {}
        for key, cell in zip(keys, cells):
            if key is None:
                continue
            if key == "link":
                a = cell.find("a")
                row[key] = a.get("href") if a and a.get("href") else None
            else:
                row[key] = _clean(cell.get_text())
        if row.get("name"):
            rows.append(row)
    return rows


def fetch_divisions(limit=60):
    """
    يرجّع قائمة dict لكل منطقة/مرحلة: name, pros, cons, avg_area,
    plot_count, min_deposit, max_deposit, location, link.
    البيانات دي أهم حاجة موجودة في الموقع — أقل/أعلى مقدم لكل منطقة
    فعليًا هي "سعر الدخول" الحقيقي، وده مش متاح في أي مصدر رسمي.
    """
    if not config.BIT_MZAYASOFT_ENABLED or not _HAVE_BS4:
        return []
    try:
        html_text = _get(DIVISIONS_URL)
    except Exception as exc:
        print(f"    - bit.mzayasoft (البرشامة): {str(exc)[:70]}")
        return []

    try:
        rows = _parse_divisions_table(html_text)
    except Exception as exc:
        print(f"    - bit.mzayasoft (تحليل جدول البرشامة): {str(exc)[:70]}")
        return []

    for row in rows:
        if row.get("link") and row["link"].startswith("/"):
            row["link"] = "https://bit.mzayasoft.com" + row["link"]
        row["plot_count_n"] = _to_int(row.get("plot_count"))
        row["min_deposit_n"] = _to_int(row.get("min_deposit"))
        row["max_deposit_n"] = _to_int(row.get("max_deposit"))

    return rows[:limit]


def divisions_price_range(divisions):
    """أقل وأعلى مقدم مسجّل في كل الجدول — نطاق السوق الحقيقي كله."""
    mins = [d["min_deposit_n"] for d in divisions if d.get("min_deposit_n")]
    maxs = [d["max_deposit_n"] for d in divisions if d.get("max_deposit_n")]
    if not mins and not maxs:
        return None
    return {
        "lowest": min(mins) if mins else None,
        "highest": max(maxs) if maxs else None,
        "divisions_count": len(divisions),
    }


# ============================================================
#  3) LandAds — إعلانات بيع/شراء قطع فعلية بأسعار حقيقية
# ============================================================
#  كل إعلان عبارة عن كارت فيه: حالة (معروض للبيع/مطلوب للشراء)،
#  اسم منطقة/مرحلة، مساحة، "X المدفوع" (المبلغ المدفوع فعليًا للهيئة
#  لحد دلوقتي)، "Y الأوفر" (المطلوب زيادة عن المدفوع = سعر البيع)،
#  وصف حر، واسم/تليفون المعلن.
#
#  بنسحب صفحة 1 بس (الأحدث) كل دورة — 22 صفحة كاملة (2500+ إعلان)
#  تحميل زيادة عن اللزوم كل شوية دقايق، والأحدث هو الأهم للتنبيه.

LAND_ADS_URL = "https://bit.mzayasoft.com/LandAds"

_STATUS_WORDS = ("معروض للبيع", "مطلوب للشراء")


def _parse_land_ads_cards(html_text):
    if not _HAVE_BS4:
        return []
    soup = BeautifulSoup(html_text, "html.parser")

    # الكروت غالبًا داخل عناصر card/div بترتيب متكرر — بندور بمرونة
    # على أي حاوية فيها كلمة حالة واحدة بالضبط (معروض للبيع/مطلوب للشراء).
    # لو الحاوية فيها أكتر من كارت جواها (يعني أكتر من كلمة حالة)، دي
    # حاوية أب مش كارت مفرد — بنستبعدها، ونسيب بس أصغر حاوية (leaf) لكل
    # ادعاء حالة عشان مانكررش نفس الإعلان مرتين.
    candidates = soup.find_all(["div", "li"])
    matches = []
    for el in candidates:
        text = _clean(el.get_text(" "))
        if not text:
            continue
        status_hits = sum(text.count(w) for w in _STATUS_WORDS)
        if status_hits != 1:
            continue
        if len(text) > 500:
            continue
        matches.append((el, text))

    # من كل مجموعة نصوص متطابقة أو متداخلة (حاوية جوه حاوية)، خد الأقصر
    # (الأقرب للكارت الفعلي) بس.
    matches.sort(key=lambda pair: len(pair[1]))
    cards = []
    seen_texts = set()
    for el, text in matches:
        if any(text in kept or kept in text for kept in seen_texts):
            continue
        seen_texts.add(text)
        cards.append((el, text))

    ads = []
    for el, text in cards:
        status = next((w for w in _STATUS_WORDS if w in text), None)
        area_m = re.search(r"(\d[\d,]*)\s*م", text)
        paid = re.search(r"([\d,]+)\s*(?:جنيه\s*)?المدفوع", text)
        extra = re.search(r"([\d,]+)\s*(?:جنيه\s*)?الأوفر", text)
        phone = None
        tel_a = el.find("a", href=re.compile(r"^tel:"))
        if tel_a:
            phone = tel_a.get("href", "").replace("tel:", "").strip()

        ad = {
            "status": status,
            "area_m2": _to_int(area_m.group(1)) if area_m else None,
            "paid": _to_int(paid.group(1)) if paid else None,
            "premium": _to_int(extra.group(1)) if extra else None,
            "phone": phone,
            "raw_text": text[:280],
        }
        if ad["status"] or ad["area_m2"] or ad["paid"]:
            # بصمة ثابتة من محتوى الإعلان — نفس الإعلان (لو اتعرض تاني
            # في نفس الترتيب) بيرجّع نفس id، عشان نعرف نميّز الجديد فعليًا.
            ad["id"] = hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]
            ads.append(ad)

    return ads


def fetch_land_ads(limit=40):
    """
    يرجّع قائمة إعلانات (أحدث ما هو معروض/مطلوب) من صفحة 1، لحد limit
    عنصر. كل إعلان: status, area_m2, paid, premium, phone, raw_text.
    """
    if not config.BIT_MZAYASOFT_ENABLED or not _HAVE_BS4:
        return []
    try:
        html_text = _get(LAND_ADS_URL)
    except Exception as exc:
        print(f"    - bit.mzayasoft (إعلانات القطع): {str(exc)[:70]}")
        return []

    try:
        ads = _parse_land_ads_cards(html_text)
    except Exception as exc:
        print(f"    - bit.mzayasoft (تحليل إعلانات القطع): {str(exc)[:70]}")
        return []

    return ads[:limit]


def land_ads_price_stats(ads):
    """
    ملخص سريع: متوسط "الأوفر" (سعر البيع الفعلي فوق المدفوع) وعدد
    إعلانات البيع مقابل الشراء — مؤشر لاتجاه السوق الحقيقي.
    """
    if not ads:
        return None
    sell = [a for a in ads if a.get("status") == "معروض للبيع"]
    buy = [a for a in ads if a.get("status") == "مطلوب للشراء"]
    premiums = [a["premium"] for a in ads if a.get("premium")]
    return {
        "sell_count": len(sell),
        "buy_count": len(buy),
        "total": len(ads),
        "avg_premium": (sum(premiums) // len(premiums)) if premiums else None,
        "max_premium": max(premiums) if premiums else None,
        "min_premium": min(premiums) if premiums else None,
    }


# ============================================================
#  4) رصد تغيّر — إعلانات جديدة فعليًا (مش نفس اللي شفناها قبل كده)
# ============================================================

def _load_state():
    if os.path.exists(MZAYASOFT_STATE):
        try:
            with open(MZAYASOFT_STATE, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"seen_ad_ids": [], "last_summary": None}


def _save_state(state):
    d = os.path.dirname(MZAYASOFT_STATE)
    if d:
        os.makedirs(d, exist_ok=True)
    tmp = MZAYASOFT_STATE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=1)
    os.replace(tmp, MZAYASOFT_STATE)


def detect_new_ads(ads):
    """
    يقارن إعلانات هذه الدورة ببصمات (id) الدورة اللي فاتت، ويرجّع
    (new_ads, state_after) — new_ads هي بس الإعلانات اللي مشفناهاش قبل
    كده (يعني إعلان جديد بجد اتنشر، مش نفس القطع اللي كانت موجودة).
    الاستدعاء الأول (state فاضية) بيسجّل كل شيء كـ"معروف" من غير تنبيه،
    عشان مانبعتش دفعة كاملة كأنها كلها "جديدة" أول مرة.
    """
    state = _load_state()
    seen = set(state.get("seen_ad_ids") or [])
    first_run = len(seen) == 0

    new_ads = [a for a in ads if a.get("id") and a["id"] not in seen]
    seen.update(a["id"] for a in ads if a.get("id"))

    state["seen_ad_ids"] = list(seen)[-4000:]
    state["updated"] = datetime.now(timezone.utc).isoformat()
    _save_state(state)

    if first_run:
        return [], state
    return new_ads, state


def summary_delta(summary):
    """
    يقارن كروت الصفحة الرئيسية (إجمالي/محجوز/متبقي) بالدورة اللي فاتت،
    ويرجّع dict فيه التغيّر لكل رقم (موجب = زيادة). بيسجّل القيم الحالية
    كـ"آخر قراءة" عشان الدورة الجاية تقارن بيها. أول قراءة بترجع None
    (مفيش حاجة نقارنها بيها لسه).
    """
    if not summary:
        return None
    state = _load_state()
    prev = state.get("last_summary")
    state["last_summary"] = {k: v for k, v in summary.items() if k != "source_url"}
    _save_state(state)

    if not prev:
        return None
    delta = {}
    for key in ("total", "reserved", "remaining", "today"):
        if key in summary and key in prev:
            d = summary[key] - prev[key]
            if d != 0:
                delta[key] = d
    return delta or None


# ============================================================
#  تجميع: كل حاجة من مزايا سوفت في نداء واحد
# ============================================================

def fetch_all():
    """
    يجيب المصادر التلاتة مرة واحدة ويرجعهم في dict واحد جاهز للعرض:
    {"summary": {...}, "divisions": [...], "price_range": {...},
     "land_ads": [...], "ads_stats": {...}, "new_ads": [...],
     "source_url": "..."}
    أي جزء فشل بيرجع None/[] لوحده من غير ما يوقف الباقي.
    """
    if not config.BIT_MZAYASOFT_ENABLED:
        return None

    summary = fetch_summary()
    divisions = fetch_divisions()
    price_range = divisions_price_range(divisions) if divisions else None
    land_ads = fetch_land_ads()
    ads_stats = land_ads_price_stats(land_ads) if land_ads else None
    new_ads = []
    if land_ads:
        try:
            new_ads, _ = detect_new_ads(land_ads)
        except Exception as exc:
            print(f"    - bit.mzayasoft (رصد الجديد): {str(exc)[:70]}")

    delta = None
    if summary:
        try:
            delta = summary_delta(summary)
        except Exception as exc:
            print(f"    - bit.mzayasoft (رصد التغيّر بالأرقام): {str(exc)[:70]}")

    if not any([summary, divisions, land_ads]):
        return None

    return {
        "summary": summary,
        "summary_delta": delta,
        "divisions": divisions,
        "price_range": price_range,
        "land_ads": land_ads,
        "ads_stats": ads_stats,
        "new_ads": new_ads,
        "source_url": config.BIT_MZAYASOFT_URL,
    }
