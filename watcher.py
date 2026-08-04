# -*- coding: utf-8 -*-
"""
مراقبة المصادر الرسمية — أهم طبقة في النظام
============================================
بيحفظ بصمة كل صفحة رسمية، ولو اتغيرت بيقارن ويطلع الجديد بالظبط.
ده اللي بيخليك تعرف قبل الجرايد.

إصلاحات جوهرية عن النسخة القديمة:
  1. كانت بتحفظ أول 600 سطر بس وتقارن بيهم الصفحة كلها → أي صفحة أطول
     من كده كانت بتبعت "سطور جديدة" كل دورة للأبد. دلوقتي بنحفظ بصمة
     مختصرة (hash) لكل سطر — الملف يفضل صغير والمقارنة كاملة.
  2. الترميز: مواقع مصرية كتير مابتبعتش charset فـ requests كان بيخمّن غلط
     ويطلع نص مشوّه → بصمة مختلفة كل مرة. دلوقتي بنضبط الترميز يدويًا.
  3. الإنذار الأحمر كان بيشتغل على أي تغيير في صفحة urgent (حتى عدّاد زوار).
     دلوقتي لازم كلمة مفتاحية أو سطر ذو معنى بعد تنقية الضوضاء.
  4. تنقية الضوضاء: تواريخ وأرقام وسطور تنقّل مش تغييرات.
"""

import os
import re
import json
import html
import hashlib
from datetime import datetime, timezone

import config
from sources import session

UA_FALLBACK_ENCODINGS = ("utf-8", "windows-1256", "iso-8859-6")

_NOISE_RE = [re.compile(p) for p in config.WATCH_NOISE_PATTERNS]


# ============================================================
#  استخراج نص الصفحة
# ============================================================

def _decode(resp):
    """يفك ترميز الصفحة صح حتى لو السيرفر مابعتش charset."""
    raw = resp.content
    declared = None

    m = re.search(rb'charset=["\']?\s*([\w\-]+)', raw[:4096], re.I)
    if m:
        declared = m.group(1).decode("ascii", "ignore").lower()

    candidates = []
    if declared:
        candidates.append(declared)
    if resp.encoding and resp.encoding.lower() != "iso-8859-1":
        candidates.append(resp.encoding.lower())
    candidates.extend(UA_FALLBACK_ENCODINGS)

    for enc in candidates:
        try:
            text = raw.decode(enc)
        except (LookupError, UnicodeDecodeError):
            continue
        # فحص سلامة: لو فيه عربي مقروء أو مفيش رموز بديلة كتير
        if text.count("�") < len(text) * 0.01:
            return text
    return raw.decode("utf-8", "replace")


def _is_noise(line):
    if len(line) < config.WATCH_MIN_LINE_LEN:
        return True
    for rx in _NOISE_RE:
        if rx.search(line):
            return True
    return False


def page_text(url, timeout=None):
    """يجيب سطور الصفحة النصية بدون HTML. يرجّع (lines, error)."""
    timeout = timeout or config.REQUEST_TIMEOUT
    try:
        r = session().get(url, timeout=timeout)
        r.raise_for_status()
    except Exception as exc:
        return None, f"تعذّر الوصول: {str(exc)[:100]}"

    doc = _decode(r)
    doc = re.sub(r"(?is)<(script|style|noscript|svg)[^>]*>.*?</\1>", " ", doc)
    doc = re.sub(r"(?is)<!--.*?-->", " ", doc)
    text = re.sub(r"(?s)<[^>]+>", "\n", doc)
    text = html.unescape(text)

    lines, seen = [], set()
    for raw_line in text.split("\n"):
        line = re.sub(r"\s+", " ", raw_line).strip()
        if not line or line in seen:
            continue
        seen.add(line)
        lines.append(line)
    return lines, None


def _h(line):
    """بصمة مختصرة للسطر — 10 حروف كفاية وبتخلي الملف صغير."""
    return hashlib.sha1(line.encode("utf-8")).hexdigest()[:10]


def _fingerprint(lines):
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


# ============================================================
#  الحالة المحفوظة
# ============================================================

def load_state():
    path = config.WATCH_STATE
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_state(state):
    path = config.WATCH_STATE
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


# ============================================================
#  الفحص
# ============================================================

def _keyword_hits(lines):
    blob = " ".join(lines)
    return [kw for kw in config.URGENT_KEYWORDS if kw in blob]


