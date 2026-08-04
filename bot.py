#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
بوت تليجرام التفاعلي
=====================
بيرد على أوامرك بالمعلومة الحالية من آخر دورة للمرصد،
وكمان بيسمحلك تسأل الذكاء الاصطناعي سؤال مفتوح.

    python monitor.py --daemon   ← بيجمع ويحلل ويبعت التنبيهات
    python bot.py                ← بيرد على أوامرك

الأوامر:
  /الحالة /بيتالوطن /المواعيد /الخطوات /الناس /التوقعات
  /الملخص /عاجل /الاهم /تحديث /مساعدة
  أي سؤال تكتبه عادي → يرد عليه الـ AI

إصلاحات أمنية عن النسخة القديمة:
  • كان أي شخص يلاقي البوت يقدر يستخدمه ويشغّل /تحديث على جهازك.
    دلوقتي فيه قايمة سماح (config.TELEGRAM_ALLOWED).
  • تقسيم الرسائل كان بيكسر وسوم HTML → تليجرام يرفض. اتظبط.
  • مافيش تحقق من رد تليجرام أصلاً → دلوقتي بيتقرأ وفيه بديل نص عادي.
  • getUpdates كان بيعيد معالجة الرسايل القديمة عند التشغيل.
"""

import os
import re
import sys
import json
import time
import html
import signal
import subprocess
from datetime import datetime, timezone

import config
from ai_engine import MultiAI, SYSTEM_AR
from sources import session

API = f"https://api.telegram.org/bot{config.TELEGRAM_TOKEN}"
ROOT = os.path.dirname(os.path.abspath(__file__))
_STOP = False

HELP = """🏛️ <b>مرصد العقارات المصرية</b>

<b>رادار الإشارات المبكرة</b>
/تسريبات — معلومات بيقولها الناس ومش في الأخبار 🔥
/اشارات — كل الإشارات المرصودة بترتيب الثقة
/اسئلة — أسئلة الناس اللي مالهاش إجابة
/دقة — أداء الرادار: سبق الجمهور الأخبار بكام يوم

<b>بيت الوطن</b>
/بيتالوطن — البطاقة الكاملة للمرحلة
/المواعيد — كل المواعيد والعدّ التنازلي
/الخطوات — إيه اللي تعمله دلوقتي
/الناس — خلاصة كلام الناس ومخاوفهم
/فيديوهات — آخر الفيديوهات وملخص كل واحد بالـ AI

<b>عام</b>
/الحالة — حالة كل الملفات المتابَعة
/الملخص — الملخص التنفيذي
/التوقعات — القراءة الاستشرافية
/عاجل — آخر الأخبار العاجلة
/الاهم — أهم الأخبار
/تحديث — تشغيل دورة فحص جديدة
/مساعدة — الرسالة دي

