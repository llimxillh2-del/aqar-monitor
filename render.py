# -*- coding: utf-8 -*-
"""
توليد الصفحات (أسلوب تقرير مؤسسي) ورسائل تليجرام
==================================================
صفحتين:
  index.html        — التقرير الدوري العام
  beit-alwatan.html — الملف المخصّص لبيت الوطن

إصلاح مهم: الدالة القديمة _slug() كانت بتشيل كل الحروف العربية فكل الأقسام
كانت بتطلع بنفس المعرّف "-" → التبويبات مابتفلترش حاجة. دلوقتي فيه خريطة
معرّفات إنجليزية في config.SECTION_SLUGS مع بديل مستقر بالـ hash.
"""

import re
import html
import hashlib
from datetime import datetime, timezone, timedelta

import config

AR_MONTHS_OUT = ["يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو",
                 "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"]


# ============================================================
#  أدوات عامة
# ============================================================

def esc(text):
    return html.escape(str(text or ""))


def cairo_now():
    return datetime.now(timezone.utc) + timedelta(hours=config.TIMEZONE_OFFSET_HOURS)


def stamp():
    d = cairo_now()
    return f"{d.day} {AR_MONTHS_OUT[d.month - 1]} {d.year} — {d:%H:%M} بتوقيت القاهرة"


def slug(name):
    """معرّف إنجليزي مستقر لأي اسم قسم (عربي أو غيره)."""
    if name in config.SECTION_SLUGS:
        return config.SECTION_SLUGS[name]
    ascii_part = re.sub(r"[^a-z0-9]+", "-", str(name).lower()).strip("-")
    if ascii_part:
        return ascii_part
    return "s" + hashlib.md5(str(name).encode("utf-8")).hexdigest()[:6]


def num(n):
    try:
        n = int(n)
    except (TypeError, ValueError):
        return "0"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1000:
        return f"{n / 1000:.1f}K"
    return str(n)


def ago(iso):
    if not iso:
        return ""
    try:
        d = datetime.fromisoformat(iso)
    except (TypeError, ValueError):
        return ""
    ref = datetime.now(d.tzinfo) if d.tzinfo else datetime.now()
    hours = (ref - d).total_seconds() / 3600
    if hours < 0:
        return "الآن"
    if hours < 1:
        return "منذ دقائق"
    if hours < 24:
        return f"منذ {int(hours)} ساعة"
    days = int(hours / 24)
    if days == 1:
        return "أمس"
    if days < 30:
        return f"منذ {days} يومًا"
    return d.strftime("%Y-%m-%d")


def md_to_html(text):
    """تحويل ماركداون مبسط لعناصر HTML نظيفة."""
    if not text:
        return ""
    out, in_list = [], False

    def close():
        nonlocal in_list
        if in_list:
            out.append("</ul>")
            in_list = False

    for line in str(text).split("\n"):
        s = line.strip()
        if not s:
            close()
            continue
        if s.startswith("#### "):
            close(); out.append(f"<h5>{inline(s[5:])}</h5>")
        elif s.startswith("### "):
            close(); out.append(f"<h4>{inline(s[4:])}</h4>")
        elif s.startswith("## "):
            close(); out.append(f"<h3>{inline(s[3:])}</h3>")
        elif s.startswith("# "):
            close(); out.append(f"<h3>{inline(s[2:])}</h3>")
        elif s.startswith(("- ", "* ", "• ", "– ")):
            if not in_list:
                out.append("<ul>"); in_list = True
            out.append(f"<li>{inline(s[2:])}</li>")
        elif re.match(r"^\d+[.)]\s", s):
            if not in_list:
                out.append("<ul>"); in_list = True
            stripped = re.sub(r"^\d+[.)]\s", "", s)
            out.append("<li>" + inline(stripped) + "</li>")
        else:
            close(); out.append(f"<p>{inline(s)}</p>")
    close()
    return "\n".join(out)


def inline(text):
    t = esc(text)
    t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
    t = re.sub(r"(?<!\*)\*([^*]+?)\*(?!\*)", r"<em>\1</em>", t)
    return t


# ============================================================
#  نظام التصميم — مشترك بين الصفحتين
# ============================================================

