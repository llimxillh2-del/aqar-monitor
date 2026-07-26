# -*- coding: utf-8 -*-
"""
مصادر البيانات: أخبار · يوتيوب · سوشيال ميديا (RSSHub) · RSS عام
"""

import re
import time
import urllib.parse
from datetime import datetime, timezone, timedelta

import feedparser
import requests

import config


# ============================================================
#  أدوات مشتركة
# ============================================================

def _cutoff():
    return datetime.now(timezone.utc) - timedelta(days=config.MAX_AGE_DAYS)


def _entry_date(entry):
    if getattr(entry, "published_parsed", None):
        return datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
    if getattr(entry, "updated_parsed", None):
        return datetime(*entry.updated_parsed[:6], tzinfo=timezone.utc)
    return None


def _strip_html(text):
    text = re.sub(r"<[^>]+>", " ", text or "")
    return re.sub(r"\s+", " ", text).strip()


def parse_feed(url, label=""):
    """يقرأ أي RSS ويرجع عناصر موحّدة الشكل."""
    items = []
    try:
        feed = feedparser.parse(url)
    except Exception as exc:
        print(f"  [!] فشل قراءة {label or url}: {exc}")
        return items

    cutoff = _cutoff()
    for entry in feed.entries[:config.MAX_PER_QUERY]:
        published = _entry_date(entry)
        if published and published < cutoff:
            continue
        source = ""
        if getattr(entry, "source", None) is not None:
            source = getattr(entry.source, "title", "") or ""
        items.append({
            "title": _strip_html(entry.get("title", "")),
            "link": entry.get("link", ""),
            "source": source or label,
            "snippet": _strip_html(entry.get("summary", ""))[:400],
            "published": published.isoformat() if published else "",
            "published_ts": published.timestamp() if published else 0,
        })
    return items


# ============================================================
#  الأخبار — Google News RSS
# ============================================================

def _clean_title(title):
    return re.sub(r"\s+-\s+[^-]+$", "", title).strip()


def google_news(query):
    q = urllib.parse.quote(query)
    url = f"https://news.google.com/rss/search?q={q}&hl=ar&gl=EG&ceid=EG:ar"
    items = parse_feed(url, label="Google News")
    for it in items:
        it["title"] = _clean_title(it["title"])
        it["kind"] = "news"
    return items


def score_item(item):
    s = 0
    for word in config.PRIORITY_WORDS:
        if word in item["title"]:
            s += 10
    return s


def fetch_news():
    """يجمع كل أقسام الأخبار."""
    result = {}
    for section, queries in config.NEWS_SECTIONS.items():
        print(f"[*] أخبار: {section}")
        seen_links, bucket = set(), []
        for q in queries:
            print(f"    - {q}")
            for item in google_news(q):
                if not item["link"] or item["link"] in seen_links:
                    continue
                seen_links.add(item["link"])
                bucket.append(item)
            time.sleep(1)
        bucket.sort(key=lambda x: (score_item(x), x["published_ts"]), reverse=True)
        result[section] = bucket
    return result


# ============================================================
#  يوتيوب
# ============================================================

def youtube_channel_feed(channel_id, name="YouTube"):
    """RSS رسمي لأي قناة — مجاني وبدون مفتاح."""
    url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
    items = parse_feed(url, label=name)
    for it in items:
        it["kind"] = "video"
        it["video_id"] = _extract_video_id(it["link"])
        it["source"] = name
    return items


