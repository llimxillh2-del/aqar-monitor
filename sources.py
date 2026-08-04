# -*- coding: utf-8 -*-
"""
مصادر البيانات: أخبار · يوتيوب · سوشيال ميديا (RSSHub) · RSS عام

إصلاحات عن النسخة القديمة:
  • feedparser مابقاش بيجيب الرابط بنفسه (كان بدون مهلة ولا User-Agent
    وممكن يعلّق للأبد) — بنجيب بـ requests بمهلة وبعدين نمرّر البايتات.
  • ضبط الترميز يدويًا للمواقع المصرية اللي مابتبعتش charset.
  • جلسة requests واحدة بـ retry تلقائي.
"""

import re
import html
import time
import urllib.parse
from datetime import datetime, timezone, timedelta

import feedparser
import requests
from requests.adapters import HTTPAdapter

try:                                     # urllib3 v2 و v1 مختلفين في المسار
    from urllib3.util.retry import Retry
except ImportError:                      # pragma: no cover
    Retry = None

import config
import quality


UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

_SESSION = None


def session():
    """جلسة واحدة بإعادة محاولة تلقائية — أسرع وأثبت من requests.get المباشر."""
    global _SESSION
    if _SESSION is not None:
        return _SESSION
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept-Language": "ar,en;q=0.8"})
    if Retry is not None:
        retry = Retry(total=2, backoff_factor=0.6,
                      status_forcelist=(429, 500, 502, 503, 504),
                      allowed_methods=frozenset(["GET", "POST"]))
        adapter = HTTPAdapter(max_retries=retry, pool_connections=10,
                              pool_maxsize=10)
        s.mount("https://", adapter)
        s.mount("http://", adapter)
    _SESSION = s
    return s


# ============================================================
#  أدوات مشتركة
# ============================================================

def _cutoff():
    return datetime.now(timezone.utc) - timedelta(days=config.MAX_AGE_DAYS)


def _entry_date(entry):
    for attr in ("published_parsed", "updated_parsed"):
        parsed = getattr(entry, attr, None)
        if parsed:
            try:
                return datetime(*parsed[:6], tzinfo=timezone.utc)
            except (TypeError, ValueError):
                continue
    return None


def _strip_html(text):
    """
    يشيل الوسوم **ويفك رموز HTML**. من غير الفك كان `&nbsp;` بيوصل
    للصفحة كنص، وبعدين esc() بيهرب الـ& فيشوفه الزائر «&nbsp;&nbsp;».
    """
    text = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", text or "")
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    return re.sub(r"[\s\u00a0\u200f\u200e]+", " ", text).strip()


def fetch_bytes(url, timeout=None):
    """يجيب محتوى رابط كبايتات — بمهلة وUser-Agent. يرجّع (bytes, error)."""
    timeout = timeout or config.REQUEST_TIMEOUT
    try:
        r = session().get(url, timeout=timeout)
        r.raise_for_status()
        return r.content, None
    except Exception as exc:
        return None, str(exc)[:120]