<b>كمان:</b> اكتب أي سؤال عادي عن العقارات والمصريين بالخارج والـ AI هيرد عليك من آخر بيانات مرصودة."""


def _handle_stop(signum, frame):
    global _STOP
    _STOP = True


# ============================================================
#  الإرسال
# ============================================================

def _split(text, limit=3600):
    """تقسيم آمن — بيحافظ على الترتيب وبيقفل وسوم HTML المفتوحة."""
    from monitor import _split_message
    return _split_message(text, limit)


def _plain(text):
    return html.unescape(re.sub(r"<[^>]+>", "", text or ""))


def send(chat_id, text, preview=False):
    for chunk in _split(text):
        payload = {"chat_id": chat_id, "text": chunk, "parse_mode": "HTML",
                   "disable_web_page_preview": "false" if preview else "true"}
        try:
            r = session().post(f"{API}/sendMessage", data=payload, timeout=30)
            body = r.json() if r.content else {}
            if not body.get("ok"):
                print(f"[!] رفض: {str(body.get('description'))[:100]}")
                payload.pop("parse_mode", None)
                payload["text"] = _plain(chunk)
                session().post(f"{API}/sendMessage", data=payload, timeout=30)
        except Exception as exc:
            print(f"[!] فشل الإرسال: {str(exc)[:90]}")
        time.sleep(0.5)


def load_latest():
    path = os.path.join(ROOT, config.LATEST_JSON)
    for candidate in (config.LATEST_JSON, path):
        if os.path.exists(candidate):
            try:
                with open(candidate, encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                continue
    return {}


def md_to_tg(text):
    """تحويل مبسط للماركداون لصيغة تليجرام."""
    if not text:
        return ""
    out = []
    for line in str(text).split("\n"):
        s = line.strip()
        if not s:
            out.append("")
        elif s.startswith("### "):
            out.append(f"<b>{html.escape(s[4:])}</b>")
        elif s.startswith("## "):
            out.append(f"\n<b>▸ {html.escape(s[3:])}</b>")
        elif s.startswith("# "):
            out.append(f"\n<b>▸ {html.escape(s[2:])}</b>")
        elif s.startswith(("- ", "* ", "• ")):
            out.append(f"• {html.escape(s[2:])}")
        else:
            out.append(html.escape(s))
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", "\n".join(out))


def _stale_note(data):
    upd = data.get("updated")
    if not upd:
        return ""
    try:
        d = datetime.fromisoformat(upd)
        hours = (datetime.now(d.tzinfo or timezone.utc) - d).total_seconds() / 3600
    except (TypeError, ValueError):
        return ""
    if hours < 6:
        return ""
    return f"\n\n<i>⚠️ آخر تحديث من {int(hours)} ساعة — شغّل /تحديث</i>"


# ============================================================
#  ردود بيت الوطن
# ============================================================

def reply_beit(chat_id):
    data = load_latest()
    b = data.get("beit") or {}
    if not any(b.get(k) for k in ("stage", "booking", "summary")):
        send(chat_id, "لسه مفيش بيانات كافية عن بيت الوطن — شغّل <code>/تحديث</code>.")
        return

    lines = ["🏘️ <b>بيت الوطن — البطاقة الكاملة</b>", ""]
    fields = [("المرحلة الحالية", "stage"), ("حالة الحجز", "booking"),
              ("سعر المتر", "price"), ("المساحات المتاحة", "areas"),
              ("قيمة الجدية", "deposit"), ("طريقة السداد", "payment"),
              ("شروط التقديم", "conditions"), ("آخر تطور", "last")]
    for label, key in fields:
        if b.get(key):
            lines.append(f"▸ <b>{label}:</b> {html.escape(str(b[key])[:300])}")

    nxt = b.get("next")
    if nxt:
        lines += ["", f"⏰ <b>{html.escape(nxt['label'])}</b>: "
                      f"{html.escape(nxt['raw'])} — خلال <b>{nxt['days_left']}</b> يوم"]

    cities = b.get("cities") or {}
    if cities:
        top = "، ".join(list(cities)[:8])
        lines += ["", f"📍 <b>المدن الأكثر ذكرًا:</b> {html.escape(top)}"]

    mz_range = b.get("mzaya_price_range")
    mz_ads = b.get("mzaya_ads_stats")
    if mz_range or mz_ads:
        lines += ["", "🧮 <b>سوق القطع الحي — bit.mzayasoft (مصدر مجتمعي)</b>"]
        if mz_range and mz_range.get("lowest"):
            lines.append(f"   نطاق المقدم: {mz_range['lowest']:,}–"
                        f"{mz_range['highest']:,} جنيه عبر {mz_range['divisions_count']} منطقة")
        if mz_ads and mz_ads.get("total"):
            lines.append(f"   {mz_ads['total']} إعلان نشط "
                        f"({mz_ads.get('sell_count', 0)} بيع / {mz_ads.get('buy_count', 0)} شراء)")

    lines += ["", f"<i>درجة الثقة في البيانات: {html.escape(str(b.get('confidence') or '—'))}</i>"]

    if b.get("summary"):
        lines += ["", "───────────", md_to_tg(b["summary"])]

    send(chat_id, "\n".join(lines) + _stale_note(data))


def reply_videos(chat_id):
    data = load_latest()
    videos = data.get("videos") or []
    if not videos:
        send(chat_id, "مفيش فيديوهات جديدة اتلخصت لسه — شغّل /تحديث.")
        return

    lines = ["🎬 <b>آخر الفيديوهات وتحليلاتها</b>", ""]
    shown = 0
    for v in videos:
        if not v.get("summary"):
            continue
        shown += 1
        lines.append(f"▸ <b><a href=\"{html.escape(v['link'])}\">"
                     f"{html.escape(v['title'][:120])}</a></b>")
        if v.get("channel"):
            lines.append(f"  <i>{html.escape(v['channel'])}</i>")
        lines.append(md_to_tg(str(v["summary"])[:500]))
        lines.append("")
        if shown >= 5:
            break

    if not shown:
        titles = "\n".join(f"• <a href=\"{html.escape(v['link'])}\">"
                           f"{html.escape(v['title'][:120])}</a>"
                           for v in videos[:6])
        lines = ["🎬 <b>آخر الفيديوهات</b>", "",
                 "لسه مفيش ملخص AI جاهز ليها، بس دي آخر الفيديوهات اللي ظهرت:",
                 "", titles]

    send(chat_id, "\n".join(lines) + _stale_note(data))


def reply_dates(chat_id):
    data = load_latest()
    dates = ((data.get("beit") or {}).get("dates")) or []
    if not dates:
        send(chat_id, "مفيش مواعيد معلنة مؤكدة لبيت الوطن حاليًا.\n"
                      "أول ما يظهر إعلان رسمي هيوصلك تنبيه فورًا.")
        return

    icons = {"قادم": "🟢", "النهاردة": "🟡", "فات": "⚪",
             "غير محدد بدقة": "⚪"}
    lines = ["📅 <b>مواعيد بيت الوطن</b>", ""]
    for d in dates:
        icon = icons.get(d.get("status"), "⚪")
        lines.append(f"{icon} <b>{html.escape(d['label'])}</b>")
        lines.append(f"    {html.escape(d['raw'])}")
        if d.get("days_left") is not None:
            if d["days_left"] > 0:
                lines.append(f"    ⏳ باقي <b>{d['days_left']}</b> يوم")
            elif d["days_left"] == 0:
                lines.append("    🔔 <b>النهاردة</b>")
            else:
                lines.append(f"    انتهى من {abs(d['days_left'])} يوم")
        lines.append("")
    lines.append("<i>راجع كراسة الشروط الرسمية قبل أي إجراء.</i>")
    send(chat_id, "\n".join(lines) + _stale_note(data))


def reply_steps(chat_id):
    data = load_latest()
    text = (data.get("beit") or {}).get("checklist")
    if not text:
        send(chat_id, "الخطوات لسه مش جاهزة — شغّل <code>/تحديث</code>.")
        return
    send(chat_id, "✅ <b>خطوات عملية — بيت الوطن</b>\n" + md_to_tg(text)
         + _stale_note(data))


def reply_people(chat_id):
    data = load_latest()
    text = (data.get("beit") or {}).get("people")
    if not text:
        send(chat_id, "مفيش تحليل تعليقات متاح دلوقتي.\n"
                      "<i>محتاج YOUTUBE_API_KEY عشان يسحب الكومنتات.</i>")
        return
    send(chat_id, "💬 <b>كلام الناس — بيت الوطن</b>\n" + md_to_tg(text)
         + "\n\n<i>⚠️ ده كلام أفراد على الإنترنت، مش مصدر رسمي.</i>")


# ============================================================
#  ردود رادار الإشارات
# ============================================================

TIER_ICON = {"مؤكدة رسميًا": "✅", "إشارة قوية": "🟠", "إشارة متقاطعة": "🟡",
             "شهادة فردية": "🔵", "إشارة فردية": "⚪", "مكذّبة": "❌"}


def _signal_lines(sig, with_quotes=True):
    icon = TIER_ICON.get(sig.get("tier"), "🔍")
    out = [f"{icon} <b>{html.escape(str(sig.get('statement', '')))}</b>"]

    bits = [f"{sig.get('mentions', 0)} شخص",
            f"{sig.get('independence', 0)} مصدر مستقل"]
    if sig.get("firsthand"):
        bits.append(f"{sig['firsthand']} تجربة شخصية 👁")
    out.append(f"   <i>{html.escape(' · '.join(bits))}</i>")
    out.append(f"   الثقة: {html.escape(str(sig.get('tier', '—')))}")

    if sig.get("novel") and sig.get("status") != "مؤكدة رسميًا":
        out.append("   ⚠️ <b>مش في الأخبار</b>")
    if sig.get("lead_days") is not None:
        out.append(f"   ✅ سبقت الأخبار بـ <b>{sig['lead_days']}</b> يوم")

    if with_quotes:
        for s in (sig.get("sources") or [])[:2]:
            who = html.escape(str(s.get("author") or s.get("channel") or ""))
            quote = html.escape(str(s.get("quote", ""))[:170])
            eye = " 👁" if s.get("firsthand") else ""
            if s.get("url"):
                out.append(f'   • <a href="{html.escape(str(s["url"]))}">'
                           f'{who}</a>{eye}: «{quote}»')
            else:
                out.append(f"   • {who}{eye}: «{quote}»")
    return out


def reply_leaks(chat_id):
    """أهم أمر — اللي الناس بتقوله ومش في الأخبار."""
    data = load_latest()
    intel = data.get("intel") or {}
    sigs = [s for s in (intel.get("signals") or [])
            if s.get("novel") and s.get("status") != "مؤكدة رسميًا"]
    if not sigs:
        send(chat_id, "مفيش دلوقتي معلومات من الناس خارج الأخبار الرسمية.\n\n"
                      "<i>الرادار بيشتغل كل دورة — أول ما يظهر حاجة هتوصلك "
                      "فورًا من غير ما تسأل.</i>")
        return

    lines = ["🔥 <b>معلومات من الناس مش في الأخبار</b>", ""]
    for sig in sigs[:10]:
        lines += _signal_lines(sig)
        lines.append("")
    lines.append("<i>⚠️ ده كلام ناس على الإنترنت — مش مصدر رسمي. "
                 "راجع كراسة الشروط قبل أي إجراء.</i>")
    send(chat_id, "\n".join(lines) + _stale_note(data))


def reply_signals(chat_id):
    data = load_latest()
    intel = data.get("intel") or {}
    sigs = intel.get("signals") or []
    if not sigs:
        send(chat_id, "لسه مفيش إشارات مرصودة — شغّل <code>/تحديث</code>.")
        return

    counts = intel.get("counts") or {}
    lines = ["📡 <b>رادار الإشارات المبكرة</b>",
             f"<i>{counts.get('total', 0)} إشارة · "
             f"{counts.get('novel', 0)} مش في الأخبار · "
             f"{counts.get('confirmed', 0)} اتأكدت</i>", ""]
    for sig in sigs[:12]:
        lines += _signal_lines(sig, with_quotes=False)
        lines.append("")
    lines.append("<i>استخدم /تسريبات للتفاصيل والاقتباسات.</i>")
    send(chat_id, "\n".join(lines) + _stale_note(data))


def reply_questions(chat_id):
    data = load_latest()
    qs = (data.get("intel") or {}).get("questions") or []
    if not qs:
        send(chat_id, "مفيش أسئلة مرصودة دلوقتي.")
        return
    lines = ["❓ <b>أسئلة الناس اللي مالهاش إجابة</b>",
             "<i>دي بتوضّح فين الغموض الرسمي</i>", ""]
    for q in qs[:15]:
        text = html.escape(str(q.get("text", "")))
        if q.get("url"):
            lines.append(f'• <a href="{html.escape(str(q["url"]))}">{text}</a>')
        else:
            lines.append(f"• {text}")
    send(chat_id, "\n".join(lines))


def reply_accuracy(chat_id):
    """أداء الرادار — بيقولك تثق فيه قد إيه."""
    data = load_latest()
    intel = data.get("intel") or {}
    stats = intel.get("stats") or {}
    counts = intel.get("counts") or {}

    if not stats.get("cycles"):
        send(chat_id, "الرادار لسه ماشتغلش دورة كاملة.")
        return

    lines = ["🎯 <b>أداء الرادار</b>", ""]
    lines.append(f"دورات: <b>{stats.get('cycles', 0)}</b>")
    lines.append(f"كلام اتحلل: <b>{stats.get('utterances', 0)}</b>")
    lines.append(f"إشارات مرصودة: <b>{counts.get('total', 0)}</b>")
    lines.append(f"اتأكدت رسميًا: <b>{counts.get('confirmed', 0)}</b>")

    if stats.get("avg_lead_days") is not None:
        lines += ["", f"⏱️ <b>الجمهور سبق الأخبار بمتوسط "
                      f"{stats['avg_lead_days']} يوم</b>"]
        if stats.get("max_lead_days") is not None:
            lines.append(f"أطول سبق: <b>{stats['max_lead_days']}</b> يوم")
    else:
        lines += ["", "<i>لسه مفيش إشارة اتأكدت رسميًا — "
                      "المقياس ده بيظهر بعد أول تأكيد.</i>"]

    confirmed = [s for s in (intel.get("signals") or [])
                 if s.get("status") == "مؤكدة رسميًا"]
    if confirmed:
        lines += ["", "<b>إشارات اتأكدت:</b>"]
        for s in confirmed[:5]:
            lead = (f" (سبق {s['lead_days']} يوم)"
                    if s.get("lead_days") is not None else "")
            lines.append(f"✅ {html.escape(str(s.get('statement', '')))}{lead}")

    send(chat_id, "\n".join(lines))


def reply_radar_digest(chat_id):
    data = load_latest()
    digest = (data.get("intel") or {}).get("digest")
    if not digest:
        send(chat_id, "قراءة الرادار لسه مش جاهزة — شغّل <code>/تحديث</code>.")
        return
    send(chat_id, "📡 <b>قراءة الرادار</b>\n" + md_to_tg(digest)
         + "\n\n<i>⚠️ مبني على كلام ناس، مش مصادر رسمية.</i>")


# ============================================================
#  ردود عامة
# ============================================================

def reply_status(chat_id):
    data = load_latest()
    rows = data.get("market") or []
    if not rows:
        send(chat_id, "لسه مفيش بيانات — شغّل <code>/تحديث</code> أو استنى أول دورة.")
        return
    lines = ["📋 <b>حالة الملفات المتابَعة</b>", ""]
    for r in rows:
        lines.append(f"<b>▸ {html.escape(r.get('topic', ''))}</b>")
        for label, key in (("المرحلة", "stage"), ("الحالة", "status"),
                           ("⏰ موعد قادم", "next"), ("↳", "last")):
            v = r.get(key)
            if v and v != "—":
                lines.append(f"  {label}: {html.escape(str(v))}")
        lines.append("")
    send(chat_id, "\n".join(lines) + _stale_note(data))


def reply_text_field(chat_id, key, title, icon):
    data = load_latest()
    if not data.get(key):
        send(chat_id, f"{title} لسه مش جاهز — شغّل <code>/تحديث</code>.")
        return
    send(chat_id, f"{icon} <b>{title}</b>\n" + md_to_tg(data[key])
         + _stale_note(data))


def reply_list(chat_id, key, title, icon):
    data = load_latest()
    items = data.get(key) or []
    if not items:
        send(chat_id, f"مفيش {title} في آخر دورة.")
        return
    lines = [f"{icon} <b>{title}</b>", ""]
    for it in items:
        link = it.get("link", "")
        text = html.escape(it.get("title", "بدون عنوان"))
        lines.append(f'• <a href="{html.escape(link)}">{text}</a>' if link
                     else f"• {text}")
        if it.get("source"):
            lines.append(f'  <i>{html.escape(it["source"])}</i>')
    send(chat_id, "\n".join(lines))


def reply_refresh(chat_id):
    send(chat_id, "⏳ بشغّل دورة فحص جديدة... ممكن تاخد دقيقتين.")
    try:
        subprocess.Popen([sys.executable, "monitor.py", "--once"], cwd=ROOT)
    except Exception as exc:
        send(chat_id, f"تعذّر التشغيل: {html.escape(str(exc)[:120])}")


def reply_ai(chat_id, question, ai):
    if not ai.available:
        send(chat_id, "مفيش مفتاح AI مضبوط، فمش هقدر أرد على الأسئلة المفتوحة.")
        return

    data = load_latest()
    ctx = []
    b = data.get("beit") or {}
    if any(b.get(k) for k in ("stage", "booking", "price")):
        facts = [f"{k}: {b[k]}" for k in
                 ("stage", "booking", "price", "areas", "deposit",
                  "payment", "conditions", "last") if b.get(k)]
        ctx.append("حالة بيت الوطن:\n" + "\n".join(f"- {f}" for f in facts))
    if b.get("dates"):
        ctx.append("مواعيد بيت الوطن:\n" + "\n".join(
            f"- {d['label']}: {d['raw']} ({d.get('status', '')})"
            for d in b["dates"]))

    # بيانات bit.mzayasoft (مصدر مجتمعي غير رسمي) — أرقام حقيقية عن
    # المقدم والأسعار الفعلية، مش موجودة في أي مصدر رسمي. مهم جدًا
    # نديها للـ AI عشان يقدر يرد على أسئلة زي "كام المقدم؟"
    mz_divisions = b.get("mzaya_divisions") or []
    mz_range = b.get("mzaya_price_range")
    if mz_range and mz_range.get("lowest"):
        ctx.append(
            f"نطاق المقدم الفعلي المرصود (مصدر مجتمعي bit.mzayasoft، "
            f"غير رسمي، لكن بيانات سوق حقيقية):\n"
            f"- أقل مقدم: {mz_range['lowest']:,} جنيه\n"
            f"- أعلى مقدم: {mz_range['highest']:,} جنيه\n"
            f"- عدد المناطق المرصودة: {mz_range['divisions_count']}")
    if mz_divisions:
        top_divs = mz_divisions[:8]
        ctx.append("تفاصيل المقدم لكل منطقة (bit.mzayasoft، غير رسمي):\n"
                   + "\n".join(
                       f"- {d.get('name', '')}: مقدم من "
                       f"{d.get('min_deposit', '؟')} لـ {d.get('max_deposit', '؟')} جنيه"
                       + (f" · {d.get('plot_count')} قطعة" if d.get('plot_count') else "")
                       for d in top_divs))
    mz_ads_stats = b.get("mzaya_ads_stats")
    if mz_ads_stats and mz_ads_stats.get("total"):
        ctx.append(
            f"سوق القطع الحالي على bit.mzayasoft (غير رسمي):\n"
            f"- {mz_ads_stats['total']} إعلان نشط "
            f"({mz_ads_stats.get('sell_count', 0)} معروض للبيع، "
            f"{mz_ads_stats.get('buy_count', 0)} مطلوب للشراء)"
            + (f"\n- متوسط الفرق فوق المدفوع (الأوفر): "
               f"{mz_ads_stats['avg_premium']:,} جنيه"
               if mz_ads_stats.get('avg_premium') else ""))
    mz_new_ads = b.get("mzaya_new_ads") or []
    if mz_new_ads:
        ctx.append(f"إعلانات قطع جديدة ظهرت مؤخرًا ({len(mz_new_ads)}):\n"
                   + "\n".join(
                       f"- {a.get('status', '')}: {a.get('area_m2', '؟')} م²"
                       + (f"، الأوفر {a['premium']:,} جنيه" if a.get('premium') else "")
                       for a in mz_new_ads[:5]))

    intel = data.get("intel") or {}
    novel = [s for s in (intel.get("signals") or [])
             if s.get("novel") and s.get("status") != "مؤكدة رسميًا"]
    if novel:
        ctx.append("إشارات من كلام الناس (غير مؤكدة رسميًا — عاملها كذلك):\n"
                   + "\n".join(
                       f"- {s.get('statement')} "
                       f"[{s.get('tier')}, {s.get('independence', 0)} مصدر مستقل]"
                       for s in novel[:10]))
    if intel.get("questions"):
        ctx.append("أسئلة الناس بلا إجابة:\n" + "\n".join(
            f"- {q.get('text')}" for q in intel["questions"][:8]))
    if data.get("brief"):
        ctx.append("الملخص الحالي:\n" + str(data["brief"])[:1600])
    for r in (data.get("market") or []):
        ctx.append(f"- {r.get('topic')}: مرحلة {r.get('stage')}, "
                   f"حالة {r.get('status')}, موعد قادم {r.get('next')}")
    tops = data.get("top") or []
    if tops:
        ctx.append("أهم العناوين:\n" + "\n".join(
            f"- {t.get('title', '')}" for t in tops[:12]))

    context = "\n\n".join(ctx) or "لا توجد بيانات محدّثة متاحة."

    prompt = f"""إنت مساعد متخصص في مرصد عقاري بيتابع بيت الوطن والسوق المصري
