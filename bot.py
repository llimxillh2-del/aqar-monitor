#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
بوت تليجرام التفاعلي
=====================
بيرد على أوامرك بالمعلومة الحالية من آخر دورة للمرصد،
وكمان بيسمحلك تسأل الذكاء الاصطناعي سؤال مفتوح.

بيشتغل بالتوازي مع monitor.py:
    python monitor.py     ← بيجمع ويحلل ويبعت التنبيهات
    python bot.py         ← بيرد على أوامرك

الأوامر:
  /start   /مساعدة
  /الحالة      حالة السوق الآن
  /الملخص      الملخص التنفيذي
  /التوقعات    قراءة السوق والأماكن
  /عاجل        آخر الأخبار العاجلة
  /الاهم       أهم الأخبار
  /تحديث       تشغيل دورة جديدة فورًا
  أي سؤال تكتبه عادي → يرد عليه الـ AI
"""

import os
import sys
import json
import time
import html
import subprocess
from datetime import datetime

import requests

import config
from ai_engine import MultiAI, SYSTEM_AR

API = f"https://api.telegram.org/bot{config.TELEGRAM_TOKEN}"

HELP = """🏛️ <b>مرصد العقارات المصرية</b>

<b>الأوامر:</b>
/الحالة — حالة كل مشروع دلوقتي
/الملخص — الملخص التنفيذي
/التوقعات — قراءة السوق والأماكن
/عاجل — آخر الأخبار العاجلة
/الاهم — أهم الأخبار
/تحديث — تشغيل دورة فحص جديدة
/مساعدة — الرسالة دي

<b>كمان:</b> اكتب أي سؤال عادي عن العقارات والمصريين بالخارج والـ AI هيرد عليك بناءً على آخر بيانات موجودة."""


# ============================================================
#  أدوات
# ============================================================

def send(chat_id, text, preview=False):
    for i in range(0, len(text), 3800):
        try:
            requests.post(f"{API}/sendMessage", data={
                "chat_id": chat_id,
                "text": text[i:i + 3800],
                "parse_mode": "HTML",
                "disable_web_page_preview": "false" if preview else "true",
            }, timeout=30)
            time.sleep(0.6)
        except Exception as exc:
            print(f"[!] فشل الإرسال: {exc}")


def load_latest():
    if os.path.exists(config.LATEST_JSON):
        try:
            with open(config.LATEST_JSON, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def md_to_tg(text):
    """تحويل مبسط للماركداون لصيغة تليجرام."""
    if not text:
        return ""
    out = []
    for line in text.split("\n"):
        s = line.strip()
        if not s:
            out.append("")
        elif s.startswith("## "):
            out.append(f"\n<b>▸ {html.escape(s[3:])}</b>")
        elif s.startswith("### "):
            out.append(f"<b>{html.escape(s[4:])}</b>")
        elif s.startswith(("- ", "* ", "• ")):
            out.append(f"• {html.escape(s[2:])}")
        else:
            out.append(html.escape(s))
    txt = "\n".join(out)
    # **عريض** → <b>
    import re
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", txt)


# ============================================================
#  الردود
# ============================================================

def reply_status(chat_id):
    data = load_latest()
    rows = data.get("market") or []
    if not rows:
        send(chat_id, "لسه مفيش بيانات — شغّل <code>/تحديث</code> أو استنى أول دورة.")
        return
    lines = ["📋 <b>حالة السوق الآن</b>", ""]
    for r in rows:
        lines.append(f"<b>▸ {html.escape(r['topic'])}</b>")
        if r.get("stage") and r["stage"] != "—":
            lines.append(f"  المرحلة: {html.escape(r['stage'])}")
        if r.get("status") and r["status"] != "—":
            lines.append(f"  الحالة: {html.escape(r['status'])}")
        if r.get("next") and r["next"] != "—":
            lines.append(f"  ⏰ موعد قادم: <b>{html.escape(r['next'])}</b>")
        if r.get("last") and r["last"] != "—":
            lines.append(f"  ↳ {html.escape(r['last'])}")
        lines.append("")
    upd = data.get("updated", "")
    if upd:
        lines.append(f"<i>آخر تحديث: {upd[:16].replace('T',' ')}</i>")
    send(chat_id, "\n".join(lines))


def reply_brief(chat_id):
    data = load_latest()
    if not data.get("brief"):
        send(chat_id, "الملخص لسه مش جاهز — شغّل <code>/تحديث</code>.")
        return
    send(chat_id, "🧭 <b>الملخص التنفيذي</b>\n" + md_to_tg(data["brief"]))


def reply_forecast(chat_id):
    data = load_latest()
    if not data.get("forecast"):
        send(chat_id, "التوقعات لسه مش جاهزة — شغّل <code>/تحديث</code>.")
        return
    send(chat_id, "🔮 <b>التوقعات وقراءة السوق</b>\n" + md_to_tg(data["forecast"]))


def reply_list(chat_id, key, title, icon):
    data = load_latest()
    items = data.get(key) or []
    if not items:
        send(chat_id, f"مفيش {title} في آخر دورة.")
        return
    lines = [f"{icon} <b>{title}</b>", ""]
    for it in items:
        lines.append(f'• <a href="{html.escape(it["link"])}">'
                     f'{html.escape(it["title"])}</a>')
        if it.get("source"):
            lines.append(f'  <i>{html.escape(it["source"])}</i>')
    send(chat_id, "\n".join(lines))


def reply_refresh(chat_id):
    send(chat_id, "⏳ بشغّل دورة فحص جديدة... ممكن تاخد دقيقتين.")
    try:
        subprocess.Popen([sys.executable, "monitor.py", "--once"],
                         cwd=os.path.dirname(os.path.abspath(__file__)))
    except Exception as exc:
        send(chat_id, f"تعذّر التشغيل: {html.escape(str(exc)[:120])}")


def reply_ai(chat_id, question, ai):
    if not ai.available:
        send(chat_id, "مفيش مفتاح AI مضبوط، فمش هقدر أرد على الأسئلة المفتوحة.")
        return
    data = load_latest()
    ctx_parts = []
    if data.get("brief"):
        ctx_parts.append("الملخص الحالي:\n" + data["brief"][:1800])
    rows = data.get("market") or []
    if rows:
        ctx_parts.append("حالة المشاريع:\n" + "\n".join(
            f"- {r['topic']}: مرحلة {r['stage']}, حالة {r['status']}, "
            f"موعد قادم {r['next']}" for r in rows))
    tops = data.get("top") or []
    if tops:
        ctx_parts.append("أهم العناوين:\n" + "\n".join(
            f"- {t['title']}" for t in tops[:12]))

    ctx = "\n\n".join(ctx_parts) or "لا توجد بيانات محدّثة متاحة."

    prompt = f"""دي أحدث المعلومات المتاحة عندنا عن السوق العقاري المصري:

