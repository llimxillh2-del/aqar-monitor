#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
مرصد العقارات المصرية للمغتربين — النسخة الكاملة
=================================================
يجمع من: Google News · يوتيوب (بنص الفيديو) · RSSHub للسوشيال · أي RSS
يحلل بـ: Gemini / Groq / Cerebras / OpenRouter (تبديل تلقائي عند الفشل)
يخرج: صفحة index.html + رسالة تليجرام بالجديد فقط

التشغيل:
    python monitor.py --once     # مرة واحدة (للـ cron و GitHub Actions)
    python monitor.py            # يفضل شغال ويكرر كل 4 ساعات
"""

import os
import sys
import json
import time
from datetime import datetime

import requests

import config
import sources
import render
import watcher
import market_state
from ai_engine import (MultiAI, summarize_video, analyze_news_batch,
                       write_executive_brief, analyze_comments,
                       predict_and_advise, triage)


# ============================================================
#  الذاكرة
# ============================================================

def load_seen():
    if os.path.exists(config.SEEN_FILE):
        try:
            with open(config.SEEN_FILE, encoding="utf-8") as f:
                return set(json.load(f))
        except Exception:
            pass
    return set()


def save_seen(seen):
    with open(config.SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(seen), f, ensure_ascii=False, indent=1)


def load_summaries():
    """ملخصات الفيديوهات المحفوظة — عشان متتعادش كل دورة."""
    if os.path.exists(config.SUMMARY_CACHE):
        try:
            with open(config.SUMMARY_CACHE, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_summaries(cache):
    # الاحتفاظ بآخر 200 ملخص فقط
    if len(cache) > 200:
        cache = dict(list(cache.items())[-200:])
    with open(config.SUMMARY_CACHE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=1)


# ============================================================
#  تليجرام
# ============================================================

def send_telegram(text):
    if not config.TELEGRAM_TOKEN or not config.TELEGRAM_CHAT_ID:
        print("[!] لا يوجد TELEGRAM_TOKEN/CHAT_ID — تم تخطي الإرسال.")
        return False
    url = f"https://api.telegram.org/bot{config.TELEGRAM_TOKEN}/sendMessage"
    ok = True
    for i in range(0, len(text), 3800):
        try:
            r = requests.post(url, data={
                "chat_id": config.TELEGRAM_CHAT_ID,
                "text": text[i:i + 3800],
                "parse_mode": "HTML",
                "disable_web_page_preview": "true",
            }, timeout=30)
            if r.status_code != 200:
                print(f"[!] تليجرام {r.status_code}: {r.text[:160]}")
                ok = False
            time.sleep(1)
        except Exception as exc:
            print(f"[!] فشل الإرسال: {exc}")
            ok = False
    return ok


# ============================================================
#  الدورة الواحدة
# ============================================================

def run_once():
    print("=" * 58)
    print(f"[+] بدء الدورة — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 58)

    ai = MultiAI()
    if ai.available:
        print(f"[+] محركات AI المتاحة: {', '.join(n for n, _ in ai.providers)}")
    else:
        print("[!] لا يوجد مفتاح AI — سيعمل النظام بدون تلخيص أو تحليل.")

    # ---------- 0) المصادر الرسمية (الأسرع — قبل أي حاجة) ----------
    print("[*] فحص المصادر الرسمية")
    official_changes = watcher.check_all()
    # تنبيه فوري للتغييرات العاجلة — من غير انتظار باقي الدورة
    for ch in official_changes:
        if ch["urgent"]:
            send_telegram(watcher.format_alert(ch))
            print("    🔴 تم إرسال تنبيه عاجل")

    # ---------- 1) الجمع ----------
    sections = {}
    official_items = watcher.changes_to_items(official_changes)
    if official_items:
        sections["تحديثات رسمية"] = official_items

    sections.update(sources.fetch_news())

    videos = sources.fetch_videos()
    if videos:
        sections["فيديوهات وتحليلات"] = videos

    social = sources.fetch_social()
    if social:
        sections["السوشيال ميديا"] = social

    extra = sources.fetch_extra_rss()
    if extra:
        sections.setdefault("مصادر إضافية", []).extend(extra)

    total = sum(len(v) for v in sections.values())
    print(f"[+] إجمالي العناصر المجمّعة: {total}")

    # ---------- 2) تحديد الجديد ----------
    seen = load_seen()
    new_links, new_by_section = set(), {}
    for name, items in sections.items():
        fresh = [i for i in items if i["link"] not in seen]
        new_by_section[name] = fresh
        new_links |= {i["link"] for i in fresh}
    total_new = len(new_links)
    print(f"[+] عناصر جديدة: {total_new}")

    # ---------- 3) الفيديوهات: تلخيص + كومنتات ----------
    video_summaries, comment_insights = [], []
    cache = load_summaries()

    # إعادة استخدام المحفوظ
    for vid in videos:
        saved = cache.get(vid["link"])
        if not saved:
            continue
        if isinstance(saved, str):          # صيغة قديمة
            saved = {"summary": saved}
        if saved.get("summary"):
            vid["ai_summary"] = saved["summary"]
            video_summaries.append((vid["title"], saved["summary"]))
        if saved.get("comments_analysis"):
            vid["comment_analysis"] = saved["comments_analysis"]
            comment_insights.append(saved["comments_analysis"])
        if saved.get("top_comments"):
            vid["top_comments"] = saved["top_comments"]

    if videos:
        print("[*] معالجة الفيديوهات")
        done = 0
        for vid in videos:
            if done >= config.MAX_VIDEOS_TO_SUMMARIZE:
                break
            if vid["link"] in cache or not vid.get("video_id"):
                continue
            print(f"    - {vid['title'][:60]}")
            entry = {}

            # (أ) ملخص من نص الفيديو
            if ai.available:
                transcript = sources.get_transcript(vid["video_id"])
                if transcript:
                    summary = summarize_video(ai, vid["title"], transcript)
                    if summary:
                        vid["ai_summary"] = summary
                        entry["summary"] = summary
                        video_summaries.append((vid["title"], summary))

            # (ب) الكومنتات — أعلاها تفاعلًا + تحليل كلام الناس
            comments = sources.get_top_comments(vid["video_id"])
            if comments:
                top = comments[:config.TOP_COMMENTS_TO_SHOW]
                vid["top_comments"] = top
                entry["top_comments"] = top
                print(f"      ({len(comments)} كومنت — أعلى تفاعل {top[0]['likes']} إعجاب)")
                if ai.available:
                    insight = analyze_comments(ai, vid["title"], comments)
                    if insight:
                        vid["comment_analysis"] = insight
                        entry["comments_analysis"] = insight
                        comment_insights.append(insight)

            if entry:
                cache[vid["link"]] = entry
                done += 1
            time.sleep(2)

        print(f"[+] تمت معالجة {done} فيديو جديد")
        if done:
            save_summaries(cache)

    # ---------- 4) الفرز السريع ثم التصنيف العميق ----------
    top_links, urgent_links = set(), set()

    # (أ) فرز سريع بموديل رخيص — على كل العناصر الجديدة
    all_new = [i for items in sections.values() for i in items
               if i["link"] in new_links]
    levels = {}
    if ai.available and all_new:
        print(f"[*] فرز سريع لـ {len(all_new)} عنصر (موديل سريع)")
        levels = triage(ai, all_new[:60])
        counts = {}
        for lv in levels.values():
            counts[lv] = counts.get(lv, 0) + 1
        if counts:
            print(f"    {counts}")
        for link, lv in levels.items():
            if lv == "urgent":
                urgent_links.add(link)
            elif lv == "important":
                top_links.add(link)

    # (ب) تصنيف عميق بالموديل القوي — على المهم فقط
    news_pool = []
    for name, items in sections.items():
        if name not in ("فيديوهات وتحليلات", "السوشيال ميديا"):
            news_pool.extend(items)
    news_pool = news_pool[:config.MAX_ARTICLES_TO_ANALYZE]

    if ai.available and news_pool:
        print("[*] تصنيف عميق للأخبار")
        verdict = analyze_news_batch(ai, news_pool)
        if verdict:
            for idx in verdict.get("top", []) or []:
                if isinstance(idx, int) and 1 <= idx <= len(news_pool):
                    top_links.add(news_pool[idx - 1]["link"])
            for idx in verdict.get("urgent", []) or []:
                if isinstance(idx, int) and 1 <= idx <= len(news_pool):
                    urgent_links.add(news_pool[idx - 1]["link"])
            themes = verdict.get("themes") or []
            if themes:
                print(f"    مواضيع متكررة: {' | '.join(map(str, themes))}")

    # (ج) تنبيه فوري لأي خبر عاجل جديد
    urgent_new = [i for i in all_new if i["link"] in urgent_links]
    if urgent_new:
        lines = ["⚡ <b>أخبار عاجلة</b>", ""]
        for i in urgent_new[:6]:
            lines.append(f'🔴 <a href="{i["link"]}">{i["title"]}</a>')
            if i.get("source"):
                lines.append(f'  <i>{i["source"]}</i>')
        send_telegram("\n".join(lines))
        print(f"[+] تم إرسال تنبيه بـ {len(urgent_new)} خبر عاجل")

    # ---------- 4.5) ذاكرة السوق ----------
    mstate = market_state.load()
    state_changes = []
    if ai.available and news_pool:
        print("[*] تحديث ذاكرة السوق")
        facts = market_state.extract_facts(ai, news_pool)
        state_changes = market_state.diff_and_update(mstate, facts)
        market_state.save(mstate)
        if state_changes:
            print(f"    {len(state_changes)} تغيير في حالة السوق")
            msg = market_state.format_changes(state_changes)
            if msg:
                send_telegram(msg)
        else:
            print("    لا تغيير في حالة السوق")

    # ---------- 5) الملخص التنفيذي والتوقعات ----------
    brief = forecast = None
    if ai.available and news_pool:
        print("[*] كتابة الملخص التنفيذي")
        brief = write_executive_brief(ai, news_pool, video_summaries)
        print("[*] التوقعات وتحليل الأماكن")
        forecast = predict_and_advise(ai, news_pool, video_summaries, comment_insights)

    # ---------- 6) الإخراج ----------
    engines_note = f"محركات التحليل — {ai.report()}" if ai.available else ""
    page = render.build_page(sections, brief, new_links, top_links,
                             urgent_links, engines_note, forecast=forecast,
                             market_rows=market_state.summary_rows(mstate))
    with open(config.OUTPUT_HTML, "w", encoding="utf-8") as f:
        f.write(page)
    print(f"[+] تم تحديث {config.OUTPUT_HTML}")

    # حفظ نسخة للبوت التفاعلي
    try:
        with open(config.LATEST_JSON, "w", encoding="utf-8") as f:
            json.dump({
                "updated": datetime.now().isoformat(),
                "brief": brief,
                "forecast": forecast,
                "market": market_state.summary_rows(mstate),
                "urgent": [{"title": i["title"], "link": i["link"]}
                           for i in all_new if i["link"] in urgent_links][:10],
                "top": [{"title": i["title"], "link": i["link"],
                         "source": i.get("source", "")}
                        for items in sections.values() for i in items
                        if i["link"] in top_links][:15],
            }, f, ensure_ascii=False, indent=1)
    except Exception as exc:
        print(f"[!] تعذّر حفظ {config.LATEST_JSON}: {exc}")

    if total_new:
        msg = render.build_telegram(new_by_section, brief, urgent_links)
        if send_telegram(msg):
            print("[+] تم الإرسال على تليجرام")
        seen |= new_links
        save_seen(seen)
    else:
        print("[i] لا يوجد جديد — لم تُرسل رسالة.")

    if ai.available:
        print(f"[i] إحصائيات AI: {ai.report()}")


def main():
    once = "--once" in sys.argv
    while True:
        try:
            run_once()
        except KeyboardInterrupt:
            print("\n[i] تم الإيقاف.")
            break
        except Exception as exc:
            print(f"[!] خطأ في الدورة: {exc}")
        if once:
            break
        print(f"\n[i] في انتظار {config.INTERVAL_HOURS} ساعات...\n")
        time.sleep(config.INTERVAL_HOURS * 3600)


if __name__ == "__main__":
    main()
