# -*- coding: utf-8 -*-
"""
جامع كلام الناس
================
بيسحب النص البشري الخام من كل مكان الناس بتتكلم فيه عن بيت الوطن:

  • يوتيوب المعمّق — كل الكومنتات **والردود**، مرتبة بالأحدث مش بالأشهر.
    الردود بالذات مهمة: المعلومة الحقيقية غالبًا بتكون في رد على سؤال.
  • قنوات تليجرام العامة — بتتقرا من t.me/s/<name> بدون مفتاح ولا تسجيل.
  • Reddit — بحث + تعليقات، JSON مجاني بالكامل.
  • RSSHub — فيسبوك / X لو مفعّل.

كل حاجة بترجع بنفس الشكل الموحّد (utterance) عشان محرك الإشارات
يشتغل على الكل بنفس الطريقة.
"""

import re
import json
import time
import html
import hashlib
import urllib.parse
from datetime import datetime, timezone, timedelta

import config
from sources import session, _strip_html, _cutoff


# ============================================================
#  الشكل الموحّد
# ============================================================

def utterance(text, platform, channel, author="", url="", likes=0,
              replies=0, published="", context="", parent=""):
    """
    وحدة كلام واحدة من أي مصدر.
    channel = وحدة الاستقلالية (قناة يوتيوب / قناة تليجرام / subreddit).
              الإشارة اللي تتكرر في قناتين مختلفين أقوى بكتير من
              اللي تتكرر ١٠ مرات في نفس القناة.
    """
    clean = re.sub(r"\s+", " ", (text or "")).strip()
    return {
        "id": hashlib.sha1(
            f"{platform}|{channel}|{clean[:200]}".encode("utf-8")
        ).hexdigest()[:16],
        "text": clean,
        "platform": platform,
        "channel": channel or platform,
        "author": author or "",
        "url": url or "",
        "likes": int(likes or 0),
        "replies": int(replies or 0),
        "published": published or "",
        "context": context or "",
        "parent": parent or "",
    }


def _matches_beit(text):
    return any(w in text for w in config.BEIT_ALWATAN["match_words"])


# ============================================================
#  1) يوتيوب المعمّق
# ============================================================

def youtube_deep(video_ids, contexts=None):
    """
    كل الكومنتات والردود من الفيديوهات المحددة، مرتبة بالأحدث.
    contexts: {video_id: عنوان الفيديو}
    """
    if not config.YOUTUBE_API_KEY or not video_ids:
        return []

    contexts = contexts or {}
    out = []
    api = "https://www.googleapis.com/youtube/v3/commentThreads"
    part = ("snippet,replies" if config.INTEL_YT_INCLUDE_REPLIES else "snippet")

    for vid in list(video_ids)[:config.INTEL_YT_VIDEOS]:
        ctx = contexts.get(vid, "")
        channel = f"yt:{ctx[:40]}" if ctx else f"yt:{vid}"
        token, pages = None, 0

        while pages < config.INTEL_YT_PAGES_PER_VIDEO:
            params = {
                "key": config.YOUTUBE_API_KEY,
                "videoId": vid,
                "part": part,
                "order": "time",            # الأحدث — هنا التسريبات
                "maxResults": 100,
                "textFormat": "plainText",
            }
            if token:
                params["pageToken"] = token

            try:
                r = session().get(api, params=params,
                                  timeout=config.REQUEST_TIMEOUT)
                r.raise_for_status()
                data = r.json()
            except Exception as exc:
                msg = str(exc)
                if "403" in msg:
                    print(f"      (كومنتات مقفولة: {vid})")
                elif "404" not in msg:
                    print(f"      (تعذّر: {msg[:60]})")
                break

            for thread in data.get("items", []):
                sn = ((thread.get("snippet") or {})
                      .get("topLevelComment") or {}).get("snippet") or {}
                text = (sn.get("textDisplay") or "").strip()
                if text:
                    out.append(utterance(
                        text, "youtube", channel,
                        author=sn.get("authorDisplayName", ""),
                        url=f"https://www.youtube.com/watch?v={vid}"
                            f"&lc={thread.get('id', '')}",
                        likes=sn.get("likeCount", 0),
                        replies=(thread.get("snippet") or {}).get("totalReplyCount", 0),
                        published=sn.get("publishedAt", ""),
                        context=ctx))

                # الردود — أغلى مصدر للمعلومة
                for rep in ((thread.get("replies") or {}).get("comments") or []):
                    rsn = rep.get("snippet") or {}
                    rtext = (rsn.get("textDisplay") or "").strip()
                    if not rtext:
                        continue
                    out.append(utterance(
                        rtext, "youtube", channel,
                        author=rsn.get("authorDisplayName", ""),
                        url=f"https://www.youtube.com/watch?v={vid}"
                            f"&lc={rep.get('id', '')}",
                        likes=rsn.get("likeCount", 0),
                        published=rsn.get("publishedAt", ""),
                        context=ctx,
                        parent=text[:120]))

            token = data.get("nextPageToken")
            pages += 1
            if not token:
                break
            time.sleep(0.25)

    print(f"    - يوتيوب: {len(out)} تعليق ورد")
    return out


