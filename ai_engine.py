# -*- coding: utf-8 -*-
"""
محرك الذكاء الاصطناعي متعدد المزوّدين
======================================
بيجرّب المزوّدين بالترتيب، ولو واحد فشل أو خلص حدّه اليومي ينتقل للي بعده.
كلهم عندهم طبقة مجانية.
"""

import re
import json
import time
import requests

import config


class MultiAI:
    """محرك AI بيبدّل بين أكتر من مزوّد تلقائيًا."""

    def __init__(self, verbose=True):
        self.verbose = verbose
        self.providers = []
        self.stats = {}

        if config.GEMINI_API_KEY:
            self.providers.append(("Gemini", self._call_gemini))
        if config.GROQ_API_KEY:
            self.providers.append(("Groq", self._call_groq))
        if config.CEREBRAS_API_KEY:
            self.providers.append(("Cerebras", self._call_cerebras))
        if config.OPENROUTER_API_KEY:
            self.providers.append(("OpenRouter", self._call_openrouter))

        for name, _ in self.providers:
            self.stats[name] = {"ok": 0, "fail": 0}

    @property
    def available(self):
        return len(self.providers) > 0

    def log(self, msg):
        if self.verbose:
            print(msg)

    # ---------- المزوّدون ----------

    def _call_gemini(self, prompt, system, fast=False):
        model = config.GEMINI_FAST_MODEL if fast else config.GEMINI_MODEL
        url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
               f"{model}:generateContent")
        body = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.3, "maxOutputTokens": 2048},
        }
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        r = requests.post(url, params={"key": config.GEMINI_API_KEY},
                          json=body, timeout=90)
        r.raise_for_status()
        data = r.json()
        return data["candidates"][0]["content"]["parts"][0]["text"]

    def _openai_style(self, url, key, model, prompt, system, extra_headers=None):
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        if extra_headers:
            headers.update(extra_headers)
        r = requests.post(url, headers=headers, json={
            "model": model,
            "messages": messages,
            "temperature": 0.3,
            "max_tokens": 2048,
        }, timeout=90)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]

    def _call_groq(self, prompt, system, fast=False):
        model = config.GROQ_FAST_MODEL if fast else config.GROQ_MODEL
        return self._openai_style(
            "https://api.groq.com/openai/v1/chat/completions",
            config.GROQ_API_KEY, model, prompt, system)

    def _call_cerebras(self, prompt, system, fast=False):
        return self._openai_style(
            "https://api.cerebras.ai/v1/chat/completions",
            config.CEREBRAS_API_KEY, config.CEREBRAS_MODEL, prompt, system)

    def _call_openrouter(self, prompt, system, fast=False):
        return self._openai_style(
            "https://openrouter.ai/api/v1/chat/completions",
            config.OPENROUTER_API_KEY, config.OPENROUTER_MODEL, prompt, system,
            extra_headers={"HTTP-Referer": "https://github.com",
                           "X-Title": "Egypt Real Estate Monitor"})

    # ---------- الواجهة ----------

    def ask(self, prompt, system=None, retries=1, fast=False):
        """
        يسأل أول مزوّد متاح، ولو فشل ينتقل للي بعده.
        fast=True → يستخدم الموديل السريع الرخيص (للفرز على أعداد كبيرة).
        """
        if not self.providers:
            self.log("  [!] لا يوجد أي مفتاح AI — تم تخطي التحليل.")
            return None

        for name, fn in self.providers:
            for attempt in range(retries + 1):
                try:
                    out = fn(prompt, system, fast)
                    if out and out.strip():
                        self.stats[name]["ok"] += 1
                        self.log(f"  [AI:{name}] تم")
                        return out.strip()
                except requests.HTTPError as exc:
                    code = exc.response.status_code if exc.response is not None else "?"
                    if code == 429 and attempt < retries:
                        self.log(f"  [AI:{name}] تجاوز الحد — انتظار 20 ثانية")
                        time.sleep(20)
                        continue
                    self.log(f"  [AI:{name}] فشل ({code}) — تجربة المزوّد التالي")
                    break
                except Exception as exc:
                    self.log(f"  [AI:{name}] خطأ: {str(exc)[:80]}")
                    break
            self.stats[name]["fail"] += 1

        self.log("  [!] كل المزوّدين فشلوا في هذا الطلب.")
        return None

    def ask_json(self, prompt, system=None, fast=False):
        """يطلب رد JSON ويحاول يفكّه."""
        raw = self.ask(prompt, system, fast=fast)
        if not raw:
            return None
        text = raw.strip()
        # إزالة أسوار الكود لو موجودة
        if text.startswith("```"):
            text = text.split("```")[1] if "```" in text[3:] else text[3:]
            if text.startswith("json"):
                text = text[4:]
        text = text.strip().strip("`").strip()
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end == -1:
            start, end = text.find("["), text.rfind("]")
        if start == -1 or end == -1:
            return None
        try:
            return json.loads(text[start:end + 1])
        except Exception:
            return None

    def report(self):
        if not self.stats:
            return "لا يوجد مزوّد AI مفعّل"
        return " · ".join(f"{n}: {s['ok']}✓/{s['fail']}✗" for n, s in self.stats.items())


