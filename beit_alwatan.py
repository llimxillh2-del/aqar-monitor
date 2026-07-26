#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
متابعة بيت الوطن — نسخة مبسّطة
================================
ملف واحد، مفيش رادار ولا تحليل عام ولا "كلام ناس". بس:

  1. يدور على أخبار وفيديوهات فيها كلمات مفتاحية عن بيت الوطن
     (حجز / قرعة / ترتيب / مواعيد / كراسة شروط)
  2. يقارن باللي بعته قبل كده
  3. أي حاجة جديدة → يبعتها فورًا على تليجرام: العنوان + المصدر + الرابط

مفيش "إشارات" ولا "درجة ثقة" ولا تحليل AI معقد. خبر جديد = رسالة.
هدفه إنه يجيبلك أي إعلان عن فتح الحجز أو نتيجة القرعة أو الترتيب
أسرع من إنك تفتح فيسبوك بنفسك، مش إنه "يفهم السوق".

التشغيل:
    python beit_alwatan_simple.py --once     دورة واحدة
    python beit_alwatan_simple.py --daemon   يشتغل كل 30 دقيقة لوحده
"""

import os
import re
import sys
import json
import time
import argparse
import urllib.parse
from datetime import datetime, timezone, timedelta

import requests
import feedparser

# ============================================================
#  الإعدادات — عدّل هنا بس
# ============================================================

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY", "").strip()

# كل عبارة هنا بتترصد في Google News منفصلة
SEARCH_QUERIES = [
    "بيت الوطن حجز",
    "بيت الوطن قرعة",
    "بيت الوطن ترتيب المتقدمين",
    "بيت الوطن كراسة الشروط",
    "بيت الوطن موعد",
    "بيت الوطن المرحلة",
    "بيت الوطن تخصيص",
    "بيت الوطن المصريين بالخارج",
]

# لازم العنوان يحتوي على كلمة من دول عشان يتحسب "يخص بيت الوطن" فعلًا
MUST_CONTAIN = ["بيت الوطن", "بيتك في مصر"]

# كلمات لو ظهرت في العنوان = عاجل (🔴 بدل 🔵)
URGENT_WORDS = ["حجز", "قرعة", "ترتيب", "فتح", "موعد", "كراسة الشروط",
                "تخصيص", "نتيجة", "إعلان"]

# كومنتات الفيديوهات — بنقرا الأعلى تفاعلًا بس، ونبعت اللي فيها معلومة حقيقية
# (مش رأي أو دعاء). محتاج YOUTUBE_API_KEY.
COMMENTS_ENABLED = True
MAX_COMMENTS_PER_VIDEO = 40      # كام كومنت نقرا من كل فيديو
MIN_LIKES_TO_REPORT = 15         # أقل عدد إعجابات عشان الكومنت "يستاهل"
MAX_VIDEOS_FOR_COMMENTS = 6      # كام فيديو (الأحدث) نقرا كومنتاته كل دورة

# كومنت "يستاهل" لازم يحتوي على كلمة من دول — علامة إنه معلومة مش كلام عام
COMMENT_INFO_WORDS = [
    "حجز", "قرعة", "ترتيب", "موعد", "كراسة", "شروط", "سعر", "جنيه",
    "دولار", "متر", "تحويل", "بنك", "مساحة", "مرحلة", "تخصيص", "كلمت",
    "اتصلت", "الهيئة", "رد عليا", "قالولي", "استلمت", "جاني", "رقمي",
]

# كلمات فاضية بتترمي حتى لو فيها إعجابات كتير
COMMENT_NOISE_WORDS = ["ربنا يوفق", "الله يكرمك", "جزاك الله", "تسلم",
                       "اشتركوا", "لايك للفيديو", "ما شاء الله"]

YOUTUBE_QUERIES = [
    "بيت الوطن حجز",
    "بيت الوطن قرعة ترتيب",
]

# قنوات يوتيوب بعينها بنتابعها بالكامل — أي فيديو جديد منها عن بيت الوطن
# (فيديوهاتهم التانية بتتفلتر بنفس شرط MUST_CONTAIN، فمش كل حاجة بتاعتهم
# هتوصلك، بس اللي يخص بيت الوطن بس)
YOUTUBE_CHANNELS = [
    ("الاسكان مع عمر مخلوف", "UCTRxog2J5dFMIiDqDvc4DYw"),
    ("الإسكان مع عمرو زكي", "UC68MAMp5g8Lft48Knm3pheg"),
    ("كلام في المفيد — هاني الخميسي", "UCl3L_aO3A1-nqQhBRFtbcnw"),
    ("عقارات", "UCGiEiZDpqoyfXUcWmTrLfWw"),
]

MAX_AGE_DAYS = 14           # يتجاهل الأخبار الأقدم من كده
CHECK_INTERVAL_MINUTES = 30  # في وضع --daemon

SEEN_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "state", "beit_seen_simple.json")

# سجل كل العناصر اللي اتبعتت (للموقع) — بيحتفظ بآخر عناصر بس
LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "state", "beit_log_simple.json")
MAX_LOG_ITEMS = 500

# مجلد الموقع الثابت اللي بينشر على GitHub Pages
SITE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "site")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")


# ============================================================
#  أدوات
# ============================================================

def log(msg):
    now = datetime.now().strftime("%H:%M:%S")
    print(f"[{now}] {msg}", flush=True)


def load_seen():
    if os.path.exists(SEEN_FILE):
        try:
            with open(SEEN_FILE, encoding="utf-8") as f:
                return set(json.load(f))
        except Exception:
            pass
    return set()


def save_seen(seen):
    os.makedirs(os.path.dirname(SEEN_FILE), exist_ok=True)
    tmp = SEEN_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(sorted(seen)[-3000:], f, ensure_ascii=False, indent=1)
    os.replace(tmp, SEEN_FILE)


def load_log():
    if os.path.exists(LOG_FILE):
        try:
            with open(LOG_FILE, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return []


def save_log(items):
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    tmp = LOG_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(items[-MAX_LOG_ITEMS:], f, ensure_ascii=False, indent=1)
    os.replace(tmp, LOG_FILE)


def is_relevant(title, snippet=""):
    blob = f"{title} {snippet}"
    return any(w in blob for w in MUST_CONTAIN)


def is_urgent(title):
    return any(w in title for w in URGENT_WORDS)


def clean_title(title):
    return re.sub(r"\s+-\s+[^-]+$", "", title).strip()


# ============================================================
#  جلب الأخبار
# ============================================================

def fetch_news():
    """يدور في Google News على كل عبارة، ويرجّع عناصر موحّدة."""
    items = []
    seen_links = set()
    cutoff = datetime.now(timezone.utc) - timedelta(days=MAX_AGE_DAYS)

    for query in SEARCH_QUERIES:
        log(f"  بدور: {query}")
        q = urllib.parse.quote(query)
        url = f"https://news.google.com/rss/search?q={q}&hl=ar&gl=EG&ceid=EG:ar"

        try:
            r = requests.get(url, headers={"User-Agent": UA}, timeout=20)
            r.raise_for_status()
            feed = feedparser.parse(r.content)
        except Exception as exc:
            log(f"    ! فشل: {str(exc)[:70]}")
            continue

        for entry in feed.entries[:15]:
            link = entry.get("link", "")
            if not link or link in seen_links:
                continue

            title = clean_title(entry.get("title", ""))
            if not title or not is_relevant(title):
                continue

            published = None
            if getattr(entry, "published_parsed", None):
                published = datetime(*entry.published_parsed[:6],
                                     tzinfo=timezone.utc)
            if published and published < cutoff:
                continue

            source = ""
            src_obj = getattr(entry, "source", None)
            if src_obj is not None:
                source = getattr(src_obj, "title", "") or ""

            seen_links.add(link)
            items.append({
                "title": title,
                "link": link,
                "source": source or "خبر",
                "kind": "news",
                "when": published.isoformat() if published else "",
            })
        time.sleep(0.8)

    log(f"  → {len(items)} خبر يخص بيت الوطن")
    return items


def fetch_youtube():
    """يدور في يوتيوب لو فيه مفتاح — عناوين فيديوهات بس، من غير كومنتات."""
    if not YOUTUBE_API_KEY:
        return []

    items = []
    seen_links = set()
    cutoff = datetime.now(timezone.utc) - timedelta(days=MAX_AGE_DAYS)

    for query in YOUTUBE_QUERIES:
        log(f"  يوتيوب: {query}")
        try:
            r = requests.get(
                "https://www.googleapis.com/youtube/v3/search",
                params={"key": YOUTUBE_API_KEY, "q": query, "part": "snippet",
                       "type": "video", "order": "date", "maxResults": 8,
                       "relevanceLanguage": "ar"},
                timeout=20)
            r.raise_for_status()
        except Exception as exc:
            log(f"    ! فشل: {str(exc)[:70]}")
            continue

        for entry in r.json().get("items", []):
            sn = entry.get("snippet", {})
            vid = (entry.get("id") or {}).get("videoId")
            if not vid:
                continue
            link = f"https://www.youtube.com/watch?v={vid}"
            if link in seen_links:
                continue

            title = sn.get("title", "")
            if not is_relevant(title, sn.get("description", "")):
                continue

            published = None
            try:
                published = datetime.fromisoformat(
                    (sn.get("publishedAt") or "").replace("Z", "+00:00"))
            except (TypeError, ValueError):
                pass
            if published and published < cutoff:
                continue

            seen_links.add(link)
            items.append({
                "title": title,
                "link": link,
                "source": sn.get("channelTitle", "قناة يوتيوب"),
                "kind": "video",
                "when": published.isoformat() if published else "",
            })
        time.sleep(0.5)

    log(f"  → {len(items)} فيديو يخص بيت الوطن")
    return items


def fetch_youtube_channels():
    """
    RSS رسمي مجاني لكل قناة من YOUTUBE_CHANNELS — بيرجّع آخر ١٥ فيديو
    منها من غير أي مفتاح API ومن غير حصة (quota). بيتفلتر بعدين على
    اللي يخص بيت الوطن بس.
    """
    if not YOUTUBE_CHANNELS:
        return []

    items = []
    cutoff = datetime.now(timezone.utc) - timedelta(days=MAX_AGE_DAYS)

    for name, channel_id in YOUTUBE_CHANNELS:
        log(f"  قناة: {name}")
        url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
        try:
            r = requests.get(url, headers={"User-Agent": UA}, timeout=20)
            r.raise_for_status()
            feed = feedparser.parse(r.content)
        except Exception as exc:
            log(f"    ! فشل: {str(exc)[:70]}")
            continue

        for entry in feed.entries[:15]:
            title = entry.get("title", "")
            link = entry.get("link", "")
            if not link or not is_relevant(title):
                continue

            published = None
            if getattr(entry, "published_parsed", None):
                published = datetime(*entry.published_parsed[:6],
                                     tzinfo=timezone.utc)
            if published and published < cutoff:
                continue

            items.append({
                "title": title,
                "link": link,
                "source": name,
                "kind": "video",
                "when": published.isoformat() if published else "",
            })
        time.sleep(0.4)

    log(f"  → {len(items)} فيديو من القنوات المتابَعة يخص بيت الوطن")
    return items


QUESTION_STARTERS = ("هل ", "حد عارف", "حد يعرف", "في حد", "فيه حد",
                     "ياريت حد", "محتاج اعرف", "محتاجة اعرف")

# سؤال شائع محتاج لايكات أعلى بكتير عشان يستاهل يتبعت (فرق عن معلومة عادية)
MIN_LIKES_FOR_TRENDING_QUESTION = 60


def _is_question(text):
    if "؟" in text or text.strip().endswith("?"):
        return True
    return any(text.startswith(w) for w in QUESTION_STARTERS)


def _is_worthy_comment(text):
    """
    كومنت يستاهل التقرير كـ"معلومة": فيه كلمة معلومة، مش كلام فاضي معروف،
    ومش سؤال (سؤال ≠ معلومة حتى لو فيه نفس الكلمات وإعجابات كتير).
    """
    if len(text) < 20:
        return False
    if any(n in text for n in COMMENT_NOISE_WORDS):
        return False
    if _is_question(text):
        return False
    return any(w in text for w in COMMENT_INFO_WORDS)


def _extract_comment_item(vid, comment_id, sn):
    """يبني عنصر تقرير من snippet كومنت (سواء أساسي أو رد) لو يستاهل."""
    text = (sn.get("textDisplay") or "").strip()
    likes = int(sn.get("likeCount", 0) or 0)
    if likes < MIN_LIKES_TO_REPORT or not _is_worthy_comment(text):
        return None
    return {
        "title": text[:180],
        "link": f"https://www.youtube.com/watch?v={vid}&lc={comment_id}",
        "source": f'تعليق ({likes} إعجاب) — '
                  f'{sn.get("authorDisplayName", "مستخدم")}',
        "kind": "comment",
        "when": sn.get("publishedAt", ""),
    }


def _extract_trending_question(vid, comment_id, sn):
    """
    سؤال شائع (لايكات عالية جدًا) من غير رد فيه معلومة — بيتبعت
    بعلامة "سؤال متكرر" عشان يوريك إن ناس كتير قلقانة من نفس النقطة،
    من غير ما نوهم إنه "معلومة" أو "تسريب".
    """
    text = (sn.get("textDisplay") or "").strip()
    likes = int(sn.get("likeCount", 0) or 0)
    if likes < MIN_LIKES_FOR_TRENDING_QUESTION or len(text) < 15:
        return None
    if any(n in text for n in COMMENT_NOISE_WORDS):
        return None
    if not _is_question(text):
        return None
    if not any(w in text for w in COMMENT_INFO_WORDS):
        return None
    return {
        "title": text[:180],
        "link": f"https://www.youtube.com/watch?v={vid}&lc={comment_id}",
        "source": f'سؤال متكرر ({likes} إعجاب) — لسه من غير رد رسمي',
        "kind": "trending_question",
        "when": sn.get("publishedAt", ""),
    }


def fetch_comments(video_ids):
    """
    أعلى الكومنتات تفاعلًا من كل فيديو (التعليق الأساسي وكمان الردود عليه)،
    مفلترة على اللي فيها معلومة حقيقية (مش رأي أو دعاء). الأسئلة العادية
    بتترفض، لكن سؤال شائع جدًا (لايكات عالية) بيتبعت بعلامة "سؤال متكرر"
    عشان يوضح اهتمام الناس حتى لو مفيش إجابة عليه لسه.
    """
    if not (COMMENTS_ENABLED and YOUTUBE_API_KEY and video_ids):
        return []

    items = []
    for vid in list(video_ids)[:MAX_VIDEOS_FOR_COMMENTS]:
        try:
            r = requests.get(
                "https://www.googleapis.com/youtube/v3/commentThreads",
                params={"key": YOUTUBE_API_KEY, "videoId": vid,
                       "part": "snippet,replies", "order": "relevance",
                       "maxResults": min(MAX_COMMENTS_PER_VIDEO, 100),
                       "textFormat": "plainText"},
                timeout=20)
            r.raise_for_status()
        except Exception as exc:
            msg = str(exc)
            if "403" not in msg:      # 403 = كومنتات مقفولة، عادي نتخطاها بصمت
                log(f"    ! كومنتات {vid}: {msg[:60]}")
            continue

        for thread in r.json().get("items", []):
            top = ((thread.get("snippet") or {}).get("topLevelComment") or {})
            top_id = top.get("id", thread.get("id", ""))
            top_sn = top.get("snippet") or {}

            item = _extract_comment_item(vid, top_id, top_sn)
            if item:
                items.append(item)
            else:
                tq = _extract_trending_question(vid, top_id, top_sn)
                if tq:
                    items.append(tq)

            # الردود كمان ممكن تحمل المعلومة الحقيقية، مش بس السؤال الأصلي
            for reply in (thread.get("replies") or {}).get("comments", []):
                r_sn = reply.get("snippet") or {}
                r_item = _extract_comment_item(
                    vid, reply.get("id", ""), r_sn)
                if r_item:
                    items.append(r_item)

    if items:
        log(f"  → {len(items)} كومنت/رد/سؤال متكرر مرصود")
    return items


# ============================================================
#  تليجرام
# ============================================================

def send_telegram(text):
    if not (TELEGRAM_TOKEN and TELEGRAM_CHAT_ID):
        log("  ! تليجرام مش مضبوط — مش هيتبعت")
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        r = requests.post(url, data={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": "false",
        }, timeout=20)
        body = r.json()
        if not body.get("ok"):
            log(f"  ! تليجرام رفض: {body.get('description', '')[:100]}")
            return False
        return True
    except Exception as exc:
        log(f"  ! فشل الإرسال: {str(exc)[:80]}")
        return False


def _ar_date():
    months = ["يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو", "يوليو",
              "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"]
    now = datetime.now()
    return f"{now.day} {months[now.month - 1]} {now.year} — {now:%H:%M}"


def format_digest(new_items):
    """
    تقرير واحد منظّم بدل رسالة لكل خبر — أسهل للقراءة ومحترف.
    الترتيب: العاجل (فيه كلمة حجز/قرعة/موعد) الأول، بعدين الباقي.
    """
    import html

    trending_qs = [it for it in new_items if it["kind"] == "trending_question"]
    rest = [it for it in new_items if it["kind"] != "trending_question"]

    urgent = [it for it in rest if is_urgent(it["title"])]
    normal = [it for it in rest if not is_urgent(it["title"])]

    lines = [
        "🏛️ <b>متابعة بيت الوطن</b>",
        f"<i>{_ar_date()}</i>",
        "",
    ]

    comments = [it for it in normal if it["kind"] == "comment"]
    normal = [it for it in normal if it["kind"] != "comment"]

    if urgent:
        lines.append(f"🔴 <b>مستجدات مهمة ({len(urgent)})</b>")
        lines.append("")
        for it in urgent:
            kind = "💬" if it["kind"] == "comment" else (
                "🎥" if it["kind"] == "video" else "📰")
            lines.append(
                f'{kind} <a href="{html.escape(it["link"])}">'
                f'{html.escape(it["title"])}</a>')
            lines.append(f'   <i>المصدر: {html.escape(it["source"])}</i>')
            lines.append("")

    if normal:
        lines.append(f"📋 <b>أخبار أخرى ({len(normal)})</b>")
        lines.append("")
        for it in normal:
            kind = "🎥" if it["kind"] == "video" else "📰"
            lines.append(
                f'{kind} <a href="{html.escape(it["link"])}">'
                f'{html.escape(it["title"])}</a>')
            lines.append(f'   <i>المصدر: {html.escape(it["source"])}</i>')
            lines.append("")

    if comments:
        lines.append(f"💬 <b>من كلام الناس — غير مؤكد رسميًا ({len(comments)})</b>")
        lines.append("")
        for it in comments:
            lines.append(
                f'💬 <a href="{html.escape(it["link"])}">'
                f'{html.escape(it["title"])}</a>')
            lines.append(f'   <i>{html.escape(it["source"])}</i>')
            lines.append("")

    if trending_qs:
        lines.append(f"❓ <b>أسئلة متكررة من الناس — لسه من غير رد ({len(trending_qs)})</b>")
        lines.append("")
        for it in trending_qs:
            lines.append(
                f'❓ <a href="{html.escape(it["link"])}">'
                f'{html.escape(it["title"])}</a>')
            lines.append(f'   <i>{html.escape(it["source"])}</i>')
            lines.append("")

    lines.append("─" * 22)
    lines.append("<i>مصادر: Google News · يوتيوب · تعليقات — رصد آلي، راجع كراسة "
                 "الشروط الرسمية قبل أي إجراء. كلام الناس مش مصدر رسمي.</i>")

    return "\n".join(lines).strip()


# حد أقصى لطول رسالة تليجرام — لو التقرير أطول، بيتقسم عند فاصل خبر
_TG_LIMIT = 3800


def split_digest(text):
    """تقسيم آمن عند نهاية عنصر — ما بيكسرش وسم <a> أو <b> نص."""
    if len(text) <= _TG_LIMIT:
        return [text]
    blocks = text.split("\n\n")
    chunks, current = [], ""
    for block in blocks:
        if len(current) + len(block) + 2 > _TG_LIMIT:
            if current.strip():
                chunks.append(current.strip())
            current = block
        else:
            current = f"{current}\n\n{block}" if current else block
    if current.strip():
        chunks.append(current.strip())
    return chunks


# ============================================================
#  الموقع (صفحة واحدة ثابتة، بتتحدث كل دورة، تُنشر على GitHub Pages)
# ============================================================

_KIND_LABEL = {
    "news": ("📰", "خبر"),
    "video": ("🎥", "فيديو"),
    "comment": ("💬", "من كلام الناس"),
    "trending_question": ("❓", "سؤال متكرر"),
}


def build_site(log_items):
    """
    صفحة HTML واحدة بسيطة تعرض كل العناصر اللي اتبعتت من الأحدث للأقدم.
    بتتبني من نفس الـ log اللي بيتحدث كل دورة — مفيش قاعدة بيانات
    ولا سيرفر، مجرد ملف ثابت يتنشر عبر GitHub Pages.
    """
    import html

    os.makedirs(SITE_DIR, exist_ok=True)

    rows = []
    for it in reversed(log_items):
        icon, label = _KIND_LABEL.get(it.get("kind"), ("📄", "عنصر"))
        urgent_badge = ""
        if it.get("kind") not in ("comment", "trending_question") \
                and is_urgent(it.get("title", "")):
            urgent_badge = '<span class="badge urgent">عاجل</span>'
        rows.append(f'''
        <div class="item">
          <div class="item-head">
            <span class="icon">{icon}</span>
            <span class="label">{html.escape(label)}</span>
            {urgent_badge}
          </div>
          <a class="title" href="{html.escape(it.get("link", "#"))}" target="_blank"
             rel="noopener">{html.escape(it.get("title", ""))}</a>
          <div class="source">المصدر: {html.escape(it.get("source", ""))}</div>
        </div>''')

    page = f"""<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>متابعة بيت الوطن</title>
