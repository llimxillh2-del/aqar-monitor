# -*- coding: utf-8 -*-
"""
تشخيص المصادر
==============
    python monitor.py --sources

بيفحص كل مصدر واحد واحد ويقولك:
  ✅ شغال (وكام عنصر جاب)
  ⚠️ ناقصه حاجة (وإيه بالظبط والخطوة الجاية)
  ❌ مقفول (وليه)

ده أهم أمر في النظام — من غيره ممكن تفتكر إنك بتراقب حاجة وإنت مش شايفها.
"""

import os
import time

import config

OK, WARN, FAIL, OFF = "✅", "⚠️", "❌", "⭕"


class Report:
    def __init__(self):
        self.rows = []

    def add(self, mark, group, name, detail, fix=""):
        self.rows.append((mark, group, name, detail, fix))

    def show(self):
        print("\n" + "═" * 72)
        print("  تشخيص المصادر")
        print("═" * 72)

        current = None
        for mark, group, name, detail, fix in self.rows:
            if group != current:
                print(f"\n\033[1m{group}\033[0m")
                current = group
            print(f"  {mark} {name}")
            if detail:
                print(f"      {detail}")
            if fix:
                print(f"      \033[33m← {fix}\033[0m")

        counts = {}
        for mark, *_ in self.rows:
            counts[mark] = counts.get(mark, 0) + 1

        print("\n" + "═" * 72)
        parts = [f"{m} {counts.get(m, 0)}" for m in (OK, WARN, FAIL, OFF)]
        print("  " + "   ".join(parts))
        print("═" * 72)

        todo = [(n, f) for m, _, n, _, f in self.rows if m == WARN and f]
        if todo:
            print("\n\033[1mالخطوات الناقصة بالترتيب:\033[0m")
            for i, (name, fix) in enumerate(todo, 1):
                print(f"  {i}. {name}\n     {fix}")
            print()


# ============================================================

def _check_official(rep):
    import watcher
    for page in config.WATCH_PAGES:
        lines, err = watcher.page_text(page["url"], timeout=20)
        label = page["name"]
        if err:
            rep.add(FAIL, "المصادر الرسمية", label, err[:80],
                    "لو الخطأ مؤقت هيرجع لوحده. لو مستمر، شيل الصفحة من "
                    "WATCH_PAGES في config.py")
        else:
            useful = [ln for ln in lines if not watcher._is_noise(ln)]
            if page.get("js") or len(useful) < 8:
                rep.add(WARN, "المصادر الرسمية", label,
                        f"{len(useful)} سطر مفيد فقط — الصفحة بتتبني بجافاسكريبت",
                        "الرصد عليها ضعيف. اعتمد على lands.nuca.gov.eg "
                        "و mhuc.gov.eg كمصدر أساسي")
            else:
                rep.add(OK, "المصادر الرسمية", label, f"{len(useful)} سطر مرصود")
        time.sleep(0.4)


def _check_news(rep):
    import sources
    q = config.BEIT_ALWATAN["queries"][0]
    items = sources.google_news(q)
    if items:
        rep.add(OK, "الأخبار", "Google News", f"{len(items)} خبر على «{q}»")
    else:
        rep.add(FAIL, "الأخبار", "Google News", "مفيش نتائج",
                "غالبًا حجب مؤقت من جوجل. جرّب تاني بعد شوية، "
                "أو شغّل من IP مختلف")


