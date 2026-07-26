# -*- coding: utf-8 -*-
"""
مراقبة المصادر الرسمية — أهم طبقة في النظام
============================================
بيحفظ بصمة كل صفحة رسمية، ولو اتغيرت بيقارن ويطلع الجديد بالظبط.
ده اللي بيخليك تعرف قبل الجرايد بساعات.
"""

import os
import re
import json
import hashlib
from datetime import datetime, timezone

import requests

import config

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0 Safari/537.36")


# ============================================================
#  استخراج نص الصفحة
# ============================================================

def page_text(url, timeout=40):
    """يجيب نص الصفحة بدون HTML."""
    try:
        r = requests.get(url, headers={"User-Agent": UA,
                                       "Accept-Language": "ar,en;q=0.8"},
                         timeout=timeout)
        r.raise_for_status()
    except Exception as exc:
        return None, f"تعذّر الوصول: {str(exc)[:90]}"

    html_txt = r.text
    # إزالة السكربتات والاستايلات
    html_txt = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", html_txt)
    # تحويل الوسوم لمسافات
    text = re.sub(r"(?s)<[^>]+>", "\n", html_txt)
    # فك الكيانات الشائعة
    for a, b in [("&nbsp;", " "), ("&amp;", "&"), ("&quot;", '"'),
                 ("&#39;", "'"), ("&lt;", "<"), ("&gt;", ">")]:
        text = text.replace(a, b)

    lines = [ln.strip() for ln in text.split("\n")]
    lines = [ln for ln in lines if len(ln) > 2]
    return lines, None


def _fingerprint(lines):
    joined = "\n".join(lines)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


# ============================================================
#  الحالة المحفوظة
# ============================================================

def load_state():
    if os.path.exists(config.WATCH_STATE):
        try:
            with open(config.WATCH_STATE, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_state(state):
    with open(config.WATCH_STATE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=1)


# ============================================================
#  الفحص
# ============================================================

def _is_urgent(new_lines):
    hits = []
    blob = " ".join(new_lines)
    for kw in config.URGENT_KEYWORDS:
        if kw in blob:
            hits.append(kw)
    return hits


def check_all(verbose=True):
    """
    يفحص كل الصفحات المراقَبة.
    بيرجع قائمة بالتغييرات المكتشفة.
    """
    state = load_state()
    changes = []

    for page in config.WATCH_PAGES:
        name, url = page["name"], page["url"]
        if verbose:
            print(f"    - {name}")

        lines, err = page_text(url)
        if err:
            if verbose:
                print(f"      ({err})")
            continue

        fp = _fingerprint(lines)
        prev = state.get(url) or {}

        if not prev:
            # أول مرة — نسجل البصمة بس من غير تنبيه
            state[url] = {"fp": fp, "lines": lines[:600],
                          "checked": datetime.now(timezone.utc).isoformat()}
            if verbose:
                print("      (تسجيل أولي — لا تنبيه)")
            continue

        if prev.get("fp") == fp:
            state[url]["checked"] = datetime.now(timezone.utc).isoformat()
            continue

        # اتغيرت — نطلع السطور الجديدة
        old_set = set(prev.get("lines") or [])
        added = [ln for ln in lines if ln not in old_set]
        # تجاهل الضوضاء (تواريخ وعدادات)
        added = [ln for ln in added if len(ln) > 12][:40]

        urgent_hits = _is_urgent(added)
        change = {
            "name": name,
            "url": url,
            "added": added,
            "urgent": bool(urgent_hits) or page.get("tier") == "urgent" and bool(added),
            "keywords": urgent_hits,
            "when": datetime.now(timezone.utc).isoformat(),
        }

        if added:
            changes.append(change)
            if verbose:
                mark = "🔴" if change["urgent"] else "•"
                print(f"      {mark} تغيير مرصود — {len(added)} سطر جديد")
                if urgent_hits:
                    print(f"        كلمات مفتاحية: {', '.join(urgent_hits[:5])}")

        state[url] = {"fp": fp, "lines": lines[:600],
                      "checked": datetime.now(timezone.utc).isoformat()}

    save_state(state)
    return changes


def changes_to_items(changes):
    """يحوّل التغييرات لعناصر تظهر في الفيد."""
    items = []
    for ch in changes:
        preview = " · ".join(ch["added"][:3])[:300]
        items.append({
            "title": f"تغيير في {ch['name']}",
            "link": ch["url"],
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
    head = "🚨 <b>تنبيه عاجل — مصدر رسمي</b>" if change["urgent"] \
        else "🏛️ <b>تحديث — مصدر رسمي</b>"
    lines = [head, "", f"<b>{change['name']}</b>"]
    if change["keywords"]:
        lines.append(f"<i>كلمات مرصودة: {', '.join(change['keywords'][:6])}</i>")
    lines.append("")
    for ln in change["added"][:8]:
        lines.append(f"• {ln[:200]}")
    lines += ["", f'<a href="{change["url"]}">افتح الصفحة ←</a>']
    return "\n".join(lines)
