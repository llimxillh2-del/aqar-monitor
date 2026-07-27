# -*- coding: utf-8 -*-
"""
محرك الذكاء الاصطناعي متعدد المزوّدين
======================================
بيجرّب المزوّدين بالترتيب، ولو واحد فشل أو خلص حدّه اليومي ينتقل للي بعده.
كلهم عندهم طبقة مجانية.

إصلاحات مهمة عن النسخة القديمة:
  • Gemini 2.5 بيستهلك توكنز في "التفكير" — بنقفلها عشان الرد ما يرجعش فاضي.
  • قراءة رد Gemini بقت محصّنة (كانت بترمي KeyError لو finishReason=MAX_TOKENS).
  • كل المزوّدين بقوا يحترموا fast=True (قبل كده Cerebras/OpenRouter كانوا
    بيستخدموا الموديل الكبير في الفرز السريع ويحرقوا الحد المجاني).
  • احترام Retry-After عند 429.
"""

import re
import json
import time
import requests

import config


class ProviderError(Exception):
    """فشل مزوّد معيّن — بننتقل للي بعده."""


class MultiAI:
    """محرك AI بيبدّل بين أكتر من مزوّد تلقائيًا."""

    def __init__(self, verbose=True):
        self.verbose = verbose
        self.providers = []
        self.stats = {}
        self.disabled = set()      # مزوّدين فشلوا فشل دائم (401/403) — بنوقفهم للدورة كلها

        # الترتيب: Groq الأول (سريع وحدّه اليومي عالي)، وبعده الباقي
        if config.GROQ_API_KEY:
            self.providers.append(("Groq", self._call_groq))
        if config.GEMINI_API_KEY:
            self.providers.append(("Gemini", self._call_gemini))
        if config.CEREBRAS_API_KEY:
            self.providers.append(("Cerebras", self._call_cerebras))
        if config.OPENROUTER_API_KEY:
            self.providers.append(("OpenRouter", self._call_openrouter))

        for name, _ in self.providers:
            self.stats[name] = {"ok": 0, "fail": 0}

    @property
    def available(self):
        return any(n not in self.disabled for n, _ in self.providers)

    @property
    def names(self):
        return [n for n, _ in self.providers]

    def log(self, msg):
        if self.verbose:
            print(msg)

    # ------------------------------------------------------------------
    #  المزوّدون
    # ------------------------------------------------------------------

    def _call_gemini(self, prompt, system, fast=False):
        model = config.GEMINI_FAST_MODEL if fast else config.GEMINI_MODEL
        url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
               f"{model}:generateContent")
        body = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.3,
                "maxOutputTokens": config.AI_MAX_TOKENS,
            },
        }
        if config.GEMINI_DISABLE_THINKING:
            body["generationConfig"]["thinkingConfig"] = {"thinkingBudget": 0}
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}

        r = requests.post(url, params={"key": config.GEMINI_API_KEY},
                          json=body, timeout=90)
        r.raise_for_status()
        data = r.json()

        candidates = data.get("candidates") or []
        if not candidates:
            block = (data.get("promptFeedback") or {}).get("blockReason")
            raise ProviderError(f"رد فاضي{' — محجوب: ' + block if block else ''}")

        cand = candidates[0]
        parts = (cand.get("content") or {}).get("parts") or []
        text = "".join(p.get("text", "") for p in parts)
        if not text.strip():
            raise ProviderError(f"رد فاضي (finishReason={cand.get('finishReason')})")
        return text

    def _openai_style(self, url, key, model, prompt, system, extra_headers=None):
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        headers = {"Authorization": f"Bearer {key}",
                   "Content-Type": "application/json"}
        if extra_headers:
            headers.update(extra_headers)

        r = requests.post(url, headers=headers, json={
            "model": model,
            "messages": messages,
            "temperature": 0.3,
            "max_tokens": config.AI_MAX_TOKENS,
        }, timeout=90)
        r.raise_for_status()

        data = r.json()
        choices = data.get("choices") or []
        if not choices:
            raise ProviderError(f"رد بدون choices: {str(data)[:120]}")
        content = (choices[0].get("message") or {}).get("content") or ""
        if not content.strip():
            raise ProviderError("رد فاضي")
        return content

    def _call_groq(self, prompt, system, fast=False):
        model = config.GROQ_FAST_MODEL if fast else config.GROQ_MODEL
        return self._openai_style(
            "https://api.groq.com/openai/v1/chat/completions",
            config.GROQ_API_KEY, model, prompt, system)

    def _call_cerebras(self, prompt, system, fast=False):
        model = config.CEREBRAS_FAST_MODEL if fast else config.CEREBRAS_MODEL
        return self._openai_style(
            "https://api.cerebras.ai/v1/chat/completions",
            config.CEREBRAS_API_KEY, model, prompt, system)

    def _call_openrouter(self, prompt, system, fast=False):
        model = config.OPENROUTER_FAST_MODEL if fast else config.OPENROUTER_MODEL
        return self._openai_style(
            "https://openrouter.ai/api/v1/chat/completions",
            config.OPENROUTER_API_KEY, model, prompt, system,
            extra_headers={"HTTP-Referer": "https://github.com",
                           "X-Title": "Egypt Real Estate Monitor"})

    # ------------------------------------------------------------------
    #  الواجهة
    # ------------------------------------------------------------------

    def ask(self, prompt, system=None, retries=1, fast=False):
        """
        يسأل أول مزوّد متاح، ولو فشل ينتقل للي بعده.
        fast=True → يستخدم الموديل السريع الرخيص.
        """
        if not self.providers:
            self.log("  [!] لا يوجد أي مفتاح AI — تم تخطي التحليل.")
            return None

        for name, fn in self.providers:
            if name in self.disabled:
                continue

            for attempt in range(retries + 1):
                try:
                    out = fn(prompt, system, fast)
                    if out and out.strip():
                        self.stats[name]["ok"] += 1
                        self.log(f"  [AI:{name}] تم")
                        return out.strip()
                    raise ProviderError("رد فاضي")

                except requests.HTTPError as exc:
                    resp = exc.response
                    code = resp.status_code if resp is not None else 0

                    if code in (401, 403):
                        self.disabled.add(name)
                        self.log(f"  [AI:{name}] المفتاح مرفوض ({code}) — "
                                 f"تم إيقافه لباقي الدورة")
                        break

                    if code == 429 and attempt < retries:
                        wait = 20
                        try:
                            wait = min(int(float(
                                resp.headers.get("Retry-After", 20))), 60)
                        except (TypeError, ValueError):
                            pass
                        self.log(f"  [AI:{name}] تجاوز الحد — انتظار {wait}ث")
                        time.sleep(wait)
                        continue

                    if code >= 500 and attempt < retries:
                        time.sleep(3)
                        continue

                    self.log(f"  [AI:{name}] فشل ({code}) — المزوّد التالي")
                    break

                except (requests.Timeout, requests.ConnectionError) as exc:
                    if attempt < retries:
                        time.sleep(3)
                        continue
                    self.log(f"  [AI:{name}] شبكة: {str(exc)[:70]}")
                    break

                except Exception as exc:
                    self.log(f"  [AI:{name}] خطأ: {str(exc)[:90]}")
                    break

            self.stats[name]["fail"] += 1

        self.log("  [!] كل المزوّدين فشلوا في هذا الطلب.")
        return None

    # ---------- JSON ----------

    @staticmethod
    def _strip_fences(text):
        """يشيل ```json ... ``` بشكل سليم مهما كانت الصيغة."""
        t = text.strip()
        m = re.search(r"```(?:json|JSON)?\s*(.*?)\s*```", t, re.S)
        if m:
            return m.group(1).strip()
        if t.startswith("```"):
            t = t[3:]
            if t[:4].lower() == "json":
                t = t[4:]
        return t.strip().strip("`").strip()

    def ask_json(self, prompt, system=None, fast=False, retries=1):
        """يطلب رد JSON ويحاول يفكّه بأكتر من طريقة."""
        raw = self.ask(prompt, system, fast=fast, retries=retries)
        if not raw:
            return None

        text = self._strip_fences(raw)

        # محاولة مباشرة
        try:
            return json.loads(text)
        except Exception:
            pass

        # قص أول/آخر قوس
        for opener, closer in (("{", "}"), ("[", "]")):
            start, end = text.find(opener), text.rfind(closer)
            if start != -1 and end > start:
                chunk = text[start:end + 1]
                try:
                    return json.loads(chunk)
                except Exception:
                    # إصلاح الفواصل الزائدة قبل قوس الإغلاق
                    fixed = re.sub(r",\s*([}\]])", r"\1", chunk)
                    try:
                        return json.loads(fixed)
                    except Exception:
                        continue

        self.log("  [!] الرد مش JSON صالح — تم تجاهله.")
        return None

    def report(self):
        if not self.stats:
            return "لا يوجد مزوّد AI مفعّل"
        parts = []
        for n, s in self.stats.items():
            tag = " (موقوف)" if n in self.disabled else ""
            parts.append(f"{n}: {s['ok']}✓/{s['fail']}✗{tag}")
        return " · ".join(parts)


