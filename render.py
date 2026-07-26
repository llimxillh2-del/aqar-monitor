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
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+Arabic:wght@300;400;500;600;700&display=swap');

:root{
  --ink:#15181c; --body:#2f3640; --muted:#69727e; --faint:#98a1ad;
  --line:#e0e4ea; --line-soft:#eef1f5; --bg:#f2f4f7; --paper:#ffffff;
  --navy:#0f3557; --navy-2:#1b4f7d; --gold:#96702c; --gold-soft:#f6f1e6;
  --red:#a52820; --red-soft:#fbeeed; --green:#17603f; --green-soft:#ecf5f0;
  --amber:#8a5a00; --amber-soft:#fdf4e3;
  --radius:4px;
}
*{box-sizing:border-box;}
html{scroll-behavior:smooth;}
body{
  margin:0; background:var(--bg); color:var(--body);
  font-family:'IBM Plex Sans Arabic','Segoe UI',Tahoma,Arial,sans-serif;
  font-size:15.5px; line-height:1.85; -webkit-font-smoothing:antialiased;
}
a{color:var(--navy-2); text-decoration:none;}
a:hover{text-decoration:underline;}

/* ---------- الترويسة ---------- */
.masthead{background:var(--navy); color:#fff; border-bottom:4px solid var(--gold);}
.masthead-in{max-width:1180px; margin:0 auto; padding:26px 24px 22px;}
.eyebrow{font-size:11.5px; letter-spacing:2.6px; text-transform:uppercase;
  color:#9fc0dd; margin-bottom:9px; font-weight:500;}
.masthead h1{margin:0; font-size:27px; font-weight:700; letter-spacing:-.3px;}
.masthead .lede{margin:7px 0 0; font-size:14px; color:#c6dbeb; font-weight:300;}
.issue{margin-top:16px; padding-top:13px; border-top:1px solid rgba(255,255,255,.16);
  display:flex; gap:22px; flex-wrap:wrap; font-size:12.5px; color:#b9d3e6;}
.issue b{color:#fff; font-weight:600;}

/* ---------- شريط التنقل ---------- */
.topbar{position:sticky; top:0; z-index:60; background:var(--paper);
  border-bottom:1px solid var(--line); box-shadow:0 1px 4px rgba(15,53,87,.07);}
.topbar-in{max-width:1180px; margin:0 auto; padding:0 24px;
  display:flex; align-items:center; gap:4px; flex-wrap:wrap;}
.topbar a{display:inline-block; padding:12px 13px; font-size:13.5px;
  font-weight:500; color:var(--muted); border-bottom:2px solid transparent;}
.topbar a:hover{color:var(--navy); border-bottom-color:var(--line); text-decoration:none;}
.topbar a.cta{margin-inline-start:auto; color:var(--gold); font-weight:600;}

/* ---------- التخطيط ---------- */
.wrap{max-width:1180px; margin:0 auto; padding:26px 24px 60px;
  display:grid; grid-template-columns:1fr 268px; gap:26px; align-items:start;}
@media(max-width:940px){ .wrap{grid-template-columns:1fr; padding:18px 15px 44px;} .rail{order:-1;} }

/* ---------- المؤشرات ---------- */
.kpis{display:grid; grid-template-columns:repeat(auto-fit,minmax(132px,1fr));
  gap:1px; background:var(--line); border:1px solid var(--line);
  border-radius:var(--radius); overflow:hidden; margin-bottom:22px;}
.kpi{background:var(--paper); padding:14px 16px;}
.kpi .k-label{font-size:11.5px; color:var(--muted); letter-spacing:.4px;}
.kpi .k-value{font-size:25px; font-weight:700; color:var(--navy); line-height:1.35;
  font-variant-numeric:tabular-nums;}
.kpi.alert .k-value{color:var(--red);}
.kpi.good .k-value{color:var(--green);}

/* ---------- الأقسام ---------- */
.doc{counter-reset:sec;}
section.block{background:var(--paper); border:1px solid var(--line);
  border-radius:var(--radius); margin-bottom:22px; overflow:hidden;}
section.block > h2{counter-increment:sec; margin:0; padding:15px 22px;
  font-size:16.5px; font-weight:600; color:var(--navy);
  background:linear-gradient(180deg,#fbfcfd,#f5f7fa);
  border-bottom:1px solid var(--line); display:flex; align-items:baseline; gap:11px;}
section.block > h2::before{content:counter(sec); font-size:12px; font-weight:700;
  color:#fff; background:var(--navy); min-width:23px; height:23px; border-radius:3px;
  display:inline-flex; align-items:center; justify-content:center; flex:none;
  align-self:center; font-variant-numeric:tabular-nums;}
.block-body{padding:19px 22px 22px;}
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
.filters{display:flex; gap:7px; flex-wrap:wrap; padding:13px 22px;
  border-bottom:1px solid var(--line); background:#fafbfc;}
.filters button{font-family:inherit; font-size:13px; font-weight:500;
  padding:6px 14px; border:1px solid var(--line); background:var(--paper);
  color:var(--muted); border-radius:100px; cursor:pointer; transition:.12s;}
.filters button:hover{border-color:var(--navy); color:var(--navy);}
.filters button.on{background:var(--navy); border-color:var(--navy); color:#fff;}

.entry{padding:16px 22px; border-bottom:1px solid var(--line-soft);}
.entry:last-child{border-bottom:none;}
.entry-meta{display:flex; gap:8px; align-items:center; flex-wrap:wrap;
  font-size:12px; color:var(--faint); margin-bottom:5px;}
.entry-meta .src{font-weight:600; color:var(--muted);}
.entry h3.t{border:none; padding:0; margin:0 0 5px; font-size:15.5px;
  font-weight:600; line-height:1.6;}
.entry h3.t a{color:var(--ink);}
.entry h3.t a:hover{color:var(--navy-2);}
.snip{font-size:13.5px; color:var(--muted); margin:5px 0 0;}
.metrics{display:flex; gap:15px; font-size:12px; color:var(--faint);
  margin-top:8px; font-variant-numeric:tabular-nums;}

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

/* ---------- بانر بيت الوطن ---------- */
.spotlight{background:linear-gradient(135deg,var(--navy) 0%,#154572 100%);
  color:#fff; border-radius:var(--radius); padding:22px 24px; margin-bottom:22px;
  border-inline-start:4px solid var(--gold);}
.spotlight .sp-eyebrow{font-size:11px; letter-spacing:2.2px; color:#9fc0dd;
  text-transform:uppercase; font-weight:600;}
.spotlight h2{margin:6px 0 12px; font-size:21px; font-weight:700; color:#fff;}
.spotlight .sp-grid{display:grid; grid-template-columns:repeat(auto-fit,minmax(128px,1fr));
  gap:14px; margin:15px 0;}
.spotlight .sp-cell .l{font-size:11.5px; color:#9fc0dd;}
.spotlight .sp-cell .v{font-size:15px; font-weight:600; color:#fff; line-height:1.55;}
.spotlight .sp-cta{display:inline-block; margin-top:6px; background:var(--gold);
  color:#fff; padding:8px 19px; border-radius:3px; font-size:14px; font-weight:600;}
.spotlight .sp-cta:hover{background:#ab8034; text-decoration:none;}

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
  var scope = bar.closest('section');
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

    parts = [
        f'    <article class="entry" data-sec="{slug(section)}">',
        '      <div class="entry-meta">',
        f'        <span class="src">{esc(item.get("source") or "مصدر")}</span>',
        f'        <span>·</span><span>{esc(section)}</span>',
    ]
    when = ago(item.get("published", ""))
    if when:
        parts.append(f'        <span>·</span><span>{esc(when)}</span>')
    if tags:
        parts.append("        " + "".join(tags))
    parts.append('      </div>')
    parts.append(
        f'      <h3 class="t"><a href="{esc(item["link"])}" target="_blank" '
        f'rel="noopener">{esc(item["title"])}</a></h3>')

    if item.get("snippet"):
        parts.append(f'      <p class="snip">{esc(item["snippet"][:230])}</p>')

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
    if novel:
        body.append("<h3>معلومات من الناس مش موجودة في الأخبار</h3>")
        body.append('<p style="font-size:13px;color:var(--muted);margin-top:0">'
                    'دي أهم حاجة في الرادار — كلام بيتقال ومحدش نشره رسميًا. '
                    '<b>كل واحدة محتاجة تأكيد قبل ما تتصرف عليها.</b></p>')
        for sig in novel[:limit]:
            body.append(_signal_card(sig))

    confirmed = intel.get("confirmed") or []
    if confirmed:
        body.append("<h3>إشارات اتأكدت رسميًا</h3>")
        body.append('<p style="font-size:13px;color:var(--muted);margin-top:0">'
                    'الحاجات دي قالها الناس الأول وبعدين نزلت رسميًا — '
                    'المقياس ده بيقولك تثق في الرادار قد إيه.</p>')
        for sig in confirmed[:10]:
            body.append(_signal_card(sig))

    others = [s for s in (intel.get("signals") or [])
              if s not in novel and s not in confirmed]
    if others:
        body.append("<h3>باقي الإشارات</h3>")
        for sig in others[:limit]:
            body.append(_signal_card(sig))

    questions = intel.get("questions") or []
    if questions and not compact:
        body.append("<h3>أسئلة الناس اللي مالهاش إجابة</h3>")
        body.append('<p style="font-size:13px;color:var(--muted);margin-top:0">'
                    'دي بتوضّح فين الغموض الرسمي — الحاجات اللي الناس محتاجة '
                    'تعرفها والجهات ماوضّحتهاش.</p>')
        body.append('<ul class="qlist">')
        for q in questions[:14]:
            src = PLATFORM_LABEL.get(q.get("platform"), q.get("platform", ""))
            link = (f' · <a href="{esc(q["url"])}" target="_blank" '
                    f'rel="noopener">المصدر</a>' if q.get("url") else "")
            body.append(f'<li>{esc(q.get("text", ""))}'
                        f'<div class="meta">{esc(src)}{link}</div></li>')
        body.append('</ul>')

    if not (novel or confirmed or others or questions):
        body.append('<div class="empty">لسه مفيش إشارات مرصودة. '
                    'الرادار محتاج دورة أو اتنين عشان يجمع كلام كفاية.</div>')

    return "\n".join(body)


# ============================================================
#  الصفحة الرئيسية
# ============================================================

def build_index(sections, brief, new_links, top_links, urgent_links,
                engines_note, forecast=None, market_rows=None,
                health_rows=None, beit=None, official_changes=None,
                intel=None):
    total = sum(len(v) for v in sections.values())
    official_ok = sum(1 for r in (health_rows or []) if r["status"] == "يعمل")
    novel_count = ((intel or {}).get("counts") or {}).get("novel", 0)

    masthead = f"""<header class="masthead"><div class="masthead-in">
  <div class="eyebrow">تقرير دوري · رصد وتحليل</div>
  <h1>مرصد العقارات المصرية للمصريين بالخارج</h1>
  <p class="lede">رصد آلي للمصادر الرسمية والإعلامية · تحليل واستشراف مدعوم بالذكاء الاصطناعي</p>
  <div class="issue">
    <span>صدر في: <b>{esc(stamp())}</b></span>
    <span>العناصر المرصودة: <b>{total}</b></span>
    <span>مصادر رسمية عاملة: <b>{official_ok}/{len(health_rows or [])}</b></span>
  </div>
</div></header>"""

    radar_link = ('\n  <a href="#radar">رادار الإشارات</a>' if intel else "")
    topbar = f"""<nav class="topbar"><div class="topbar-in">
  <a href="#summary">الملخص التنفيذي</a>
  <a href="#status">حالة الملفات</a>{radar_link}
  <a href="#outlook">الاستشراف</a>
  <a href="#official">الرصد الرسمي</a>
  <a href="#feed">الرصد الإخباري</a>
  <a href="beit-alwatan.html" class="cta">ملف بيت الوطن ←</a>
</div></nav>"""

    kpi_cells = [
        ("إجمالي العناصر", total, ""),
        ("جديد هذه الدورة", len(new_links), "good" if new_links else ""),
        ("عاجل", len(urgent_links), "alert" if urgent_links else ""),
        ("تغييرات رسمية", len(official_changes or []),
         "alert" if official_changes else ""),
    ]
    if intel:
        kpi_cells.append(("إشارات مش في الأخبار", novel_count,
                          "alert" if novel_count else ""))
    main = [_kpis(kpi_cells)]

    # بانر بيت الوطن
    if beit:
        cells = []
        for label, key in (("المرحلة", "stage"), ("حالة الحجز", "booking"),
                           ("سعر المتر", "price"), ("المساحات", "areas")):
            v = beit.get(key) or "لم يُعلن بعد"
            cells.append(f'<div class="sp-cell"><div class="l">{esc(label)}</div>'
                         f'<div class="v">{esc(str(v)[:60])}</div></div>')
        nxt = beit.get("next")
        nxt_line = ""
        if nxt:
            nxt_line = (f'<p style="margin:4px 0 0;color:#f0d9a8;font-size:14px">'
                        f'أقرب موعد: <b style="color:#fff">{esc(nxt["label"])}</b> — '
                        f'{esc(nxt["raw"])} (خلال {nxt["days_left"]} يومًا)</p>')
        main.append(f"""<div class="spotlight">
  <div class="sp-eyebrow">الملف المتابَع باستمرار</div>
  <h2>بيت الوطن — أراضي المصريين بالخارج</h2>
  <div class="sp-grid">{''.join(cells)}</div>
  {nxt_line}
  <a class="sp-cta" href="beit-alwatan.html">افتح الملف الكامل ←</a>
</div>""")

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

    # الرصد الرسمي
    official_body = []
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
    main.append(_block("الرصد الرسمي", "\n".join(official_body), "official"))

    # الفيد
    buttons = ['<button class="on" data-filter="all">الكل</button>']
    for name, items in sections.items():
        if items:
            buttons.append(f'<button data-filter="{slug(name)}">{esc(name)}</button>')

    entries = []
    for name, items in sections.items():
        for item in items[:config.MAX_ITEMS_PER_SECTION_ON_PAGE]:
            entries.append(_entry(item, name, new_links, top_links, urgent_links))

    feed_html = "\n".join(entries) or '<div class="empty">لا توجد عناصر مرصودة.</div>'
    main.append(f"""<section class="block" id="feed">
  <h2>الرصد الإخباري</h2>
  <div class="filters" data-filters>{''.join(buttons)}</div>
{feed_html}
</section>""")

    main.append(f"""<div class="disclaimer">
  <b>تنويه منهجي.</b> تُجمَع المصادر آليًا وتُلخَّص بالذكاء الاصطناعي.
  الملخصات والتحليلات <b>قابلة للخطأ</b> — يُرجع إلى المصدر الأصلي دائمًا.
  المحتوى للاطلاع فقط وليس استشارة مالية أو قانونية. راجع كراسة الشروط الرسمية
  ومنصة مصر العقارية قبل أي التزام مالي.
  <div class="engines">{esc(engines_note or "")}</div>
</div>""")

    # العمود الجانبي
    rail = ['<div class="box"><h4>محتويات التقرير</h4><div class="toc">',
            '<a href="#summary">الملخص التنفيذي</a>',
            '<a href="#status">حالة الملفات</a>']
    if intel:
        rail.append('<a href="#radar">رادار الإشارات المبكرة</a>')
    rail += ['<a href="#outlook">الاستشراف وقراءة السوق</a>',
             '<a href="#official">الرصد الرسمي</a>',
             '<a href="#feed">الرصد الإخباري</a>',
             '<a href="beit-alwatan.html"><b>ملف بيت الوطن</b></a>',
             '</div></div>']

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

    rail.append('<div class="box"><h4>توزيع العناصر</h4>')
    for name, items in sections.items():
        if items:
            rail.append(f'<div class="r"><span>{esc(name)}</span><b>{len(items)}</b></div>')
    rail.append('</div>')

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

def build_beit_page(d, engines_note, intel=None):
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

    # المصادر
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
        main.append(_block("المصادر المعتمدة في هذا الملف", "\n".join(lst), "sources"))

    main.append(f"""<div class="disclaimer">
  <b>تنويه منهجي.</b> كل البيانات في هذه الصفحة مستخرجة آليًا بالذكاء الاصطناعي
  من أخبار ومصادر عامة، و<b>قابلة للخطأ</b>. المواعيد والأسعار والشروط
  <b>لا يُعتمد عليها</b> إلا بعد التأكد من كراسة الشروط الرسمية ومنصة مصر العقارية.
  هذا المحتوى للاطلاع فقط وليس استشارة مالية أو قانونية.
  <div class="engines">{esc(engines_note or "")}</div>
</div>""")

    rail = ['<div class="box"><h4>محتويات الملف</h4><div class="toc">',
            '<a href="#brief">الملخص التنفيذي</a>',
            '<a href="#facts">البطاقة التعريفية</a>',
            '<a href="#dates">المواعيد الرسمية</a>']
    if intel:
        rail.append('<a href="#radar"><b>رادار الإشارات المبكرة</b></a>')
    rail += ['<a href="#places">المدن الأكثر ذكرًا</a>',
             '<a href="#timeline">الخط الزمني</a>',
             '<a href="#people">كلام الناس</a>',
             '<a href="#outlook">القراءة الاستشرافية</a>',
             '<a href="#steps">خطوات عملية</a>',
             '<a href="#sources">المصادر</a>',
             '</div></div>']

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

    if nxt:
        rail.append(f"""<div class="box"><h4>أقرب موعد</h4>
  <div style="font-size:15px;font-weight:600;color:var(--navy)">{esc(nxt["label"])}</div>
  <div style="font-size:13.5px;color:var(--muted);margin-top:3px">{esc(nxt["raw"])}</div>
  <div style="font-size:26px;font-weight:700;color:var(--gold);margin-top:7px">
    {nxt["days_left"]} <span style="font-size:13px;color:var(--muted)">يومًا</span></div>
</div>""")

    rail.append(f"""<div class="box"><h4>روابط الإجراء</h4>
  <a class="lnk" href="{esc(config.BEIT_ALWATAN["booking_url"])}" target="_blank" rel="noopener">منصة مصر العقارية — الحجز</a>
  <a class="lnk" href="{esc(config.BEIT_ALWATAN["authority_url"])}" target="_blank" rel="noopener">هيئة المجتمعات العمرانية</a>
  <a class="lnk" href="{esc(config.BEIT_ALWATAN["official_url"])}" target="_blank" rel="noopener">بيتك في مصر</a>
</div>""")

    updated = d.get("updated")
    if updated:
        rail.append(f'<div class="box"><h4>حالة البيانات</h4>'
                    f'<div class="r"><span>آخر مزامنة</span><b>{esc(ago(updated))}</b></div>'
                    f'<div class="r"><span>درجة الثقة</span>'
                    f'<b>{esc(d.get("confidence"))}</b></div>'
                    f'<div class="r"><span>أحداث مرصودة</span>'
                    f'<b>{len(d.get("timeline") or [])}</b></div></div>')

    return _page("بيت الوطن — ملف متابعة | مرصد العقارات المصرية",
                 "متابعة لحظية لمشروع بيت الوطن: المرحلة، المواعيد، الأسعار، الشروط، وتحليل",
                 masthead, topbar, "\n".join(main), "\n".join(rail))


# ============================================================
#  تليجرام
# ============================================================

def build_telegram(new_by_section, brief, urgent_links, beit=None):
    lines = ["🏛️ <b>مرصد العقارات المصرية</b>", f"<i>{stamp()}</i>", ""]

    if beit and (beit.get("stage") or beit.get("booking")):
        lines.append("🏘️ <b>بيت الوطن</b>")
        if beit.get("stage"):
            lines.append(f"  المرحلة: <b>{esc(beit['stage'])}</b>")
        if beit.get("booking"):
            lines.append(f"  الحجز: <b>{esc(beit['booking'])}</b>")
        nxt = beit.get("next")
        if nxt:
            lines.append(f"  ⏰ {esc(nxt['label'])}: <b>{esc(nxt['raw'])}</b> "
                         f"(خلال {nxt['days_left']} يوم)")
        lines.append("")

    if brief:
        summary = next((p.strip() for p in str(brief).split("##") if p.strip()), "")
        if summary:
            plain = re.sub(r"\*\*(.+?)\*\*", r"\1", summary)[:600]
            lines += ["📋 <b>الخلاصة</b>", esc(plain), ""]

    for section, items in new_by_section.items():
        if not items:
            continue
        lines.append(f"<b>▸ {esc(section)}</b>")
        for it in items[:6]:
            mark = "🔴 " if it["link"] in urgent_links else "• "
            lines.append(f'{mark}<a href="{esc(it["link"])}">{esc(it["title"])}</a>')
            bits = []
            if it.get("source"):
                bits.append(it["source"])
            st = it.get("stats") or {}
            if st.get("views"):
                bits.append(f'👁 {num(st["views"])}')
            if bits:
                lines.append(f'  <i>{esc(" · ".join(bits))}</i>')
        lines.append("")

    return "\n".join(lines).strip()
