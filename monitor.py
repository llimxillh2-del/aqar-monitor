#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
مرصد العقارات المصرية — المشغّل الأساسي
========================================

أوضاع التشغيل:
    python monitor.py --once      دورة كاملة واحدة ثم خروج  (GitHub Actions)
    python monitor.py --watch     فحص المصادر الرسمية فقط — سريع ورخيص
    python monitor.py --daemon    تشغيل مستمر: رصد لحظي + دورة كاملة كل N ساعة
    python monitor.py --test      دورة كاملة بدون إرسال تليجرام وبدون AI

خيارات:
    --no-telegram    ما يبعتش رسائل
    --no-ai          يتخطى كل تحليل AI (للاختبار السريع)
    --force          يتجاهل seen.json ويعيد معالجة كل حاجة
"""

import os
import sys
import json
import time
import signal
import argparse
import traceback
from datetime import datetime, timezone

import config
import sources
import watcher
import market_state
import beit_alwatan
import human_sources
import intel
import render
from ai_engine import (MultiAI, summarize_video, triage, analyze_comments,
                       predict_and_advise, analyze_news_batch,
                       write_executive_brief)

try:
    import requests
except ImportError:                                        # pragma: no cover
    print("!! المكتبات ناقصة. شغّل: pip install -r requirements.txt")
    sys.exit(1)


_STOP = False
OFFICIAL_SECTION = "🏛️ المصادر الرسمية"


def _handle_stop(signum, frame):
    global _STOP
    _STOP = True
    print("\n[i] جاري الإيقاف بأمان...")


# ============================================================
#  أدوات ملفات
# ============================================================

def _ensure_dirs():
    for path in (config.SEEN_FILE, config.SUMMARY_CACHE, config.WATCH_STATE,
                 config.MARKET_STATE, config.BEIT_STATE):
        d = os.path.dirname(path)
        if d:
            os.makedirs(d, exist_ok=True)


def load_json(path, default):
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception as exc:
            print(f"[!] تعذّر قراءة {path}: {str(exc)[:80]}")
    return default


def save_json(path, data):
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def write_text(path, text):
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


# ============================================================
#  تليجرام
# ============================================================

_TG_SPLIT_LIMIT = 3600


def _split_message(text, limit=_TG_SPLIT_LIMIT):
    """
    تقسيم آمن: بيقطع عند نهاية سطر، ومابيقطعش وسم HTML في النص.
    (النسخة القديمة كانت بتقطع كل 3800 حرف بشكل أعمى فبتكسر الوسوم
     وتليجرام يرفض الرسالة بـ 400.)
    """
    text = text or ""
    if len(text) <= limit:
        return [text] if text.strip() else []

    chunks, current = [], ""
    for line in text.split("\n"):
        while len(line) > limit:                       # سطر واحد طويل جدًا
            cut = line.rfind(" ", 0, limit)
            if cut <= 0:                               # مفيش مسافة نقطع عندها
                cut = limit
            chunks.append(line[:cut])
            line = line[cut:].lstrip()
        if len(current) + len(line) + 1 > limit:
            if current.strip():
                chunks.append(current.rstrip())
            current = line
        else:
            current = f"{current}\n{line}" if current else line
    if current.strip():
        chunks.append(current.rstrip())
    return chunks


def telegram(text, preview=False, silent=False):
    """يبعت رسالة (أو أكتر) ويتأكد إن تليجرام قبلها."""
    if not config.SEND_TELEGRAM:
        return False
    if not (config.TELEGRAM_TOKEN and config.TELEGRAM_CHAT_ID):
        print("[i] تليجرام غير مضبوط — تم تخطي الإرسال.")
        return False

    url = f"https://api.telegram.org/bot{config.TELEGRAM_TOKEN}/sendMessage"
    ok_all = True

    for chunk in _split_message(text):
        payload = {
            "chat_id": config.TELEGRAM_CHAT_ID,
            "text": chunk,
            "parse_mode": "HTML",
            "disable_web_page_preview": "false" if preview else "true",
            "disable_notification": "true" if silent else "false",
        }
        try:
            r = sources.session().post(url, data=payload, timeout=30)
            body = r.json() if r.content else {}
            if not body.get("ok"):
                desc = str(body.get("description", ""))[:110]
                print(f"[!] تليجرام رفض الرسالة: {desc}")
                # محاولة أخيرة كنص عادي بدون HTML
                payload.pop("parse_mode", None)
                payload["text"] = _strip_tags(chunk)
                r2 = sources.session().post(url, data=payload, timeout=30)
                if not (r2.json() or {}).get("ok"):
                    ok_all = False
        except Exception as exc:
            print(f"[!] فشل الإرسال: {str(exc)[:90]}")
            ok_all = False
        time.sleep(0.7)
    return ok_all


def _strip_tags(text):
    import re as _re
    import html as _html
    return _html.unescape(_re.sub(r"<[^>]+>", "", text or ""))


# ============================================================
#  طبقة 1 — الرصد اللحظي للمصادر الرسمية
# ============================================================

def watch_cycle(verbose=True, notify=True):
    """فحص المصادر الرسمية فقط. رخيص وسريع — ينفع يتكرر كل ثواني."""
    if verbose:
        print("[*] فحص المصادر الرسمية")
    changes = watcher.check_all(verbose=verbose)

    if changes and notify:
        for ch in changes:
            telegram(watcher.format_alert(ch), preview=False,
                     silent=not ch["urgent"])
            print(f"    ↗ تنبيه مُرسل: {ch['name']}")
    return changes


# ============================================================
#  طبقة 2 — الدورة الكاملة
# ============================================================

def full_cycle(ai, use_ai=True, notify=True, force=False):
    started = time.time()
    print("\n" + "=" * 62)
    print(f"  دورة كاملة — {render.stamp()}")
    print("=" * 62)

    _ensure_dirs()
    seen = set(load_json(config.SEEN_FILE, []))
    summaries = load_json(config.SUMMARY_CACHE, {})

    # ---------- 1) المصادر الرسمية ----------
    official_changes = watch_cycle(verbose=True, notify=notify)
    official_items = watcher.changes_to_items(official_changes)
    official_lines = [ln for ch in official_changes for ln in ch["added"][:12]]

    # ---------- 2) الأخبار ----------
    beit_queries = config.BEIT_ALWATAN["queries"]
    sections = sources.fetch_news(extra_queries=beit_queries)

    extra = sources.fetch_extra_rss()
    if extra:
        first = next(iter(sections))
        sections[first] = extra + sections[first]

    social = sources.fetch_social()
    if social:
        sections.setdefault("سوشيال ميديا", []).extend(social)

    # ---------- 3) الفيديوهات ----------
    videos = sources.fetch_videos(
        extra_queries=config.BEIT_ALWATAN["youtube_queries"])
    if videos:
        sections["فيديوهات وتحليلات"] = videos

    if official_items:
        sections = {OFFICIAL_SECTION: official_items, **sections}

    # ---------- 4) الجديد ----------
    all_items = [it for items in sections.values() for it in items]
    new_items = [it for it in all_items if force or it["link"] not in seen]
    new_links = {it["link"] for it in new_items}
    print(f"\n[*] {len(all_items)} عنصر · {len(new_items)} جديد")

    top_links, urgent_links = set(), set()
    brief = forecast = None
    comment_insights = []
    video_summaries = []

    # ---------- 5) الفرز السريع ----------
    if use_ai and ai.available and new_items:
        print("[*] فرز سريع")
        levels = triage(ai, new_items[:60])
        for link, lv in levels.items():
            if lv == "urgent":
                urgent_links.add(link)
            elif lv == "important":
                top_links.add(link)
        print(f"    → {len(urgent_links)} عاجل · {len(top_links)} مهم")

    for ch in official_changes:
        if ch["urgent"]:
            urgent_links.add(ch["url"])

    # ---------- 6) تلخيص الفيديوهات ----------
    if use_ai and ai.available and videos:
        print("[*] تلخيص الفيديوهات")
        done = 0
        for vid in videos:
            if done >= config.MAX_VIDEOS_TO_SUMMARIZE:
                break
            vid_id = vid.get("video_id")
            if not vid_id:
                continue
            if vid["link"] not in new_links and vid_id not in summaries:
                continue

            if vid_id in summaries:
                vid["ai_summary"] = summaries[vid_id]
            else:
                print(f"    - {vid['title'][:58]}")
                transcript = sources.get_transcript(vid_id)
                if not transcript:
                    continue
                summary = summarize_video(ai, vid["title"], transcript)
                if not summary:
                    continue
                summaries[vid_id] = summary
                vid["ai_summary"] = summary
                done += 1

            video_summaries.append((vid["title"], vid["ai_summary"]))

            # كومنتات
            comments = sources.get_top_comments(vid_id)
            if comments:
                vid["top_comments"] = comments[:config.TOP_COMMENTS_TO_SHOW]
                vid["_all_comments"] = comments
                analysis = analyze_comments(ai, vid["title"], comments)
                if analysis:
                    vid["comment_analysis"] = analysis
                    comment_insights.append(analysis)

        save_json(config.SUMMARY_CACHE, summaries)

    # ---------- 7) التحليل العام ----------
    analyze_pool = [it for it in all_items
                    if it.get("kind") in ("news", "official")][:config.MAX_ARTICLES_TO_ANALYZE]

    if use_ai and ai.available and analyze_pool:
        print("[*] تصنيف الأخبار")
        verdict = analyze_news_batch(ai, analyze_pool)
        if isinstance(verdict, dict):
            for idx in (verdict.get("top") or []):
                try:
                    top_links.add(analyze_pool[int(idx) - 1]["link"])
                except (ValueError, TypeError, IndexError):
                    continue
            for idx in (verdict.get("urgent") or []):
                try:
                    urgent_links.add(analyze_pool[int(idx) - 1]["link"])
                except (ValueError, TypeError, IndexError):
                    continue

        print("[*] كتابة الملخص التنفيذي")
        brief = write_executive_brief(ai, analyze_pool, video_summaries)

        print("[*] الاستشراف")
        forecast = predict_and_advise(ai, analyze_pool, video_summaries,
                                      comment_insights)

    # ---------- 8) ذاكرة السوق ----------
    mstate = market_state.load()
    market_changes = []
    if use_ai and ai.available and analyze_pool:
        print("[*] تحديث ذاكرة السوق")
        facts = market_state.extract_facts(ai, analyze_pool)
        market_changes = market_state.diff_and_update(mstate, facts)
        market_state.save(mstate)
        if market_changes:
            print(f"    → {len(market_changes)} تغيير")
    market_rows = market_state.summary_rows(mstate)

    # ---------- 9) ملف بيت الوطن ----------
    beit_state = beit_alwatan.load()
    beit_items = beit_alwatan.filter_items(all_items)
    beit_changes = []
    print(f"\n[*] بيت الوطن — {len(beit_items)} عنصر مطابق")

    if beit_items:
        if use_ai and ai.available:
            print("    - استخراج الحقائق")
            beit_vids = [(t, s) for t, s in video_summaries
                         if any(w in t for w in config.BEIT_ALWATAN["match_words"])]
            facts = beit_alwatan.extract(ai, beit_items, beit_vids or video_summaries,
                                         official_lines)
            beit_changes = beit_alwatan.diff_and_update(beit_state, facts, beit_items)
            if beit_changes:
                print(f"    → {len(beit_changes)} تغيير مرصود")

            # كلام الناس — من كل الكومنتات المتعلقة
            beit_comments = []
            for vid in videos:
                if any(w in vid["title"] for w in config.BEIT_ALWATAN["match_words"]):
                    beit_comments.extend(vid.get("_all_comments") or [])
            if not beit_comments:
                for vid in videos:
                    beit_comments.extend(vid.get("_all_comments") or [])
            if beit_comments:
                print("    - تحليل كلام الناس")
                beit_state["people"] = beit_alwatan.people_pulse(ai, beit_comments)

            print("    - الملخص والتوقعات والخطوات")
            beit_state["summary"] = beit_alwatan.summarize(ai, beit_state, beit_items)
            beit_state["forecast"] = beit_alwatan.forecast(
                ai, beit_state, beit_items, beit_state.get("people"))
            beit_state["checklist"] = beit_alwatan.checklist(ai, beit_state)
        else:
            beit_alwatan.diff_and_update(beit_state, {}, beit_items)

        beit_alwatan.save(beit_state)

    beit_view = beit_alwatan.dashboard(beit_state)

    # ---------- 9-ب) رادار الإشارات المبكرة ----------
    intel_view = None
    intel_msgs = []
    if config.INTEL_ENABLED:
        print("\n[*] رادار الإشارات المبكرة")
        try:
            vid_ids, vid_titles = [], {}
            for v in videos:
                if v.get("video_id"):
                    vid_ids.append(v["video_id"])
                    vid_titles[v["video_id"]] = v.get("title", "")
            # الفيديوهات اللي عن بيت الوطن الأول
            vid_ids.sort(key=lambda i: 0 if any(
                w in vid_titles.get(i, "")
                for w in config.BEIT_ALWATAN["match_words"]) else 1)

            utts = human_sources.harvest(vid_ids, vid_titles)

            istate, fresh, strengthened, confirmed = intel.run(
                ai, utts, analyze_pool, official_lines,
                beit_state.get("facts"), use_ai=use_ai)

            intel_view = intel.board(istate)
            intel_msgs = intel.alerts(fresh, strengthened, confirmed)
        except Exception as exc:
            print(f"    ! الرادار فشل: {str(exc)[:100]}")
            traceback.print_exc(limit=2)
            try:
                intel_view = intel.board(intel.load())
            except Exception:
                intel_view = None

    # ---------- 10) الصفحات ----------
    print("\n[*] توليد الصفحات")
    health = watcher.health()
    engines = "محركات التحليل — " + (ai.report() if use_ai else "معطّل (--no-ai)")

    write_text(config.OUTPUT_HTML, render.build_index(
        sections, brief, new_links, top_links, urgent_links, engines,
        forecast=forecast, market_rows=market_rows, health_rows=health,
        beit=beit_view, official_changes=official_changes,
        intel=intel_view))
    print(f"    ✓ {config.OUTPUT_HTML}")

    write_text(config.BEIT_HTML,
               render.build_beit_page(beit_view, engines, intel=intel_view))
    print(f"    ✓ {config.BEIT_HTML}")

    # ---------- 11) latest.json (للبوت) ----------
    def _slim(items):
        return [{"title": i["title"], "link": i["link"],
                 "source": i.get("source", "")} for i in items]

    save_json(config.LATEST_JSON, {
        "updated": datetime.now(timezone.utc).isoformat(),
        "brief": brief,
        "forecast": forecast,
        "market": market_rows,
        "beit": {
            "stage": beit_view.get("stage"),
            "booking": beit_view.get("booking"),
            "price": beit_view.get("price"),
            "areas": beit_view.get("areas"),
            "deposit": beit_view.get("deposit"),
            "conditions": beit_view.get("conditions"),
            "payment": beit_view.get("payment"),
            "last": beit_view.get("last"),
            "confidence": beit_view.get("confidence"),
            "dates": beit_view.get("dates"),
            "next": beit_view.get("next"),
            "cities": beit_view.get("cities"),
            "summary": beit_view.get("summary"),
            "people": beit_view.get("people"),
            "forecast": beit_view.get("forecast"),
            "checklist": beit_view.get("checklist"),
            "timeline": (beit_view.get("timeline") or [])[:15],
        },
        "intel": {
            "counts": (intel_view or {}).get("counts", {}),
            "stats": (intel_view or {}).get("stats", {}),
            "digest": (intel_view or {}).get("digest"),
            "signals": [
                {k: s.get(k) for k in
                 ("statement", "type", "tier", "status", "novel", "mentions",
                  "independence", "firsthand", "weight", "lead_days",
                  "first_seen", "total_likes")}
                | {"sources": [{"channel": x.get("channel"),
                                "author": x.get("author"),
                                "url": x.get("url"),
                                "quote": x.get("quote", "")[:200],
                                "firsthand": x.get("firsthand")}
                               for x in (s.get("sources") or [])[:4]]}
                for s in ((intel_view or {}).get("signals") or [])[:30]
            ],
            "questions": (intel_view or {}).get("questions", [])[:15],
        } if intel_view else {},
        "urgent": _slim([i for i in all_items if i["link"] in urgent_links])[:15],
        "top": _slim([i for i in all_items if i["link"] in top_links])[:15],
        "counts": {"total": len(all_items), "new": len(new_items),
                   "beit": len(beit_items)},
    })

    # ---------- 12) تليجرام ----------
    if notify:
        if beit_changes:
            telegram(beit_alwatan.format_changes(beit_changes))
        if market_changes:
            telegram(market_state.format_changes(market_changes))
        for msg in intel_msgs:
            telegram(msg, preview=False)
        if intel_msgs:
            print(f"[*] {len(intel_msgs)} تنبيه إشارة مُرسل")

        new_by_section = {
            name: [it for it in items if it["link"] in new_links]
            for name, items in sections.items()
        }
        if any(new_by_section.values()):
            telegram(render.build_telegram(new_by_section, brief, urgent_links,
                                           beit_view))
            print("[*] رسالة تليجرام مُرسلة")
        else:
            print("[i] مفيش جديد — مفيش رسالة")

    # ---------- 13) حفظ المشاهَد ----------
    seen.update(it["link"] for it in all_items)
    save_json(config.SEEN_FILE, sorted(seen)[-4000:])

    took = int(time.time() - started)
    print(f"\n[✓] تمت الدورة في {took // 60}د {took % 60}ث — {engines}")
    return {"total": len(all_items), "new": len(new_items),
            "urgent": len(urgent_links), "beit_changes": len(beit_changes)}


# ============================================================
#  الأوضاع
# ============================================================

def run_daemon(ai, use_ai=True, notify=True):
    """رصد لحظي مستمر + دورة كاملة كل INTERVAL_HOURS."""
    interval = max(config.WATCH_INTERVAL_SECONDS, 20)
    full_every = config.INTERVAL_HOURS * 3600

    print(f"[+] وضع الرصد المستمر")
    print(f"    المصادر الرسمية: كل {interval} ثانية")
    print(f"    الدورة الكاملة:  كل {config.INTERVAL_HOURS} ساعة")
    print("    Ctrl+C للإيقاف\n")

    last_full = 0.0
    while not _STOP:
        cycle_start = time.time()
        try:
            if cycle_start - last_full >= full_every:
                full_cycle(ai, use_ai=use_ai, notify=notify)
                last_full = time.time()
            else:
                changes = watch_cycle(verbose=False, notify=notify)
                mark = f"  🔴 {len(changes)} تغيير" if changes else ""
                print(f"\r[{render.cairo_now():%H:%M:%S}] فحص رسمي{mark}",
                      end="", flush=True)
                if changes:
                    print()
        except Exception:
            print("\n[!] خطأ في الدورة:")
            traceback.print_exc(limit=3)

        slept = 0
        while slept < interval and not _STOP:
            time.sleep(1)
            slept += 1

    print("\n[i] تم الإيقاف.")


def main():
    parser = argparse.ArgumentParser(
        description="مرصد العقارات المصرية للمصريين بالخارج")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--once", action="store_true", help="دورة كاملة واحدة")
    mode.add_argument("--watch", action="store_true", help="المصادر الرسمية فقط")
    mode.add_argument("--daemon", action="store_true", help="تشغيل مستمر")
    mode.add_argument("--test", action="store_true",
                      help="دورة بدون AI وبدون تليجرام")
    mode.add_argument("--sources", action="store_true",
                      help="تشخيص كل المصادر — مين شغال ومين لأ وليه")
    parser.add_argument("--no-telegram", action="store_true")
    parser.add_argument("--no-ai", action="store_true")
    parser.add_argument("--force", action="store_true",
                       help="يتجاهل seen.json ويعيد كل حاجة")
    args = parser.parse_args()

    signal.signal(signal.SIGINT, _handle_stop)
    try:
        signal.signal(signal.SIGTERM, _handle_stop)
    except (AttributeError, ValueError):
        pass

    _ensure_dirs()

    if args.sources:
        import diagnose
        diagnose.run()
        return

    use_ai = not (args.no_ai or args.test)
    notify = not (args.no_telegram or args.test)
    if not config.SEND_TELEGRAM:
        notify = False

    ai = MultiAI(verbose=config.VERBOSE)
    if use_ai:
        if ai.available:
            print(f"[+] محركات AI: {', '.join(ai.names)}")
        else:
            print("[!] مفيش أي مفتاح AI — التحليل هيتخطى.")
            print("    ضيف GROQ_API_KEY أو GEMINI_API_KEY (مجانيين).")

    if args.watch:
        changes = watch_cycle(verbose=True, notify=notify)
        print(f"[✓] {len(changes)} تغيير مرصود")
        return

    if args.daemon:
        run_daemon(ai, use_ai=use_ai, notify=notify)
        return

    # --once / --test / بدون خيارات
    full_cycle(ai, use_ai=use_ai, notify=notify, force=args.force)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[i] تم الإيقاف.")
    except Exception:
        traceback.print_exc()
        sys.exit(1)