بدقة عالية. دي أحدث المعلومات المرصودة عندنا فعليًا (مش معلومات عامة —
دي بيانات حقيقية جمعناها من مصادر رسمية، أخبار، وموقع bit.mzayasoft
المجتمعي):

{context}

سؤال المستخدم: {question}

جاوب بالعربية المصرية، مباشر ومحدد (لغاية 8 أسطر).
- لو السؤال عن رقم (سعر، مقدم، موعد) وعندك رقم فعلي فوق، اذكره بالظبط
  بدل ما ترد بعمومية زي "الأسعار بتختلف حسب المنطقة" — ده رد ضعيف
  ومحبط للمستخدم اللي محتاج رقم حقيقي.
- **فرّق بوضوح بين 3 مستويات**: (1) مؤكد رسميًا، (2) بيانات bit.mzayasoft
  (مصدر مجتمعي حقيقي بس مش رسمي)، (3) إشارات من كلام الناس (الأضعف).
  اذكر المستوى بوضوح مع أي رقم بتديه.
- لو مفيش معلومة كافية فعلاً في أي مستوى، قول صراحة "مفيش بيانات كافية
  عن ده دلوقتي" واقترح مصدر رسمي يراجعه — بدون رد عام مايقولش حاجة.
- ماتخترعش أرقام أو مواعيد مش موجودة فوق.
- ماتديش نصيحة استثمارية مباشرة."""

    send(chat_id, "🤔 لحظة...")
    answer = ai.ask(prompt, SYSTEM_AR)
    send(chat_id, md_to_tg(answer) if answer
         else "معرفتش أوصل لرد دلوقتي، جرّب تاني.")


# ============================================================
#  التوجيه
# ============================================================

ROUTES = {
    ("/start", "/مساعدة", "/help"): lambda cid, ai: send(cid, HELP),
    ("/تسريبات", "/تسريب", "/leaks"): lambda cid, ai: reply_leaks(cid),
    ("/اشارات", "/إشارات", "/signals", "/radar"):
        lambda cid, ai: reply_signals(cid),
    ("/اسئلة", "/أسئلة", "/questions"): lambda cid, ai: reply_questions(cid),
    ("/دقة", "/الدقة", "/accuracy"): lambda cid, ai: reply_accuracy(cid),
    ("/الرادار", "/digest"): lambda cid, ai: reply_radar_digest(cid),
    ("/بيتالوطن", "/بيت_الوطن", "/beit"): lambda cid, ai: reply_beit(cid),
    ("/فيديوهات", "/فيديو", "/videos"): lambda cid, ai: reply_videos(cid),
    ("/المواعيد", "/مواعيد", "/dates"): lambda cid, ai: reply_dates(cid),
    ("/الخطوات", "/خطوات", "/steps"): lambda cid, ai: reply_steps(cid),
    ("/الناس", "/ناس", "/people"): lambda cid, ai: reply_people(cid),
    ("/الحالة", "/status"): lambda cid, ai: reply_status(cid),
    ("/الملخص", "/brief"): lambda cid, ai: reply_text_field(
        cid, "brief", "الملخص التنفيذي", "🧭"),
    ("/التوقعات", "/forecast"): lambda cid, ai: reply_text_field(
        cid, "forecast", "القراءة الاستشرافية", "🔮"),
    ("/عاجل", "/urgent"): lambda cid, ai: reply_list(
        cid, "urgent", "أخبار عاجلة", "🔴"),
    ("/الاهم", "/الأهم", "/top"): lambda cid, ai: reply_list(
        cid, "top", "أهم الأخبار", "⭐"),
    ("/تحديث", "/refresh"): lambda cid, ai: reply_refresh(cid),
}


def allowed(chat_id):
    if not config.TELEGRAM_ALLOWED:
        return False
    return str(chat_id) in config.TELEGRAM_ALLOWED


def handle(chat_id, text, ai):
    cmd = text.strip().split()[0].split("@")[0] if text.strip() else ""
    for keys, fn in ROUTES.items():
        if cmd in keys:
            fn(chat_id, ai)
            return
    if cmd.startswith("/"):
        send(chat_id, "أمر مش معروف. اكتب /مساعدة للأوامر المتاحة.")
        return
    reply_ai(chat_id, text.strip(), ai)


def _drop_backlog():
    """يتخطى الرسايل القديمة عند التشغيل بدل ما يعيد الرد عليها."""
    try:
        r = session().get(f"{API}/getUpdates",
                          params={"timeout": 0, "offset": -1}, timeout=20)
        result = (r.json() or {}).get("result") or []
        return result[-1]["update_id"] + 1 if result else None
    except Exception:
        return None


def main():
    if not config.TELEGRAM_TOKEN:
        print("[!] لازم تضبط TELEGRAM_TOKEN الأول.")
        return
    if not config.TELEGRAM_ALLOWED:
        print("[!] TELEGRAM_CHAT_ID مش مضبوط — البوت هيرفض كل الرسايل.")
        print("    ده مقصود: من غيره أي حد يلاقي البوت هيقدر يستخدمه.")
        return

    signal.signal(signal.SIGINT, _handle_stop)
    try:
        signal.signal(signal.SIGTERM, _handle_stop)
    except (AttributeError, ValueError):
        pass

    ai = MultiAI(verbose=False)
    print("[+] البوت شغال. اضغط Ctrl+C للإيقاف.")
    print(f"[+] مسموح لـ: {', '.join(config.TELEGRAM_ALLOWED)}")
    if ai.available:
        print(f"[+] محركات AI: {', '.join(ai.names)}")

    offset = _drop_backlog()

    while not _STOP:
        try:
            r = session().get(f"{API}/getUpdates",
                              params={"timeout": 50, "offset": offset},
                              timeout=65)
            data = r.json()
        except Exception as exc:
            print(f"[!] {str(exc)[:90]}")
            time.sleep(5)
            continue

        for upd in data.get("result", []):
            offset = upd["update_id"] + 1
            msg = upd.get("message") or upd.get("edited_message")
            if not msg:
                continue
            chat_id = msg["chat"]["id"]
            text = msg.get("text", "")
            if not text:
                continue

            if not allowed(chat_id):
                print(f"[✗] رفض من {chat_id}: {text[:40]}")
                continue

            print(f"[>] {chat_id}: {text[:60]}")
            try:
                handle(chat_id, text, ai)
            except Exception as exc:
                print(f"[!] خطأ في المعالجة: {exc}")
                send(chat_id, "حصل خطأ في تنفيذ الأمر، جرّب تاني.")

    print("\n[i] تم الإيقاف.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[i] تم الإيقاف.")