def check_all(verbose=True, pages=None):
    """
    يفحص كل الصفحات المراقَبة ويرجع قائمة بالتغييرات الحقيقية.
    """
    state = load_state()
    changes = []
    now = datetime.now(timezone.utc).isoformat()

    for page in (pages or config.WATCH_PAGES):
        name, url = page["name"], page["url"]
        if page.get("skip_diff"):
            # صفحة بتتغير أرقامها الطبيعي (عدادات، لوحات حية) — رصد التغيير
            # النصي عليها هيغرقنا بتنبيهات كاذبة. نتجاهلها هنا تمامًا؛
            # بياناتها بتتجاب بطريقة تانية (مثلاً bit_mzayasoft.py).
            continue
        if verbose:
            print(f"    - {name}")

        lines, err = page_text(url)
        if err:
            prev = state.get(url) or {}
            prev["last_error"] = err
            prev["checked"] = now
            prev["fail_count"] = int(prev.get("fail_count", 0)) + 1
            state[url] = prev
            if verbose:
                print(f"      ⚠ {err}")
            continue

        meaningful = [ln for ln in lines if not _is_noise(ln)]
        hashes = [_h(ln) for ln in meaningful]
        fp = _fingerprint(meaningful)
        prev = state.get(url) or {}

        record = {
            "fp": fp,
            "hashes": hashes,
            "sample": meaningful[:40],
            "count": len(meaningful),
            "checked": now,
            "fail_count": 0,
        }

        # أول مرة → تسجيل بدون تنبيه
        if not prev.get("hashes"):
            state[url] = record
            if verbose:
                note = " (صفحة جافاسكريبت — الرصد محدود)" if page.get("js") else ""
                print(f"      تسجيل أولي: {len(meaningful)} سطر{note}")
            continue

        if prev.get("fp") == fp:
            prev.update({"checked": now, "fail_count": 0})
            state[url] = prev
            continue

        # اتغيرت — نطلع السطور الجديدة فعلًا (مقارنة كاملة، مش أول 600)
        old_hashes = set(prev.get("hashes") or [])
        added = [ln for ln in meaningful if _h(ln) not in old_hashes][:40]
        removed_count = len(old_hashes - set(hashes))

        state[url] = record

        if not added:
            # الصفحة اتغيرت بس مفيش محتوى جديد (حاجة اتشالت مثلًا)
            if verbose and removed_count:
                print(f"      · {removed_count} سطر اتشال، مفيش جديد")
            continue

        hits = _keyword_hits(added)
        # 🔴 أحمر فقط لو: كلمة مفتاحية، أو صفحة urgent فيها محتوى جديد ذو وزن
        is_urgent = bool(hits) or (
            page.get("tier") == "urgent" and len(added) >= 2
        )

        change = {
            "name": name,
            "url": url,
            "added": added,
            "removed_count": removed_count,
            "urgent": is_urgent,
            "keywords": hits,
            "when": now,
        }
        changes.append(change)

        if verbose:
            mark = "🔴" if is_urgent else "•"
            print(f"      {mark} تغيير مرصود — {len(added)} سطر جديد")
            if hits:
                print(f"        كلمات: {', '.join(hits[:5])}")

    save_state(state)
    return changes


def health(state=None):
    """حالة كل مصدر رسمي — بتظهر في الصفحة عشان تعرف مين شغال ومين لأ."""
    state = state if state is not None else load_state()
    rows = []
    for page in config.WATCH_PAGES:
        if page.get("skip_diff"):
            continue
        rec = state.get(page["url"]) or {}
        fails = int(rec.get("fail_count", 0))
        if fails >= 3:
            status = "متعذّر"          # فشل متكرر = واقع فعلًا مش «متقطع»
        elif rec.get("count") and fails == 0:
            status = "يعمل"
        elif rec.get("count"):
            status = "متقطع"
        elif rec.get("last_error"):
            status = "متعذّر"
        else:
            status = "لم يُفحص"
        rows.append({
            "name": page["name"],
            "url": page["url"],
            "status": status,
            "lines": rec.get("count", 0),
            "checked": rec.get("checked", ""),
            "error": rec.get("last_error", ""),
            "js": bool(page.get("js")),
            "tier": page.get("tier", "normal"),
        })
    return rows


def changes_to_items(changes):
    """يحوّل التغييرات لعناصر تظهر في الفيد."""
    items = []
    for ch in changes:
        preview = " · ".join(ch["added"][:3])[:320]
        # بصمة المحتوى الجديد في الرابط — من غيرها كل التغييرات على نفس
        # الصفحة بتاخد نفس الـ link، فأول واحد بس بيتحسب «جديد» والباقي
        # بيتفلتر للأبد لأنه موجود في seen.json.
        stamp = hashlib.sha1(
            "|".join(ch["added"][:8]).encode("utf-8")).hexdigest()[:10]
        items.append({
            "title": f"تغيير في {ch['name']}",
            "link": f"{ch['url']}#chg-{stamp}",
            "source_url": ch["url"],
            "source": "🏛️ مصدر رسمي",
            "snippet": preview,
            "published": ch["when"],
            "published_ts": datetime.now(timezone.utc).timestamp(),
            "kind": "official",
            "official_change": ch,
        })
    return items


def format_alert(change):
    """رسالة تليجرام فورية لتغيير رسمي."""
    head = ("🚨 <b>تنبيه عاجل — مصدر رسمي</b>" if change["urgent"]
            else "🏛️ <b>تحديث — مصدر رسمي</b>")
    lines = [head, "", f"<b>{html.escape(change['name'])}</b>"]
    if change.get("keywords"):
        kws = html.escape("، ".join(change["keywords"][:6]))
        lines.append(f"<i>كلمات مرصودة: {kws}</i>")
    lines.append("")
    for ln in change["added"][:8]:
        lines.append(f"• {html.escape(ln[:220])}")
    if len(change["added"]) > 8:
        lines.append(f"<i>… و{len(change['added']) - 8} سطر آخر</i>")
    lines += ["", f'<a href="{html.escape(change["url"])}">افتح الصفحة ←</a>']
    return "\n".join(lines)