CSS = """
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+Arabic:wght@300;400;500;600;700&family=Cairo:wght@600;700;800;900&display=swap');

:root{
  --ink:#0d1220; --body:#26303f; --muted:#5c6879; --faint:#8b95a5;
  --line:#dde2eb; --line-soft:#eef1f6; --bg:#f4f6fa; --paper:#ffffff;
  --navy:#082a4d; --navy-2:#124a7d; --navy-3:#1c6dab;
  --gold:#8b6420; --gold-2:#b28638; --gold-soft:#faf3e2;
  --red:#a91d1d; --red-soft:#fcecec;
  --green:#0f5c39; --green-soft:#e8f4ee;
  --amber:#8a5a00; --amber-soft:#fef4d9;
  --purple:#5d3aa8; --purple-soft:#f0ebfb;
  --radius:6px;
  --shadow-sm:0 1px 2px rgba(8,42,77,.06);
  --shadow-md:0 4px 14px rgba(8,42,77,.08);
  --shadow-lg:0 10px 30px rgba(8,42,77,.12);
}
*{box-sizing:border-box;}
html{scroll-behavior:smooth;}
body{
  margin:0; background:var(--bg); color:var(--body);
  font-family:'IBM Plex Sans Arabic','Segoe UI',Tahoma,Arial,sans-serif;
  font-size:15px; line-height:1.8; -webkit-font-smoothing:antialiased;
}
a{color:var(--navy-2); text-decoration:none; transition:color .15s;}
a:hover{color:var(--navy-3);}
.display{font-family:'Cairo','IBM Plex Sans Arabic',sans-serif; letter-spacing:-.4px;}

/* ---------- الترويسة ---------- */
.masthead{background:linear-gradient(135deg,var(--navy) 0%,#0d3866 60%,#124a7d 100%);
  color:#fff; border-bottom:3px solid var(--gold-2); position:relative;}
.masthead::after{content:''; position:absolute; inset:auto 0 0 0; height:3px;
  background:linear-gradient(90deg,var(--gold),var(--gold-2),var(--gold));}
.masthead-in{max-width:1240px; margin:0 auto; padding:30px 26px 26px;
  display:flex; align-items:flex-end; gap:28px; flex-wrap:wrap;}
.masthead-brand{flex:1 1 480px; min-width:0;}
.eyebrow{font-size:11px; letter-spacing:2.8px; text-transform:uppercase;
  color:#b8d0e8; margin-bottom:10px; font-weight:600;}
.masthead h1{margin:0; font-size:30px; font-weight:800; letter-spacing:-.5px;
  font-family:'Cairo','IBM Plex Sans Arabic',sans-serif; line-height:1.3;}
.masthead .lede{margin:10px 0 0; font-size:14.5px; color:#d2e2f0; font-weight:400;
  max-width:640px;}
.masthead-meta{display:flex; gap:20px; flex-wrap:wrap; font-size:12.5px;
  color:#a8c4dd; padding:12px 18px; background:rgba(0,0,0,.18);
  border-radius:var(--radius); border:1px solid rgba(255,255,255,.08);}
.masthead-meta b{color:#fff; font-weight:700; font-variant-numeric:tabular-nums;}
.masthead-meta .live{display:inline-flex; align-items:center; gap:6px;
  color:#7fe0a5; font-weight:700; letter-spacing:.4px;}
.masthead-meta .live::before{content:''; width:8px; height:8px; border-radius:50%;
  background:#7fe0a5; animation:pulse 2s infinite;}
@keyframes pulse{0%,100%{opacity:1;} 50%{opacity:.35;}}

/* ---------- شريط التنقل ---------- */
.topbar{position:sticky; top:0; z-index:60; background:rgba(255,255,255,.95);
  backdrop-filter:blur(10px); border-bottom:1px solid var(--line);
  box-shadow:0 2px 10px rgba(8,42,77,.04);}
.topbar-in{max-width:1240px; margin:0 auto; padding:0 26px;
  display:flex; align-items:center; gap:2px; flex-wrap:wrap;}
.topbar a{display:inline-block; padding:14px 15px; font-size:13.5px;
  font-weight:600; color:var(--muted); border-bottom:2px solid transparent;
  transition:.15s;}
.topbar a:hover{color:var(--navy); border-bottom-color:var(--gold-2);}
.topbar a.cta{margin-inline-start:auto; color:#fff; background:var(--gold-2);
  padding:8px 18px; border-radius:var(--radius); font-weight:700; margin-block:6px;}
.topbar a.cta:hover{background:var(--gold); color:#fff;}

/* ---------- التخطيط ---------- */
.wrap{max-width:1240px; margin:0 auto; padding:30px 26px 70px;
  display:grid; grid-template-columns:1fr 300px; gap:30px; align-items:start;}
@media(max-width:1000px){ .wrap{grid-template-columns:1fr; padding:22px 16px 50px;} .rail{order:-1;} }

/* ---------- خلاصة "الأهم دلوقتي" ---------- */
.now-digest{background:linear-gradient(135deg,#fff9ec,#fdf3dc);
  border:1px solid #e9d9ac; border-inline-start:5px solid var(--gold-2);
  border-radius:var(--radius); padding:16px 20px; margin-bottom:20px;
  box-shadow:var(--shadow-sm);}
.now-digest-label{font-size:12px; font-weight:800; letter-spacing:.6px;
  color:var(--gold); text-transform:uppercase; margin-bottom:7px;}
.now-digest-body{font-size:15.5px; line-height:1.85; color:var(--ink);}
.now-digest-body p{margin:5px 0;}
.now-digest-body ul{margin:5px 0; padding-inline-start:20px;}

.plots-box{background:#f8fafc; border:1px solid var(--line);
  border-radius:var(--radius); padding:14px 18px; margin-bottom:20px;}
.plots-label{font-size:12.5px; font-weight:600; color:var(--muted);}
.plots-label a{margin-inline-start:8px; font-size:12px;}

/* ---------- طيّ الأقسام الثانوية ---------- */
.collapsible > summary{cursor:pointer; list-style:none; user-select:none;}
.collapsible > summary::-webkit-details-marker{display:none;}
.collapsible > summary.toggle-head{display:flex; align-items:center; gap:10px;
  padding:18px 24px; font-size:17px; font-weight:700; color:var(--navy);
  background:linear-gradient(180deg,#fcfdff,#f5f8fc);
  border-bottom:1px solid transparent; font-family:'Cairo','IBM Plex Sans Arabic',sans-serif;}
.collapsible[open] > summary.toggle-head{border-bottom-color:var(--line);}
.collapsible > summary.toggle-head::after{content:'▸'; margin-inline-start:auto;
  color:var(--muted); font-size:13px; transition:transform .15s;}
.collapsible[open] > summary.toggle-head::after{transform:rotate(90deg);}
.collapsible > summary.toggle-head .hint{font-size:12px; font-weight:500;
  color:var(--faint); margin-inline-start:6px;}

/* ---------- المؤشرات ---------- */
.kpis{display:grid; grid-template-columns:repeat(auto-fit,minmax(160px,1fr));
  gap:12px; margin-bottom:24px;}
.kpi{background:var(--paper); padding:18px 20px; border-radius:var(--radius);
  border:1px solid var(--line); box-shadow:var(--shadow-sm); position:relative;
  overflow:hidden;}
.kpi::before{content:''; position:absolute; inset-inline-start:0; top:0; bottom:0;
  width:3px; background:var(--navy-3);}
.kpi.alert::before{background:var(--red);}
.kpi.good::before{background:var(--green);}
.kpi.warn::before{background:var(--gold-2);}
.kpi .k-label{font-size:12px; color:var(--muted); letter-spacing:.4px;
  font-weight:600; margin-bottom:4px; text-transform:uppercase;}
.kpi .k-value{font-size:32px; font-weight:800; color:var(--navy); line-height:1.15;
  font-variant-numeric:tabular-nums; font-family:'Cairo','IBM Plex Sans Arabic',sans-serif;}
.kpi.alert .k-value{color:var(--red);}
.kpi.good .k-value{color:var(--green);}
.kpi.warn .k-value{color:var(--gold-2);}
.kpi .k-hint{font-size:11.5px; color:var(--faint); margin-top:4px;}

/* ---------- الأقسام ---------- */
.doc{counter-reset:sec;}
.block{background:var(--paper); border:1px solid var(--line);
  border-radius:var(--radius); margin-bottom:22px; overflow:hidden;
  box-shadow:var(--shadow-sm);}
section.block > h2{counter-increment:sec; margin:0; padding:18px 24px;
  font-size:17px; font-weight:700; color:var(--navy);
  background:linear-gradient(180deg,#fcfdff,#f5f8fc);
  border-bottom:1px solid var(--line); display:flex; align-items:center; gap:12px;
  font-family:'Cairo','IBM Plex Sans Arabic',sans-serif;}
section.block > h2::before{content:counter(sec); font-size:12px; font-weight:800;
  color:#fff; background:linear-gradient(180deg,var(--navy-2),var(--navy));
  min-width:26px; height:26px; border-radius:6px;
  display:inline-flex; align-items:center; justify-content:center; flex:none;
  font-variant-numeric:tabular-nums;}
details.collapsible.block > summary.toggle-head{counter-increment:sec;}
.block-body{padding:22px 24px 24px;}
.block-body > *:first-child{margin-top:0;}
.block-body > *:last-child{margin-bottom:0;}

h3{font-size:15px; font-weight:600; color:var(--navy-2); margin:20px 0 7px;
  padding-inline-start:11px; border-inline-start:3px solid var(--gold);}
h4{font-size:14px; font-weight:600; color:var(--gold); margin:15px 0 5px;}
h5{font-size:13.5px; font-weight:600; color:var(--body); margin:12px 0 4px;}
p{margin:9px 0;}
ul{margin:9px 0; padding-inline-start:21px;}
li{margin:5px 0;}

/* ---------- الجداول ---------- */
table{width:100%; border-collapse:collapse; font-size:14px; margin:12px 0;}
th{background:#f6f8fa; text-align:start; padding:10px 12px; font-weight:600;
  color:var(--navy); border-bottom:2px solid var(--line); font-size:13px;
  white-space:nowrap;}
td{padding:10px 12px; border-bottom:1px solid var(--line-soft); vertical-align:top;}
tr:last-child td{border-bottom:none;}
tbody tr:hover{background:#fafbfc;}
td.k{font-weight:600; color:var(--ink); width:32%; white-space:nowrap;}
.note-row td{background:#fbfcfd; color:var(--muted); font-size:13px; padding-top:0;}

/* ---------- الشارات ---------- */
.tag{display:inline-block; font-size:11.5px; font-weight:600; padding:2px 9px;
  border-radius:3px; white-space:nowrap; line-height:1.7;}
.tag.red{background:var(--red-soft); color:var(--red);}
.tag.green{background:var(--green-soft); color:var(--green);}
.tag.amber{background:var(--amber-soft); color:var(--amber);}
.tag.navy{background:#eaf1f7; color:var(--navy);}
.tag.gold{background:var(--gold-soft); color:var(--gold);}
.tag.gray{background:#eff1f4; color:var(--muted);}

/* ---------- الفيد ---------- */
.filters{display:flex; gap:8px; flex-wrap:wrap; padding:16px 24px;
  border-bottom:1px solid var(--line); background:#fafbfd;}
.filters button{font-family:inherit; font-size:13px; font-weight:600;
  padding:7px 16px; border:1px solid var(--line); background:var(--paper);
  color:var(--muted); border-radius:100px; cursor:pointer; transition:.15s;}
.filters button:hover{border-color:var(--navy-2); color:var(--navy); background:#fff;}
.filters button.on{background:var(--navy); border-color:var(--navy); color:#fff;
  box-shadow:0 2px 8px rgba(8,42,77,.2);}

.entry{padding:20px 24px; border-bottom:1px solid var(--line-soft);
  transition:background .15s;}
.entry:last-child{border-bottom:none;}
.entry:hover{background:#fafbfd;}
.entry-meta{display:flex; gap:8px; align-items:center; flex-wrap:wrap;
  font-size:12px; color:var(--faint); margin-bottom:7px;}
.entry-meta .src{font-weight:700; color:var(--navy-2); display:inline-flex;
  align-items:center; gap:4px;}
.entry-meta .src::before{content:''; width:3px; height:3px; border-radius:50%;
  background:var(--gold-2); display:inline-block;}
.entry-meta .src-plus{background:var(--gold-soft); color:var(--gold);
  padding:1px 8px; border-radius:100px; font-weight:700; font-size:11px;
  margin-inline-start:4px;}
.entry-meta .dot{color:var(--faint); user-select:none;}
.entry h3.t{border:none; padding:0; margin:0 0 6px; font-size:16.5px;
  font-weight:700; line-height:1.55; font-family:'Cairo','IBM Plex Sans Arabic',sans-serif;}
.entry h3.t a{color:var(--ink);}
.entry h3.t a:hover{color:var(--navy-3);}
.snip{font-size:14px; color:var(--muted); margin:6px 0 0; line-height:1.75;}
.metrics{display:flex; gap:16px; font-size:12px; color:var(--faint);
  margin-top:10px; font-variant-numeric:tabular-nums;}

/* أخبار مدموجة — عرض المصادر المتعددة */
.aliases{margin-top:8px; padding-top:8px; border-top:1px dashed var(--line);
  display:flex; gap:6px; flex-wrap:wrap; font-size:11.5px;}
.aliases .a-label{color:var(--faint); font-weight:600; margin-inline-end:4px;}
.aliases a{color:var(--muted); background:#f2f4f8; padding:2px 9px;
  border-radius:100px; text-decoration:none;}
.aliases a:hover{background:#e8ecf2; color:var(--navy);}

/* ---------- قسم آخر التحديثات ---------- */
.updates{background:linear-gradient(180deg,#fff,#fafbfd);
  border:1px solid var(--line); border-radius:var(--radius);
  margin-bottom:24px; overflow:hidden; box-shadow:var(--shadow-md);}
.updates-head{display:flex; align-items:center; justify-content:space-between;
  gap:12px; padding:16px 22px; background:linear-gradient(90deg,var(--navy) 0%,var(--navy-2) 100%);
  color:#fff; flex-wrap:wrap;}
.updates-head h2{margin:0; font-size:17px; font-weight:800; color:#fff;
  display:flex; align-items:center; gap:10px;
  font-family:'Cairo','IBM Plex Sans Arabic',sans-serif;}
.updates-head h2::before{content:''; width:10px; height:10px; border-radius:50%;
  background:#ff5544; box-shadow:0 0 0 4px rgba(255,85,68,.2);
  animation:pulse 1.5s infinite;}
.updates-head .u-when{font-size:12.5px; color:#c8dcee; font-weight:500;}
.updates-list{padding:8px 0;}
.u-item{display:grid; grid-template-columns:96px 1fr auto; gap:16px;
  padding:14px 22px; border-bottom:1px solid var(--line-soft); align-items:start;}
.u-item:last-child{border-bottom:none;}
.u-item:hover{background:#fbfcfd;}
.u-when{font-size:11.5px; color:var(--muted); font-weight:600;
  padding-top:2px; font-variant-numeric:tabular-nums;
  text-transform:uppercase; letter-spacing:.3px;}
.u-when b{display:block; color:var(--navy); font-size:13.5px; margin-bottom:1px;}
.u-body{min-width:0;}
.u-title{font-size:14.5px; font-weight:700; color:var(--ink); line-height:1.5;
  margin-bottom:4px; font-family:'Cairo','IBM Plex Sans Arabic',sans-serif;}
.u-title a{color:inherit;}
.u-title a:hover{color:var(--navy-3);}
.u-meta{display:flex; gap:8px; align-items:center; flex-wrap:wrap;
  font-size:11.5px; color:var(--faint);}
.u-meta .src{color:var(--navy-2); font-weight:600;}
.u-tags{display:flex; gap:4px; flex-wrap:wrap; align-items:flex-start;}
@media(max-width:640px){
  .u-item{grid-template-columns:1fr; gap:6px;}
  .u-when{font-size:11px;}
  .u-when b{display:inline; margin-inline-end:6px;}
  .u-tags{margin-top:4px;}
}

.ai-box{background:#f8fafc; border:1px solid var(--line);
  border-inline-start:3px solid var(--navy-2); border-radius:var(--radius);
  padding:12px 15px; margin-top:11px; font-size:13.5px;}
.ai-box .ai-label{font-size:11px; font-weight:700; letter-spacing:1.1px;
  color:var(--navy-2); text-transform:uppercase; margin-bottom:5px;}
.ai-box.people{border-inline-start-color:var(--gold); background:#fdfbf7;}
.ai-box.people .ai-label{color:var(--gold);}
.ai-box p{margin:5px 0;} .ai-box ul{margin:5px 0; padding-inline-start:18px;}
.ai-box h4{margin:9px 0 3px; font-size:13px;}

.quotes{margin-top:11px; border-top:1px dashed var(--line); padding-top:10px;}
.quotes .q-label{font-size:11.5px; font-weight:600; color:var(--faint); margin-bottom:8px;}
.quote{display:flex; gap:9px; margin-bottom:9px;}
.quote .av{width:27px; height:27px; border-radius:50%; flex:none; background:#e8ebef;
  color:var(--muted); display:flex; align-items:center; justify-content:center;
  font-size:12px; font-weight:600;}
.quote .qb{flex:1; background:#f7f8fa; border-radius:var(--radius);
  padding:8px 12px; font-size:13px;}
.quote .qn{font-weight:600; font-size:12.5px; color:var(--ink);}
.quote .ql{font-size:11.5px; color:var(--faint); margin-top:3px;}

/* ---------- العمود الجانبي ---------- */
.rail{position:sticky; top:60px;}
@media(max-width:940px){ .rail{position:static;} }
.rail .box{background:var(--paper); border:1px solid var(--line);
  border-radius:var(--radius); padding:15px 17px; margin-bottom:16px;}
.rail h4{margin:0 0 11px; font-size:12px; letter-spacing:1.1px; color:var(--muted);
  text-transform:uppercase; font-weight:700;}
.rail .r{display:flex; justify-content:space-between; gap:10px; font-size:13.5px;
  padding:7px 0; border-bottom:1px solid var(--line-soft);}
.rail .r:last-child{border-bottom:none;}
.rail .r b{color:var(--navy); font-variant-numeric:tabular-nums;}
.rail .lnk{display:block; padding:6px 0; font-size:13.5px;
  border-bottom:1px solid var(--line-soft);}
.rail .lnk:last-child{border-bottom:none;}
.rail .toc a{display:block; padding:5px 0; font-size:13.5px; color:var(--body);}
.rail .toc a:hover{color:var(--navy); text-decoration:none;}

/* ---------- بانر بيت الوطن (Hero) ---------- */
.spotlight{background:linear-gradient(135deg,var(--navy) 0%,#0d3866 40%,#154572 100%);
  color:#fff; border-radius:var(--radius); padding:0; margin-bottom:24px;
  overflow:hidden; box-shadow:var(--shadow-lg); position:relative;}
.spotlight::before{content:''; position:absolute; inset:0;
  background:radial-gradient(1200px 400px at 90% -20%,rgba(178,134,56,.35),transparent 60%);
  pointer-events:none;}
.spotlight-in{position:relative; padding:28px 32px 26px;
  border-inline-start:5px solid var(--gold-2);}
.spotlight .sp-eyebrow{font-size:11px; letter-spacing:3px; color:#c9dded;
  text-transform:uppercase; font-weight:700;
  display:inline-flex; align-items:center; gap:8px;}
.spotlight .sp-eyebrow::before{content:''; width:22px; height:2px;
  background:var(--gold-2);}
.spotlight h2{margin:10px 0 6px; font-size:26px; font-weight:800; color:#fff;
  font-family:'Cairo','IBM Plex Sans Arabic',sans-serif; letter-spacing:-.4px;}
.spotlight .sp-tag{display:inline-block; background:rgba(178,134,56,.25);
  color:#fce6b8; padding:3px 12px; border-radius:100px; font-size:12px;
  font-weight:600; margin-bottom:4px;
  border:1px solid rgba(178,134,56,.35);}
.spotlight .sp-grid{display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr));
  gap:14px; margin:20px 0 18px;}
.spotlight .sp-cell{background:rgba(255,255,255,.06); padding:12px 14px;
  border-radius:var(--radius); border:1px solid rgba(255,255,255,.08);}
.spotlight .sp-cell .l{font-size:11px; color:#a8c4dd; font-weight:600;
  letter-spacing:.5px; margin-bottom:3px; text-transform:uppercase;}
.spotlight .sp-cell .v{font-size:15.5px; font-weight:700; color:#fff; line-height:1.5;}
.spotlight .sp-cta{display:inline-flex; align-items:center; gap:8px;
  background:var(--gold-2); color:#fff; padding:10px 24px; border-radius:var(--radius);
  font-size:14px; font-weight:700; transition:.15s;}
.spotlight .sp-cta:hover{background:var(--gold); color:#fff;
  transform:translateY(-1px); box-shadow:0 6px 16px rgba(178,134,56,.4);}
.spotlight .sp-next{margin-top:14px; padding:12px 16px;
  background:rgba(255,255,255,.08); border-radius:var(--radius);
  border-inline-start:3px solid #fce6b8; font-size:14px;}
.spotlight .sp-next b{color:#fce6b8;}
.spotlight .sp-next .days{color:#fff; font-weight:700; font-variant-numeric:tabular-nums;}

/* ---------- العدّاد ---------- */
.countdown{background:var(--gold-soft); border:1px solid #e5d9c0;
  border-radius:var(--radius); padding:17px 20px; margin:14px 0; text-align:center;}
.countdown .cd-label{font-size:12.5px; color:var(--gold); font-weight:600;
  letter-spacing:.5px;}
.countdown .cd-when{font-size:16px; font-weight:700; color:var(--ink); margin:5px 0;}
.countdown .cd-units{display:flex; justify-content:center; gap:22px; margin-top:10px;}
.countdown .u{min-width:56px;}
.countdown .u .n{font-size:27px; font-weight:700; color:var(--navy);
  font-variant-numeric:tabular-nums; line-height:1.2;}
.countdown .u .s{font-size:11.5px; color:var(--muted);}

/* ---------- الخط الزمني ---------- */
.timeline{position:relative; padding-inline-start:22px; margin:12px 0;}
.timeline::before{content:''; position:absolute; inset-inline-start:5px; top:6px;
  bottom:6px; width:2px; background:var(--line);}
.tl-item{position:relative; padding-bottom:16px;}
.tl-item::before{content:''; position:absolute; inset-inline-start:-21px; top:7px;
  width:10px; height:10px; border-radius:50%; background:var(--paper);
  border:2px solid var(--navy-2);}
.tl-item.new::before{background:var(--gold); border-color:var(--gold);}
.tl-when{font-size:11.5px; color:var(--faint); font-variant-numeric:tabular-nums;}
.tl-what{font-size:14px; margin-top:1px;}
.tl-what b{color:var(--navy);}
.tl-what s{color:var(--faint);}

/* ---------- تذييل ---------- */
.disclaimer{background:#fffdf7; border:1px solid #e8ddc4;
  border-radius:var(--radius); padding:16px 20px; font-size:13px;
  color:#6b5c3c; line-height:1.8;}
.disclaimer b{color:#8a6d2f;}
.engines{margin-top:11px; padding-top:10px; border-top:1px solid #e8ddc4;
  font-size:11.5px; color:#9a8a68; font-family:ui-monospace,Menlo,Consolas,monospace;
  direction:ltr; text-align:end;}
.empty{padding:30px 22px; text-align:center; color:var(--faint); font-size:14px;}
.hidden{display:none !important;}

/* ---------- رادار الإشارات ---------- */
.radar-intro{background:#f7f9fb; border:1px solid var(--line);
  border-radius:var(--radius); padding:13px 16px; font-size:13.5px;
  color:var(--muted); margin-bottom:16px;}
.radar-intro b{color:var(--navy);}

.signal{border:1px solid var(--line); border-radius:var(--radius);
  margin-bottom:13px; overflow:hidden; background:var(--paper);}
.signal.novel{border-inline-start:4px solid var(--gold); background:#fffdf8;}
.signal.confirmed{border-inline-start:4px solid var(--green); background:#f8fcfa;}
.signal.weak{opacity:.86;}
.sig-head{padding:12px 15px 9px; display:flex; gap:9px;
  align-items:flex-start; flex-wrap:wrap;}
.sig-statement{flex:1 1 260px; font-size:15px; font-weight:600;
  color:var(--ink); line-height:1.65; min-width:200px;}
.sig-evidence{display:flex; gap:14px; flex-wrap:wrap; padding:0 15px 10px;
  font-size:12.5px; color:var(--muted); font-variant-numeric:tabular-nums;}
.sig-evidence b{color:var(--navy); font-weight:600;}
.sig-quotes{background:#f8f9fb; border-top:1px solid var(--line-soft);
  padding:10px 15px;}
.sig-quote{font-size:13px; color:var(--body); padding:5px 0;
  border-bottom:1px dotted var(--line); line-height:1.7;}
.sig-quote:last-child{border-bottom:none;}
.sig-quote .who{font-weight:600; color:var(--navy-2); font-size:12.5px;}
.sig-quote .eye{color:var(--gold); font-size:11.5px; font-weight:600;}
.sig-lead{background:var(--green-soft); color:var(--green); font-size:12.5px;
  font-weight:600; padding:7px 15px; border-top:1px solid #d5e8de;}

.gauge{display:grid; grid-template-columns:repeat(auto-fit,minmax(118px,1fr));
  gap:1px; background:var(--line); border:1px solid var(--line);
  border-radius:var(--radius); overflow:hidden; margin-bottom:18px;}
.gauge .g{background:var(--paper); padding:12px 14px; text-align:center;}
.gauge .g .n{font-size:23px; font-weight:700; color:var(--navy);
  font-variant-numeric:tabular-nums; line-height:1.3;}
.gauge .g .l{font-size:11.5px; color:var(--muted);}
.gauge .g.gold .n{color:var(--gold);}
.gauge .g.green .n{color:var(--green);}

.qlist{margin:0; padding:0; list-style:none;}
.qlist li{padding:8px 0; border-bottom:1px solid var(--line-soft);
  font-size:13.5px;}
.qlist li:last-child{border-bottom:none;}
.qlist .meta{font-size:11.5px; color:var(--faint); margin-top:2px;}

/* ---------- طباعة ---------- */
@media print{
  body{background:#fff; font-size:11.5pt;}
  .topbar,.filters,.rail,.sp-cta{display:none !important;}
  .wrap{display:block; max-width:100%; padding:0;}
  section.block{border:1px solid #ccc; break-inside:avoid; margin-bottom:14px;
    box-shadow:none;}
  .masthead{background:#fff !important; color:#000; border-bottom:3px solid #000;}
  .masthead .eyebrow,.masthead .lede,.issue{color:#444 !important;}
  .masthead h1,.issue b{color:#000 !important;}
  .spotlight{background:#fff !important; color:#000; border:2px solid #000;}
  .spotlight h2,.spotlight .v{color:#000 !important;}
  .spotlight .sp-eyebrow,.spotlight .l{color:#444 !important;}
  a{color:#000; text-decoration:underline;}
  .entry{break-inside:avoid;}
}
"""