# ============================================================
#  2) قنوات تليجرام العامة
# ============================================================

_TG_MSG_RE = re.compile(
    r'<div class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>', re.S)
_TG_TIME_RE = re.compile(r'<time[^>]+datetime="([^"]+)"')
_TG_VIEWS_RE = re.compile(r'tgme_widget_message_views">([^<]+)<')
_TG_LINK_RE = re.compile(r'href="(https://t\.me/[^/]+/\d+)"')


def _tg_views(raw):
    """يحوّل 12.5K / 3M لرقم."""
    raw = (raw or "").strip().upper().replace(",", "")
    m = re.match(r"^([\d.]+)([KM]?)$", raw)
    if not m:
        return 0
    n = float(m.group(1))
    return int(n * {"K": 1000, "M": 1_000_000}.get(m.group(2), 1))


def telegram_channels(channels=None):
    """
    قراءة آخر رسائل أي قناة تليجرام عامة.
    t.me/s/<name> بترجع HTML فيه آخر ~20 رسالة — مجاني وبدون أي مفتاح.
    """
    channels = channels or config.TELEGRAM_CHANNELS
    if not channels:
        return []

    out = []
    cutoff = _cutoff()

    for name in channels:
        name = name.lstrip("@").strip()
        if not name:
            continue
        try:
            r = session().get(f"https://t.me/s/{name}",
                              timeout=config.REQUEST_TIMEOUT)
            if r.status_code == 404:
                print(f"    - تليجرام @{name}: القناة مش موجودة أو مش عامة")
                continue
            r.raise_for_status()
            page = r.text
        except Exception as exc:
            print(f"    - تليجرام @{name}: {str(exc)[:60]}")
            continue

        blocks = page.split('class="tgme_widget_message ')
        found = 0
        for block in blocks[1:]:
            m = _TG_MSG_RE.search(block)
            if not m:
                continue
            text = _strip_html(m.group(1).replace("<br/>", " ").replace("<br>", " "))
            text = html.unescape(text)
            if len(text) < 20:
                continue

            when = ""
            tm = _TG_TIME_RE.search(block)
            if tm:
                when = tm.group(1)
                try:
                    dt = datetime.fromisoformat(when.replace("Z", "+00:00"))
                    if dt < cutoff:
                        continue
                except (TypeError, ValueError):
                    pass

            link = ""
            lm = _TG_LINK_RE.search(block)
            if lm:
                link = lm.group(1)

            views = 0
            vm = _TG_VIEWS_RE.search(block)
            if vm:
                views = _tg_views(vm.group(1))

            out.append(utterance(text, "telegram", f"tg:{name}",
                                 author=f"@{name}", url=link or f"https://t.me/{name}",
                                 likes=views, published=when,
                                 context=f"قناة تليجرام @{name}"))
            found += 1

        if found:
            print(f"    - تليجرام @{name}: {found} رسالة")
        time.sleep(0.6)

    return out


