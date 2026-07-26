# -*- coding: utf-8 -*-
"""توليد صفحة الويب (تصميم فيد شبيه بفيسبوك) ورسالة تليجرام"""

import re
import html
from datetime import datetime

PAGE = """<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>مرصد العقارات المصرية للمغتربين</title>
<style>
  :root{
    --bg:#f0f2f5; --card:#ffffff; --text:#1c1e21; --muted:#65676b;
    --line:#e4e6eb; --brand:#8a4b1f; --brand2:#a8632c;
    --blue:#1877f2; --chip:#f0e6d8; --red:#d33b27;
  }
  *{box-sizing:border-box;}
  body{margin:0;padding:0;background:var(--bg);color:var(--text);
       font-family:"Segoe UI",Tahoma,Arial,sans-serif;font-size:15px;line-height:1.7;}
  .shell{max-width:1120px;margin:0 auto;padding:16px;}

  /* شريط علوي ثابت */
  .nav{position:sticky;top:0;z-index:50;background:var(--card);
       border-bottom:1px solid var(--line);box-shadow:0 1px 3px rgba(0,0,0,.06);}
  .nav-in{max-width:1120px;margin:0 auto;padding:10px 16px;
          display:flex;align-items:center;gap:12px;flex-wrap:wrap;}
  .logo{width:40px;height:40px;border-radius:50%;flex:none;
        background:linear-gradient(135deg,var(--brand),var(--brand2));
        color:#fff;display:flex;align-items:center;justify-content:center;font-size:19px;}
  .nav h1{font-size:17px;margin:0;}
  .nav .when{font-size:12px;color:var(--muted);}
  .tabs{display:flex;gap:6px;margin-inline-start:auto;flex-wrap:wrap;}
  .tab{border:none;background:#f0f2f5;color:#050505;font-family:inherit;
       font-size:13px;font-weight:600;padding:7px 14px;border-radius:18px;cursor:pointer;}
  .tab:hover{background:#e4e6eb;}
  .tab.on{background:var(--brand);color:#fff;}

  /* التخطيط */
  .cols{display:grid;grid-template-columns:1fr 320px;gap:16px;align-items:start;}
  @media(max-width:900px){.cols{grid-template-columns:1fr;} .side{order:-1;}}

  /* البطاقات */
  .card{background:var(--card);border-radius:12px;margin-bottom:14px;
        box-shadow:0 1px 2px rgba(0,0,0,.1);overflow:hidden;}
  .card-h{display:flex;gap:10px;padding:12px 14px 8px;align-items:flex-start;}
  .ava{width:40px;height:40px;border-radius:50%;flex:none;color:#fff;
       display:flex;align-items:center;justify-content:center;font-size:17px;
       background:linear-gradient(135deg,#8a4b1f,#c07a3c);}
  .ava.v{background:linear-gradient(135deg,#c0392b,#e74c3c);}
  .ava.s{background:linear-gradient(135deg,#1877f2,#42a5f5);}
  .who{font-weight:700;font-size:14px;}
  .sub{font-size:12px;color:var(--muted);}
  .card-b{padding:0 14px 12px;}
  .card-b a.title{color:var(--text);text-decoration:none;font-size:15.5px;
                  font-weight:600;display:block;margin-bottom:6px;}
  .card-b a.title:hover{color:var(--blue);text-decoration:underline;}
  .snip{font-size:13.5px;color:#3a3b3c;}

  /* شارات */
  .chips{display:flex;gap:5px;flex-wrap:wrap;margin-top:4px;}
  .chip{font-size:11px;padding:2px 9px;border-radius:12px;background:var(--chip);color:var(--brand);}
  .chip.new{background:#e7f3ff;color:#1877f2;}
  .chip.top{background:#fff3cd;color:#8a6100;}
  .chip.urgent{background:var(--red);color:#fff;}

  /* شريط الإحصائيات (زي فيسبوك) */
  .stats{display:flex;gap:16px;padding:8px 14px;border-top:1px solid var(--line);
         font-size:12.5px;color:var(--muted);}
  .stats b{color:#3a3b3c;}

  /* الملخص الذكي داخل البطاقة */
  .ai{background:#f7f9fc;border-inline-start:3px solid var(--blue);
      border-radius:8px;padding:10px 13px;margin-top:9px;font-size:13.5px;color:#3a3b3c;}
  .ai .lab{font-size:11px;font-weight:700;color:var(--blue);
           text-transform:uppercase;letter-spacing:.4px;margin-bottom:4px;}
  .ai p{margin:5px 0;} .ai ul{margin:5px 0;padding-inline-start:19px;} .ai li{margin:3px 0;}
  .ai h4{margin:9px 0 3px;font-size:13.5px;color:var(--brand);}

  /* الكومنتات */
  .cmts{background:#f7f8fa;border-radius:8px;padding:10px 12px;margin-top:9px;}
  .cmts .lab{font-size:11.5px;font-weight:700;color:var(--muted);margin-bottom:7px;}
  .cmt{display:flex;gap:8px;margin-bottom:8px;}
  .cmt:last-child{margin-bottom:0;}
  .cmt .cava{width:26px;height:26px;border-radius:50%;flex:none;background:#d8dadf;
             color:#65676b;display:flex;align-items:center;justify-content:center;font-size:12px;}
  .cmt .cbody{background:#fff;border-radius:14px;padding:7px 11px;font-size:13px;flex:1;}
  .cmt .cname{font-weight:700;font-size:12.5px;}
  .cmt .clikes{font-size:11px;color:var(--muted);margin-top:2px;}

  /* التقارير الكبيرة */
  .report{background:var(--card);border-radius:12px;padding:18px 22px;margin-bottom:14px;
          box-shadow:0 1px 2px rgba(0,0,0,.1);}
  .report h2{font-size:17px;margin:0 0 12px;color:var(--brand);
             border-bottom:2px solid var(--chip);padding-bottom:9px;}
  .report h3{font-size:14.5px;color:var(--brand2);margin:15px 0 5px;}
  .report ul{padding-inline-start:20px;margin:6px 0;}
  .report li{margin-bottom:5px;}
  .report p{margin:7px 0;}

  /* العمود الجانبي */
  .side .card{padding:14px 16px;}
  .side h3{font-size:14px;margin:0 0 10px;color:var(--brand);}
  .side .row{display:flex;justify-content:space-between;font-size:13px;
             padding:6px 0;border-bottom:1px solid var(--line);}
  .side .row:last-child{border:none;}
  .side .row b{color:var(--brand);}
  .srcline{font-size:12.5px;color:var(--muted);padding:4px 0;}

  .foot{background:#fff;border-radius:12px;padding:14px 18px;font-size:12.5px;
        color:var(--muted);box-shadow:0 1px 2px rgba(0,0,0,.1);}
  .hidden{display:none;}
</style>
</head>
<body>

<div class="nav"><div class="nav-in">
  <div class="logo">&#127963;</div>
  <div>
    <h1>مرصد العقارات المصرية للمغتربين</h1>
    <div class="when">آخر تحديث: __UPDATED__</div>
  </div>
  <div class="tabs">__TABS__</div>
</div></div>

<div class="shell"><div class="cols">
  <div class="feed">
__REPORTS__
__FEED__
    <div class="foot">
      تُجمَع المصادر آليًا وتُلخَّص بالذكاء الاصطناعي — <b>الملخصات والتحليلات قابلة للخطأ</b>،
      ارجع للمصدر الأصلي دائمًا. المحتوى للاطلاع فقط وليس استشارة مالية أو قانونية.
      راجع كراسة الشروط الرسمية ومنصة مصر العقارية قبل أي التزام مالي.
      <div style="margin-top:8px;font-size:11.5px;">__ENGINES__</div>
    </div>
  </div>

  <div class="side">
__SIDE__
  </div>
</div></div>

<script>
  const tabs = document.querySelectorAll('.tab');
  const cards = document.querySelectorAll('[data-sec]');
  tabs.forEach(t => t.addEventListener('click', () => {
    tabs.forEach(x => x.classList.remove('on'));
    t.classList.add('on');
    const want = t.dataset.filter;
    cards.forEach(c => {
      c.classList.toggle('hidden', want !== 'all' && c.dataset.sec !== want);
    });
  }));
</script>
</body>
</html>
"""