SHELL = """<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="description" content="__DESC__">
<meta name="robots" content="index,follow">
<title>__TITLE__</title>
<style>__CSS__</style>
</head>
<body>
__MASTHEAD__
__TOPBAR__
<div class="wrap">
  <main class="doc">
__MAIN__
  </main>
  <aside class="rail">
__RAIL__
  </aside>
</div>
<script>__JS__</script>
</body>
</html>
"""

JS = """
document.querySelectorAll('[data-filters]').forEach(function(bar){
  var scope = bar.closest('section') || bar.closest('details') || bar.parentElement;
  var btns = bar.querySelectorAll('button');
  btns.forEach(function(b){
    b.addEventListener('click', function(){
      btns.forEach(function(x){ x.classList.remove('on'); });
      b.classList.add('on');
      var want = b.dataset.filter;
      scope.querySelectorAll('[data-sec]').forEach(function(card){
        card.classList.toggle('hidden', want !== 'all' && card.dataset.sec !== want);
      });
    });
  });
});

(function(){
  var el = document.getElementById('countdown');
  if(!el || !el.dataset.deadline) return;
  var target = new Date(el.dataset.deadline + 'T00:00:00+03:00').getTime();
  var slots = el.querySelectorAll('.u .n');
  function tick(){
    var diff = target - Date.now();
    if(diff < 0){ el.querySelector('.cd-units').innerHTML =
      '<div style="font-size:16px;font-weight:600;color:#a52820">حلّ الموعد</div>'; return; }
    var d = Math.floor(diff/86400000),
        h = Math.floor(diff/3600000)%24,
        m = Math.floor(diff/60000)%60,
        s = Math.floor(diff/1000)%60;
    [d,h,m,s].forEach(function(v,i){ if(slots[i]) slots[i].textContent = v; });
    setTimeout(tick, 1000);
  }
  tick();
})();
"""


def _page(title, desc, masthead, topbar, main, rail):
    return (SHELL
            .replace("__TITLE__", esc(title))
            .replace("__DESC__", esc(desc))
            .replace("__CSS__", CSS)
            .replace("__MASTHEAD__", masthead)
            .replace("__TOPBAR__", topbar)
            .replace("__MAIN__", main)
            .replace("__RAIL__", rail)
            .replace("__JS__", JS))


def _block(title, body, anchor=None):
    a = f' id="{anchor}"' if anchor else ""
    return (f'<section class="block"{a}>\n  <h2>{esc(title)}</h2>\n'
            f'  <div class="block-body">\n{body}\n  </div>\n</section>')


def _block_collapsed(title, body, anchor=None, hint="", open_=False):
    """
    نفس _block لكن قابل للطي (details/summary) — للأقسام الثانوية اللي
    مش لازم تظهر مفتوحة بالكامل من أول وهلة (فيد الأخبار، جدول المصادر،
    إشارات ضعيفة...). بيشتغل بدون JS، ومحتواه مقروء لو JS متعطّل أو
    لمحركات البحث.
    """
    a = f' id="{anchor}"' if anchor else ""
    open_attr = " open" if open_ else ""
    hint_html = f'<span class="hint">{esc(hint)}</span>' if hint else ""
    return (f'<details class="collapsible block"{a}{open_attr}>\n'
            f'  <summary class="toggle-head">{esc(title)}{hint_html}</summary>\n'
            f'  <div class="block-body">\n{body}\n  </div>\n</details>')


def _kpis(pairs):
    cells = []
    for label, value, cls in pairs:
        cells.append(f'  <div class="kpi {cls}"><div class="k-label">{esc(label)}</div>'
                     f'<div class="k-value">{esc(value)}</div></div>')
    return '<div class="kpis">\n' + "\n".join(cells) + "\n</div>"


# ============================================================
#  مكوّنات الفيد
# ============================================================