# ============================================================
#  3) Reddit
# ============================================================

def _reddit_get(url, params=None):
    try:
        r = session().get(url, params=params, timeout=config.REQUEST_TIMEOUT,
                          headers={"User-Agent": "aqar-monitor/2.0 (research)"})
        r.raise_for_status()
        return r.json()
    except Exception as exc:
        print(f"      (reddit: {str(exc)[:60]})")
        return None


def reddit(queries=None, subs=None, with_comments=True):
    """بحث Reddit + تعليقات البوستات المطابقة. JSON مجاني بالكامل."""
    if not config.REDDIT_ENABLED:
        return []

    queries = queries or config.REDDIT_QUERIES
    subs = subs or config.REDDIT_SUBS
    out, post_ids = [], []
    cutoff_ts = _cutoff().timestamp()

    for q in queries:
        data = _reddit_get("https://www.reddit.com/search.json", {
            "q": q, "sort": "new", "limit": 50, "t": "month",
            "raw_json": 1,
        })
        for child in ((data or {}).get("data") or {}).get("children", []):
            d = child.get("data") or {}
            if d.get("created_utc", 0) < cutoff_ts:
                continue
            sub = d.get("subreddit", "")
            body = (d.get("selftext") or "").strip()
            title = (d.get("title") or "").strip()
            text = f"{title}. {body}" if body else title
            if len(text) < 20:
                continue
            out.append(utterance(
                text, "reddit", f"r/{sub}",
                author=d.get("author", ""),
                url="https://www.reddit.com" + (d.get("permalink") or ""),
                likes=d.get("score", 0), replies=d.get("num_comments", 0),
                published=datetime.fromtimestamp(
                    d.get("created_utc", 0), timezone.utc).isoformat(),
                context=f"Reddit r/{sub}"))
            if d.get("num_comments", 0) > 0 and d.get("id"):
                post_ids.append((d["id"], sub, title))
        time.sleep(1.2)

    if with_comments:
        for post_id, sub, title in post_ids[:12]:
            data = _reddit_get(
                f"https://www.reddit.com/comments/{post_id}.json",
                {"limit": 60, "sort": "new", "raw_json": 1})
            if not isinstance(data, list) or len(data) < 2:
                continue
            for child in ((data[1].get("data") or {}).get("children") or []):
                d = child.get("data") or {}
                body = (d.get("body") or "").strip()
                if len(body) < 20 or body in ("[deleted]", "[removed]"):
                    continue
                out.append(utterance(
                    body, "reddit", f"r/{sub}",
                    author=d.get("author", ""),
                    url="https://www.reddit.com" + (d.get("permalink") or ""),
                    likes=d.get("score", 0),
                    published=datetime.fromtimestamp(
                        d.get("created_utc", 0), timezone.utc).isoformat(),
                    context=f"Reddit r/{sub} — {title[:60]}"))
            time.sleep(1.2)

    print(f"    - Reddit: {len(out)} بوست وتعليق")
    return out


# ============================================================
#  4) جروبات فيسبوك — عبر إشعارات الإيميل
# ============================================================
# ليه الطريقة دي؟
#   Graph API للجروبات اتلغى في ٢٠٢٤، و RSSHub بيتحجب، والـ scraping
#   بيكسر شروط الاستخدام وبيتقفل الحساب. الطريقة الشرعية الوحيدة اللي
#   بتشتغل بثبات: تفعّل إشعارات الجروب بالإيميل، والنظام يقرا الإيميلات.
#
#   إنت عضو في الجروب فعلًا، وفيسبوك بيبعتلك المحتوى بإرادته — مفيش
#   أي خرق ولا مخاطرة على حسابك.

_FB_SENDERS = ("facebookmail.com", "facebook.com")

_EMAIL_NOISE = re.compile(
    r"(?is)(تم إرسال هذا البريد|This message was sent to|"
    r"إلغاء الاشتراك|Unsubscribe|Meta Platforms|Facebook, Inc|"
    r"لتعديل إعدادات|To change your notification|"
    r"عرض المنشور|View Post|الرد على هذا البريد).*$")