# ============================================================
#  أدوات
# ============================================================

def md_to_html(text):
    if not text:
        return ""
    out, in_list = [], False
    for line in text.split("\n"):
        s = line.strip()
        if not s:
            if in_list:
                out.append("</ul>")
                in_list = False
            continue
        if s.startswith("### "):
            if in_list:
                out.append("</ul>"); in_list = False
            out.append(f"<h4>{html.escape(s[4:])}</h4>")
        elif s.startswith("## "):
            if in_list:
                out.append("</ul>"); in_list = False
            out.append(f"<h3>{html.escape(s[3:])}</h3>")
        elif s.startswith(("- ", "* ", "• ")):
            if not in_list:
                out.append("<ul>"); in_list = True
            out.append(f"<li>{_inline(s[2:])}</li>")
        elif re.match(r"^\d+[.)]\s", s):
            if not in_list:
                out.append("<ul>"); in_list = True
            stripped = re.sub(r"^\d+[.)]\s", "", s)
            out.append(f"<li>{_inline(stripped)}</li>")
        else:
            if in_list:
                out.append("</ul>"); in_list = False
            out.append(f"<p>{_inline(s)}</p>")
    if in_list:
        out.append("</ul>")
    return "\n".join(out)


def _inline(text):
    text = html.escape(text)
    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)