# ============================================================
#  المهام التحليلية
# ============================================================

SYSTEM_AR = (
    "أنت محلل عقاري مصري محترف متخصص في الفرص المتاحة للمصريين المقيمين بالخارج. "
    "ترد بالعربية المصرية الواضحة، بدقة وإيجاز، وبدون مبالغة أو ترويج. "
    "لا تخترع أرقامًا أو تواريخ غير موجودة في النص المعطى لك. "
    "إذا كانت المعلومة غير متوفرة، قل ذلك صراحة."
)

SYSTEM_JSON = (
    "أنت محرر بيانات دقيق. ترد بـ JSON صالح فقط، بدون أي نص قبله أو بعده "
    "وبدون أسوار كود. لا تخترع معلومات غير موجودة في النص المعطى لك. "
    "إذا لم تجد معلومة، استخدم null."
)


def summarize_video(ai, title, transcript):
    """يلخص نص فيديو يوتيوب."""
    text = (transcript or "")[:14000]
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
    فرز سريع بموديل رخيص على كل العناصر الجديدة.
    بيرجع dict: link → "urgent" / "important" / "normal"
    """
    if not ai.available or not items:
        return {}

    listing = "\n".join(f'{i + 1}. {it["title"]}' for i, it in enumerate(items))
    prompt = f"""صنّف كل عنوان حسب أهميته لمصري مقيم بالخارج مهتم بالفرص العقارية في مصر.