def _entry(item, section, new_links, top_links, urgent_links):
    kind = item.get("kind", "news")
    kind_tag = {"video": ("فيديو", "gold"), "official": ("مصدر رسمي", "navy"),
                "social": ("سوشيال", "gray")}.get(kind)

    tags = []
    if item["link"] in urgent_links:
        tags.append('<span class="tag red">عاجل</span>')
    if item["link"] in top_links:
        tags.append('<span class="tag amber">مهم</span>')
    if item["link"] in new_links:
        tags.append('<span class="tag green">جديد</span>')
    if kind_tag:
        tags.append(f'<span class="tag {kind_tag[1]}">{kind_tag[0]}</span>')

    # مصدر مع علامة "+ N مصادر" لو الخبر مدموج
    src_html = esc(item.get("source") or "مصدر")
    n_src = int(item.get("source_count") or 1)
    if n_src > 1:
        src_html += f' <span class="src-plus">+{n_src - 1}</span>'

    parts = [
        f'    <article class="entry" data-sec="{slug(section)}">',
        '      <div class="entry-meta">',
        f'        <span class="src">{src_html}</span>',
        f'        <span class="dot">·</span><span>{esc(section)}</span>',
    ]
    when = ago(item.get("published", ""))
    if when:
        parts.append(f'        <span class="dot">·</span><span>{esc(when)}</span>')
    if tags:
        parts.append("        " + "".join(tags))
    parts.append('      </div>')
    parts.append(
        f'      <h3 class="t"><a href="{esc(item["link"])}" target="_blank" '
        f'rel="noopener">{esc(item["title"])}</a></h3>')

    if item.get("snippet"):
        parts.append(f'      <p class="snip">{esc(item["snippet"][:230])}</p>')

    # قائمة المصادر المدموجة (لو موجودة)
    aliases = item.get("aliases") or []
    if aliases:
        alias_links = []
        for a in aliases[:8]:
            src = esc(a.get("source", "مصدر"))
            link = esc(a.get("link", "#"))
            alias_links.append(
                f'<a href="{link}" target="_blank" rel="noopener">{src}</a>')
        parts.append(
            '      <div class="aliases">'
            '<span class="a-label">نُشر أيضًا في:</span>'
            + " ".join(alias_links) + '</div>')

    st = item.get("stats") or {}
    if st.get("views"):
        parts.append(
            '      <div class="metrics">'
            f'<span>{num(st.get("views", 0))} مشاهدة</span>'
            f'<span>{num(st.get("likes", 0))} إعجاب</span>'
            f'<span>{num(st.get("comments", 0))} تعليق</span></div>')

    if item.get("ai_summary"):
        parts.append('      <div class="ai-box"><div class="ai-label">ملخص آلي</div>'
                     + md_to_html(item["ai_summary"]) + '</div>')

    if item.get("comment_analysis"):
        parts.append('      <div class="ai-box people">'
                     '<div class="ai-label">قراءة تعليقات الجمهور</div>'
                     + md_to_html(item["comment_analysis"]) + '</div>')

    tops = item.get("top_comments") or []
    if tops:
        rows = ['      <div class="quotes"><div class="q-label">أبرز التعليقات تفاعلًا</div>']
        for c in tops:
            initial = esc((c.get("author") or "؟").strip()[:1])
            extra = f' · {c.get("replies", 0)} رد' if c.get("replies") else ""
            rows.append(
                f'        <div class="quote"><div class="av">{initial}</div>'
                f'<div class="qb"><div class="qn">{esc(c.get("author", ""))}</div>'
                f'{esc(c.get("text", "")[:280])}'
                f'<div class="ql">{num(c.get("likes", 0))} إعجاب{extra}</div>'
                f'</div></div>')
        rows.append('      </div>')
        parts.append("\n".join(rows))

    parts.append('    </article>')
    return "\n".join(parts)


def _official_table(health_rows):
    if not health_rows:
        return ""
    tone = {"يعمل": "green", "متقطع": "amber", "متعذّر": "red", "لم يُفحص": "gray"}
    rows = ['<table><thead><tr><th>المصدر</th><th>الحالة</th>'
            '<th>سطور مرصودة</th><th>آخر فحص</th></tr></thead><tbody>']
    for r in health_rows:
        note = ' <span class="tag gray">JS</span>' if r["js"] else ""
        checked = ago(r.get("checked", "")) or "—"
        rows.append(
            f'<tr><td><a href="{esc(r["url"])}" target="_blank" rel="noopener">'
            f'{esc(r["name"])}</a>{note}</td>'
            f'<td><span class="tag {tone.get(r["status"], "gray")}">'
            f'{esc(r["status"])}</span></td>'
            f'<td>{r["lines"]}</td><td>{esc(checked)}</td></tr>')
        if r.get("error"):
            rows.append(f'<tr class="note-row"><td colspan="4">{esc(r["error"][:160])}</td></tr>')
    rows.append('</tbody></table>')
    return "\n".join(rows)


def _market_table(rows):
    if not rows:
        return ""
    tone = {"مفتوح": "green", "مغلق": "red", "منتظر": "amber"}
    out = ['<table><thead><tr><th>الملف</th><th>المرحلة</th><th>الحالة</th>'
           '<th>الموعد القادم</th></tr></thead><tbody>']
    for r in rows:
        out.append(
            f'<tr><td class="k">{esc(r["topic"])}</td><td>{esc(r["stage"])}</td>'
            f'<td><span class="tag {tone.get(r["status"], "gray")}">'
            f'{esc(r["status"])}</span></td><td>{esc(r["next"])}</td></tr>')
        if r.get("last") and r["last"] != "—":
            out.append(f'<tr class="note-row"><td colspan="4">↳ {esc(r["last"])}</td></tr>')
    out.append('</tbody></table>')
    return "\n".join(out)


# ============================================================
#  رادار الإشارات المبكرة
# ============================================================

TIER_TONE = {
    "مؤكدة رسميًا": "green", "إشارة قوية": "amber", "إشارة متقاطعة": "amber",
    "شهادة فردية": "navy", "إشارة فردية": "gray", "مكذّبة": "red",
    "منتهية": "gray",
}
PLATFORM_LABEL = {"youtube": "يوتيوب", "telegram": "تليجرام",
                  "reddit": "Reddit", "social": "سوشيال"}


def _signal_card(sig):
    tier_name = sig.get("tier", "—")
    cls = "signal"
    if sig.get("status") == "مؤكدة رسميًا":
        cls += " confirmed"
    elif sig.get("novel"):
        cls += " novel"
    if tier_name in ("إشارة فردية", "منتهية"):
        cls += " weak"

    tags = [f'<span class="tag {TIER_TONE.get(tier_name, "gray")}">'
            f'{esc(tier_name)}</span>']
    if sig.get("novel") and sig.get("status") != "مؤكدة رسميًا":
        tags.append('<span class="tag gold">مش في الأخبار</span>')
    if sig.get("type"):
        tags.append(f'<span class="tag gray">{esc(sig["type"])}</span>')

    out = [f'<div class="{cls}">',
           '  <div class="sig-head">',
           f'    <div class="sig-statement">{esc(sig.get("statement", ""))}</div>',
           f'    <div>{"".join(tags)}</div>',
           '  </div>',
           '  <div class="sig-evidence">',
           f'    <span>قالها <b>{sig.get("mentions", 0)}</b> شخص</span>',
           f'    <span>من <b>{sig.get("independence", 0)}</b> مصدر مستقل</span>']

    if sig.get("firsthand"):
        out.append(f'    <span><b>{sig["firsthand"]}</b> تجربة شخصية 👁</span>')
    if sig.get("total_likes"):
        out.append(f'    <span><b>{num(sig["total_likes"])}</b> تفاعل</span>')
    platforms = sorted({s.get("platform") for s in (sig.get("sources") or [])
                        if s.get("platform")})
    if platforms:
        names = "، ".join(PLATFORM_LABEL.get(p, p) for p in platforms)
        out.append(f'    <span>{esc(names)}</span>')
    if sig.get("first_seen"):
        out.append(f'    <span>أول رصد: {esc(ago(sig["first_seen"]))}</span>')
    out.append('  </div>')

    quotes = (sig.get("sources") or [])[:3]
    if quotes:
        out.append('  <div class="sig-quotes">')
        for s in quotes:
            who = esc(s.get("author") or s.get("channel") or "مجهول")
            if s.get("url"):
                who = (f'<a href="{esc(s["url"])}" target="_blank" '
                       f'rel="noopener">{who}</a>')
            eye = ' <span class="eye">شاف بنفسه</span>' if s.get("firsthand") else ""
            out.append(f'    <div class="sig-quote"><span class="who">{who}</span>'
                       f'{eye}<br>«{esc(s.get("quote", "")[:260])}»</div>')
        out.append('  </div>')

    if sig.get("status") == "مؤكدة رسميًا":
        cb = sig.get("confirmed_by") or {}
        lead = sig.get("lead_days")
        msg = f'✅ اتأكدت من: {esc(str(cb.get("source", "مصدر رسمي")))}'
        if lead is not None:
            msg += f' — الجمهور سبق الأخبار بـ <b>{lead}</b> يوم'
        out.append(f'  <div class="sig-lead">{msg}</div>')

    out.append('</div>')
    return "\n".join(out)


def _radar_body(intel, limit=24, compact=False):
    counts = intel.get("counts") or {}
    stats = intel.get("stats") or {}

    body = []
    if not compact:
        body.append("""<div class="radar-intro">
  الرادار بيقرا كلام الناس في تعليقات يوتيوب وقنوات تليجرام و Reddit، ويطلّع منه
  <b>الادعاءات الواقعية</b> بس (مش الآراء). الادعاء اللي يتكرر من
  <b>مصادر مستقلة مختلفة</b> بياخد ثقة أعلى. الإشارة المعلّمة
  <b>«مش في الأخبار»</b> يعني ناس بتقولها ومحدش نشرها رسميًا لحد دلوقتي.
  <br><b>ده كلام ناس على الإنترنت — مش مصدر رسمي، ومش كله صح.</b>
</div>""")

    cells = [
        ("إشارة مرصودة", counts.get("total", 0), ""),
        ("مش في الأخبار", counts.get("novel", 0), "gold"),
        ("قوية أو متقاطعة", counts.get("strong", 0), ""),
        ("اتأكدت رسميًا", counts.get("confirmed", 0), "green"),
    ]
    if stats.get("avg_lead_days") is not None:
        cells.append(("متوسط سبق الجمهور",
                      f"{stats['avg_lead_days']} يوم", "green"))

    body.append('<div class="gauge">' + "".join(
        f'<div class="g {c}"><div class="n">{esc(v)}</div>'
        f'<div class="l">{esc(l)}</div></div>' for l, v, c in cells
    ) + '</div>')

    if intel.get("digest") and not compact:
        body.append('<div class="ai-box people">'
                    '<div class="ai-label">قراءة الرادار</div>'
                    + md_to_html(intel["digest"]) + '</div>')

    novel = intel.get("novel") or []
    confirmed = intel.get("confirmed") or []
    others = [s for s in (intel.get("signals") or [])
              if s not in novel and s not in confirmed]

    if compact:
        # وضع مختصر (الصفحة الرئيسية): أقوى ٣-٤ إشارات بس كسطر واحد،
        # والباقي وراء رابط. الهدف صفحة قصيرة تُقرأ في ثوانٍ.
        top = (confirmed + novel)[:4]
        if top:
            body.append("<h3>أهم الإشارات</h3>")
            body.append('<ul class="qlist">')
            for sig in top:
                icon = "✅" if sig in confirmed else "🆕"
                body.append(
                    f'<li>{icon} <b>{esc(sig.get("statement", ""))}</b>'
                    f'<div class="meta">قالها {sig.get("mentions", 0)} شخص من '
                    f'{sig.get("independence", 0)} مصدر مستقل'
                    f'{" · اتأكدت رسميًا" if sig in confirmed else ""}</div></li>')
            body.append('</ul>')
        elif not (novel or confirmed or others):
            body.append('<div class="empty">لسه مفيش إشارات مرصودة. '
                        'الرادار محتاج دورة أو اتنين عشان يجمع كلام كفاية.</div>')
        return "\n".join(body)

    if novel:
        body.append("<h3>معلومات من الناس مش موجودة في الأخبار</h3>")
        body.append('<p style="font-size:13px;color:var(--muted);margin-top:0">'
                    'دي أهم حاجة في الرادار — كلام بيتقال ومحدش نشره رسميًا. '
                    '<b>كل واحدة محتاجة تأكيد قبل ما تتصرف عليها.</b></p>')
        for sig in novel[:limit]:
            body.append(_signal_card(sig))

    if confirmed:
        body.append("<h3>إشارات اتأكدت رسميًا</h3>")
        body.append('<p style="font-size:13px;color:var(--muted);margin-top:0">'
                    'الحاجات دي قالها الناس الأول وبعدين نزلت رسميًا — '
                    'المقياس ده بيقولك تثق في الرادار قد إيه.</p>')
        for sig in confirmed[:10]:
            body.append(_signal_card(sig))

    if others:
        others_html = "\n".join(_signal_card(sig) for sig in others[:limit])
        body.append(_block_collapsed(
            "باقي الإشارات", others_html, hint=f"{len(others)} إشارة أضعف"))

    questions = intel.get("questions") or []
    if questions:
        q_html = ['<ul class="qlist">']
        for q in questions[:14]:
            src = PLATFORM_LABEL.get(q.get("platform"), q.get("platform", ""))
            link = (f' · <a href="{esc(q["url"])}" target="_blank" '
                    f'rel="noopener">المصدر</a>' if q.get("url") else "")
            q_html.append(f'<li>{esc(q.get("text", ""))}'
                          f'<div class="meta">{esc(src)}{link}</div></li>')
        q_html.append('</ul>')
        body.append(_block_collapsed(
            "أسئلة الناس اللي مالهاش إجابة", "\n".join(q_html),
            hint="بتوضّح فين الغموض الرسمي"))

    if not (novel or confirmed or others or questions):
        body.append('<div class="empty">لسه مفيش إشارات مرصودة. '
                    'الرادار محتاج دورة أو اتنين عشان يجمع كلام كفاية.</div>')

    return "\n".join(body)