def youtube_search(query):
    """بحث يوتيوب — يحتاج YOUTUBE_API_KEY (مجاني)."""
    if not config.YOUTUBE_API_KEY:
        return []
    try:
        r = requests.get("https://www.googleapis.com/youtube/v3/search", params={
            "key": config.YOUTUBE_API_KEY,
            "q": query,
            "part": "snippet",
            "type": "video",
            "order": "date",
            "maxResults": 6,
            "relevanceLanguage": "ar",
        }, timeout=30)
        r.raise_for_status()
    except Exception as exc:
        print(f"  [!] بحث يوتيوب فشل: {str(exc)[:90]}")
        return []

    items = []
    cutoff = _cutoff()
    for entry in r.json().get("items", []):
        sn = entry.get("snippet", {})
        vid = entry.get("id", {}).get("videoId")
        if not vid:
            continue
        published = None
        try:
            published = datetime.fromisoformat(
                sn.get("publishedAt", "").replace("Z", "+00:00"))
        except Exception:
            pass
        if published and published < cutoff:
            continue
        items.append({
            "title": sn.get("title", ""),
            "link": f"https://www.youtube.com/watch?v={vid}",
            "source": sn.get("channelTitle", ""),
            "snippet": (sn.get("description") or "")[:300],
            "published": published.isoformat() if published else "",
            "published_ts": published.timestamp() if published else 0,
            "kind": "video",
            "video_id": vid,
        })
    return items


def _extract_video_id(url):
    m = re.search(r"(?:v=|youtu\.be/|/shorts/)([A-Za-z0-9_-]{11})", url or "")
    return m.group(1) if m else ""


def get_transcript(video_id):
    """يجيب نص الفيديو لو عليه ترجمة."""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError:
        print("  [!] youtube-transcript-api غير مثبتة — تخطي النصوص.")
        return None

    try:
        api = YouTubeTranscriptApi()
        # الأفضلية للعربية ثم الإنجليزية ثم أي لغة متاحة
        try:
            fetched = api.fetch(video_id, languages=["ar", "ar-EG", "en"])
        except Exception:
            listing = api.list(video_id)
            first = next(iter(listing))
            fetched = first.fetch()
        parts = []
        for snippet in fetched:
            parts.append(getattr(snippet, "text", "") or "")
        text = " ".join(p for p in parts if p).strip()
        return text or None
    except Exception as exc:
        print(f"  [!] لا يوجد نص للفيديو {video_id}: {str(exc)[:70]}")
        return None


def get_video_stats(video_ids):
    """إحصائيات الفيديوهات (مشاهدات/إعجابات/كومنتات) — يحتاج مفتاح."""
    if not config.YOUTUBE_API_KEY or not video_ids:
        return {}
    stats = {}
    ids = list(video_ids)
    for i in range(0, len(ids), 50):
        chunk = ids[i:i + 50]
        try:
            r = requests.get("https://www.googleapis.com/youtube/v3/videos", params={
                "key": config.YOUTUBE_API_KEY,
                "id": ",".join(chunk),
                "part": "statistics",
            }, timeout=30)
            r.raise_for_status()
        except Exception as exc:
            print(f"  [!] تعذّر جلب الإحصائيات: {str(exc)[:80]}")
            continue
        for entry in r.json().get("items", []):
            s = entry.get("statistics", {})
            stats[entry["id"]] = {
                "views": int(s.get("viewCount", 0) or 0),
                "likes": int(s.get("likeCount", 0) or 0),
                "comments": int(s.get("commentCount", 0) or 0),
            }
    return stats


def get_top_comments(video_id, limit=None):
    """أكتر الكومنتات تفاعلًا على الفيديو — مجاني عبر YouTube Data API."""
    limit = limit or config.MAX_COMMENTS_PER_VIDEO
    if not config.YOUTUBE_API_KEY:
        return []
    try:
        r = requests.get("https://www.googleapis.com/youtube/v3/commentThreads", params={
            "key": config.YOUTUBE_API_KEY,
            "videoId": video_id,
            "part": "snippet",
            "order": "relevance",       # الأكثر تفاعلًا
            "maxResults": min(limit, 100),
            "textFormat": "plainText",
        }, timeout=30)
        r.raise_for_status()
    except Exception as exc:
        msg = str(exc)
        if "403" in msg:
            print("      (الكومنتات مقفولة على الفيديو ده)")
        else:
            print(f"      (تعذّر جلب الكومنتات: {msg[:60]})")
        return []

    out = []
    for thread in r.json().get("items", []):
        sn = (thread.get("snippet", {})
                    .get("topLevelComment", {})
                    .get("snippet", {}))
        text = (sn.get("textDisplay") or "").strip()
        if not text:
            continue
        out.append({
            "author": sn.get("authorDisplayName", ""),
            "text": text,
            "likes": int(sn.get("likeCount", 0) or 0),
            "replies": int(thread.get("snippet", {}).get("totalReplyCount", 0) or 0),
        })
    out.sort(key=lambda c: (c["likes"], c["replies"]), reverse=True)
    return out


