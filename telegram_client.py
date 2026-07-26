# -*- coding: utf-8 -*-
"""
قارئ تليجرام بحسابك الشخصي
===========================
t.me/s/ بيقرا القنوات **العامة** بس. الجروبات والقنوات الخاصة اللي إنت
عضو فيها محتاجة حساب حقيقي — وده بيتم عبر API تليجرام الرسمي (Telethon).

ليه ده مهم؟ أهم الكلام في العقارات المصرية بيتقال في جروبات خاصة
مش في قنوات عامة. الطبقة دي بتفتحلك الجروبات دي كلها.

  • رسمي بالكامل — API تليجرام المعلن، مش scraping
  • بيقرا اللي إنت شايفه بحسابك بس، ولا بيبعت ولا بيعدّل حاجة
  • مجاني تمامًا

── التنصيب ─────────────────────────────────────────
  pip install telethon

  1) روح my.telegram.org → API development tools
  2) هتاخد api_id و api_hash
  3) حطهم في متغيرات البيئة:
       TELEGRAM_API_ID=1234567
       TELEGRAM_API_HASH=abcdef...
  4) سجّل دخول مرة واحدة بس:
       python telegram_client.py --login
     (هيطلب رقمك وكود بيوصلك على تليجرام — بعدها بيحفظ جلسة
      ويشتغل لوحده للأبد)

الجلسة بتتحفظ في ملف .session — **متشاركهوش مع حد ومترفعهوش على git**.
"""

import os
import re
import sys
import asyncio
from datetime import datetime, timezone, timedelta

import config

try:
    from telethon import TelegramClient
    from telethon.tl.types import Channel, Chat, User
    AVAILABLE = True
except ImportError:                                       # pragma: no cover
    TelegramClient = None
    Channel = Chat = User = ()
    AVAILABLE = False


SESSION = os.environ.get("TELEGRAM_SESSION", "aqar_session")
API_ID = os.environ.get("TELEGRAM_API_ID", "").strip()
API_HASH = os.environ.get("TELEGRAM_API_HASH", "").strip()


def configured():
    return bool(AVAILABLE and API_ID and API_HASH)


def status():
    """يشرح للمستخدم ناقصه إيه بالظبط."""
    if not AVAILABLE:
        return ("غير مثبت", "شغّل: pip install telethon")
    if not (API_ID and API_HASH):
        return ("ناقص مفاتيح",
                "هات api_id و api_hash من my.telegram.org وحطهم في "
                "TELEGRAM_API_ID و TELEGRAM_API_HASH")
    if not os.path.exists(f"{SESSION}.session"):
        return ("محتاج تسجيل دخول", "شغّل مرة واحدة: python telegram_client.py --login")
    return ("جاهز", "")


# ============================================================
#  الجمع
# ============================================================

def _match(text):
    return any(w in text for w in config.BEIT_ALWATAN["match_words"])


async def _collect(limit_per_chat, days, only_matching, chats_filter):
    from human_sources import utterance

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    out, scanned = [], 0

    client = TelegramClient(SESSION, int(API_ID), API_HASH)
    await client.start()

    async for dialog in client.iter_dialogs():
        entity = dialog.entity
        # الجروبات والقنوات بس — مش المحادثات الشخصية (خصوصية)
        if isinstance(entity, User):
            continue
        if not isinstance(entity, (Channel, Chat)):
            continue

        title = getattr(entity, "title", "") or "مجهول"
        if chats_filter and not any(
                f.lower() in title.lower() for f in chats_filter):
            continue

        scanned += 1
        username = getattr(entity, "username", None)
        channel_key = f"tg:{username or title[:40]}"
        found = 0

        try:
            async for msg in client.iter_messages(entity, limit=limit_per_chat):
                text = (msg.message or "").strip()
                if len(text) < 20:
                    continue
                when = msg.date
                if when and when.replace(tzinfo=timezone.utc) < cutoff:
                    break
                if only_matching and not _match(text):
                    continue

                author = ""
                try:
                    sender = await msg.get_sender()
                    if sender is not None:
                        author = (getattr(sender, "first_name", "")
                                  or getattr(sender, "title", "")
                                  or getattr(sender, "username", "") or "")
                except Exception:
                    pass

                link = (f"https://t.me/{username}/{msg.id}" if username
                        else f"https://t.me/c/{entity.id}/{msg.id}")

                out.append(utterance(
                    text, "telegram", channel_key,
                    author=author or title,
                    url=link,
                    likes=getattr(msg, "views", 0) or 0,
                    replies=getattr(getattr(msg, "replies", None),
                                    "replies", 0) or 0,
                    published=when.isoformat() if when else "",
                    context=f"تليجرام — {title}"))
                found += 1
        except Exception as exc:
            print(f"    - تليجرام «{title[:30]}»: {str(exc)[:60]}")
            continue

        if found:
            print(f"    - تليجرام «{title[:34]}»: {found} رسالة")

    await client.disconnect()
    print(f"    → فُحص {scanned} جروب/قناة · {len(out)} رسالة مطابقة")
    return out