# ============================================================
#  قسم "آخر التحديثات" — Latest Updates timeline
# ============================================================

_SECTION_ICON = {
    "بيت الوطن ومبادرات المغتربين": "🏘️",
    "طروحات ومشروعات جديدة": "📢",
    "تحليل السوق والأسعار": "📊",
    "فيديوهات وتحليلات": "🎬",
    "🏛️ المصادر الرسمية": "🏛️",
    "سوشيال ميديا": "💬",
}


def _pick_latest(sections, new_links, urgent_links, official_changes, limit=8):
    """
    يجمع آخر التحديثات من كل مصدر:
      • تغييرات رسمية جديدة (أولوية)
      • أخبار عاجلة/جديدة من كل قسم
    مرتّبة زمنيًا — الأحدث فوق.
    """
    latest = []

    # تغييرات رسمية → أولوية قصوى
    for ch in (official_changes or [])[:5]:
        latest.append({
            "kind": "official",
            "when_iso": ch.get("when") or "",
            "title": f"تغيير في {ch['name']}",
            "source": "🏛️ مصدر رسمي",
            "section": "🏛️ المصادر الرسمية",
            "link": ch.get("url", "#"),
            "urgent": ch.get("urgent", False),
            "is_new": True,
            "snippet": " · ".join((ch.get("added") or [])[:2])[:200],
            "source_count": 1,
        })

    # أخبار من كل الأقسام — بس الجديد والعاجل والمهم
    for name, items in (sections or {}).items():
        for it in items:
            link = it.get("link", "")
            is_new = link in new_links
            is_urgent = link in urgent_links
            if not (is_new or is_urgent):
                continue
            latest.append({
                "kind": it.get("kind", "news"),
                "when_iso": it.get("published") or "",
                "when_ts": it.get("published_ts") or 0,
                "title": it.get("title", ""),
                "source": it.get("source", ""),
                "section": name,
                "link": link,
                "urgent": is_urgent,
                "is_new": is_new,
                "snippet": (it.get("snippet") or "")[:180],
                "source_count": it.get("source_count", 1),
            })

    # ترتيب: عاجل الأول، بعده الأحدث
    latest.sort(key=lambda x: (
        0 if x.get("urgent") else 1,
        -float(x.get("when_ts") or 0),
    ))
    return latest[:limit]


def _updates_block(latest):
    """قسم آخر التحديثات على شكل timeline نظيف."""
    if not latest:
        return ""

    rows = []
    for it in latest:
        when = ago(it.get("when_iso") or "")
        if not when:
            when = "الآن"
        # نجزّئ الوقت: "منذ 2 ساعة" → b:2 remainder:ساعة
        m = re.match(r"منذ\s+(\d+)\s+(.+)", when)
        if m:
            when_html = f'<b>{m.group(1)}</b>{esc(m.group(2))}'
        else:
            when_html = f'<b>{esc(when)}</b>'

        tags = []
        if it.get("urgent"):
            tags.append('<span class="tag red">عاجل</span>')
        if it.get("kind") == "official":
            tags.append('<span class="tag navy">رسمي</span>')
        elif it.get("kind") == "video":
            tags.append('<span class="tag gold">فيديو</span>')
        if it.get("is_new") and not it.get("urgent"):
            tags.append('<span class="tag green">جديد</span>')

        icon = _SECTION_ICON.get(it.get("section", ""), "•")
        src = esc(it.get("source", "مصدر"))
        n = int(it.get("source_count") or 1)
        if n > 1:
            src += f' <span class="src-plus">+{n - 1}</span>'

        rows.append(
            f'    <div class="u-item">'
            f'<div class="u-when">{when_html}</div>'
            f'<div class="u-body">'
            f'<div class="u-title"><a href="{esc(it["link"])}" '
            f'target="_blank" rel="noopener">{icon} {esc(it["title"])}</a></div>'
            f'<div class="u-meta"><span class="src">{src}</span>'
            f'<span>·</span><span>{esc(it.get("section", ""))}</span></div>'
            f'</div>'
            f'<div class="u-tags">{" ".join(tags)}</div>'
            f'</div>')

    return f"""<section class="updates" id="updates">
  <div class="updates-head">
    <h2>آخر التحديثات</h2>
    <div class="u-when">تحديث كل ٤ ساعات · آخر دورة: {esc(stamp())}</div>
  </div>
  <div class="updates-list">
{chr(10).join(rows)}
  </div>
</section>"""


# ============================================================
#  الصفحة الرئيسية
# ============================================================

def _now_digest_block(now_digest, more_href="#updates"):
    """
    شريط الخلاصة العاجلة — أول حاجة يشوفها القارئ فوق الصفحة. لو مفيش
    مستجدات حقيقية من آخر دورة، مابيظهرش خالص بدل فقرة عامة فاضية.
    """
    if not now_digest or not str(now_digest).strip():
        return ""
    return f"""<div class="now-digest">
  <div class="now-digest-label">⚡ الأهم من آخر تحديث</div>
  <div class="now-digest-body">{md_to_html(now_digest)}</div>
</div>"""


def build_index(sections, brief, new_links, top_links, urgent_links,
                engines_note, forecast=None, market_rows=None,
                health_rows=None, beit=None, official_changes=None,
                intel=None, now_digest=None):
    total = sum(len(v) for v in sections.values())
    official_ok = sum(1 for r in (health_rows or []) if r["status"] == "يعمل")
    novel_count = ((intel or {}).get("counts") or {}).get("novel", 0)

    masthead = f"""<header class="masthead"><div class="masthead-in">
  <div class="masthead-brand">
    <div class="eyebrow">مرصد مستقل · رصد وتحليل آلي</div>
    <h1>مرصد العقارات المصرية للمصريين بالخارج</h1>
    <p class="lede">متابعة لحظية لبيت الوطن ومبادرات المغتربين ومصادر وزارة الإسكان الرسمية،
      بتحليل مدعوم بالذكاء الاصطناعي وتنبيهات مبكرة.</p>
  </div>
  <div class="masthead-meta">
    <span class="live">مباشر</span>
    <span>الإصدار: <b>{esc(stamp())}</b></span>
    <span>العناصر المرصودة: <b>{total}</b></span>
    <span>مصادر رسمية عاملة: <b>{official_ok}/{len(health_rows or [])}</b></span>
  </div>
</div></header>"""

    radar_link = ('\n  <a href="#radar">رادار الإشارات</a>' if intel else "")
    topbar = f"""<nav class="topbar"><div class="topbar-in">
  <a href="#updates">آخر التحديثات</a>
  <a href="#summary">الملخص التنفيذي</a>
  <a href="#status">حالة الملفات</a>{radar_link}
  <a href="#outlook">الاستشراف</a>
  <a href="#official">الرصد الرسمي</a>
  <a href="#feed">الرصد الإخباري</a>
  <a href="beit-alwatan.html" class="cta">ملف بيت الوطن ←</a>
</div></nav>"""

    kpi_cells = [
        ("إجمالي العناصر", str(total), ""),
        ("جديد هذه الدورة", str(len(new_links)), "good" if new_links else ""),
        ("عاجل", str(len(urgent_links)), "alert" if urgent_links else ""),
        ("تغييرات رسمية", str(len(official_changes or [])),
         "warn" if official_changes else ""),
    ]
    if intel:
        kpi_cells.append(("إشارات مش في الأخبار", str(novel_count),
                          "warn" if novel_count else ""))

    main = []
    digest_html = _now_digest_block(now_digest)
    if digest_html:
        main.append(digest_html)
    main.append(_kpis(kpi_cells))

    # بانر بيت الوطن (Hero)
    if beit:
        cells = []
        for label, key in (("المرحلة", "stage"), ("حالة الحجز", "booking"),
                           ("سعر المتر", "price"), ("المساحات", "areas"),
                           ("مقدم الجدية", "deposit")):
            v = beit.get(key) or "لم يُعلن بعد"
            cells.append(f'<div class="sp-cell"><div class="l">{esc(label)}</div>'
                         f'<div class="v">{esc(str(v)[:60])}</div></div>')
        nxt = beit.get("next")
        nxt_line = ""
        if nxt:
            days = nxt.get("days_left")
            days_txt = ""
            if isinstance(days, int):
                if days < 0:
                    days_txt = ' — <span class="days">مرّ الموعد</span>'
                elif days == 0:
                    days_txt = ' — <span class="days">النهاردة!</span>'
                elif days <= 3:
                    days_txt = f' — <span class="days">باقي {days} يوم فقط ⚠️</span>'
                else:
                    days_txt = f' — <span class="days">باقي {days} يوم</span>'
            nxt_line = (f'<div class="sp-next">⏰ <b>{esc(nxt.get("label", "الموعد القادم"))}:</b> '
                        f'{esc(nxt.get("raw", ""))}{days_txt}</div>')
        summary_line = ""
        if beit.get("summary"):
            plain = re.sub(r"\*\*(.+?)\*\*", r"\1", str(beit["summary"]))
            plain = re.sub(r"##[^\n]*\n", "", plain).strip()[:220]
            if plain:
                summary_line = (f'<p style="margin:12px 0 0;color:#e0ecf7;'
                                f'font-size:14.5px;line-height:1.7">{esc(plain)}…</p>')
        main.append(f"""<div class="spotlight"><div class="spotlight-in">
  <div class="sp-tag">الملف الأهم — متابعة مستمرة</div>
  <div class="sp-eyebrow">أراضي المصريين بالخارج</div>
  <h2 class="display">بيت الوطن</h2>
  {summary_line}
  <div class="sp-grid">{''.join(cells)}</div>
  {nxt_line}
  <div style="margin-top:18px">
    <a class="sp-cta" href="beit-alwatan.html">افتح الملف الكامل ←</a>
  </div>
</div></div>""")

    # آخر التحديثات — أهم قسم بصريًا، فوق الملخص
    latest = _pick_latest(sections, new_links, urgent_links, official_changes,
                          limit=10)
    updates_html = _updates_block(latest)
    if updates_html:
        main.append(updates_html)

    if brief:
        main.append(_block("الملخص التنفيذي", md_to_html(brief), "summary"))

    if market_rows:
        main.append(_block("حالة الملفات المتابَعة", _market_table(market_rows), "status"))

    if intel and (intel.get("signals") or intel.get("questions")):
        main.append(_block("رادار الإشارات المبكرة — من كلام الناس",
                           _radar_body(intel, limit=10, compact=True) +
                           '<p style="margin-top:16px"><a href="beit-alwatan.html#radar">'
                           '<b>افتح الرادار الكامل في ملف بيت الوطن ←</b></a></p>',
                           "radar"))

    if forecast:
        main.append(_block("الاستشراف وقراءة السوق", md_to_html(forecast), "outlook"))

    # الرصد الرسمي — التغييرات (لو فيه) ظاهرة دايمًا، جدول الحالة مطوي
    official_body = []
    has_official_changes = bool(official_changes)
    if official_changes:
        official_body.append("<h3>تغييرات مرصودة في هذه الدورة</h3>")
        for ch in official_changes[:8]:
            badge = ('<span class="tag red">عاجل</span>' if ch["urgent"]
                     else '<span class="tag navy">تحديث</span>')
            kws = (f'<div class="snip">كلمات مرصودة: {esc("، ".join(ch["keywords"][:6]))}</div>'
                   if ch.get("keywords") else "")
            lines = "".join(f"<li>{esc(l[:220])}</li>" for l in ch["added"][:6])
            official_body.append(
                f'<div style="margin:14px 0;padding-inline-start:12px;'
                f'border-inline-start:3px solid var(--navy-2)">'
                f'<div>{badge} <a href="{esc(ch["url"])}" target="_blank" rel="noopener">'
                f'<b>{esc(ch["name"])}</b></a></div>{kws}<ul>{lines}</ul></div>')
    else:
        official_body.append('<p style="color:var(--muted)">'
                             'لا توجد تغييرات مرصودة في المصادر الرسمية خلال هذه الدورة.</p>')
    official_body.append("<h3>حالة المصادر المراقَبة</h3>")
    official_body.append(_official_table(health_rows or []))
    if has_official_changes:
        main.append(_block("الرصد الرسمي", "\n".join(official_body), "official"))
    else:
        main.append(_block_collapsed("الرصد الرسمي", "\n".join(official_body),
                                     "official", hint="مفيش تغييرات جديدة"))

    # الفيد — مطوي افتراضيًا: قسم "آخر التحديثات" فوق بيغطي الجديد والعاجل
    # بالفعل، ده أرشيف كامل لمن يريد التفاصيل
    buttons = ['<button class="on" data-filter="all">الكل</button>']
    for name, items in sections.items():
        if items:
            buttons.append(f'<button data-filter="{slug(name)}">{esc(name)}</button>')

    entries = []
    for name, items in sections.items():
        for item in items[:config.MAX_ITEMS_PER_SECTION_ON_PAGE]:
            entries.append(_entry(item, name, new_links, top_links, urgent_links))

    feed_html = "\n".join(entries) or '<div class="empty">لا توجد عناصر مرصودة.</div>'
    main.append(f"""<details class="collapsible block" id="feed">
  <summary class="toggle-head">الرصد الإخباري الكامل
    <span class="hint">كل العناصر — {total} عنصر</span></summary>
  <div class="block-body">
  <div class="filters" data-filters>{''.join(buttons)}</div>
{feed_html}
  </div>
</details>""")

    main.append(f"""<div class="disclaimer">
  <b>تنويه منهجي.</b> تُجمَع المصادر آليًا وتُلخَّص بالذكاء الاصطناعي.
  الملخصات والتحليلات <b>قابلة للخطأ</b> — يُرجع إلى المصدر الأصلي دائمًا.
  المحتوى للاطلاع فقط وليس استشارة مالية أو قانونية. راجع كراسة الشروط الرسمية
  ومنصة مصر العقارية قبل أي التزام مالي.
  <div class="engines">{esc(engines_note or "")}</div>
</div>""")

    # العمود الجانبي — عناصر فعلية بس، بلا تكرار للتنقل اللي فوق أصلًا
    rail = []

    if intel and novel_count:
        rail.append(f"""<div class="box" style="border-color:#e5d9c0;background:#fffdf8">
  <h4 style="color:var(--gold)">تنبيه الرادار</h4>
  <div style="font-size:26px;font-weight:700;color:var(--gold);line-height:1.3">
    {novel_count}</div>
  <div style="font-size:13px;color:var(--muted)">معلومة بيقولها الناس
    ولسه منزلتش في الأخبار</div>
  <a href="#radar" style="display:inline-block;margin-top:8px;font-size:13.5px">
    شوفها ←</a>
</div>""")

    rail.append(f"""<div class="box"><h4>مصادر رسمية</h4>
  <a class="lnk" href="{esc(config.BEIT_ALWATAN["authority_url"])}" target="_blank" rel="noopener">هيئة المجتمعات العمرانية</a>
  <a class="lnk" href="{esc(config.BEIT_ALWATAN["booking_url"])}" target="_blank" rel="noopener">منصة مصر العقارية</a>
  <a class="lnk" href="{esc(config.BEIT_ALWATAN["official_url"])}" target="_blank" rel="noopener">بيتك في مصر</a>
</div>""")

    return _page("مرصد العقارات المصرية للمصريين بالخارج",
                 "رصد وتحليل آلي لسوق العقارات المصري وفرص المصريين بالخارج",
                 masthead, topbar, "\n".join(main), "\n".join(rail))