def parse_feed(url, label=""):
    """يقرأ أي RSS ويرجع عناصر موحّدة الشكل."""
    items = []
    raw, err = fetch_bytes(url)
    if err:
        print(f"  [!] فشل قراءة {label or url}: {err}")
        return items

    try:
        feed = feedparser.parse(raw)
    except Exception as exc:
        print(f"  [!] فشل تحليل {label or url}: {str(exc)[:90]}")
        return items

    cutoff = _cutoff()
    for entry in feed.entries[:config.MAX_PER_QUERY]:
        published = _entry_date(entry)
        if published and published < cutoff:
            continue

        source = ""
        src_obj = getattr(entry, "source", None)
        if src_obj is not None:
            source = getattr(src_obj, "title", "") or ""

        link = entry.get("link", "") or ""
        title = _strip_html(entry.get("title", ""))
        if not link or not title:
            continue

        items.append({
            "title": title,
            "link": link,
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
    """Google News بيلزق ' - اسم الموقع' في آخر العنوان."""
    return re.sub(r"\s+-\s+[^-]+$", "", title).strip()


def _useful_snippet(snippet, title):
    """
    ملخص Google News دايمًا = «العنوان + اسم الموقع» — تكرار خالص.
    بنرميه لو مش بيضيف معلومة فعلية على العنوان.
    """
    snip = (snippet or "").strip()
    if not snip:
        return ""
    core = re.sub(r"\W+", "", snip)
    head = re.sub(r"\W+", "", title or "")
    if not core or (head and core.startswith(head[:40])):
        return ""
    return snip if len(core) > len(head) + 40 else ""


def google_news(query):
    q = urllib.parse.quote(query)
    url = f"https://news.google.com/rss/search?q={q}&hl=ar&gl=EG&ceid=EG:ar"
    items = parse_feed(url, label="Google News")
    for it in items:
        it["title"] = _clean_title(it["title"])
        it["snippet"] = _useful_snippet(it.get("snippet"), it["title"])
        it["kind"] = "news"
    return items


def score_item(item):
    """أولوية مبدئية بالكلمات — قبل ما الـ AI يشوفها."""
    title = item.get("title", "")
    s = 0
    for word in config.PRIORITY_WORDS:
        if word in title:
            s += 10
    for word in config.BEIT_ALWATAN["match_words"]:
        if word in title:
            s += 15
            break
    return s


def fetch_news(extra_queries=None):
    """
    يجمع كل أقسام الأخبار مع طبقة الجودة:
      • فك تشفير روابط Google News (شغّالة فعلًا مش wrappers)
      • تصنيف tier للمصادر (الأهرام أعلى من بلوج مجهول)
      • فلتر مصر (بيرمي أخبار السعودية/الإمارات من "تحليل السوق")
      • dedup ذكي (نفس القصة من ٨ مصادر = كارت واحد + قائمة مصادر)

    extra_queries: عبارات إضافية تتحط في القسم الأول (بيت الوطن).
    """
    result = {}
    sections = {k: list(v) for k, v in config.NEWS_SECTIONS.items()}

    if extra_queries:
        first = next(iter(sections))
        for q in extra_queries:
            if q not in sections[first]:
                sections[first].append(q)

    # منع التكرار **بين** الأقسام كمان — قبل كده كان لكل قسم مجموعته
    # الخاصة، فنفس الخبر كان بيظهر في قسمين.
    global_links, global_titles = set(), set()

    for section, queries in sections.items():
        print(f"[*] أخبار: {section}")
        seen_links, seen_titles, bucket = global_links, global_titles, []
        for q in queries:
            print(f"    - {q}")
            for item in google_news(q):
                key = re.sub(r"\W+", "", item["title"])[:60]
                if item["link"] in seen_links or key in seen_titles:
                    continue
                seen_links.add(item["link"])
                seen_titles.add(key)
                bucket.append(item)
            time.sleep(0.8)

        # ٥) طبقة الجودة — الفلترة والدمج
        raw_count = len(bucket)
        # فلتر مصر بس على "تحليل السوق" — الأقسام التانية أصلاً عن مصر
        filter_eg = "تحليل السوق" in section
        clean = quality.enrich_items(bucket, filter_egypt=filter_eg,
                                     dedupe=True, dedupe_threshold=0.42)
        # الأحدث أولاً — القارئ بيتوقع تسلسل زمني. الأولوية والمصدر
        # بيكسروا التعادل بس. (قبل كده كان الترتيب بالكلمات المفتاحية
        # فالتواريخ كانت بتقفز قدام وورا على الصفحة.)
        clean.sort(key=lambda x: (
            -float(x.get("published_ts") or 0),
            -score_item(x),
            x.get("source_tier", 3),
        ))
        result[section] = clean
        merged = raw_count - len(clean)
        print(f"    → {len(clean)} عنصر (اتدمج {merged} خبر مكرر)")

    quality.save_url_cache()
    return result


# ============================================================
#  يوتيوب
# ============================================================

def _extract_video_id(url):
    m = re.search(r"(?:v=|youtu\.be/|/shorts/|/embed/)([A-Za-z0-9_-]{11})",
                  url or "")
    return m.group(1) if m else ""


def youtube_channel_feed(channel_id, name="YouTube"):
    """RSS رسمي لأي قناة — مجاني وبدون مفتاح."""
    url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
    items = parse_feed(url, label=name)
    for it in items:
        it["kind"] = "video"
        it["video_id"] = _extract_video_id(it["link"])
        it["source"] = name
    return items


def youtube_search(query, max_results=6):
    """بحث يوتيوب — يحتاج YOUTUBE_API_KEY (مجاني)."""
    if not config.YOUTUBE_API_KEY:
        return []
    try:
        r = session().get("https://www.googleapis.com/youtube/v3/search", params={
            "key": config.YOUTUBE_API_KEY,
            "q": query,
            "part": "snippet",
            "type": "video",
            "order": "date",
            "maxResults": max_results,
            "relevanceLanguage": "ar",
        }, timeout=config.REQUEST_TIMEOUT)
        r.raise_for_status()
    except Exception as exc:
        print(f"  [!] بحث يوتيوب فشل: {str(exc)[:90]}")
        return []

    items, cutoff = [], _cutoff()
    for entry in r.json().get("items", []):
        sn = entry.get("snippet", {})
        vid = (entry.get("id") or {}).get("videoId")
        if not vid:
            continue
        published = None
        try:
            published = datetime.fromisoformat(
                (sn.get("publishedAt") or "").replace("Z", "+00:00"))
        except (TypeError, ValueError):
            pass
        if published and published < cutoff:
            continue
        items.append({
            "title": _strip_html(sn.get("title", "")),
            "link": f"https://www.youtube.com/watch?v={vid}",
            "source": sn.get("channelTitle", ""),
            "snippet": (sn.get("description") or "")[:300],
            "published": published.isoformat() if published else "",
            "published_ts": published.timestamp() if published else 0,
            "kind": "video",
            "video_id": vid,
        })
    return items


def get_transcript(video_id):
    """يجيب نص الفيديو لو عليه ترجمة."""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError:
        print("  [!] youtube-transcript-api غير مثبتة — تخطي النصوص.")
        return None

    try:
        api = YouTubeTranscriptApi()
        try:
            fetched = api.fetch(video_id, languages=["ar", "ar-EG", "en"])
        except Exception:
            listing = api.list(video_id)
            first = next(iter(listing))
            fetched = first.fetch()
        parts = [getattr(sn, "text", "") or "" for sn in fetched]
        text = " ".join(p for p in parts if p).strip()
        return text or None
    except Exception as exc:
        print(f"  [!] لا يوجد نص للفيديو {video_id}: {str(exc)[:70]}")
        return None


def get_video_stats(video_ids):
    """إحصائيات الفيديوهات — يحتاج مفتاح."""
    if not config.YOUTUBE_API_KEY or not video_ids:
        return {}
    stats, ids = {}, list(dict.fromkeys(video_ids))
    for i in range(0, len(ids), 50):
        chunk = ids[i:i + 50]
        try:
            r = session().get("https://www.googleapis.com/youtube/v3/videos", params={
                "key": config.YOUTUBE_API_KEY,
                "id": ",".join(chunk),
                "part": "statistics",
            }, timeout=config.REQUEST_TIMEOUT)
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
    """أكتر الكومنتات تفاعلًا على الفيديو."""
    limit = limit or config.MAX_COMMENTS_PER_VIDEO
    if not config.YOUTUBE_API_KEY:
        return []
    try:
        r = session().get(
            "https://www.googleapis.com/youtube/v3/commentThreads", params={
                "key": config.YOUTUBE_API_KEY,
                "videoId": video_id,
                "part": "snippet",
                "order": "relevance",
                "maxResults": min(limit, 100),
                "textFormat": "plainText",
            }, timeout=config.REQUEST_TIMEOUT)
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
        top = (thread.get("snippet", {}) or {}).get("topLevelComment", {}) or {}
        sn = top.get("snippet", {}) or {}
        text = (sn.get("textDisplay") or "").strip()
        if not text:
            continue
        out.append({
            "author": sn.get("authorDisplayName", ""),
            "text": text,
            "likes": int(sn.get("likeCount", 0) or 0),
            "replies": int((thread.get("snippet", {}) or {})
                           .get("totalReplyCount", 0) or 0),
            "video_id": video_id,
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


def fetch_videos(extra_queries=None):
    """يجمع فيديوهات من القنوات المتابَعة والبحث + إحصائيات التفاعل."""
    print("[*] يوتيوب")
    seen, bucket = set(), []

    for entry in config.YOUTUBE_CHANNELS:
        name, ch_id = entry if isinstance(entry, (tuple, list)) \
            else ("YouTube", entry)
        print(f"    - قناة: {name}")
        for it in youtube_channel_feed(ch_id, name):
            if it["link"] not in seen:
                seen.add(it["link"])
                bucket.append(it)
        time.sleep(0.6)

    queries = list(config.YOUTUBE_QUERIES)
    for q in (extra_queries or []):
        if q not in queries:
            queries.append(q)

    for q in queries:
        found = youtube_search(q)
        if found:
            print(f"    - بحث: {q} ({len(found)})")
        for it in found:
            if it["link"] not in seen:
                seen.add(it["link"])
                bucket.append(it)
        time.sleep(0.6)

    vids = [it["video_id"] for it in bucket if it.get("video_id")]
    stats = get_video_stats(vids)
    if stats:
        for it in bucket:
            it["stats"] = stats.get(it.get("video_id"), {})
        print(f"    - إحصائيات {len(stats)} فيديو")

    if config.RANK_VIDEOS_BY_ENGAGEMENT and stats:
        bucket.sort(key=lambda x: (score_item(x), _engagement_rate(x)),
                    reverse=True)
    else:
        bucket.sort(key=lambda x: (score_item(x), x["published_ts"]),
                    reverse=True)
    print(f"    → {len(bucket)} فيديو")
    return bucket


# ============================================================
#  السوشيال ميديا عبر RSSHub + RSS إضافي
# ============================================================

def fetch_social():
    """يعتمد على RSSHub. النسخة العامة كثيرًا ما تُحجب من المنصات."""
    if not config.SOCIAL_FEEDS:
        return []
    print("[*] السوشيال ميديا (RSSHub)")
    out = []
    for feed in config.SOCIAL_FEEDS:
        url = config.RSSHUB_BASE.rstrip("/") + feed["path"]
        print(f"    - {feed['name']}")
        items = parse_feed(url, label=feed["name"])
        if not items:
            print("      (لا توجد نتائج — قد يكون المسار محجوبًا)")
        for it in items:
            it["kind"] = "social"
        out.extend(items)
        time.sleep(0.8)
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
        time.sleep(0.6)
    out.sort(key=lambda x: (score_item(x), x["published_ts"]), reverse=True)
    return out