{listing}

المستويات:
- "urgent" = فيه موعد أو مهلة أو إجراء لازم يتحرك فيه دلوقتي (فتح حجز، كراسة شروط، آخر موعد تحويل، نتيجة قرعة، قرار جديد يخصه)
- "important" = معلومة مؤثرة على قراره بس مش عاجلة
- "normal" = خبر عادي أو تكرار أو محتوى ترويجي

رجّع JSON فقط بالشكل ده:
{{"1": "urgent", "2": "normal"}}

كل الأرقام من 1 لـ {len(items)} لازم تكون موجودة."""

    result = ai.ask_json(prompt, SYSTEM_JSON, fast=True)
    if not isinstance(result, dict):
        return {}

    out = {}
    for key, level in result.items():
        digits = re.sub(r"\D", "", str(key))
        if not digits:
            continue
        idx = int(digits)
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
        for c in comments[:config.MAX_COMMENTS_PER_VIDEO]
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
    """توقعات وتحليل الأماكن والسيناريوهات."""
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

## أسئلة قبل القرار
(إيه الأسئلة اللي المفروض تجاوب عليها قبل ما تاخد قرار — مش نصيحة بالشراء)

قواعد صارمة:
- ده تحليل اجتهادي مبني على المعطيات فوق، وضّح ده.
- ماتخترعش أرقام أو نسب مش موجودة في المعطيات.
- ماتقولش "اشتري" أو "متشتريش" — اعرض الاعتبارات وسيب القرار له.
- لو المعطيات مش كفاية لاستنتاج، قول كده صراحة."""
    return ai.ask(prompt, SYSTEM_AR)