# ============================================================
#  صفحة بيت الوطن
# ============================================================

def build_beit_page(d, engines_note, intel=None, now_digest=None):
    """d = beit_alwatan.dashboard(state) · intel = intel.board(state)"""
    booking = d.get("booking") or "غير معروف"
    novel_count = ((intel or {}).get("counts") or {}).get("novel", 0)
    tone = ({"مفتوح": "green", "مغلق": "red", "منتهي": "red",
             "لم يُفتح بعد": "amber", "منتظر": "amber"}).get(booking, "gray")

    masthead = f"""<header class="masthead"><div class="masthead-in">
  <div class="eyebrow">ملف متابعة مخصّص</div>
  <h1>بيت الوطن — أراضي المصريين بالخارج</h1>
  <p class="lede">رصد مستمر للمرحلة والمواعيد والأسعار والشروط · تحليل وقراءة استشرافية</p>
  <div class="issue">
    <span>آخر تحديث: <b>{esc(stamp())}</b></span>
    <span>المرحلة: <b>{esc(d.get("stage") or "لم تُعلن")}</b></span>
    <span>حالة الحجز: <b>{esc(booking)}</b></span>
    <span>درجة الثقة: <b>{esc(d.get("confidence"))}</b></span>
  </div>
</div></header>"""

    radar_link = ('\n  <a href="#radar" style="color:var(--gold);font-weight:600">'
                  'رادار الإشارات</a>' if intel else "")
    topbar = f"""<nav class="topbar"><div class="topbar-in">
  <a href="index.html">← التقرير العام</a>
  <a href="#brief">الملخص</a>
  <a href="#facts">البطاقة</a>
  <a href="#dates">المواعيد</a>{radar_link}
  <a href="#places">المدن</a>
  <a href="#timeline">الخط الزمني</a>
  <a href="#people">كلام الناس</a>
  <a href="#outlook">التوقعات</a>
  <a href="#steps">خطوات عملية</a>
</div></nav>"""

    main = []

    digest_html = _now_digest_block(now_digest)
    if digest_html:
        main.append(digest_html)

    # لوحة القطع المتاحة/المحجوزة — مصدر مجتمعي حي (bit.mzayasoft)
    plots = d.get("plots")
    mzaya_url = d.get("mzaya_source_url") or (plots or {}).get("source_url") or config.BIT_MZAYASOFT_URL
    if plots:
        cells = []
        for label, key in (("الإجمالي", "total"), ("المحجوز", "reserved"),
                           ("المتبقي", "remaining"), ("اليوم", "today")):
            if key in plots:
                cells.append(f'<div class="kpi"><div class="k-label">{esc(label)}</div>'
                             f'<div class="k-value">{plots[key]:,}</div></div>')
        if cells:
            main.append(f"""<div class="plots-box">
  <div class="plots-label">لوحة القطع الحية — مصدر مجتمعي (غير رسمي)
    <a href="{esc(mzaya_url)}" target="_blank" rel="noopener">bit.mzayasoft.com ↗</a></div>
  <div class="kpis" style="margin:10px 0 0">{"".join(cells)}</div>
</div>""")

    # إعلانات جديدة فعليًا (لو فيه) — أهم حاجة، تظهر فوق فورًا
    new_ads = d.get("mzaya_new_ads")
    if new_ads:
        rows_html = []
        for a in new_ads[:8]:
            bits = []
            if a.get("status"):
                bits.append(f'<span class="tag {"good" if a["status"]=="معروض للبيع" else "alert"}">{esc(a["status"])}</span>')
            if a.get("area_m2"):
                bits.append(f'{a["area_m2"]:,} م²')
            if a.get("paid"):
                bits.append(f'مدفوع {a["paid"]:,} ج')
            if a.get("premium"):
                bits.append(f'الأوفر {a["premium"]:,} ج')
            phone_html = (f' · <a href="tel:{esc(a["phone"])}">{esc(a["phone"])}</a>'
                         if a.get("phone") else "")
            rows_html.append(f'<li>{" · ".join(bits)}{phone_html}</li>')
        main.append(f"""<div class="plots-box" style="border-inline-start:4px solid var(--gold-2)">
  <div class="plots-label">🆕 إعلانات قطع جديدة على bit.mzayasoft ({len(new_ads)})</div>
  <ul style="margin:10px 0 0; padding-inline-start:20px; font-size:14px; line-height:1.9">
    {"".join(rows_html)}
  </ul>
</div>""")

    # البرشامة — نطاق أقل/أعلى مقدم فعلي عبر كل المناطق + جدول تفصيلي
    price_range = d.get("mzaya_price_range")
    divisions = d.get("mzaya_divisions") or []
    if price_range or divisions:
        pr_html = ""
        if price_range and price_range.get("lowest") and price_range.get("highest"):
            pr_html = (f'<div class="kpis" style="margin:10px 0">'
                       f'<div class="kpi"><div class="k-label">أقل مقدم مسجّل</div>'
                       f'<div class="k-value">{price_range["lowest"]:,} ج</div></div>'
                       f'<div class="kpi"><div class="k-label">أعلى مقدم مسجّل</div>'
                       f'<div class="k-value">{price_range["highest"]:,} ج</div></div>'
                       f'<div class="kpi"><div class="k-label">عدد المناطق المرصودة</div>'
                       f'<div class="k-value">{price_range["divisions_count"]}</div></div>'
                       f'</div>')

        table_rows = []
        for div in divisions[:25]:
            name = esc(div.get("name") or "—")
            plot_count = div.get("plot_count") or "—"
            min_d = f'{div["min_deposit_n"]:,}' if div.get("min_deposit_n") else "—"
            max_d = f'{div["max_deposit_n"]:,}' if div.get("max_deposit_n") else "—"
            avg_area = esc(div.get("avg_area") or "—")
            link = div.get("link")
            name_html = (f'<a href="{esc(link)}" target="_blank" rel="noopener">{name}</a>'
                        if link else name)
            table_rows.append(f"<tr><td>{name_html}</td><td>{avg_area}</td>"
                             f"<td>{plot_count}</td><td>{min_d}</td><td>{max_d}</td></tr>")

        table_html = ""
        if table_rows:
            table_html = (f'<table><thead><tr><th>المنطقة/المرحلة</th>'
                         f'<th>متوسط المساحة</th><th>عدد القطع</th>'
                         f'<th>أقل مقدم (ج)</th><th>أعلى مقدم (ج)</th></tr></thead>'
                         f'<tbody>{"".join(table_rows)}</tbody></table>')

        body = pr_html + table_html
        main.append(_block_collapsed(
            "البرشامة — أقل وأعلى مقدم فعلي لكل منطقة (مصدر مجتمعي)",
            body, anchor="divisions",
            hint=f"{len(divisions)} منطقة مرصودة", open_=bool(price_range)))

    ads_stats = d.get("mzaya_ads_stats")
    if ads_stats and ads_stats.get("total"):
        parts = [f'{ads_stats["total"]} إعلان نشط']
        if ads_stats.get("sell_count") is not None:
            parts.append(f'{ads_stats["sell_count"]} معروض للبيع')
        if ads_stats.get("buy_count") is not None:
            parts.append(f'{ads_stats["buy_count"]} مطلوب للشراء')
        if ads_stats.get("avg_premium"):
            parts.append(f'متوسط الأوفر {ads_stats["avg_premium"]:,} ج')
        land_ads_url = mzaya_url.rstrip("/") + "/LandAds"
        main.append(f'<p class="hint" style="margin:-6px 0 14px">'
                   f'سوق القطع الحالي على bit.mzayasoft: {" · ".join(parts)} — '
                   f'<a href="{esc(land_ads_url)}" target="_blank" rel="noopener">كل الإعلانات ↗</a></p>')

    nxt = d.get("next")
    kpi_cells = [
        ("المرحلة الحالية", d.get("stage") or "—", ""),
        ("حالة الحجز", booking, "good" if tone == "green" else
         "alert" if tone == "red" else ""),
        ("سعر المتر", d.get("price") or "—", ""),
        ("أقرب موعد", (f"{nxt['days_left']} يوم" if nxt else "—"),
         "alert" if nxt and nxt["days_left"] <= 7 else ""),
    ]
    if intel:
        kpi_cells.append(("إشارات مش في الأخبار", novel_count,
                          "alert" if novel_count else ""))
    main.append(_kpis(kpi_cells))

    # العدّاد التنازلي
    if nxt and nxt.get("iso"):
        main.append(f"""<div class="countdown" id="countdown" data-deadline="{esc(nxt['iso'])}">
  <div class="cd-label">{esc(nxt['label'])}</div>
  <div class="cd-when">{esc(nxt['raw'])}</div>
  <div class="cd-units">
    <div class="u"><div class="n">{nxt['days_left']}</div><div class="s">يوم</div></div>
    <div class="u"><div class="n">0</div><div class="s">ساعة</div></div>
    <div class="u"><div class="n">0</div><div class="s">دقيقة</div></div>
    <div class="u"><div class="n">0</div><div class="s">ثانية</div></div>
  </div>
</div>""")

    if d.get("summary"):
        main.append(_block("الملخص التنفيذي", md_to_html(d["summary"]), "brief"))

    # البطاقة التعريفية
    fields = [
        ("المرحلة الحالية", d.get("stage")),
        ("حالة الحجز", f'<span class="tag {tone}">{esc(booking)}</span>'),
        ("سعر المتر", d.get("price")),
        ("المساحات المتاحة", d.get("areas")),
        ("المدن المطروحة", d.get("cities_text")),
        ("قيمة الجدية", d.get("deposit")),
        ("طريقة السداد", d.get("payment")),
        ("شروط التقديم", d.get("conditions")),
        ("آخر تطور", d.get("last")),
    ]
    rows = ['<table><tbody>']
    for label, value in fields:
        shown = value if value else '<span style="color:var(--faint)">لم يُعلن رسميًا بعد</span>'
        if label != "حالة الحجز" and value:
            shown = esc(value)
        rows.append(f'<tr><td class="k">{esc(label)}</td><td>{shown}</td></tr>')
    rows.append('</tbody></table>')
    rows.append('<p style="font-size:13px;color:var(--muted);margin-top:12px">'
                'البيانات مستخرجة آليًا من الأخبار والمصادر الرسمية المرصودة. '
                '<b>أي رقم أو موعد لازم يتأكد من كراسة الشروط الرسمية قبل أي إجراء.</b></p>')
    main.append(_block("البطاقة التعريفية للمرحلة", "\n".join(rows), "facts"))

    # المواعيد
    dates = d.get("dates") or []
    if dates:
        tone_map = {"قادم": "green", "النهاردة": "amber", "فات": "gray",
                    "غير محدد بدقة": "gray"}
        t = ['<table><thead><tr><th>الموعد</th><th>كما ورد</th>'
             '<th>الحالة</th><th>المتبقي</th></tr></thead><tbody>']
        for e in dates:
            left = ("—" if e.get("days_left") is None
                    else "انتهى" if e["days_left"] < 0
                    else f'{e["days_left"]} يوم')
            t.append(f'<tr><td class="k">{esc(e["label"])}</td>'
                     f'<td>{esc(e["raw"])}</td>'
                     f'<td><span class="tag {tone_map.get(e["status"], "gray")}">'
                     f'{esc(e["status"])}</span></td><td>{esc(left)}</td></tr>')
        t.append('</tbody></table>')
        body = "\n".join(t)
    else:
        body = ('<p style="color:var(--muted)">لا توجد مواعيد معلنة مؤكدة حتى الآن. '
                'بمجرد صدور أي إعلان رسمي سيظهر هنا تلقائيًا مع عدّاد تنازلي.</p>')
    main.append(_block("المواعيد الرسمية", body, "dates"))

    # رادار الإشارات المبكرة — القسم الكامل
    if intel:
        main.append(_block("رادار الإشارات المبكرة — ما يقوله الناس قبل الأخبار",
                           _radar_body(intel, limit=30), "radar"))

    # المدن
    cities = d.get("cities") or {}
    # التوافق مع الشكلين: dict (المفروض) و list (لو حد بعتها مخطئة)
    if isinstance(cities, list):
        cities = {c: 1 for c in cities}
    if cities:
        top = list(cities.items())[:14]
        mx = max(v for _, v in top) or 1
        bars = ['<table><tbody>']
        for city, cnt in top:
            pct = int(cnt / mx * 100)
            bars.append(
                f'<tr><td class="k">{esc(city)}</td>'
                f'<td><div style="background:#eaf1f7;border-radius:3px;height:19px;'
                f'position:relative;min-width:60px">'
                f'<div style="background:var(--navy-2);height:100%;width:{pct}%;'
                f'border-radius:3px"></div></div></td>'
                f'<td style="width:70px;text-align:center">{cnt} ذكر</td></tr>')
        bars.append('</tbody></table>')
        bars.append('<p style="font-size:13px;color:var(--muted)">'
                    'ترتيب حسب تكرار ذكر المدينة في الأخبار المرصودة — '
                    'مؤشر اهتمام إعلامي، <b>ليس تأكيدًا على الطرح</b>.</p>')
        main.append(_block("المدن الأكثر ذكرًا", "\n".join(bars), "places"))

    # الخط الزمني
    tl = d.get("timeline") or []
    if tl:
        from beit_alwatan import FIELD_LABELS
        items = ['<div class="timeline">']
        for i, ev in enumerate(tl[:30]):
            label = FIELD_LABELS.get(ev["field"], ev["field"].replace("_", " "))
            when = (ev.get("when") or "")[:10]
            if ev.get("from"):
                what = (f'<b>{esc(label)}</b>: <s>{esc(str(ev["from"])[:80])}</s> '
                        f'← {esc(str(ev["to"])[:140])}')
            else:
                what = f'<b>{esc(label)}</b>: {esc(str(ev["to"])[:160])}'
            src = ""
            if ev.get("source_link"):
                src = (f' <a href="{esc(ev["source_link"])}" target="_blank" '
                       f'rel="noopener" style="font-size:12px">[المصدر]</a>')
            cls = "tl-item new" if i == 0 else "tl-item"
            items.append(f'<div class="{cls}"><div class="tl-when">{esc(when)}</div>'
                         f'<div class="tl-what">{what}{src}</div></div>')
        items.append('</div>')
        main.append(_block("الخط الزمني للتغييرات المرصودة", "\n".join(items), "timeline"))

    if d.get("people"):
        main.append(_block("كلام الناس — قراءة تعليقات الجمهور",
                           md_to_html(d["people"]) +
                           '<p style="font-size:13px;color:var(--muted);margin-top:14px">'
                           '⚠️ هذا القسم مبني على تعليقات أفراد على الإنترنت. '
                           '<b>ليس مصدرًا رسميًا</b> ولا يُبنى عليه قرار.</p>',
                           "people"))

    if d.get("forecast"):
        main.append(_block("القراءة الاستشرافية", md_to_html(d["forecast"]), "outlook"))

    if d.get("checklist"):
        main.append(_block("خطوات عملية", md_to_html(d["checklist"]), "steps"))

    # المصادر — مطوية افتراضيًا، مرجع مش قراءة أساسية
    srcs = d.get("sources") or []
    if srcs:
        lst = ['<table><thead><tr><th>العنوان</th><th>الجهة</th>'
               '<th>التاريخ</th></tr></thead><tbody>']
        for s in srcs:
            lst.append(
                f'<tr><td><a href="{esc(s["link"])}" target="_blank" rel="noopener">'
                f'{esc(s["title"])}</a></td><td>{esc(s.get("source", ""))}</td>'
                f'<td>{esc(ago(s.get("published", "")))}</td></tr>')
        lst.append('</tbody></table>')
        main.append(_block_collapsed("المصادر المعتمدة في هذا الملف",
                                     "\n".join(lst), "sources",
                                     hint=f"{len(srcs)} مصدر"))

    main.append(f"""<div class="disclaimer">
  <b>تنويه منهجي.</b> كل البيانات في هذه الصفحة مستخرجة آليًا بالذكاء الاصطناعي
  من أخبار ومصادر عامة، و<b>قابلة للخطأ</b>. المواعيد والأسعار والشروط
  <b>لا يُعتمد عليها</b> إلا بعد التأكد من كراسة الشروط الرسمية ومنصة مصر العقارية.
  هذا المحتوى للاطلاع فقط وليس استشارة مالية أو قانونية.
  <div class="engines">{esc(engines_note or "")}</div>
</div>""")

    # العمود الجانبي — بس اللي فيه فعل ممكن تاخده، بلا تكرار للتنقل فوق
    rail = []

    if nxt:
        rail.append(f"""<div class="box"><h4>أقرب موعد</h4>
  <div style="font-size:15px;font-weight:600;color:var(--navy)">{esc(nxt["label"])}</div>
  <div style="font-size:13.5px;color:var(--muted);margin-top:3px">{esc(nxt["raw"])}</div>
  <div style="font-size:26px;font-weight:700;color:var(--gold);margin-top:7px">
    {nxt["days_left"]} <span style="font-size:13px;color:var(--muted)">يومًا</span></div>
</div>""")

    if intel:
        st = intel.get("stats") or {}
        c = intel.get("counts") or {}
        rows = [f'<div class="r"><span>إشارات مرصودة</span>'
                f'<b>{c.get("total", 0)}</b></div>',
                f'<div class="r"><span>مش في الأخبار</span>'
                f'<b style="color:var(--gold)">{c.get("novel", 0)}</b></div>',
                f'<div class="r"><span>اتأكدت رسميًا</span>'
                f'<b style="color:var(--green)">{c.get("confirmed", 0)}</b></div>']
        if st.get("avg_lead_days") is not None:
            rows.append(f'<div class="r"><span>متوسط سبق الجمهور</span>'
                        f'<b>{st["avg_lead_days"]} يوم</b></div>')
        if st.get("max_lead_days") is not None:
            rows.append(f'<div class="r"><span>أطول سبق</span>'
                        f'<b>{st["max_lead_days"]} يوم</b></div>')
        rail.append('<div class="box"><h4>الرادار</h4>' + "".join(rows) +
                    '</div>')

    rail.append(f"""<div class="box"><h4>روابط الإجراء</h4>
  <a class="lnk" href="{esc(config.BEIT_ALWATAN["booking_url"])}" target="_blank" rel="noopener">منصة مصر العقارية — الحجز</a>
  <a class="lnk" href="{esc(config.BEIT_ALWATAN["authority_url"])}" target="_blank" rel="noopener">هيئة المجتمعات العمرانية</a>
  <a class="lnk" href="{esc(config.BEIT_ALWATAN["official_url"])}" target="_blank" rel="noopener">بيتك في مصر</a>
</div>""")

    return _page("بيت الوطن — ملف متابعة | مرصد العقارات المصرية",
                 "متابعة لحظية لمشروع بيت الوطن: المرحلة، المواعيد، الأسعار، الشروط، وتحليل",
                 masthead, topbar, "\n".join(main), "\n".join(rail))