{ctx}

سؤال المستخدم: {question}

جاوب بالعربية المصرية باختصار (5 أسطر كحد أقصى).
- اعتمد على المعلومات فوق. لو مش موجودة فيها، قول إنك مش متأكد واقترح مصدر رسمي يراجعه.
- ماتخترعش أرقام أو مواعيد.
- ماتديش نصيحة استثمارية مباشرة."""

    send(chat_id, "🤔 لحظة...")
    answer = ai.ask(prompt, SYSTEM_AR)
    send(chat_id, md_to_tg(answer) if answer else "معرفتش أوصل لرد دلوقتي، جرّب تاني.")


# ============================================================
#  الحلقة
# ============================================================

ROUTES = {
    ("/start", "/مساعدة", "/help"): lambda cid, ai: send(cid, HELP),
    ("/الحالة", "/status"): lambda cid, ai: reply_status(cid),
    ("/الملخص", "/brief"): lambda cid, ai: reply_brief(cid),
    ("/التوقعات", "/forecast"): lambda cid, ai: reply_forecast(cid),
    ("/عاجل", "/urgent"): lambda cid, ai: reply_list(cid, "urgent", "أخبار عاجلة", "🔴"),
    ("/الاهم", "/الأهم", "/top"): lambda cid, ai: reply_list(cid, "top", "أهم الأخبار", "⭐"),
    ("/تحديث", "/refresh"): lambda cid, ai: reply_refresh(cid),
}


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


def main():
    if not config.TELEGRAM_TOKEN:
        print("[!] لازم تضبط TELEGRAM_TOKEN الأول.")
        return

    ai = MultiAI(verbose=False)
    print("[+] البوت شغال. اضغط Ctrl+C للإيقاف.")
    if ai.available:
        print(f"[+] محركات AI: {', '.join(n for n, _ in ai.providers)}")

    offset = None
    while True:
        try:
            r = requests.get(f"{API}/getUpdates", params={
                "timeout": 50,
                "offset": offset,
            }, timeout=60)
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
            print(f"[>] {chat_id}: {text[:60]}")
            try:
                handle(chat_id, text, ai)
            except Exception as exc:
                print(f"[!] خطأ في المعالجة: {exc}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[i] تم الإيقاف.")