<style>
  body {{ font-family: 'Segoe UI', Tahoma, Arial, sans-serif; background:#0f1420;
         color:#e8e8ec; margin:0; padding:0; }}
  header {{ background:#161c2c; padding:24px 16px; text-align:center;
            border-bottom:1px solid #262e42; }}
  header h1 {{ margin:0 0 6px; font-size:22px; }}
  header p {{ margin:0; color:#8b93a7; font-size:13px; }}
  .wrap {{ max-width:720px; margin:0 auto; padding:16px; }}
  .item {{ background:#161c2c; border:1px solid #262e42; border-radius:10px;
           padding:14px 16px; margin-bottom:12px; }}
  .item-head {{ display:flex; align-items:center; gap:8px; margin-bottom:6px;
                font-size:13px; color:#8b93a7; }}
  .icon {{ font-size:16px; }}
  .badge {{ font-size:11px; padding:2px 8px; border-radius:20px; margin-inline-start:auto; }}
  .badge.urgent {{ background:#3a1620; color:#ff6b81; }}
  .title {{ display:block; color:#fff; text-decoration:none; font-size:16px;
            font-weight:600; margin-bottom:6px; line-height:1.5; }}
  .title:hover {{ color:#7aa2f7; }}
  .source {{ font-size:12px; color:#8b93a7; }}
  .empty {{ text-align:center; color:#8b93a7; padding:60px 20px; }}
  footer {{ text-align:center; color:#565f76; font-size:11px; padding:20px; }}
</style>
</head>
<body>
<header>
  <h1>🏛️ متابعة بيت الوطن</h1>
  <p>آخر تحديث: {html.escape(_ar_date())} · {len(log_items)} عنصر مسجّل</p>
</header>
<div class="wrap">
  {"".join(rows) if rows else '<div class="empty">لسه مفيش حاجة اتسجّلت. أول ما يظهر خبر جديد هيتحط هنا.</div>'}
</div>
<footer>رصد آلي — كلام الناس مش مصدر رسمي، راجع كراسة الشروط الرسمية قبل أي إجراء.</footer>
</body>
</html>"""

    with open(os.path.join(SITE_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(page)


# ============================================================
#  الدورة
# ============================================================

def run_once():
    log("=" * 50)
    log("دورة متابعة بيت الوطن")
    log("=" * 50)

    seen = load_seen()
    news_items = fetch_news()
    video_items = fetch_youtube() + fetch_youtube_channels()

    # إزالة التكرار لو نفس الفيديو طلع من البحث ومن القناة مع بعض
    dedup, videos_dedup = set(), []
    for it in video_items:
        if it["link"] in dedup:
            continue
        dedup.add(it["link"])
        videos_dedup.append(it)
    video_items = videos_dedup

    # كومنتات على أحدث الفيديوهات المتابَعة (يخص بيت الوطن) بس
    video_ids = []
    for it in video_items:
        m = re.search(r"v=([\w-]{5,})", it["link"])
        if m:
            video_ids.append(m.group(1))
    comment_items = fetch_comments(video_ids)

    all_items = news_items + video_items + comment_items

    dedup, out = set(), []
    for it in all_items:
        if it["link"] in dedup:
            continue
        dedup.add(it["link"])
        out.append(it)
    all_items = out

    new_items = [it for it in all_items if it["link"] not in seen]
    log(f"إجمالي: {len(all_items)} · جديد: {len(new_items)}")

    if not new_items:
        log("مفيش جديد — مفيش تقرير.")
    else:
        new_items.sort(key=lambda x: is_urgent(x["title"]), reverse=True)
        digest = format_digest(new_items)
        for chunk in split_digest(digest):
            sent = send_telegram(chunk)
            log(f"  {'✓' if sent else '✗'} تقرير مُرسل ({len(new_items)} عنصر)")
            time.sleep(0.6)

        log_items = load_log()
        log_items.extend(new_items)
        save_log(log_items)

    build_site(load_log())

    seen.update(it["link"] for it in all_items)
    save_seen(seen)
    log("خلصت الدورة.\n")
    return len(new_items)


def run_daemon():
    log(f"وضع مستمر — فحص كل {CHECK_INTERVAL_MINUTES} دقيقة. Ctrl+C للإيقاف.")
    while True:
        try:
            run_once()
        except Exception as exc:
            log(f"! خطأ: {str(exc)[:100]}")
        time.sleep(CHECK_INTERVAL_MINUTES * 60)


# ============================================================
#  طبقة التوافق — API للاستخدام من monitor.py
# ============================================================
#
# النسخة القديمة من الملف ده كانت module فيها دوال زي load/save/extract/
# dashboard اللي بيستخدمها monitor.py. النسخة الحالية (سكريبت مستقل)
# مافيهاش الدوال دي، فالـ import بيبوّظ. الطبقة دي بتوفّرها من غير ما
# نبطّل السكريبت المستقل.
#
# البيانات بتتحفظ في state/beit_alwatan.json بالشكل ده:
#   {
#     "facts": {tracked_field: {value, since, source_title, source_link}},
#     "timeline": [{field, from, to, when, source_title, source_link}],
#     "dates": [{label, kind, raw, iso, days_left, status}],
#     "cities": {city_name: count},
#     "people": str | null,
#     "forecast": str | null,
#     "checklist": str | list | null,
#     "summary": str | null,
#     "sources": [links],
#     "updated": iso,
#   }

import config as _config      # نفس config الحقيقي — سابقًا مكانش mستخدم هنا


def _bw_state_path():
    return getattr(_config, "BEIT_STATE", "state/beit_alwatan.json")


def _bw_load_json(path, default):
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return default


def _bw_save_json(path, data):
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def load():
    """تحميل حالة بيت الوطن من الملف."""
    state = _bw_load_json(_bw_state_path(), {})
    state.setdefault("facts", {})
    state.setdefault("timeline", [])
    state.setdefault("dates", [])
    state.setdefault("cities", {})
    state.setdefault("sources", [])
    return state


def save(state):
    """حفظ حالة بيت الوطن."""
    state["updated"] = datetime.now(timezone.utc).isoformat()
    _bw_save_json(_bw_state_path(), state)


def filter_items(items):
    """فلترة الأخبار/الفيديوهات اللي عنوانها فيه كلمات بيت الوطن."""
    words = _config.BEIT_ALWATAN.get("match_words", [])
    if not words:
        return []
    out = []
    for it in items or []:
        title = (it.get("title") or "") + " " + (it.get("snippet") or "")
        if any(w in title for w in words):
            out.append(it)
    return out


def _bw_pack_items(items, limit=25):
    """يجهّز الأخبار في شكل مضغوط للـ AI."""
    lines = []
    for i, it in enumerate(items[:limit], 1):
        title = (it.get("title") or "").strip()[:220]
        src = (it.get("source") or "").strip()
        snip = (it.get("snippet") or "").strip()[:280]
        lines.append(f"{i}. {title} — {src}\n   {snip}")
    return "\n".join(lines)


def _bw_pack_videos(videos, limit=6):
    lines = []
    for i, (title, summary) in enumerate((videos or [])[:limit], 1):
        s = str(summary or "").strip()[:600]
        lines.append(f"{i}. {title}\n{s}")
    return "\n\n".join(lines)


def extract(ai, items, videos, official_lines):
    """
    استخراج حقائق منظمة عن بيت الوطن باستخدام AI.
    بيرجّع dict بالحقول اللي في config.BEIT_ALWATAN['tracked_fields'].
    """
    if not ai or not items:
        return {}
    tracked = _config.BEIT_ALWATAN.get("tracked_fields", [])
    news_txt = _bw_pack_items(items)
    vids_txt = _bw_pack_videos(videos)
    official_txt = "\n".join((official_lines or [])[:15])

    prompt = f"""من الأخبار والفيديوهات والمصادر الرسمية دي عن مشروع بيت الوطن:

الأخبار:
{news_txt}

الفيديوهات (ملخصاتها):
{vids_txt or '—'}

المصادر الرسمية (سطور رصدت):
{official_txt or '—'}

استخرج الحقائق التالية فقط بصيغة JSON. لأي حقل مالوش معلومة صريحة، سيبه null.
مفيش تخمين — اللي مش موجود في النص = null.

الحقول:
{json.dumps(tracked, ensure_ascii=False)}

كل قيمة تكون string قصير مباشر (مش جملة كاملة). مثال:
{{"المرحلة_الحالية": "المرحلة 12", "سعر_المتر": "20 ألف جنيه", ...}}

بالإضافة اذكر:
- "درجة_الثقة": "عالية" أو "متوسطة" أو "منخفضة" حسب وضوح المصادر
- "أرقم_مصدر": رقم أهم عنصر أخبار يعتمد عليه
"""
    data = ai.ask_json(prompt, system=SYSTEM_JSON_BW, fast=False)
    if not isinstance(data, dict):
        return {}

    # نضيف source_link للـ facts اللي عندنا رقم مصدر
    src_idx = data.pop("أرقم_مصدر", None)
    src_title = src_link = ""
    if isinstance(src_idx, (int, str)):
        try:
            src = items[int(src_idx) - 1]
            src_title = src.get("title", "")
            src_link = src.get("link", "")
        except (ValueError, IndexError):
            pass

    facts = {}
    for k, v in data.items():
        if v is None or (isinstance(v, str) and not v.strip()):
            continue
        facts[k] = {
            "value": str(v).strip(),
            "source_title": src_title,
            "source_link": src_link,
        }
    return facts


SYSTEM_JSON_BW = (
    "أنت محرر بيانات دقيق. ترد بـ JSON صالح فقط، بدون أي نص قبله أو بعده "
    "وبدون أسوار كود. لا تخترع معلومات غير موجودة في النص المعطى لك. "
    "إذا لم تجد معلومة، استخدم null."
)


def diff_and_update(state, facts, items):
    """
    يقارن الحقائق الجديدة بالمحفوظة، يحدّث state، ويرجّع قائمة التغييرات.
    """
    changes = []
    old = state.setdefault("facts", {})
    now = datetime.now(timezone.utc).isoformat()

    for field, entry in (facts or {}).items():
        new_val = entry.get("value") if isinstance(entry, dict) else str(entry)
        if not new_val:
            continue
        old_entry = old.get(field) or {}
        old_val = old_entry.get("value") if isinstance(old_entry, dict) else old_entry
        if old_val == new_val:
            # ثبّت المصدر لو مكانش موجود
            if isinstance(old_entry, dict) and not old_entry.get("source_link"):
                old[field] = {**old_entry, **entry, "since": old_entry.get("since", now)}
            continue

        record = {
            "value": new_val,
            "since": now,
            "source_title": entry.get("source_title") if isinstance(entry, dict) else "",
            "source_link": entry.get("source_link") if isinstance(entry, dict) else "",
        }
        old[field] = record
        changes.append({
            "field": field,
            "from": old_val,
            "to": new_val,
            "when": now,
            "source_title": record["source_title"],
            "source_link": record["source_link"],
        })

    if changes:
        state.setdefault("timeline", []).extend(changes)
        state["timeline"] = state["timeline"][-200:]

    # حدّث cities count من items
    city_names = _config.BEIT_ALWATAN.get("cities", [])
    counts = state.setdefault("cities", {})
    for it in items or []:
        blob = (it.get("title") or "") + " " + (it.get("snippet") or "")
        for city in city_names:
            if city in blob:
                counts[city] = counts.get(city, 0) + 1

    # حدّث sources (لينكات فقط — التوافق مع النسخ القديمة اللي كانت dicts)
    existing = state.get("sources") or []
    srcs = set()
    for s in existing:
        if isinstance(s, str):
            srcs.add(s)
        elif isinstance(s, dict) and s.get("link"):
            srcs.add(s["link"])
    for it in items or []:
        if it.get("link"):
            srcs.add(it["link"])
    state["sources"] = list(srcs)[-50:]

    return changes


def people_pulse(ai, comments, limit=40):
    """ملخص كلام الناس في الكومنتات."""
    if not ai or not comments:
        return None
    packed = []
    for c in (comments or [])[:limit]:
        txt = (c.get("text") if isinstance(c, dict) else str(c)) or ""
        txt = txt.strip()[:280]
        if txt:
            packed.append(f"- {txt}")
    if not packed:
        return None
    prompt = f"""دي كومنتات من متابعين ومهتمين ببيت الوطن:

{chr(10).join(packed)}

المطلوب فقرة قصيرة (٤-٥ جمل) توضح:
- المزاج العام (متفائل / متوجّس / محايد)
- أهم ٢-٣ مخاوف متكررة
- أهم ٢ سؤال محدش رد عليه
اكتب مباشرة، بدون تعداد ولا عناوين."""
    return ai.ask(prompt, system=SYSTEM_AR_BW)


def summarize(ai, state, items):
    """ملخص تنفيذي ٣-٤ جمل عن حالة الملف حاليًا."""
    if not ai:
        return None
    facts = state.get("facts") or {}
    facts_txt = "\n".join(f"- {k.replace('_', ' ')}: "
                         f"{v.get('value') if isinstance(v, dict) else v}"
                         for k, v in facts.items())
    news = _bw_pack_items(items, limit=8)
    prompt = f"""حالة ملف بيت الوطن حاليًا:
{facts_txt or '(بيانات ناقصة)'}

آخر أخبار:
{news or '—'}

اكتب ملخص من ٣-٤ جمل مباشرة يجاوب على:
"إيه الوضع دلوقتي وإيه اللي المصري المغترب محتاج يعرفه؟"
بدون عناوين ولا تعداد."""
    return ai.ask(prompt, system=SYSTEM_AR_BW)


def forecast(ai, state, items, people):
    """توقعات وسيناريوهات لبيت الوطن."""
    if not ai:
        return None
    facts = state.get("facts") or {}
    facts_txt = "\n".join(f"- {k.replace('_', ' ')}: "
                         f"{v.get('value') if isinstance(v, dict) else v}"
                         for k, v in facts.items())
    news = _bw_pack_items(items, limit=10)
    people_txt = people or ""
    prompt = f"""بناءً على المعطيات دي:

الحقائق المرصودة:
{facts_txt or '—'}

آخر أخبار:
{news or '—'}

كلام الناس:
{people_txt or '—'}

اكتب ٣ فقرات قصيرة:
1. أين نحن الآن (فقرة واحدة).
2. المتوقع في الأسابيع القادمة (فقرة واحدة، مع تحفظات صريحة).
3. سيناريوهات (٣ أسطر: الأرجح · متفائل · متحفظ).

لا تخترع تواريخ أو أرقام غير موجودة."""
    return ai.ask(prompt, system=SYSTEM_AR_BW)


def checklist(ai, state):
    """خطوات مقترحة للمستخدم."""
    if not ai:
        return None
    booking = None
    facts = state.get("facts") or {}
    entry = facts.get("حالة_الحجز")
    if isinstance(entry, dict):
        booking = entry.get("value")

    prompt = f"""حالة الحجز في بيت الوطن حاليًا: {booking or 'غير معلومة'}

اكتب قائمة من ٤-٦ خطوات عملية مباشرة يعملها المصري المغترب دلوقتي
عشان يكون جاهز لما الحجز يفتح (لو مقفول)، أو يتقدم صح (لو مفتوح).
كل خطوة سطر واحد قصير مباشر يبدأ برقم.
بدون شرح طويل."""
    text = ai.ask(prompt, system=SYSTEM_AR_BW)
    if not text:
        return None
    # نحوّل النص لقائمة نظيفة
    steps = []
    for line in text.split("\n"):
        line = line.strip()
        # نشيل الترقيم "1." أو "1-" أو "1)"
        line = re.sub(r"^[\d]+[\.\-\)]\s*", "", line)
        line = re.sub(r"^[\*\-]\s*", "", line)
        if len(line) > 8:
            steps.append(line)
    return steps[:6] if steps else None


SYSTEM_AR_BW = (
    "أنت محلل عقاري مصري محترف متخصص في الفرص المتاحة للمصريين المقيمين "
    "بالخارج. ترد بالعربية المصرية الواضحة، بدقة وإيجاز، وبدون مبالغة أو "
    "ترويج. لا تخترع أرقامًا أو تواريخ غير موجودة في النص المعطى لك."
)


# ---------- استخراج المواعيد وحساب الأيام المتبقية ----------

_DATE_LABELS = {
    "موعد_فتح_الحجز": "فتح الحجز",
    "موعد_غلق_الحجز": "غلق الحجز",
    "موعد_السداد": "السداد",
    "موعد_القرعة": "القرعة",
}


def _parse_days_left(raw_value):
    """يحاول يستخرج تاريخ ISO ويحسب الأيام المتبقية. بيرجع (iso, days)."""
    if not raw_value:
        return None, None
    txt = str(raw_value)
    # yyyy-mm-dd or dd/mm/yyyy
    m = re.search(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})", txt)
    if m:
        y, mo, d = map(int, m.groups())
    else:
        m = re.search(r"(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})", txt)
        if m:
            d, mo, y = map(int, m.groups())
        else:
            return None, None
    try:
        target = datetime(y, mo, d, tzinfo=timezone.utc)
    except ValueError:
        return None, None
    diff = (target - datetime.now(timezone.utc)).days
    return target.date().isoformat(), diff


def dashboard(state):
    """
    يحوّل state الخام لشكل مناسب للعرض في الصفحة ورسالة تليجرام.
    """
    facts = state.get("facts") or {}

    def _v(field):
        e = facts.get(field)
        if isinstance(e, dict):
            return e.get("value")
        return e

    # قائمة المواعيد بترتيب زمني (الأقرب الأول)
    dates = []
    for field, label in _DATE_LABELS.items():
        raw = _v(field)
        if not raw:
            continue
        iso, days_left = _parse_days_left(raw)
        dates.append({
            "label": label,
            "kind": field,
            "raw": raw,
            "iso": iso,
            "days_left": days_left,
            "status": "قادم" if (days_left is not None and days_left >= 0)
                       else ("مرّ" if days_left is not None else "غير محدد بدقة"),
        })
    # الأقرب أولاً (اللي ليه days_left >= 0)
    upcoming = [d for d in dates if isinstance(d["days_left"], int) and d["days_left"] >= 0]
    upcoming.sort(key=lambda d: d["days_left"])
    nxt = upcoming[0] if upcoming else None

    cities = state.get("cities") or {}
    top_cities = sorted(cities.items(), key=lambda x: -x[1])[:5]
    cities_out = [c for c, _ in top_cities]

    checklist_val = state.get("checklist")
    if isinstance(checklist_val, str):
        # نص → قائمة
        lines = []
        for line in checklist_val.split("\n"):
            line = re.sub(r"^[#\*\-\d\.\)\s]+", "", line).strip()
            if len(line) > 8:
                lines.append(line)
        checklist_val = lines[:6] if lines else checklist_val

    return {
        "stage":      _v("المرحلة_الحالية"),
        "booking":    _v("حالة_الحجز"),
        "price":      _v("سعر_المتر"),
        "deposit":    _v("قيمة_الجدية"),
        "areas":      _v("المساحات_المتاحة"),
        "payment":    _v("شروط_التقديم"),
        "conditions": _v("شروط_التقديم"),
        "last":       _v("آخر_تطور"),
        "confidence": _v("درجة_الثقة"),
        "cities":     cities_out,
        "dates":      dates,
        "next":       nxt,
        "summary":    state.get("summary"),
        "people":     state.get("people"),
        "forecast":   state.get("forecast"),
        "checklist":  checklist_val,
        "timeline":   (state.get("timeline") or [])[-15:],
    }


def format_changes(changes):
    """صياغة تغييرات ملف بيت الوطن لرسالة تليجرام (backward compat)."""
    if not changes:
        return None
    import html as _html
    lines = [f"🏘️ <b>تحديثات على ملف بيت الوطن ({len(changes)})</b>", ""]
    for ch in changes[:8]:
        field = str(ch.get("field", "")).replace("_", " ")
        to = _html.escape(str(ch.get("to", ""))[:160])
        if ch.get("from"):
            frm = _html.escape(str(ch["from"])[:90])
            lines.append(f"• <b>{_html.escape(field)}</b>: {to} "
                         f"<s>{frm}</s>")
        else:
            lines.append(f"• <b>{_html.escape(field)}</b>: {to}")
    return "\n".join(lines).strip()


# ============================================================
#  السكريبت المستقل (النسخة المبسّطة الأصلية)
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="متابعة بيت الوطن المبسّطة")
    parser.add_argument("--once", action="store_true", help="دورة واحدة")
    parser.add_argument("--daemon", action="store_true", help="تشغيل مستمر")
    args = parser.parse_args()

    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        log("!! لازم تضبط TELEGRAM_TOKEN و TELEGRAM_CHAT_ID الأول.")
        sys.exit(1)

    if args.daemon:
        run_daemon()
    else:
        run_once()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("تم الإيقاف.")