def _check_youtube(rep):
    import sources
    if not config.YOUTUBE_API_KEY:
        rep.add(WARN, "يوتيوب", "مفتاح YouTube API", "مش مضبوط",
                "من غيره: مفيش كومنتات ولا إحصائيات ولا رادار إشارات — "
                "وده أهم مصدر. هاته مجانًا من console.cloud.google.com "
                "→ فعّل YouTube Data API v3 → Credentials → API key، "
                "وحطه في YOUTUBE_API_KEY")
    else:
        found = sources.youtube_search("بيت الوطن", max_results=3)
        if found:
            rep.add(OK, "يوتيوب", "مفتاح YouTube API",
                    f"شغال — {len(found)} نتيجة بحث")
            vid = found[0].get("video_id")
            comments = sources.get_top_comments(vid, limit=5) if vid else []
            if comments:
                rep.add(OK, "يوتيوب", "الكومنتات",
                        f"{len(comments)} كومنت من فيديو تجريبي")
            else:
                rep.add(WARN, "يوتيوب", "الكومنتات",
                        "مفيش كومنتات في الفيديو التجريبي",
                        "ممكن يكون الفيديو ده مقفول الكومنتات — عادي")
        else:
            rep.add(FAIL, "يوتيوب", "مفتاح YouTube API",
                    "المفتاح موجود بس البحث فشل",
                    "اتأكد إن YouTube Data API v3 مفعّل على المشروع، "
                    "وإن المفتاح مش مقيّد بـ IP أو referrer")

    ok = 0
    for name, ch_id in config.YOUTUBE_CHANNELS:
        items = sources.youtube_channel_feed(ch_id, name)
        if items:
            ok += 1
        else:
            rep.add(WARN, "يوتيوب", f"قناة: {name}", "مفيش فيديوهات حديثة",
                    "اتأكد إن الـ channel ID صح: افتح القناة → Ctrl+U "
                    "→ دوّر على channelId")
        time.sleep(0.3)
    if ok:
        rep.add(OK, "يوتيوب", "القنوات المتابَعة",
                f"{ok} من {len(config.YOUTUBE_CHANNELS)} قناة شغالة")


def _check_telegram_public(rep):
    import human_sources
    if not config.TELEGRAM_CHANNELS:
        rep.add(OFF, "تليجرام (عام)", "قنوات عامة", "مفيش قنوات مضبوطة",
                "ضيف أسماء قنوات في TELEGRAM_CHANNELS في config.py")
        return
    for name in config.TELEGRAM_CHANNELS:
        items = human_sources.telegram_channels([name])
        if items:
            rep.add(OK, "تليجرام (عام)", f"@{name}", f"{len(items)} رسالة")
        else:
            rep.add(WARN, "تليجرام (عام)", f"@{name}",
                    "مفيش رسايل — القناة غالبًا مش موجودة أو مش عامة",
                    "شيلها من TELEGRAM_CHANNELS أو صحّح الاسم")
        time.sleep(0.5)


def _check_telegram_account(rep):
    try:
        import telegram_client
    except Exception as exc:
        rep.add(WARN, "تليجرام (حسابك)", "Telethon", str(exc)[:60],
                "pip install telethon")
        return

    state, hint = telegram_client.status()
    if state == "جاهز":
        got = telegram_client.collect(limit_per_chat=40, days=7,
                                      only_matching=False)
        chats = len({u["channel"] for u in got})
        rep.add(OK, "تليجرام (حسابك)", "الجروبات الخاصة",
                f"{chats} جروب/قناة · {len(got)} رسالة في آخر ٧ أيام")
    else:
        rep.add(WARN, "تليجرام (حسابك)", "الجروبات الخاصة", state, hint)


def _check_facebook(rep):
    if not config.FB_EMAIL_ENABLED:
        rep.add(OFF, "فيسبوك", "جروبات فيسبوك", "متوقّف",
                "FB_EMAIL_ENABLED=false")
        return
    if not (config.IMAP_USER and config.IMAP_PASSWORD):
        rep.add(WARN, "فيسبوك", "جروبات فيسبوك", "مش مضبوط",
                "دي الطريقة الوحيدة الشرعية لجروبات فيسبوك. "
                "اعمل إيميل مخصّص، فعّل إشعارات الجروبات عليه، "
                "وحط IMAP_USER و IMAP_PASSWORD (كلمة سر تطبيقات مش "
                "كلمة سر الإيميل). التفاصيل في README")
        return
    import human_sources
    got = human_sources.facebook_via_email(limit=40)
    if got:
        groups = len({u["channel"] for u in got})
        rep.add(OK, "فيسبوك", "جروبات فيسبوك",
                f"{groups} جروب · {len(got)} إشعار")
    else:
        rep.add(WARN, "فيسبوك", "جروبات فيسبوك",
                "الاتصال تم بس مفيش إشعارات",
                "اتأكد إن إشعارات الجروبات مفعّلة بالإيميل، "
                "وإن الإيميلات مش رايحة Spam أو تبويب Promotions")


