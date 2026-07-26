# 🏛️ مرصد العقارات المصرية للمغتربين

نظام **مستقل تمامًا** بيشتغل على سيرفرك، بيدور كل 4 ساعات على أخبار العقارات المصرية، بيلخصها ويحللها بالذكاء الاصطناعي، وبيطلعلك:

- 📄 **صفحة ويب** (`index.html`) فيها ملخص تنفيذي + الأخبار مصنّفة
- 📱 **رسالة تليجرام** بالجديد بس (مش بيكرر نفس الخبر)

---

## إيه اللي بيتابعه؟

| المصدر | الحالة | ملاحظات |
|---|---|---|
| **🏛️ المصادر الرسمية — رصد التغيير** | ✅ شغال | **بيعرف قبل الجرايد** |
| Google News (كل المواقع المصرية) | ✅ شغال | مجاني بدون مفتاح |
| يوتيوب — قنوات محددة | ✅ شغال | RSS رسمي مجاني |
| يوتيوب — بحث | ✅ شغال | يحتاج مفتاح مجاني |
| **تلخيص الفيديوهات بالـ AI** | ✅ شغال | بيقرا نص الفيديو ويلخصه |
| **كومنتات يوتيوب + تحليل كلام الناس** | ✅ شغال | أعلى الكومنتات تفاعلًا + تحليل المزاج العام |
| **إحصائيات التفاعل** | ✅ شغال | مشاهدات/لايكات/كومنتات + ترتيب بالأسخن |
| **توقعات وتحليل أماكن** | ✅ شغال | سيناريوهات + إشارات إنذار |
| أي موقع فيه RSS | ✅ شغال | تضيفه في `EXTRA_RSS` |
| X / فيسبوك / إنستجرام / تيك توك | ⚠️ محدود | اقرا [قسم السوشيال](#السوشيال-ميديا) |

### 🏛️ رصد المصادر الرسمية — أهم ميزة

بدل انتظار الجرايد، النظام بيحفظ **بصمة** كل صفحة رسمية وبيقارنها كل دورة. أول ما الصفحة تتغير، بيطلع **السطور الجديدة بالظبط** ويبعتلك تنبيه فوري — من غير ما يستنى الدورة الجاية.

الصفحات المراقَبة (في `WATCH_PAGES`):

- هيئة المجتمعات العمرانية — الأخبار والرئيسية
- منصة مصر العقارية
- بيتك في مصر

لو ظهرت كلمة زي «طرح» أو «الحجز» أو «كراسة الشروط» في التغيير → 🚨 إنذار أحمر فوري.

### 📋 ذاكرة السوق

ملف `market_state.json` بيتتبع حالة كل مشروع (المرحلة، الحالة، الموعد القادم، آخر تطور). كل دورة النظام بيقارن الحالة الجديدة بالقديمة ويبعتلك **إيه اللي اتغير فعلًا** — مش يعيد نفس العناوين. ده اللي بيخليه فاهم السوق بدل ما يبقى قارئ أخبار.

### ⚡ الفرز على سرعتين

- **موديل سريع رخيص** بيفرز كل العناصر الجديدة: عاجل / مهم / عادي
- **موديل قوي** بيشتغل على المهم بس: تحليل، توقعات، كلام الناس

كده تفضل داخل الحد المجاني والتحليل يفضل عميق.

### القنوات المتابَعة افتراضيًا

- [الاسكان مع عمر مخلوف](https://www.youtube.com/@dromarmakhlouf) — `UCTRxog2J5dFMIiDqDvc4DYw`
- [الإسكان مع عمرو زكي](https://www.youtube.com/@amr_zaky) — `UC68MAMp5g8Lft48Knm3pheg`
- [كلام في المفيد — هاني الخميسي](https://www.youtube.com/@hanyelkhamisi) — `UCl3L_aO3A1-nqQhBRFtbcnw` (مستشار قانوني وعقاري)
- عقارات — `UCGiEiZDpqoyfXUcWmTrLfWw`
- elwakil immobilier — `UC2Oea1tnYIPAEIF9sqebRNw`

تضيف قناة جديدة في `config.py`:
```python
YOUTUBE_CHANNELS = [
    ("اسم القناة", "UCxxxxxxxxxxxxxxxxxxxxxx"),
]
```
> لاستخراج الـ ID: افتح القناة → `Ctrl+U` → ابحث عن `channelId`

### مهم: مفتاح يوتيوب

الكومنتات والإحصائيات **محتاجة `YOUTUBE_API_KEY`** (مجاني، 10,000 وحدة/يوم):
[console.cloud.google.com](https://console.cloud.google.com) → مشروع جديد → فعّل **YouTube Data API v3** → **Credentials → API key**

من غير المفتاح: الفيديوهات هتظهر وتتلخص عادي، بس بدون كومنتات ولا أرقام تفاعل.

## محركات الذكاء الاصطناعي

بيستخدم **أكتر من AI بالتبديل التلقائي** — لو واحد فشل أو خلص حده اليومي، بينتقل للي بعده لوحده:

| المزوّد | الطبقة المجانية | التسجيل |
|---|---|---|
| **Google Gemini** | ~1500 طلب/يوم | [aistudio.google.com](https://aistudio.google.com/apikey) |
| **Groq** | ~14,400 طلب/يوم، سريع جدًا | [console.groq.com](https://console.groq.com/keys) |
| **Cerebras** | 1M توكن/يوم | [cloud.cerebras.ai](https://cloud.cerebras.ai) |
| **OpenRouter** | 50-1000 طلب/يوم، موديلات متعددة | [openrouter.ai/keys](https://openrouter.ai/keys) |

> محتاج **واحد على الأقل**. لو حطيت أكتر، النظام يبقى أثبت. كلهم بدون بطاقة ائتمان.
>
> ⚠️ الحدود دي بتتغير باستمرار — راجع موقع كل مزوّد.

---

## الملفات

| الملف | وظيفته |
|---|---|
| `config.py` | **كل الإعدادات هنا** — ده اللي هتعدل فيه |
| `monitor.py` | المشغّل الأساسي (الجمع والتحليل والتنبيه) |
| `bot.py` | **بوت تليجرام التفاعلي** (يشتغل بالتوازي) |
| `watcher.py` | رصد تغيّر المصادر الرسمية |
| `market_state.py` | ذاكرة السوق |
| `sources.py` | جلب الأخبار والفيديوهات والكومنتات |
| `ai_engine.py` | محرك الـ AI متعدد المزوّدين |
| `render.py` | توليد الصفحة ورسالة تليجرام |
| `test_system.py` | اختبار شامل بدون إنترنت (28 اختبار) |
| `preview.py` | توليد معاينة للتصميم |
| ملفات تتولد تلقائيًا | `seen.json` · `summaries.json` · `watch_state.json` · `market_state.json` · `latest.json` · `index.html` |

## البوت التفاعلي

`bot.py` بيشتغل بالتوازي مع `monitor.py` وبيرد على أوامرك:

| الأمر | بيعمل إيه |
|---|---|
| `/الحالة` | حالة كل مشروع دلوقتي والمواعيد القادمة |
| `/الملخص` | الملخص التنفيذي |
| `/التوقعات` | قراءة السوق والأماكن والسيناريوهات |
| `/عاجل` | آخر الأخبار العاجلة |
| `/الاهم` | أهم الأخبار |
| `/تحديث` | تشغيل دورة فحص فورًا |
| **أي سؤال عادي** | الـ AI يرد عليه من آخر بيانات |

```bash
python monitor.py     # في تيرمينال
python bot.py         # في تيرمينال تاني
```

---

## الخطوة 1 — بوت تليجرام (5 دقايق)

1. افتح تليجرام ودوّر على **@BotFather**
2. ابعتله `/newbot` → اختار اسم → اختار username ينتهي بـ `bot`
3. هيديك **توكن** شكله: `7123456789:AAF...`
4. ابعت `/start` للبوت اللي عملته
5. افتح ده في المتصفح (حط التوكن مكان `<TOKEN>`):
   `https://api.telegram.org/bot<TOKEN>/getUpdates`
6. دوّر على `"chat":{"id":123456789` — الرقم ده **Chat ID** بتاعك

## الخطوة 2 — مفتاح AI (دقيقتين)

ادخل [aistudio.google.com/apikey](https://aistudio.google.com/apikey) → **Create API key** → انسخه.

(اختياري: كرر مع Groq عشان يبقى عندك احتياطي)

## الخطوة 3 — جرّب على جهازك

محتاج Python 3.9+

```bash
pip install -r requirements.txt
```

**ويندوز (PowerShell):**
```powershell
$env:TELEGRAM_TOKEN="التوكن"
$env:TELEGRAM_CHAT_ID="الرقم"
$env:GEMINI_API_KEY="مفتاح-جيميني"
$env:YOUTUBE_API_KEY="مفتاح-يوتيوب"
python monitor.py --once
```

**لينكس / ماك:**
```bash
export TELEGRAM_TOKEN="التوكن"
export TELEGRAM_CHAT_ID="الرقم"
export GEMINI_API_KEY="مفتاح-جيميني"
export YOUTUBE_API_KEY="مفتاح-يوتيوب"
python3 monitor.py --once
```

لو كل حاجة تمام: هيتولد `index.html` وتوصلك رسالة تليجرام.

> عايز تتأكد إن الكود سليم قبل ما تشغله؟ `python test_system.py` — بيشتغل بدون إنترنت.

---

## الخطوة 4 — خليه يشتغل 24/7

### ⭐ الأفضل: GitHub Actions (مجاني بالكامل + موقع مجاني)

1. اعمل repo جديد على GitHub وارفع الملفات
2. **Settings → Secrets and variables → Actions → New repository secret**، ضيف:
   - `TELEGRAM_TOKEN`
   - `TELEGRAM_CHAT_ID`
   - `GEMINI_API_KEY`
3. اعمل ملف `.github/workflows/monitor.yml`:

```yaml
name: Real Estate Monitor
on:
  schedule:
    - cron: '0 */4 * * *'
  workflow_dispatch:

permissions:
  contents: write

jobs:
  run:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install -r requirements.txt
      - run: python monitor.py --once
        env:
          TELEGRAM_TOKEN:   ${{ secrets.TELEGRAM_TOKEN }}
          TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}
          GEMINI_API_KEY:   ${{ secrets.GEMINI_API_KEY }}
          GROQ_API_KEY:     ${{ secrets.GROQ_API_KEY }}
          YOUTUBE_API_KEY:  ${{ secrets.YOUTUBE_API_KEY }}
      - name: حفظ النتائج
        run: |
          git config user.name "monitor-bot"
          git config user.email "bot@users.noreply.github.com"
          git add -A seen.json summaries.json index.html
          git diff --staged --quiet || git commit -m "تحديث تلقائي"
          git push
```

4. **Settings → Pages → Source: Deploy from a branch → main / (root)**

خلاص. دلوقتي عندك:
- موقع حقيقي على `https://USERNAME.github.io/REPO/` بيتحدث كل 4 ساعات لوحده
- رسايل تليجرام بالجديد
- التكلفة: **صفر**

> ⚠️ نص فيديوهات يوتيوب أحيانًا بيتحجب من سيرفرات GitHub. لو حصل، التلخيص بس اللي هيتأثر — باقي النظام هيفضل شغال.

### بديل: Railway

1. حساب على [railway.app](https://railway.app)
2. **New Project → Deploy from GitHub repo**
3. من **Variables** ضيف المفاتيح
4. **Settings → Start Command**: `python monitor.py`

---

## التخصيص

كل حاجة في `config.py`:

```python
INTERVAL_HOURS = 4              # كل كام ساعة
MAX_VIDEOS_TO_SUMMARIZE = 4     # كام فيديو يتلخص في الدورة
```

**تضيف مواضيع تتابعها:**
```python
NEWS_SECTIONS = {
    "بيت الوطن ومبادرات المغتربين": [
        "بيت الوطن المصريين بالخارج",
        "عبارة بحث جديدة",       # ← ضيف هنا
    ],
}
```

**تتابع قناة يوتيوب معينة:** هات الـ Channel ID (افتح القناة → `Ctrl+U` → دوّر على `channelId`):
```python
YOUTUBE_CHANNELS = ["UCxxxxxxxxxxxxxxxxxxxxxx"]
```

**أخبار معينة تطلع فوق:** ضيف كلمات في `PRIORITY_WORDS`.

---

## السوشيال ميديا

**الوضع بصراحة:**

| المنصة | المشكلة |
|---|---|
| **X (تويتر)** | الـ API بقى مدفوع (~$100/شهر). الطبقة المجانية للنشر بس. |
| **إنستجرام** | مفيش API لمتابعة حسابات الغير. الـ scraping بيتبلوك بسرعة. |
| **تيك توك** | نفس المشكلة، والمكتبات غير الرسمية بتتعطل باستمرار. |
| **فيسبوك** | الـ Graph API للصفحات اللي أنت أدمن عليها بس. الجروبات ممنوعة تمامًا. |

**الحل الجزئي — RSSHub:** مشروع مفتوح المصدر بيحوّل صفحات المنصات لـ RSS.

```python
SOCIAL_FEEDS = [
    {"name": "حساب عقاري", "path": "/twitter/user/USERNAME"},
    {"name": "صفحة فيسبوك", "path": "/facebook/page/PAGENAME"},
]
```

⚠️ النسخة العامة (`rsshub.app`) بتتحجب من المنصات كتير. للثبات شغّل نسخة خاصة بيك:
```bash
docker run -d -p 1200:1200 diygod/rsshub
```
وبعدين `RSSHUB_BASE = "http://localhost:1200"`

**نصيحة عملية:** معظم التحليل العقاري المصري الجاد موجود على **يوتيوب** (وده مغطى بالكامل) وفي **المواقع الإخبارية** (مغطاة كمان). السوشيال إضافة، مش الأساس.

---

## مشاكل شائعة

| المشكلة | الحل |
|---|---|
| مفيش رسايل تليجرام | تأكد إنك بعت `/start` للبوت الأول |
| `[!] لا يوجد مفتاح AI` | متغير البيئة مش متظبط — تأكد من الاسم بالظبط |
| كل الأخبار جتلي مرة واحدة | طبيعي في أول تشغيل. بعد كده الجديد بس. |
| عايز أعيد كل حاجة | امسح `seen.json` |
| فيديوهات مش بتتلخص | الفيديو مالوش ترجمة، أو الـ IP متحجب (جرّب من جهازك) |

---

## ⚖️ تنويه

المحتوى بيتجمع آليًا ويتلخص بالذكاء الاصطناعي — **قابل للخطأ**، وارجع للمصدر الأصلي دايمًا.

ده **مش استشارة مالية أو قانونية**. قبل أي التزام مالي راجع:
- [كراسة الشروط الرسمية — هيئة المجتمعات العمرانية](https://lands.nuca.gov.eg/)
- [منصة مصر العقارية](https://reservations.realestate.gov.eg/ar)

واستشر متخصص عقاري أو قانوني موثوق.