def _decode_header(raw):
    from email.header import decode_header, make_header
    try:
        return str(make_header(decode_header(raw or "")))
    except Exception:
        return raw or ""


def _email_body(msg):
    """يطلّع نص الرسالة سواء plain أو html."""
    import quopri

    def _payload(part):
        try:
            data = part.get_payload(decode=True)
            if data is None:
                return ""
            charset = part.get_content_charset() or "utf-8"
            return data.decode(charset, "replace")
        except Exception:
            return ""

    plain, html_txt = "", ""
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            if part.get_filename():
                continue
            if ctype == "text/plain" and not plain:
                plain = _payload(part)
            elif ctype == "text/html" and not html_txt:
                html_txt = _payload(part)
    else:
        if msg.get_content_type() == "text/html":
            html_txt = _payload(msg)
        else:
            plain = _payload(msg)

    text = plain or _strip_html(html_txt)
    text = html.unescape(text)
    text = _EMAIL_NOISE.sub("", text)
    return re.sub(r"\n{2,}", "\n", text).strip()


def _group_name(subject, body):
    """يستخرج اسم الجروب من موضوع الإشعار."""
    subject = subject or ""
    patterns = [
        r"في\s+«(.+?)»", r"في\s+\"(.+?)\"", r"in\s+\"(.+?)\"",
        r"مجموعة\s+(.+?)(?:\s*[-–|]|$)", r"group\s+(.+?)(?:\s*[-–|]|$)",
    ]
    for rx in patterns:
        m = re.search(rx, subject, re.I)
        if m and len(m.group(1).strip()) > 2:
            return m.group(1).strip()[:60]
    m = re.search(r"(?:نشر|posted|shared).{0,40}?[«\"](.+?)[»\"]", body or "")
    if m:
        return m.group(1).strip()[:60]
    return "جروب فيسبوك"


def facebook_via_email(limit=None):
    """
    يقرا إشعارات جروبات فيسبوك من صندوق بريد عبر IMAP.
    محتاج: IMAP_HOST · IMAP_USER · IMAP_PASSWORD (كلمة سر تطبيقات)
    """
    if not config.FB_EMAIL_ENABLED:
        return []
    host = config.IMAP_HOST
    user = config.IMAP_USER
    password = config.IMAP_PASSWORD
    if not (host and user and password):
        print("    - فيسبوك (إيميل): مش مضبوط — "
              "محتاج IMAP_HOST و IMAP_USER و IMAP_PASSWORD")
        return []

    import imaplib
    import email as email_lib

    limit = limit or config.FB_EMAIL_MAX
    since = (datetime.now(timezone.utc)
             - timedelta(days=config.MAX_AGE_DAYS)).strftime("%d-%b-%Y")
    out = []

    try:
        conn = imaplib.IMAP4_SSL(host, config.IMAP_PORT)
        conn.login(user, password)
        conn.select(config.IMAP_FOLDER, readonly=True)

        uids = []
        for sender in _FB_SENDERS:
            try:
                typ, data = conn.search(None,
                                        f'(SINCE {since} FROM "{sender}")')
                if typ == "OK" and data and data[0]:
                    uids += data[0].split()
            except Exception:
                continue

        uids = list(dict.fromkeys(uids))[-limit:]

        for uid in uids:
            try:
                typ, data = conn.fetch(uid, "(RFC822)")
                if typ != "OK" or not data or not data[0]:
                    continue
                msg = email_lib.message_from_bytes(data[0][1])
            except Exception:
                continue

            subject = _decode_header(msg.get("Subject", ""))
            body = _email_body(msg)
            if len(body) < 25:
                continue

            when = ""
            try:
                from email.utils import parsedate_to_datetime
                dt = parsedate_to_datetime(msg.get("Date", ""))
                if dt:
                    when = dt.astimezone(timezone.utc).isoformat()
            except Exception:
                pass

            group = _group_name(subject, body)
            # الموضوع غالبًا فيه اسم الكاتب: "أحمد نشر في ..."
            author = ""
            m = re.match(r"^(.{2,40}?)\s+(?:نشر|علّق|كتب|posted|commented)",
                         subject)
            if m:
                author = m.group(1).strip()

            link = ""
            m = re.search(r"https?://(?:www\.|m\.)?facebook\.com/\S+", body)
            if m:
                link = m.group(0).rstrip(").,\"'>").split("&")[0]

            out.append(utterance(
                f"{subject}. {body}"[:1500], "facebook", f"fb:{group}",
                author=author or group, url=link,
                published=when, context=f"جروب فيسبوك — {group}"))

        conn.close()
        conn.logout()
    except Exception as exc:
        print(f"    - فيسبوك (إيميل): {str(exc)[:90]}")
        return []

    print(f"    - فيسبوك (إيميل): {len(out)} إشعار من "
          f"{len({u['channel'] for u in out})} جروب")
    return out