# ============================================================
#  تليجرام — رسالة موحّدة احترافية
# ============================================================
#
# فلسفة التصميم:
#   • رسالة واحدة منظّمة بأقسام واضحة، بدل ٤-٥ رسائل مبعثرة
#   • ترتيب هرمي: الأهم أولًا (بيت الوطن → تغييرات → عاجل → إشارات → أخبار
#     → استشراف → إحصائيات)
#   • فواصل بصرية متسقة بين الأقسام (━━━)
#   • أيقونات موحّدة لكل نوع (📍 مرحلة · 💰 سعر · ⏰ موعد · 📝 تطور)
#   • كل قسم اختياري: لو مفيهوش محتوى، مايظهرش أصلًا
#   • split ذكي عند حدود الأقسام لو الرسالة طويلة (Telegram limit 4096)
#
# الرسالة الوحيدة اللي بتفضل منفصلة: تنبيه رصد لحظي للمصادر الرسمية
# (`watcher.format_alert`) — لأنها لحظية وبتيجي بره الدورة الكاملة.

_SEP = "━" * 22
_SUB = "─" * 18


def _clean_brief(text, limit=600):
    """يشيل ماركداون بسيط ويقصّ لطول معقول."""
    if not text:
        return ""
    text = re.sub(r"^#+\s*", "", str(text).strip(), flags=re.M)
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    if len(text) <= limit:
        return text.strip()
    cut = text.rfind("\n", 0, limit)
    if cut < limit // 2:
        cut = text.rfind(". ", 0, limit)
    if cut < limit // 2:
        cut = limit
    return text[:cut].strip() + "…"


