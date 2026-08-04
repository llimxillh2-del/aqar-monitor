# -*- coding: utf-8 -*-
"""فحص ذاتي للإصلاحات — python selftest.py"""
from datetime import datetime, timezone, timedelta
import render, sources, monitor, beit_alwatan, quality, watcher

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    mark = "✅" if cond else "❌"
    print("   " + mark + " " + name + (("  → " + str(detail)) if detail else ""))


now = datetime.now(timezone.utc)
line = "=" * 56

print(line)
print("1) صيغ الوقت العربية")
for h, e in [(1, "منذ ساعة"), (2, "منذ ساعتين"), (5, "منذ 5 ساعات"), (12, "منذ 12 ساعة")]:
    g = render.ago((now - timedelta(hours=h, minutes=1)).isoformat())
    check(str(h) + " ساعة", g == e, g)
for d, e in [(1, "أمس"), (2, "منذ يومين"), (3, "منذ 3 أيام"), (5, "منذ 5 أيام"), (16, "منذ 16 يومًا")]:
    g = render.ago((now - timedelta(days=d, minutes=1)).isoformat())
    check(str(d) + " يوم", g == e, g)

print(line)
print("2) توقيت مصر (صيفي/شتوي)")
for m, e in [(1, 2), (6, 3), (8, 3), (12, 2)]:
    g = render.egypt_offset(datetime(2026, m, 15, tzinfo=timezone.utc))
    check("شهر " + str(m), g == e, "UTC+" + str(g))

print(line)
print("3) تقسيم رسائل تليجرام")
r = monitor._split_message("short\n" + "X" * 30, 12)
check("الترتيب محفوظ", r[0].startswith("short"), r)
r2 = monitor._split_message("<b>hello world this is bold</b>", 15)
check("وسوم HTML مقفولة",
      all(c.count("<b>") == c.count("</b>") for c in r2), r2)

print(line)
print("4) رموز HTML في الملخص")
s = sources._strip_html('<a href="#">طرح أراضي مسكن 7</a>&nbsp;&nbsp;<font>الوطن</font>')
check("اتفكت &nbsp;", "&nbsp;" not in s, s)
check("الملخص المكرر يترمى",
      sources._useful_snippet(s, "طرح أراضي مسكن 7") == "")

print(line)
print("5) فلتر المصادر")
for title, src, want in [
        ("السجل العقاري السعودي يتوسع في مكة وجدة", "almotawwer.com", False),
        ("بيت الوطن.. موعد فتح الحجز للمصريين بالخارج", "اليوم السابع", True)]:
    it = {"title": title, "source": src, "link": "https://x/1", "snippet": ""}
    got = quality.source_tier(src, "https://x/1") < 4 and quality.is_probably_egyptian(it)
    check(title[:38], got == want, "عدّى" if got else "اترمى")

print(line)
print("6) صفحة بيت الوطن")
today = now.date().isoformat()
st = {"facts": {"المرحلة_الحالية": {"value": "المرحلة 11"},
                "موعد_القرعة": {"value": today},
                "شروط_التقديم": {"value": "بطاقة + جواز"}},
      "cities": {"بدر": 3},
      "checklist": ["جهّز مستنداتك.", "راجع كراسة الشروط."]}
d = beit_alwatan.dashboard(st)
page = render.build_beit_page(d, "eng")
check("الخطوات تتعرض كقائمة", '<ol class="steps">' in page)
check("مفيش ليستة بايثون خام", "[" + chr(39) + "جهّز" not in page)
check("موعد النهاردة = قادم", d["dates"][0]["status"] == "قادم",
      str(d["dates"][0]["days_left"]) + " يوم")
check("payment مش نسخة من conditions", d["payment"] != d["conditions"])

print(line)
print("7) بناء الصفحات ورسالة تليجرام")
secs = {"بيت الوطن ومبادرات المغتربين": [
    {"title": "خبر", "link": "https://a/1", "source": "الأهرام", "snippet": "",
     "published": now.isoformat(), "published_ts": now.timestamp(), "kind": "news"}]}
h = render.build_index(secs, None, {"https://a/1"}, set(), set(), "eng", beit=d,
                       market_rows=[], health_rows=[], official_changes=[],
                       intel=None, now_digest=None)
check("index.html اتبنى", len(h) > 5000, str(len(h)) + " حرف")
msgs = render.build_unified_telegram(new_by_section=secs, beit=d, counts={"new": 1},
                                     engines="e", site_links=[("a", "http://b")])
check("كل جزء تحت حد التقسيم", all(len(x) <= 3600 for x in msgs),
      [len(x) for x in msgs])

print(line)
print("8) ذاكرة المشاهَد")
out = monitor._trim_seen(["link" + str(i) for i in range(10)],
                         [{"link": "NEW-1"}, {"link": "NEW-2"}])
check("الأحدث في الآخر", out[-1] == "NEW-2" and "link0" in out)

print(line)
print("9) رابط التغيير الرسمي")
a = watcher.changes_to_items([{"name": "n", "url": "https://u", "added": ["سطر أ"],
                              "when": now.isoformat()}])
b = watcher.changes_to_items([{"name": "n", "url": "https://u", "added": ["سطر ب"],
                              "when": now.isoformat()}])
check("كل تغيير له رابط فريد", a[0]["link"] != b[0]["link"], a[0]["link"][-14:])

print(line)
print("النتيجة: " + str(len(PASS)) + " نجح · " + str(len(FAIL)) + " فشل")
if FAIL:
    print("الفاشل: " + " | ".join(FAIL))