def _num(n):
    try:
        n = int(n)
    except Exception:
        return "0"
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if n >= 1000:
        return f"{n/1000:.1f}K"
    return str(n)


def _ago(iso):
    if not iso:
        return ""
    try:
        d = datetime.fromisoformat(iso)
    except Exception:
        return ""
    delta = datetime.now(d.tzinfo) - d
    h = delta.total_seconds() / 3600
    if h < 1:
        return "من شوية"
    if h < 24:
        return f"من {int(h)} ساعة"
    days = int(h / 24)
    if days == 1:
        return "امبارح"
    if days < 30:
        return f"من {days} يوم"
    return d.strftime("%Y-%m-%d")


def _slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()) or "s"


# ============================================================
#  البطاقات
# ============================================================

def _card(item, section, new_links, top_links, urgent_links):
    kind = item.get("kind", "news")
    ava_cls = {"video": "ava v", "social": "ava s"}.get(kind, "ava")
    ava_ico = {"video": "&#9654;", "social": "&#128172;"}.get(kind, "&#128240;")

    chips = ""
    if item["link"] in urgent_links:
        chips += '<span class="chip urgent">عاجل</span>'
    if item["link"] in top_links:
        chips += '<span class="chip top">مهم</span>'
    if item["link"] in new_links:
        chips += '<span class="chip new">جديد</span>'

    body = [
        f'<div class="card" data-sec="{_slug(section)}">',
        '  <div class="card-h">',
        f'    <div class="{ava_cls}">{ava_ico}</div>',
        '    <div>',
        f'      <div class="who">{html.escape(item.get("source") or "مصدر")}</div>',
        f'      <div class="sub">{html.escape(section)} · {_ago(item.get("published",""))}</div>',
        f'      <div class="chips">{chips}</div>' if chips else '',
        '    </div>',
        '  </div>',
        '  <div class="card-b">',
        f'    <a class="title" href="{html.escape(item["link"])}" target="_blank">'
        f'{html.escape(item["title"])}</a>',
    ]

    if item.get("snippet"):
        body.append(f'    <div class="snip">{html.escape(item["snippet"][:220])}</div>')

    if item.get("ai_summary"):
        body.append('    <div class="ai"><div class="lab">&#129302; ملخص ذكي</div>'
                    + md_to_html(item["ai_summary"]) + '</div>')

    if item.get("comment_analysis"):
        body.append('    <div class="ai" style="border-color:#8a4b1f">'
                    '<div class="lab" style="color:#8a4b1f">&#128172; تحليل كلام الناس</div>'
                    + md_to_html(item["comment_analysis"]) + '</div>')

    tops = item.get("top_comments") or []
    if tops:
        rows = ['    <div class="cmts"><div class="lab">أكتر التعليقات تفاعلًا</div>']
        for c in tops:
            initial = html.escape((c.get("author") or "؟").strip()[:1])
            rows.append(
                '      <div class="cmt">'
                f'<div class="cava">{initial}</div>'
                f'<div class="cbody"><div class="cname">{html.escape(c.get("author",""))}</div>'
                f'{html.escape(c.get("text","")[:260])}'
                f'<div class="clikes">&#128077; {_num(c.get("likes",0))}'
                + (f' · {c.get("replies",0)} رد' if c.get("replies") else '')
                + '</div></div></div>')
        rows.append('    </div>')
        body.append("\n".join(rows))

    body.append('  </div>')

    st = item.get("stats") or {}
    if st:
        body.append(
            '  <div class="stats">'
            f'<span>&#128065; <b>{_num(st.get("views",0))}</b> مشاهدة</span>'
            f'<span>&#128077; <b>{_num(st.get("likes",0))}</b></span>'
            f'<span>&#128172; <b>{_num(st.get("comments",0))}</b> تعليق</span>'
            '</div>')

    body.append('</div>')
    return "\n".join(x for x in body if x)


# ============================================================
#  الصفحة
# ============================================================