def _beit_block(beit):
    """لوحة حالة بيت الوطن — الأولوية القصوى."""
    if not beit:
        return None
    fields = [
        ("📍", "المرحلة",    beit.get("stage")),
        ("🎫", "الحجز",      beit.get("booking")),
        ("💰", "سعر المتر",  beit.get("price")),
        ("💵", "مقدم الجدية", beit.get("deposit")),
        ("📐", "المساحات",   beit.get("areas")),
        ("💳", "نظام السداد", beit.get("payment")),
    ]
    rows = [(ic, lbl, val) for ic, lbl, val in fields if val and val != "—"]
    if not (rows or beit.get("next") or beit.get("last") or beit.get("summary")):
        return None

    lines = ["🏘️ <b>بيت الوطن — لوحة الحالة</b>", _SUB]
    for ic, lbl, val in rows:
        lines.append(f"{ic} <b>{lbl}:</b> {esc(str(val)[:120])}")

    # نفضل cities_top (list) للتليجرام، ولو مش موجودة نستخدم cities
    cities = beit.get("cities_top") or beit.get("cities")
    if cities:
        if isinstance(cities, dict):
            cities = sorted(cities, key=lambda k: -cities[k])
        if isinstance(cities, str):
            cs = cities
        else:
            cs = "، ".join(list(cities)[:4])
        lines.append(f"🏙️ <b>المدن:</b> {esc(cs[:200])}")

    nxt = beit.get("next")
    if nxt:
        left = nxt.get("days_left")
        left_txt = ""
        if isinstance(left, int):
            if left < 0:
                left_txt = " · <i>مرّ الموعد</i>"
            elif left == 0:
                left_txt = " · <b>النهاردة!</b>"
            elif left <= 3:
                left_txt = f" · <b>باقي {left} يوم فقط ⚠️</b>"
            else:
                left_txt = f" · باقي {left} يوم"
        lines += ["", f"⏰ <b>{esc(nxt.get('label', 'الموعد القادم'))}</b>",
                  f"   {esc(str(nxt.get('raw', ''))[:140])}{left_txt}"]

    last = beit.get("last")
    if last:
        lines += ["", "📝 <b>آخر تطور</b>", f"   {esc(str(last)[:220])}"]

    summary = _clean_brief(beit.get("summary"), 320)
    if summary:
        lines += ["", "💡 <b>قراءة سريعة</b>", esc(summary)]

    checklist = beit.get("checklist")
    if checklist:
        items = checklist if isinstance(checklist, list) else [checklist]
        items = [str(x).strip() for x in items if str(x).strip()][:4]
        if items:
            lines += ["", "🎯 <b>خطواتك المقترحة</b>"]
            for i, step in enumerate(items, 1):
                lines.append(f"  {i}. {esc(step[:180])}")

    conf = beit.get("confidence")
    if conf:
        lines += ["", f"<i>درجة الثقة في البيانات: {esc(str(conf))}</i>"]

    return "\n".join(lines)


def _market_changes_block(changes):
    """تغييرات في السوق (بيت الوطن / بيتك في مصر / منصة عقارية...)."""
    if not changes:
        return None
    lines = [f"📌 <b>تغييرات حصلت في السوق ({len(changes)})</b>", _SUB]
    by_topic = {}
    for ch in changes:
        by_topic.setdefault(ch.get("topic", "—"), []).append(ch)
    for topic, items in by_topic.items():
        lines.append(f"<b>▸ {esc(topic)}</b>")
        for ch in items[:6]:
            field = str(ch.get("field", "")).replace("_", " ")
            to = esc(str(ch.get("to", ""))[:140])
            if ch.get("from"):
                frm = esc(str(ch["from"])[:80])
                lines.append(f"  • {esc(field)}: <b>{to}</b>  <s>{frm}</s>")
            else:
                lines.append(f"  • {esc(field)}: <b>{to}</b>")
    return "\n".join(lines)


def _beit_changes_block(changes):
    """تغييرات محددة في ملف بيت الوطن."""
    if not changes:
        return None
    lines = [f"🏘️ <b>تحديثات على ملف بيت الوطن ({len(changes)})</b>", _SUB]
    for ch in changes[:6]:
        field = str(ch.get("field", "")).replace("_", " ")
        to = esc(str(ch.get("to", ""))[:140])
        if ch.get("from"):
            frm = esc(str(ch["from"])[:80])
            lines.append(f"• <b>{esc(field)}</b>: {to}  <s>{frm}</s>")
        else:
            lines.append(f"• <b>{esc(field)}</b>: {to}")
    return "\n".join(lines)


def _urgent_block(items, urgent_links):
    urgent = [it for it in items if it.get("link") in urgent_links][:6]
    if not urgent:
        return None
    lines = [f"🚨 <b>تنبيهات عاجلة ({len(urgent)})</b>", _SUB]
    for it in urgent:
        title = esc(str(it.get("title", ""))[:180])
        link = esc(it.get("link", ""))
        src = esc(it.get("source", ""))
        lines.append(f'🔴 <a href="{link}">{title}</a>')
        if src:
            lines.append(f'   <i>{src}</i>')
    return "\n".join(lines)


def _intel_block(intel_view, max_signals=4):
    """أهم إشارات مبكرة من كلام الناس."""
    if not intel_view:
        return None
    signals = intel_view.get("signals") or []
    if not signals:
        return None
    # ترتيب: الجديد غير المنشور رسميًا الأول
    picked = sorted(signals, key=lambda s: (
        0 if s.get("novel") else 1,
        -int(s.get("weight", 0) or 0),
    ))[:max_signals]
    if not picked:
        return None

    counts = intel_view.get("counts") or {}
    header = f"🔍 <b>إشارات مبكرة ({counts.get('total', len(signals))})</b>"
    if counts.get("novel"):
        header += f" · <i>{counts['novel']} مش في الأخبار</i>"
    lines = [header, _SUB]

    for sig in picked:
        icon = "✅" if sig.get("status") == "مؤكدة رسميًا" else (
            "🆕" if sig.get("novel") else "🟢")
        stmt = esc(str(sig.get("statement", ""))[:220])
        lines.append(f"{icon} <b>{stmt}</b>")

        meta = []
        m = sig.get("mentions")
        i = sig.get("independence")
        if m:
            meta.append(f"{m} شخص من {i or 1} مصدر")
        if sig.get("firsthand"):
            meta.append(f"👁 {sig['firsthand']} تجربة شخصية")
        if sig.get("lead_days"):
            meta.append(f"⏱ سبقت الأخبار بـ {sig['lead_days']} يوم")
        if meta:
            lines.append(f"   <i>{esc(' · '.join(meta))}</i>")

        sources = sig.get("sources") or []
        if sources:
            src = sources[0]
            quote = esc(str(src.get("quote", ""))[:160])
            if quote:
                lines.append(f"   💬 «{quote}»")
    return "\n".join(lines)


def _news_block(new_by_section, urgent_links, per_section=4, total_cap=14):
    """أخبار جديدة مصنّفة — من غير تكرار للعاجل اللي فوق."""
    if not new_by_section:
        return None
    blocks = []
    total = 0
    for section, items in new_by_section.items():
        # نستبعد اللي طلع بالفعل في قسم "عاجل"
        remaining = [it for it in items if it.get("link") not in urgent_links]
        if not remaining:
            continue
        picked = remaining[:per_section]
        if total + len(picked) > total_cap:
            picked = picked[:total_cap - total]
        if not picked:
            break
        blocks.append(f"<b>▸ {esc(section)}</b>")
        for it in picked:
            title = esc(str(it.get("title", ""))[:150])
            link = esc(it.get("link", ""))
            blocks.append(f'• <a href="{link}">{title}</a>')
            bits = []
            if it.get("source"):
                bits.append(it["source"])
            st = it.get("stats") or {}
            if st.get("views"):
                bits.append(f'👁 {num(st["views"])}')
            if bits:
                blocks.append(f'  <i>{esc(" · ".join(bits))}</i>')
        blocks.append("")
        total += len(picked)
        if total >= total_cap:
            break
    if not blocks:
        return None
    return "📰 <b>أخبار جديدة</b>\n" + _SUB + "\n" + "\n".join(blocks).rstrip()


def _forecast_block(forecast):
    text = _clean_brief(forecast, 500)
    if not text:
        return None
    return "🔮 <b>قراءة استشرافية</b>\n" + _SUB + "\n" + esc(text)


def _brief_block(brief):
    if not brief:
        return None
    # ناخد أول قسم بس من الملخص التنفيذي
    parts = [p.strip() for p in str(brief).split("##") if p.strip()]
    summary = parts[0] if parts else str(brief)
    text = _clean_brief(summary, 450)
    if not text:
        return None
    return "⚡ <b>الأهم دلوقتي</b>\n" + _SUB + "\n" + esc(text)


def _stats_footer(counts, engines, links=None):
    lines = ["📊 <b>هذه الدورة</b>", _SUB]
    bits = []
    if counts.get("new"):
        bits.append(f"🆕 {counts['new']} خبر جديد")
    if counts.get("videos"):
        bits.append(f"🎬 {counts['videos']} فيديو")
    if counts.get("official_ok"):
        bits.append(f"🏛️ {counts['official_ok']} مصدر رسمي")
    if counts.get("signals"):
        bits.append(f"🔍 {counts['signals']} إشارة")
    if bits:
        lines.append(" · ".join(bits))
    if engines:
        lines.append(f"<i>🤖 {esc(engines)}</i>")
    if links:
        lines.append("")
        for label, url in links:
            lines.append(f'{label}: <a href="{esc(url)}">{esc(url)}</a>')
    return "\n".join(lines)


def build_unified_telegram(*, new_by_section=None, brief=None, forecast=None,
                           urgent_links=None, beit=None, beit_changes=None,
                           market_changes=None, intel_view=None, counts=None,
                           engines="", site_links=None):
    """
    الرسالة الموحّدة الاحترافية — ترتيب هرمي بالأهمية.

    ترجّع list من نصوص (كل نص رسالة تليجرام واحدة). عادةً عنصر واحد؛
    لو الرسالة طويلة جدًا يتم تقسيمها عند حدود الأقسام (مش في نص القسم).
    """
    all_items = []
    for items in (new_by_section or {}).values():
        all_items.extend(items)
    urgent_links = urgent_links or set()

    header = [f"🏛️ <b>مرصد العقارات المصرية</b>",
              f"<i>📅 {stamp()}</i>"]

    # الترتيب: بيت الوطن (أهم شيء) → تغييرات → عاجل → إشارات → أخبار
    # → استشراف → إحصائيات
    blocks = [
        _beit_block(beit),
        _beit_changes_block(beit_changes),
        _market_changes_block(market_changes),
        _urgent_block(all_items, urgent_links),
        _intel_block(intel_view),
        _brief_block(brief),
        _news_block(new_by_section, urgent_links),
        _forecast_block(forecast),
        _stats_footer(counts or {}, engines, site_links),
    ]
    blocks = [b for b in blocks if b]

    footer_note = ("⚠️ <i>للاسترشاد فقط — راجع كراسة الشروط والمصدر الرسمي "
                   "قبل أي التزام مالي.</i>")

    # نجمّع في رسالة واحدة، ولو تعدّت الحد نقسّم على الأقسام
    limit = 3800
    header_txt = "\n".join(header)
    parts = [header_txt]
    current = header_txt

    def push_block(b):
        nonlocal current
        candidate = current + "\n\n" + _SEP + "\n\n" + b
        if len(candidate) <= limit:
            current = candidate
            parts[-1] = current
            return
        # القسم مش هيدخل — ابدأ رسالة جديدة (بدون هيدر ضخم، بس تنويه بسيط)
        cont_header = f"🏛️ <b>مرصد العقارات — تكملة {len(parts) + 1}</b>"
        if len(cont_header) + len(b) + 6 > limit:
            # القسم لوحده أطول من الحد — نقصّه بأمان
            b = b[:limit - len(cont_header) - 10] + "…"
        current = cont_header + "\n\n" + b
        parts.append(current)

    for b in blocks:
        push_block(b)

    # التنويه القانوني على آخر رسالة
    if len(parts[-1]) + len(footer_note) + 4 <= limit:
        parts[-1] += "\n\n" + footer_note
    else:
        parts.append(footer_note)

    return parts


# للتوافق مع الكود القديم — بيرجّع نفس الشكل بس بالتنسيق الجديد
def build_telegram(new_by_section, brief, urgent_links, beit=None):
    msgs = build_unified_telegram(
        new_by_section=new_by_section, brief=brief,
        urgent_links=urgent_links, beit=beit)
    return "\n\n".join(msgs) if msgs else ""