def _engagement_rate(item):
    """مشاهدات في اليوم — مؤشر على سخونة الفيديو."""
    st = item.get("stats") or {}
    views = st.get("views", 0)
    if not views:
        return 0
    if item.get("published_ts"):
        age_days = max(
            (datetime.now(timezone.utc).timestamp() - item["published_ts"]) / 86400, 1)
    else:
        age_days = 30
    return views / age_days


def fetch_videos():
    """يجمع فيديوهات من القنوات المتابَعة والبحث + إحصائيات التفاعل."""
    print("[*] يوتيوب")
    seen, bucket = set(), []

    for entry in config.YOUTUBE_CHANNELS:
        name, ch_id = entry if isinstance(entry, (tuple, list)) else ("YouTube", entry)
        print(f"    - قناة: {name}")
        for it in youtube_channel_feed(ch_id, name):
            if it["link"] not in seen:
                seen.add(it["link"])
                bucket.append(it)
        time.sleep(1)

    for q in config.YOUTUBE_QUERIES:
        found = youtube_search(q)
        if found:
            print(f"    - بحث: {q} ({len(found)})")
        for it in found:
            if it["link"] not in seen:
                seen.add(it["link"])
                bucket.append(it)
        time.sleep(1)

    # إحصائيات التفاعل
    vids = [it["video_id"] for it in bucket if it.get("video_id")]
    stats = get_video_stats(vids)
    if stats:
        for it in bucket:
            it["stats"] = stats.get(it.get("video_id"), {})
        print(f"    - تم جلب إحصائيات {len(stats)} فيديو")

    if config.RANK_VIDEOS_BY_ENGAGEMENT and stats:
        bucket.sort(key=lambda x: (score_item(x), _engagement_rate(x)), reverse=True)
    else:
        bucket.sort(key=lambda x: (score_item(x), x["published_ts"]), reverse=True)
    return bucket


# ============================================================
#  السوشيال ميديا عبر RSSHub
# ============================================================

def fetch_social():
    """
    ⚠️ يعتمد على RSSHub. النسخة العامة كثيرًا ما تُحجب من المنصات.
    شغّل نسخة خاصة بك وحدّث RSSHUB_BASE للحصول على ثبات.
    """
    if not config.SOCIAL_FEEDS:
        return []
    print("[*] السوشيال ميديا (RSSHub)")
    out = []
    for feed in config.SOCIAL_FEEDS:
        url = config.RSSHUB_BASE.rstrip("/") + feed["path"]
        print(f"    - {feed['name']}")
        items = parse_feed(url, label=feed["name"])
        if not items:
            print(f"      (لا توجد نتائج — قد يكون المسار محجوبًا)")
        for it in items:
            it["kind"] = "social"
        out.extend(items)
        time.sleep(1)
    out.sort(key=lambda x: x["published_ts"], reverse=True)
    return out


def fetch_extra_rss():
    """أي روابط RSS إضافية."""
    if not config.EXTRA_RSS:
        return []
    print("[*] مصادر RSS إضافية")
    out = []
    for feed in config.EXTRA_RSS:
        print(f"    - {feed['name']}")
        items = parse_feed(feed["url"], label=feed["name"])
        for it in items:
            it["kind"] = "news"
        out.extend(items)
        time.sleep(1)
    out.sort(key=lambda x: (score_item(x), x["published_ts"]), reverse=True)
    return out