# ============================================================
#  المهام التحليلية
# ============================================================

SYSTEM_AR = (
    "أنت محلل عقاري مصري محترف متخصص في الفرص المتاحة للمصريين المقيمين بالخارج. "
    "ترد بالعربية المصرية الواضحة، بدقة وإيجاز، وبدون مبالغة أو ترويج. "
    "لا تخترع أرقامًا أو تواريخ غير موجودة في النص المعطى لك. "
    "إذا كانت المعلومة غير متوفرة، قل ذلك صراحة."
)


def summarize_video(ai, title, transcript):
    """يلخص نص فيديو يوتيوب."""
    text = transcript[:14000]
    prompt = f"""ده نص (transcript) فيديو يوتيوب عنوانه: "{title}"

المطلوب:
1. ملخص في 3-4 جمل لأهم اللي اتقال.
2. أهم 3 نقاط عملية تهم مصري مغترب مهتم بالعقارات في مصر.
3. أي أرقام أو مواعيد أو أسعار اتذكرت (لو مفيش، اكتب "لم تُذكر أرقام محددة").

خلي الرد منظم وقصير. النص:

{text}"""
    return ai.ask(prompt, SYSTEM_AR)


def triage(ai, items):
    """
    فرز سريع بموديل رخيص — بيشتغل على كل العناصر.
    بيرجع لكل عنصر: مستوى الأولوية + سبب مختصر.
    ده اللي بيحدد إيه اللي يستاهل إشعار فوري.
    """
    if not ai.available or not items:
        return {}

    listing = "\n".join(f'{i+1}. {it["title"]}' for i, it in enumerate(items))
    prompt = f"""صنّف كل عنوان من دول حسب أهميته لمصري مقيم بالخارج مهتم بالفرص العقارية في مصر.

{listing}

المستويات:
- "urgent" = فيه موعد أو مهلة أو إجراء لازم يتحرك فيه دلوقتي (فتح حجز، كراسة شروط، آخر موعد تحويل، قرار جديد يخصه)
- "important" = معلومة مؤثرة على قراره بس مش عاجلة
- "normal" = خبر عادي أو تكرار أو محتوى ترويجي

رجّع JSON فقط:
{{"1": "urgent", "2": "normal", ...}}

كل الأرقام من 1 لـ {len(items)} لازم تكون موجودة."""

    system = "أنت مصنّف دقيق. ترد بـ JSON صالح فقط بدون أي شرح."
    result = ai.ask_json(prompt, system, fast=True)
    if not isinstance(result, dict):
        return {}

    out = {}
    for key, level in result.items():
        try:
            idx = int(re.sub(r"\D", "", str(key)))
        except Exception:
            continue
        if 1 <= idx <= len(items) and isinstance(level, str):
            lv = level.strip().lower()
            if lv in ("urgent", "important", "normal"):
                out[items[idx - 1]["link"]] = lv
    return out


def analyze_comments(ai, video_title, comments):
    """يحلل كلام الناس في كومنتات الفيديو."""
    if not comments:
        return None
    listing = "\n".join(
        f'- ({c["likes"]} إعجاب) {c["text"][:300]}'
        for c in comments[:25]
    )
    prompt = f"""دي كومنتات الناس على فيديو عنوانه: "{video_title}"
(الرقم بين القوسين = عدد الإعجابات على الكومنت)

{listing}

المطلوب:
1. **إيه اللي الناس بتقوله؟** (2-3 جمل عن المزاج العام والمواضيع المتكررة)
2. **أكتر 3 شكاوى أو مخاوف** اتكررت
3. **معلومات عملية مفيدة** ذكرها ناس من خبرتهم (لو فيه)

مهم: ده كلام ناس على الإنترنت، مش مصدر رسمي — لو حد ذكر معلومة تبدو مهمة نبّه إنها تحتاج تأكيد من مصدر رسمي. خلي الرد قصير ومنظم."""
    return ai.ask(prompt, SYSTEM_AR)


