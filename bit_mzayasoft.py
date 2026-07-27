# -*- coding: utf-8 -*-
"""
لوحة bit.mzayasoft.com — مصدر مجتمعي (غير رسمي) لبيت الوطن
=============================================================
موقع طرف ثالث بيتابعه مغتربين بيت الوطن بأنفسهم — بيعرض عدد القطع
الإجمالي/المحجوز/المتبقي في المرحلة الحالية بشكل شبه لحظي، وتتبع حوالات.
مش مصدر رسمي، لكنه غالبًا أسرع وأدق من الجهات الرسمية في عكس الحجز الفعلي.

بنجيب بس الأرقام الصريحة (إجمالي/محجوز/متبقي) من الصفحة الرئيسية —
مفيش تخمين. أي رقم تاني مش واضح المعنى بنسيبه.
"""

import re

import config
from sources import session


def fetch_summary():
    """
    يرجّع dict بأرقام لوحة بيت الوطن لو لقيها، وإلا None.
    {"total": 4428, "reserved": 0, "remaining": 4428, "today": 0}
    """
    if not config.BIT_MZAYASOFT_ENABLED:
        return None
    url = config.BIT_MZAYASOFT_URL
    try:
        r = session().get(url, timeout=config.REQUEST_TIMEOUT)
        r.raise_for_status()
        html = r.text
    except Exception as exc:
        print(f"    - bit.mzayasoft: {str(exc)[:70]}")
        return None

    # الأرقام بتظهر في كروت متتالية بعناوين: الإجمالي / المحجوز / المتبقي / اليوم
    labels = {"total": "الإجمالي", "reserved": "المحجوز",
              "remaining": "المتبقي", "today": "اليوم"}
    out = {}
    for key, label in labels.items():
        # بندوّر على رقم (ممكن فيه فواصل آلاف) قريب من التسمية في الـ HTML
        m = re.search(
            re.escape(label) + r"[\s\S]{0,40}?([\d][\d,]{0,9})", html)
        if not m:
            # جرّب بالترتيب العكسي (رقم قبل التسمية) — بعض القوالب كده
            m = re.search(
                r"([\d][\d,]{0,9})[\s\S]{0,40}?" + re.escape(label), html)
        if m:
            try:
                out[key] = int(m.group(1).replace(",", ""))
            except ValueError:
                continue

    if not out:
        return None
    out["source_url"] = url
    return out


def format_line(summary):
    """سطر نصي جاهز للعرض/التنبيه."""
    if not summary:
        return None
    bits = []
    if "total" in summary:
        bits.append(f"الإجمالي {summary['total']:,}")
    if "reserved" in summary:
        bits.append(f"المحجوز {summary['reserved']:,}")
    if "remaining" in summary:
        bits.append(f"المتبقي {summary['remaining']:,}")
    if "today" in summary:
        bits.append(f"اليوم {summary['today']:,}")
    return " · ".join(bits) if bits else None