# ============================================================
#  5) RSSHub (فيسبوك / X / إنستجرام)
# ============================================================

def rsshub_social():
    """يعيد استخدام SOCIAL_FEEDS لكن بشكل utterance."""
    from sources import parse_feed
    if not config.SOCIAL_FEEDS:
        return []
    out = []
    for feed in config.SOCIAL_FEEDS:
        url = config.RSSHUB_BASE.rstrip("/") + feed["path"]
        items = parse_feed(url, label=feed["name"])
        for it in items:
            text = f"{it['title']}. {it.get('snippet', '')}".strip()
            if len(text) < 20:
                continue
            out.append(utterance(
                text, "social", f"fb:{feed['name']}",
                author=feed["name"], url=it["link"],
                published=it.get("published", ""),
                context=feed["name"]))
        time.sleep(0.8)
    if out:
        print(f"    - سوشيال (RSSHub): {len(out)} منشور")
    return out


# ============================================================
#  الجمع الشامل
# ============================================================

def harvest(video_ids=None, video_titles=None, beit_only=True):
    """
    يجمع كل كلام الناس من كل المصادر المفعّلة.
    beit_only=True → يفلتر على اللي يخص بيت الوطن بس (بيوفّر AI كتير).
    """
    print("[*] جمع كلام الناس")
    all_utts = []

    try:
        all_utts += youtube_deep(video_ids or [], video_titles or {})
    except Exception as exc:
        print(f"    ! يوتيوب: {str(exc)[:70]}")

    try:
        all_utts += telegram_channels()
    except Exception as exc:
        print(f"    ! تليجرام عام: {str(exc)[:70]}")

    # جروبات وقنوات تليجرام الخاصة — عبر حسابك
    try:
        import telegram_client
        all_utts += telegram_client.collect()
    except Exception as exc:
        print(f"    ! تليجرام (حسابك): {str(exc)[:70]}")

    try:
        all_utts += facebook_via_email()
    except Exception as exc:
        print(f"    ! فيسبوك: {str(exc)[:70]}")

    try:
        all_utts += reddit()
    except Exception as exc:
        print(f"    ! reddit: {str(exc)[:70]}")

    try:
        all_utts += rsshub_social()
    except Exception as exc:
        print(f"    ! سوشيال: {str(exc)[:70]}")

    # إزالة التكرار
    unique, seen_ids = [], set()
    for u in all_utts:
        if u["id"] in seen_ids:
            continue
        seen_ids.add(u["id"])
        unique.append(u)

    if beit_only:
        # نقبل اللي فيه كلمة بيت الوطن، أو اللي سياقه (الفيديو/القناة) عنه
        filtered = []
        for u in unique:
            if _matches_beit(u["text"]) or _matches_beit(u.get("context", "")) \
                    or _matches_beit(u.get("parent", "")):
                filtered.append(u)
        print(f"    → {len(filtered)} من {len(unique)} تخص بيت الوطن")
        unique = filtered

    unique.sort(key=lambda u: u.get("published", ""), reverse=True)
    return unique[:config.INTEL_MAX_UTTERANCES]