def collect(limit_per_chat=200, days=None, only_matching=True,
            chats_filter=None):
    """
    يقرا رسايل كل الجروبات والقنوات اللي إنت عضو فيها.
    chats_filter: أسماء جزئية لو عايز جروبات محددة بس.
    """
    if not configured():
        state, hint = status()
        print(f"    - تليجرام (حسابك): {state} — {hint}")
        return []

    days = days if days is not None else config.MAX_AGE_DAYS
    chats_filter = chats_filter or config.TELEGRAM_MY_CHATS or None

    try:
        return asyncio.run(_collect(limit_per_chat, days, only_matching,
                                    chats_filter))
    except Exception as exc:
        print(f"    - تليجرام (حسابك) فشل: {str(exc)[:90]}")
        return []


# ============================================================
#  تسجيل الدخول وسرد الجروبات
# ============================================================

async def _login():
    client = TelegramClient(SESSION, int(API_ID), API_HASH)
    await client.start()
    me = await client.get_me()
    name = getattr(me, "first_name", "") or getattr(me, "username", "")
    print(f"\n✓ تم تسجيل الدخول باسم: {name}")
    print(f"✓ الجلسة اتحفظت في: {SESSION}.session")
    print("  متشاركش الملف ده مع حد ومترفعهوش على git.\n")
    await client.disconnect()


async def _list_chats():
    client = TelegramClient(SESSION, int(API_ID), API_HASH)
    await client.start()
    print("\nالجروبات والقنوات اللي إنت عضو فيها:\n")
    n = 0
    async for dialog in client.iter_dialogs():
        e = dialog.entity
        if isinstance(e, User) or not isinstance(e, (Channel, Chat)):
            continue
        n += 1
        kind = "قناة" if getattr(e, "broadcast", False) else "جروب"
        uname = f" @{e.username}" if getattr(e, "username", None) else " (خاص)"
        print(f"  {n:3}. [{kind}] {getattr(e, 'title', '')}{uname}")
    print(f"\nالإجمالي: {n}")
    print("\nعايز جروبات محددة بس؟ حط أسماءها الجزئية في "
          "TELEGRAM_MY_CHATS في config.py\n")
    await client.disconnect()


def main():
    if not AVAILABLE:
        print("!! telethon مش مثبتة. شغّل: pip install telethon")
        sys.exit(1)
    if not (API_ID and API_HASH):
        print("!! محتاج TELEGRAM_API_ID و TELEGRAM_API_HASH")
        print("   هاتهم من: https://my.telegram.org → API development tools")
        sys.exit(1)

    if "--login" in sys.argv:
        asyncio.run(_login())
    elif "--list" in sys.argv:
        asyncio.run(_list_chats())
    else:
        print(__doc__)
        print("الأوامر:")
        print("  python telegram_client.py --login   تسجيل دخول (مرة واحدة)")
        print("  python telegram_client.py --list    عرض جروباتك وقنواتك")


if __name__ == "__main__":
    main()