def _check_reddit(rep):
    if not config.REDDIT_ENABLED:
        rep.add(OFF, "Reddit", "Reddit", "متوقّف")
        return
    import human_sources
    got = human_sources.reddit(queries=config.REDDIT_QUERIES[:1],
                               with_comments=False)
    if got:
        rep.add(OK, "Reddit", "البحث", f"{len(got)} بوست")
    else:
        rep.add(WARN, "Reddit", "البحث", "مفيش نتائج",
                "عادي — المحتوى العربي على Reddit قليل. "
                "أو Reddit بيحدّ الطلبات مؤقتًا")


def _check_ai(rep):
    from ai_engine import MultiAI
    ai = MultiAI(verbose=False)
    if not ai.providers:
        rep.add(FAIL, "الذكاء الاصطناعي", "المزوّدين", "مفيش أي مفتاح",
                "من غير AI مفيش تحليل ولا استخراج إشارات. "
                "أسهل واحد: console.groq.com/keys → GROQ_API_KEY")
        return
    for name, _ in ai.providers:
        rep.add(OK, "الذكاء الاصطناعي", name, "المفتاح موجود")
    out = ai.ask("رد بكلمة واحدة: تمام", fast=True)
    if out:
        rep.add(OK, "الذكاء الاصطناعي", "اختبار حي", f"رد: {out[:40]}")
    else:
        rep.add(FAIL, "الذكاء الاصطناعي", "اختبار حي", "كل المزوّدين فشلوا",
                "اتأكد إن المفاتيح صحيحة ومش منتهية")


def _check_telegram_bot(rep):
    if not config.TELEGRAM_TOKEN:
        rep.add(FAIL, "التنبيهات", "بوت تليجرام", "TELEGRAM_TOKEN مش مضبوط",
                "من @BotFather على تليجرام → /newbot")
        return
    if not config.TELEGRAM_CHAT_ID:
        rep.add(FAIL, "التنبيهات", "TELEGRAM_CHAT_ID", "مش مضبوط",
                "ابعت /start للبوت بتاعك، وبعدين افتح "
                "api.telegram.org/bot<TOKEN>/getUpdates ودوّر على chat.id")
        return
    import sources
    try:
        r = sources.session().get(
            f"https://api.telegram.org/bot{config.TELEGRAM_TOKEN}/getMe",
            timeout=20)
        body = r.json()
        if body.get("ok"):
            uname = (body.get("result") or {}).get("username", "")
            rep.add(OK, "التنبيهات", "بوت تليجرام", f"@{uname} شغال")
        else:
            rep.add(FAIL, "التنبيهات", "بوت تليجرام",
                    str(body.get("description"))[:70], "اتأكد من التوكن")
    except Exception as exc:
        rep.add(FAIL, "التنبيهات", "بوت تليجرام", str(exc)[:70], "")


CHECKS = [
    ("official", _check_official), ("news", _check_news),
    ("youtube", _check_youtube), ("tg-public", _check_telegram_public),
    ("tg-account", _check_telegram_account), ("facebook", _check_facebook),
    ("reddit", _check_reddit), ("ai", _check_ai), ("bot", _check_telegram_bot),
]


def run(only=None):
    rep = Report()
    print("جاري الفحص... (ممكن ياخد دقيقة أو اتنين)\n")
    for key, fn in CHECKS:
        if only and key not in only:
            continue
        try:
            fn(rep)
        except Exception as exc:
            rep.add(FAIL, "أخطاء", key, str(exc)[:90], "")
    rep.show()
    return rep