def analyze_news_batch(ai, items):
    """يصنّف الأخبار ويحدد الأهم منها."""
    if not items:
        return None
    listing = "\n".join(
        f'{i + 1}. {it["title"]} [{it.get("source", "")}]'
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
    return ai.ask_json(prompt, SYSTEM_JSON)


def write_executive_brief(ai, news_items, video_summaries):
    """الملخص التنفيذي للصفحة."""
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
(نقاط قصيرة — إيه المتاح فعليًا ومواعيده لو مذكورة)

## مخاطر وتحذيرات
(نقاط قصيرة — أي حاجة لازم ياخد باله منها)

## الخلاصة
(جملتين: إيه أهم حاجة يعملها دلوقتي)

قواعد مهمة: اعتمد فقط على المعلومات اللي فوق، ماتخترعش أرقام أو تواريخ، وماتديش نصيحة استثمارية مباشرة — اعرض المعلومة وخليه هو يقرر."""
    return ai.ask(prompt, SYSTEM_AR)


def write_now_digest(ai, beit_changes, market_changes, official_changes,
                     urgent_items, novel_signals, new_ads=None):
    """
    خلاصة قصيرة جدًا (2-4 جمل) بس "إيه الجديد والمهم من آخر مرة" —
    الهدف إنها تبقى أول حاجة يقراها المستخدم فوق الصفحة، فتغنيه عن قراءة
    باقي الصفحة لو مالوش وقت. لو مفيش حاجة جديدة فعلًا بيرجع None صراحة
    (أحسن من فقرة عامة مالهاش معنى).

    new_ads: إعلانات بيع/شراء جديدة فعليًا من bit.mzayasoft.com (مصدر
    مجتمعي غير رسمي) — سوق حقيقي بأسعار حقيقية، مهم يظهر هنا فورًا.
    """
    has_anything = (beit_changes or market_changes or official_changes
                    or urgent_items or novel_signals or new_ads)
    if not has_anything:
        return None

    parts = []
    if beit_changes:
        lines = "\n".join(
            f"- {c.get('field', '').replace('_', ' ')}: "
            f"{'كان ' + str(c['from']) + ' وبقى ' if c.get('from') else ''}"
            f"{c.get('to', '')}"
            for c in beit_changes[:8])
        parts.append(f"تغييرات في ملف بيت الوطن:\n{lines}")

    if official_changes:
        lines = "\n".join(
            f"- {ch['name']}: " + " · ".join(ch.get("added", [])[:3])[:200]
            for ch in official_changes[:5])
        parts.append(f"تغييرات في مصادر رسمية:\n{lines}")

    if market_changes:
        lines = "\n".join(
            f"- {c.get('topic', '')} — {c.get('field', '').replace('_', ' ')}: "
            f"{c.get('to', '')}"
            for c in market_changes[:6])
        parts.append(f"تغييرات في ملفات السوق المتابَعة:\n{lines}")

    if urgent_items:
        lines = "\n".join(f"- {it['title']}" for it in urgent_items[:6])
        parts.append(f"أخبار عاجلة جديدة:\n{lines}")

    if novel_signals:
        lines = "\n".join(f"- {s['statement']}" for s in novel_signals[:5])
        parts.append(f"كلام ناس مهم لسه مش في الأخبار الرسمية:\n{lines}")

    if new_ads:
        lines = []
        for a in new_ads[:5]:
            bits = [a.get("status") or "إعلان"]
            if a.get("area_m2"):
                bits.append(f"{a['area_m2']} م²")
            if a.get("premium"):
                bits.append(f"الأوفر {a['premium']:,} جنيه")
            lines.append("- " + " — ".join(bits))
        parts.append("إعلانات قطع جديدة على bit.mzayasoft (سوق حقيقي، "
                     "مصدر مجتمعي غير رسمي):\n" + "\n".join(lines))

    if not ai or not ai.available:
        # بدون AI: نرجّع أول سطرين خام كخلاصة بسيطة بدل ما نسيب الصفحة فاضية
        flat = "\n".join(parts)
        return flat[:400]

    body = "\n\n".join(parts)
    prompt = f"""دي كل التغييرات والمستجدات اللي حصلت من آخر تحديث للمرصد:

{body}

اكتب خلاصة قصيرة جدًا (2-4 جمل بس، مش أكتر) بالعربية المصرية تقول
للمصري المغترب "إيه الجديد اللي يستاهل انتباهك من كل ده". لو حاجة فيها
موعد أو رقم مهم، اذكره بالظبط. ابدأ بأهم حاجة على الإطلاق.
ماتكتبش عنوان ولا مقدمة، ابدأ في الموضوع على طول. ماتخترعش أي معلومة
مش موجودة فوق."""
    return ai.ask(prompt, SYSTEM_AR, fast=True)