def _market_board(rows):
    """لوحة حالة السوق — ذاكرة النظام."""
    if not rows:
        return ""
    out = ['    <div class="report"><h2>&#128203; حالة السوق الآن</h2>',
           '      <table style="width:100%;border-collapse:collapse;font-size:13.5px;">',
           '        <tr style="background:#faf7f3;">'
           '<th style="text-align:right;padding:8px;">الموضوع</th>'
           '<th style="text-align:right;padding:8px;">المرحلة</th>'
           '<th style="text-align:right;padding:8px;">الحالة</th>'
           '<th style="text-align:right;padding:8px;">موعد قادم</th></tr>']
    for r in rows:
        status = html.escape(r["status"])
        color = {"مفتوح": "#2f6b46", "مغلق": "#a13a1e"}.get(r["status"], "#65676b")
        out.append(
            '        <tr style="border-top:1px solid #e4e6eb;">'
            f'<td style="padding:8px;font-weight:600;">{html.escape(r["topic"])}</td>'
            f'<td style="padding:8px;">{html.escape(r["stage"])}</td>'
            f'<td style="padding:8px;color:{color};font-weight:600;">{status}</td>'
            f'<td style="padding:8px;">{html.escape(r["next"])}</td></tr>')
        if r["last"] and r["last"] != "—":
            out.append(
                '        <tr><td colspan="4" style="padding:0 8px 9px;'
                'font-size:12.5px;color:#65676b;">'
                f'&#8627; {html.escape(r["last"])}</td></tr>')
    out += ['      </table>', '    </div>']
    return "\n".join(out)


def build_page(sections, brief, new_links, top_links, urgent_links,
               engines_note, forecast=None, market_rows=None):
    # التبويبات
    tabs = ['<button class="tab on" data-filter="all">الكل</button>']
    for name in sections:
        if sections[name]:
            tabs.append(f'<button class="tab" data-filter="{_slug(name)}">'
                        f'{html.escape(name)}</button>')

    # التقارير
    reports = []
    board = _market_board(market_rows or [])
    if board:
        reports.append(board)
    if brief:
        reports.append('    <div class="report"><h2>&#129517; الملخص التنفيذي</h2>'
                       + md_to_html(brief) + '</div>')
    if forecast:
        reports.append('    <div class="report"><h2>&#128302; التوقعات وقراءة السوق</h2>'
                       + md_to_html(forecast) + '</div>')

    # الفيد
    feed = []
    for name, items in sections.items():
        for item in items[:15]:
            feed.append(_card(item, name, new_links, top_links, urgent_links))

    # العمود الجانبي
    total = sum(len(v) for v in sections.values())
    side = ['    <div class="card"><h3>&#128202; نظرة سريعة</h3>',
            f'      <div class="row"><span>إجمالي العناصر</span><b>{total}</b></div>',
            f'      <div class="row"><span>جديد هذه الدورة</span><b>{len(new_links)}</b></div>',
            f'      <div class="row"><span>عاجل</span><b>{len(urgent_links)}</b></div>']
    for name, items in sections.items():
        if items:
            side.append(f'      <div class="row"><span>{html.escape(name)}</span>'
                        f'<b>{len(items)}</b></div>')
    side.append('    </div>')

    side += ['    <div class="card"><h3>&#128279; روابط رسمية</h3>',
             '      <div class="srcline">· <a href="https://lands.nuca.gov.eg/" target="_blank">'
             'هيئة المجتمعات العمرانية</a></div>',
             '      <div class="srcline">· <a href="https://reservations.realestate.gov.eg/ar" '
             'target="_blank">منصة مصر العقارية</a></div>',
             '      <div class="srcline">· <a href="https://beitakfemisr.com/" target="_blank">'
             'بيتك في مصر</a></div>',
             '    </div>']

    return (PAGE
            .replace("__UPDATED__", datetime.now().strftime("%Y-%m-%d %H:%M"))
            .replace("__TABS__", "\n".join(tabs))
            .replace("__REPORTS__", "\n".join(reports))
            .replace("__FEED__", "\n".join(feed) or
                     '    <div class="card"><div class="card-b">لا توجد نتائج.</div></div>')
            .replace("__SIDE__", "\n".join(side))
            .replace("__ENGINES__", html.escape(engines_note or "")))


# ============================================================
#  تليجرام
# ============================================================

def build_telegram(new_by_section, brief, urgent_links):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = ["🏛️ <b>مرصد العقارات المصرية</b>", f"<i>{now}</i>", ""]

    if brief:
        summary = next((p.strip() for p in brief.split("##") if p.strip()), "")
        if summary:
            plain = re.sub(r"\*\*(.+?)\*\*", r"\1", summary)[:600]
            lines += ["📋 <b>الخلاصة</b>", html.escape(plain), ""]

    for section, items in new_by_section.items():
        if not items:
            continue
        lines.append(f"<b>▸ {html.escape(section)}</b>")
        for it in items[:6]:
            mark = "🔴 " if it["link"] in urgent_links else "• "
            lines.append(f'{mark}<a href="{html.escape(it["link"])}">'
                         f'{html.escape(it["title"])}</a>')
            bits = []
            if it.get("source"):
                bits.append(it["source"])
            st = it.get("stats") or {}
            if st.get("views"):
                bits.append(f'👁 {_num(st["views"])}')
            if bits:
                lines.append(f'  <i>{html.escape(" · ".join(bits))}</i>')
        lines.append("")

    return "\n".join(lines).strip()
