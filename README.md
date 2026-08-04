# 🏛️ مرصد العقارات المصرية

رصد آلي لفرص العقارات المتاحة للمصريين بالخارج — أخبار، مصادر رسمية، يوتيوب،
وكلام الناس في التعليقات. بيطلّع صفحتين ثابتتين ورسالة تليجرام كل دورة.

**الموقع:** https://llimxillh2-del.github.io/aqar-monitor

---

## طبقات الرصد

| الطبقة | المصدر | الوتيرة |
|---|---|---|
| المصادر الرسمية | هيئة المجتمعات · مصر العقارية · وزارة الإسكان | كل ساعة |
| الأخبار | Google News (3 أقسام) | كل 4 ساعات |
| الفيديوهات | 4 قنوات يوتيوب + بحث | كل 4 ساعات |
| رادار الإشارات | تعليقات يوتيوب · تليجرام · Reddit | كل 4 ساعات |
| السوق المجتمعي | bit.mzayasoft (مقدمات وإعلانات حقيقية) | كل ساعة |

---

## التشغيل على GitHub Actions (الموصى به)

### 1. الأسرار المطلوبة
`Settings` → `Secrets and variables` → `Actions`:

| الاسم | إجباري | من فين |
|---|---|---|
| `TELEGRAM_TOKEN` | ✅ | @BotFather → `/mybots` → API Token |
| `TELEGRAM_CHAT_ID` | ✅ | @userinfobot → اضغط Start |
| `GROQ_API_KEY` | ✅ | console.groq.com/keys |
| `YOUTUBE_API_KEY` | مهم | console.cloud.google.com → YouTube Data API v3 |
| `GEMINI_API_KEY` | اختياري | aistudio.google.com/apikey |

> التوكن **من غير** أقواس `< >` ومن غير كلمة `bot` ومن غير مسافات.
> طوله المفروض 46 حرف — الـ workflow بيتحقق من ده ويحذّرك.

### 2. تفعيل النشر
`Settings` → `Pages` → **Source: GitHub Actions**

### 3. أول تشغيل
`Actions` → `مرصد العقارات المصرية` → `Run workflow` → `once`

---

## التشغيل محليًا

```bash
pip install -r requirements.txt
cp .env.example .env        # واملا المفاتيح
python selftest.py          # فحص ذاتي — لازم 27 نجح · 0 فشل
```

| الأمر | إيه بيعمل |
|---|---|
| `python monitor.py --sources` | تشخيص كل مصدر: مين شغال ومين لأ وليه |
| `python monitor.py --test` | دورة كاملة بدون AI وبدون تليجرام |
| `python monitor.py --once` | الدورة الكاملة |
| `python monitor.py --fast-check` | سريع بدون AI — بيت الوطن + رسمي + إعلانات |
| `python monitor.py --watch` | المصادر الرسمية بس |
| `python monitor.py --daemon` | مستمر |
| `python bot.py` | بوت تليجرام التفاعلي |

خيارات إضافية: `--no-telegram` · `--no-ai` · `--force`

---

## المخرجات

```
index.html          التقرير العام
beit-alwatan.html   ملف بيت الوطن التفصيلي
latest.json         بيانات منظمة (بيقراها bot.py)
state/*.json        ذاكرة النظام — متمسحهاش
```

---

## حدود لازم تعرفها

- **نصوص اليوتيوب** مش بتشتغل على سيرفرات GitHub (يوتيوب بيحجب IPs الداتا سنتر).
  التلخيص بالـ AI محتاج تشغيل محلي.
- **Reddit** بيرجّع 403 من GitHub لنفس السبب.
- **الجدولة best-effort** — GitHub ممكن يأخّر التشغيلة 5-30 دقيقة.
- **بعد 60 يوم** من غير نشاط بشري في الريبو، GitHub بيوقف الجدولة. اعمل
  `git push` بسيط كل شهرين.
- **`bit.mzayasoft` مصدر مجتمعي غير رسمي** — بياناته موسومة كده في الصفحة.

---

## تنويه

كل المحتوى مستخرج آليًا ومُلخَّص بالذكاء الاصطناعي و**قابل للخطأ**.
راجع كراسة الشروط الرسمية ومنصة مصر العقارية قبل أي التزام مالي.