def predict_and_advise(ai, news_items, video_summaries, comment_insights):
    """توقعات وتحليل الأماكن والمكاسب المتوقعة."""
    news_txt = "\n".join(f"- {it['title']}" for it in news_items[:30])
    vids = "\n".join(f"- {t}: {s[:400]}" for t, s in video_summaries[:4])
    talk = "\n".join(f"- {c[:400]}" for c in comment_insights[:3])

    prompt = f"""معلومات متاحة عن السوق العقاري المصري:

الأخبار:
{news_txt}

{"ملخصات فيديوهات تحليلية:" if vids else ""}
{vids}

{"كلام الناس في التعليقات:" if talk else ""}
{talk}

بصفتك محلل عقاري، اكتب تحليلًا استشرافيًا بالأقسام دي بالظبط وبنفس العناوين:

## قراءة الوضع
(3-4 جمل: السوق رايح فين بناءً على المعطيات اللي فوق)

## أماكن تستحق المتابعة
(لكل مكان: الاسم، ليه مرشح، وإيه اللي ممكن يعطّله — 3-5 أماكن)

## سيناريوهات محتملة
(3 سيناريوهات: متفائل / الأرجح / متحفظ — وإيه المؤشر اللي يقول إن كل واحد بيحصل)

## إشارات إنذار
(علامات لو ظهرت تبقى تحذير حقيقي)

## لو كنت مكانك
(إيه الأسئلة اللي المفروض تجاوب عليها قبل ما تاخد قرار — مش نصيحة بالشراء)

قواعد صارمة:
- ده تحليل اجتهادي مبني على المعطيات فوق، وضّح ده.
- ماتخترعش أرقام أو نسب مش موجودة في المعطيات.
- ماتقولش "اشتري" أو "متشتريش" — اعرض الاعتبارات وسيب القرار له.
- لو المعطيات مش كفاية لاستنتاج، قول كده صراحة."""
    return ai.ask(prompt, SYSTEM_AR)


def analyze_news_batch(ai, items):
    """يصنّف الأخبار ويحدد الأهم منها."""
    listing = "\n".join(
        f'{i+1}. {it["title"]} [{it.get("source","")}]'
        for i, it in enumerate(items)
    )
    prompt = f"""دي عناوين أخبار عقارية مصرية من آخر فترة:

{listing}

رجّعلي JSON بالشكل ده بالظبط ومن غير أي كلام قبله أو بعده:
{{
  "top": [أرقام أهم 5 أخبار لمصري مغترب مهتم بالعقارات، مرتبة من الأهم],
  "urgent": [أرقام الأخبار اللي فيها موعد أو مهلة قريبة لازم يتحرك فيها بسرعة],
  "themes": ["أهم 3 مواضيع متكررة في الأخبار دي"]
}}"""
    return ai.ask_json(prompt, SYSTEM_AR)


def write_executive_brief(ai, news_items, video_summaries):
    """يكتب الملخص التنفيذي والتحليل العام للصفحة."""
    news_txt = "\n".join(f"- {it['title']}" for it in news_items[:30])
    vids = "\n\n".join(f"فيديو: {t}\n{s[:900]}" for t, s in video_summaries)

    prompt = f"""دي أخبار عقارية مصرية حديثة:
{news_txt}

{"وده ملخص فيديوهات تحليلية:" if vids else ""}
{vids}

اكتب تقرير موجز بالعربية المصرية لمصري مغترب مهتم يستغل فرص العقارات في مصر، بالأقسام دي بالظبط وبنفس العناوين:

## الوضع الحالي
(3-4 جمل عن أهم اللي بيحصل دلوقتي)

## فرص تستاهل الانتباه
(نقاط قصيرة - إيه المتاح فعليًا ومواعيده لو مذكورة)

## مخاطر وتحذيرات
(نقاط قصيرة - أي حاجة لازم ياخد باله منها)

## الخلاصة
(جملتين: إيه أهم حاجة يعملها دلوقتي)

قواعد مهمة: اعتمد فقط على المعلومات اللي فوق، ماتخترعش أرقام أو تواريخ، وماتديش نصيحة استثمارية مباشرة — اعرض المعلومة وخليه هو يقرر."""
    return ai.ask(prompt, SYSTEM_AR)
