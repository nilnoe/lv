#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把抓取到的《声律发蒙》txt 排版成 slides 风格的 HTML。

结构约定：
  * 平水韵目行（如「一東」「二冬」）切分韵部
  * 每韵内每 8~9 行「聯」为一段（段首必是「X對Y，X對Z。」三字对）
  * 默认每页 2 段，竖排右起，便于对照

用法：
  python3 make_slides.py --limit 1        # 只出一页样张
  python3 make_slides.py                  # 出全本
"""

import argparse
import sys
import html
import os
import re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from paths import BUILD, source_txt  # noqa: E402

# 平水韵 106 韵目（繁体）
RHYME_CHARS = (
    "東冬江支微魚虞齊佳灰真文元寒刪先蕭肴豪歌麻陽庚青蒸尤侵覃鹽咸"      # 平声 30
    "董腫講紙尾語麌薺蟹賄軫吻阮旱潸銑篠巧皓哿馬養梗迥拯有寢感琰豏"      # 上声 29
    "送宋絳寘未御遇霽泰卦隊震問願翰諫霰嘯效號箇禡漾敬徑證宥沁勘艷陷"  # 去声 30
    "屋沃覺質物月曷黠屑藥陌錫職緝合葉洽"                                # 入声 17
    # 本书刻本的异体/讹字韵目：十三間(問)、二十九豔(艷)、十七恰(洽)
    "間豔恰"
)
# 卷末版心标记等噪声行
NOISE = {"聲律發蒙", "聲律啟蒙", "聲律發蒙卷終", "__DONE__"}
NUMERALS = "一二三四五六七八九十"
RHYME_RE = re.compile(rf"^([{NUMERALS}]{{1,3}})([{RHYME_CHARS}])$")
JUAN_RE = re.compile(r"^卷([一二三四五六七八九十])$")
# 段首标志：三字对，如「南對北，北對東。」「旌對斾，蓋對幢，」
# 限定长度 <= 11，避免把「煙樓對雪屋，玉宇對瓊樓。」这类 5-5 长句误判为段首
OPENER_RE = re.compile(r"^.{1,3}對.{1,3}[，,].{1,3}對.{1,3}[。，,、；]?$")
OPEN_MAX_LEN = 11


def is_opener(line):
    return len(line) <= OPEN_MAX_LEN and bool(OPENER_RE.match(line))


# --------------------------------------------------------------------------
# 解析
# --------------------------------------------------------------------------
def parse_verse(lines):
    """输入正文行，返回 [{'juan':..,'rhyme':..,'stanzas':[[line,...],...]}, ...]"""
    rhymes, cur_juan, cur_rhyme = [], "", None
    for raw in lines:
        line = raw.strip()
        if not line or line in NOISE:
            continue
        mj = JUAN_RE.match(line)
        if mj:
            cur_juan = line
            continue
        mr = RHYME_RE.match(line)
        if mr:
            cur_rhyme = {"juan": cur_juan, "name": line, "stanzas": []}
            rhymes.append(cur_rhyme)
            continue
        if cur_rhyme is None:
            continue
        stanzas = cur_rhyme["stanzas"]
        need_new = not stanzas or (is_opener(line) and len(stanzas[-1]) >= 6)
        if need_new:
            stanzas.append([line])
        else:
            stanzas[-1].append(line)
    return rhymes


def split_front_back(lines):
    """把开头的题解/序言与结尾的附录从韵文中切出来。"""
    idx = [i for i, l in enumerate(lines) if JUAN_RE.match(l.strip())]
    if not idx:
        return lines, [], lines
    start = idx[0]
    # 找第一个韵目行
    first_rhyme = None
    for i in range(start, len(lines)):
        s = lines[i].strip()
        if RHYME_RE.match(s):
            first_rhyme = i
            break
    if first_rhyme is None:
        return lines[:start], [], lines[start:]
    # 正文结束：最后一个韵目之后再无韵目行 → 用最后一个韵的段尾判定
    last_rhyme = max(i for i, l in enumerate(lines) if RHYME_RE.match(l.strip()))
    end = len(lines)
    for i in range(last_rhyme + 1, len(lines)):
        s = lines[i].strip()
        if not s:
            continue
        if JUAN_RE.match(s):
            continue
        # 韵文行特征：含「對」或以。，结尾
        if "對" in s or s.endswith(("。", "，", "、", "；")):
            continue
        end = i
        break
    # 让「卷一」等卷首标记留在正文里，否则首个韵部会丢卷名
    start = max((i for i in range(first_rhyme) if JUAN_RE.match(lines[i].strip())),
                default=first_rhyme)
    return lines[:start], lines[start:end], lines[end:]


def to_paragraphs(lines):
    """散文：空行分段，段内合并成一行。"""
    paras, buf = [], []
    for raw in lines:
        s = raw.strip()
        if not s:
            if buf:
                paras.append(" ".join(buf))
                buf = []
            continue
        if set(s) <= set("—－-·= "):          # 分隔线
            if buf:
                paras.append(" ".join(buf))
                buf = []
            paras.append("__RULE__")
            continue
        buf.append(s)
    if buf:
        paras.append(" ".join(buf))
    return paras


# --------------------------------------------------------------------------
# 渲染
# --------------------------------------------------------------------------
CSS = """
:root{
  --paper:#f6efe1; --paper2:#efe5d2; --ink:#2b2621; --ink-soft:#5d5347;
  --cinnabar:#a8331f; --gold:#b08d57; --line:rgba(90,70,45,.22);
}
*{box-sizing:border-box;margin:0;padding:0}
html,body{background:#171512;color:var(--ink);
  font-family:"Songti SC","STSong","Source Han Serif SC","Noto Serif CJK SC","SimSun",serif;}
html,body{height:100%}
body{overflow:hidden;margin:0;padding:0;
  background:radial-gradient(ellipse at 50% 42%, #241f1a 0%, #16130f 55%, #0d0b09 100%)}

.slide{
  position:absolute;top:50%;left:50%;width:1280px;height:720px;
  transform:translate(-50%,-50%) scale(var(--deck-scale,1));
  transform-origin:center center;
  opacity:0;visibility:hidden;pointer-events:none;
  transition:opacity .26s ease, transform .26s ease;
  background:
    radial-gradient(circle at 18% 12%, rgba(255,255,255,.55), transparent 55%),
    radial-gradient(circle at 82% 88%, rgba(176,141,87,.10), transparent 50%),
    radial-gradient(ellipse 120% 90% at 50% 0%, rgba(255,255,255,.35), transparent 60%),
    linear-gradient(150deg,var(--paper),var(--paper2));
  overflow:hidden;
}
.slide.active{opacity:1;visibility:visible;pointer-events:auto;z-index:2}
.slide.prev{transform:translate(-50%,-50%) scale(calc(var(--deck-scale,1)*.97))}
.slide::before{ /* 双线外框 */
  content:"";position:absolute;inset:18px;border:1px solid var(--line);
  box-shadow:inset 0 0 0 4px transparent,inset 0 0 0 5px rgba(90,70,45,.12);
  pointer-events:none;
}
.slide::after{ /* 四角装饰 */
  content:"";position:absolute;inset:18px;pointer-events:none;
  background:
    linear-gradient(var(--gold),var(--gold)) left 0 top 0/34px 1px no-repeat,
    linear-gradient(var(--gold),var(--gold)) left 0 top 0/1px 34px no-repeat,
    linear-gradient(var(--gold),var(--gold)) right 0 top 0/34px 1px no-repeat,
    linear-gradient(var(--gold),var(--gold)) right 0 top 0/1px 34px no-repeat,
    linear-gradient(var(--gold),var(--gold)) left 0 bottom 0/34px 1px no-repeat,
    linear-gradient(var(--gold),var(--gold)) left 0 bottom 0/1px 34px no-repeat,
    linear-gradient(var(--gold),var(--gold)) right 0 bottom 0/34px 1px no-repeat,
    linear-gradient(var(--gold),var(--gold)) right 0 bottom 0/1px 34px no-repeat;
  opacity:.75;
}

/* 页眉 */
.head{position:absolute;top:44px;left:60px;right:60px;display:flex;align-items:baseline;gap:18px}
.head .book{font-family:"Kaiti SC","STKaiti","KaiTi",serif;font-size:30px;letter-spacing:.22em;color:var(--ink)}
.head .juan{font-size:17px;letter-spacing:.3em;color:var(--ink-soft)}
.head .spacer{flex:1}
.head .rhyme{font-family:"Kaiti SC","STKaiti","KaiTi",serif;font-size:33px;letter-spacing:.16em;
  color:var(--cinnabar);line-height:1}
.head .rhyme::before{content:"·";color:var(--gold);opacity:.6;margin-right:.4em;font-size:.7em}
.head .part{font-size:14px;letter-spacing:.28em;color:var(--ink-soft)}
.head-rule{position:absolute;top:92px;left:60px;right:60px;height:1px;
  background:linear-gradient(90deg,transparent,var(--line) 12%,var(--line) 88%,transparent)}

/* 正文：竖排 */
.stage{position:absolute;top:120px;bottom:68px;left:56px;right:56px;
  display:flex;flex-direction:row-reverse;justify-content:space-between;gap:48px}
.stanza{display:flex;flex-direction:row-reverse;align-items:flex-start;gap:24px;height:100%}
.col{writing-mode:vertical-rl;text-orientation:upright;white-space:nowrap;
  font-size:var(--col-font,30px);line-height:1;letter-spacing:.06em;color:var(--ink);
  -webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility;
  text-shadow:0 1px 0 rgba(255,255,255,.45)}
.stag-label{writing-mode:vertical-rl;text-orientation:upright;white-space:nowrap;
  font-family:"Kaiti SC","STKaiti",serif;font-size:15px;letter-spacing:.34em;
  color:var(--cinnabar);opacity:.85;padding-top:3px}
.divider{width:1px;align-self:stretch;background:
  linear-gradient(180deg,transparent,var(--line) 8%,var(--line) 92%,transparent)}

/* 页脚 */
.foot{position:absolute;bottom:38px;left:60px;right:60px;display:flex;
  align-items:center;gap:14px;font-size:13px;letter-spacing:.12em;color:var(--ink-soft)}
.foot .seal{width:28px;height:28px;border-radius:4px;background:var(--cinnabar);
  color:#f7f1e3;font-size:12px;display:flex;align-items:center;justify-content:center;
  letter-spacing:.02em;font-family:"Kaiti SC","STKaiti",serif;line-height:1.02;
  text-align:center;padding:3px;box-shadow:0 1px 2px rgba(120,40,25,.35)}
.foot .spacer{flex:1}
.foot .pg{font-variant-numeric:tabular-nums;color:var(--ink-soft)}

/* 散文页 */
.prose .stage{display:block;overflow:hidden}
.prose .ptitle{font-family:"Kaiti SC","STKaiti",serif;font-size:34px;letter-spacing:.2em;
  color:var(--cinnabar);margin-bottom:26px}
.prose p{font-size:22px;line-height:2.05;text-indent:2em;color:var(--ink);
  margin-bottom:18px;text-align:justify;font-family:"Songti SC","STSong",serif}
.prose p.sig{text-indent:0;text-align:right;font-family:"Kaiti SC","STKaiti",serif;font-size:20px;color:var(--ink-soft)}
.prose hr{border:0;height:1px;background:var(--line);margin:26px 0}
/* ---------- 封面 ---------- */
.cover .head,.cover .head-rule{display:none}
.cover .stage{position:absolute;inset:74px 60px 52px;display:flex;flex-direction:column;
  align-items:center;overflow:hidden}
.cover .c-main{flex:1;width:100%;display:flex;flex-direction:column;align-items:center;
  justify-content:center;min-height:0}
.cover .book{font-family:"Kaiti SC","STKaiti",serif;font-size:72px;letter-spacing:.46em;
  text-indent:.46em;color:var(--ink);line-height:1.1}
.cover .c-rule{width:170px;height:1px;background:var(--gold);opacity:.75;margin:30px 0}
.cover .vol{font-family:"Kaiti SC","STKaiti",serif;font-size:38px;letter-spacing:.42em;
  text-indent:.42em;color:var(--cinnabar);line-height:1.2}
.cover .meta{margin-top:16px;font-size:14.5px;letter-spacing:.24em;color:var(--ink-soft)}
.cover .rhymes{margin-top:34px;max-width:980px;display:flex;flex-wrap:wrap;
  justify-content:center;gap:8px 18px}
.cover .rhymes span{font-family:"Kaiti SC","STKaiti",serif;font-size:18px;
  letter-spacing:.1em;color:var(--ink);opacity:.88}
.cover .credit{flex:0 0 auto;padding-top:14px;text-align:center;
  font-size:13px;letter-spacing:.2em;color:var(--ink-soft);line-height:1.9}

/* ---------- 放映介面 ---------- */
.deck-bar{position:fixed;left:0;bottom:0;height:3px;width:0;z-index:99;
  background:linear-gradient(90deg,var(--cinnabar),var(--gold));
  transition:width .28s ease}
.deck-nav{position:fixed;right:22px;bottom:18px;display:flex;gap:10px;z-index:100;
  opacity:0;transition:opacity .25s ease}
body:hover .deck-nav{opacity:.9}
.deck-nav button{width:40px;height:40px;border-radius:50%;cursor:pointer;
  border:1px solid rgba(246,239,225,.28);background:rgba(30,26,22,.55);
  color:#f0e7d8;font-size:19px;line-height:1;font-family:Georgia,serif;
  display:flex;align-items:center;justify-content:center;backdrop-filter:blur(4px)}
.deck-nav button:hover{background:rgba(168,51,31,.75);border-color:rgba(246,239,225,.5)}
.deck-nav button:disabled{opacity:.28;cursor:default}
.deck-hint{position:fixed;left:50%;bottom:22px;transform:translateX(-50%);z-index:100;
  color:#a99c8b;font-size:13px;letter-spacing:.14em;font-family:"Kaiti SC","STKaiti",serif;
  background:rgba(20,18,16,.55);padding:6px 16px;border-radius:20px;
  border:1px solid rgba(246,239,225,.14);backdrop-filter:blur(4px);
  opacity:1;transition:opacity .6s ease;pointer-events:none}
.deck-hint.fade{opacity:0}
/* ---------- 打印 / 导出 PDF ---------- */
/* 1280×720 px @96dpi = 338.667×190.5 mm，一页一张幻灯片 */
@page{size:338.667mm 190.5mm;margin:0}
@media print{
  html,body{height:auto;overflow:visible;background:#fff;
    -webkit-print-color-adjust:exact;print-color-adjust:exact}
  .slide{position:relative;top:auto;left:auto;transform:none;opacity:1;visibility:visible;
    pointer-events:auto;margin:0;box-shadow:none;
    page-break-after:always;break-after:page;
    -webkit-print-color-adjust:exact;print-color-adjust:exact}
  .slide:last-of-type{page-break-after:auto;break-after:auto}
  .deck-bar,.deck-nav,.deck-hint{display:none!important}
  .head,.head-rule,.stage,.foot{break-inside:avoid;page-break-inside:avoid}
}
"""


def esc(s):
    return html.escape(s, quote=False)


ORD = "一二三四五六七八九十"

# 竖排正文基准字号与单列可容字数（16 字 = 30px 时占 509px / 可用 532px）
COL_BASE_PX = 30.0
FIT_CHARS = 16


def ord_cn(n):
    return ORD[n - 1] if 1 <= n <= 10 else str(n)


def page_footer(page_no, total_pages, page_label=None, seal="發蒙", note="《聲律發蒙》劉節五卷本 · 校訂 豆瓣 @K.A.Lee"):
    """统一页脚。page_label 给出时优先使用（用于卷内页码、待補占位等）。"""
    shown = page_label if page_label is not None else f"{page_no} / {total_pages}"
    return f"""  <div class="foot">
    <span class="seal">{esc(seal)}</span>
    <span>{esc(note)}</span>
    <span class="spacer"></span>
    <span class="pg">{esc(shown)}</span>
  </div>"""


def verse_slide(rhyme, stanzas, first_index, page_no, total_pages, page_label=None, slide_id=None):
    """一段或两段一页，竖排右起。"""
    parts = []
    for k, st in enumerate(stanzas):
        label = f'<div class="stag-label">其{ord_cn(first_index + k)}</div>'
        cols = "".join(f'<div class="col">{esc(l)}</div>' for l in st)
        if k:
            parts.append('<div class="divider"></div>')
        parts.append(f'<div class="stanza">{label}{cols}</div>')
    body = "".join(parts)

    idx = first_index
    if len(stanzas) == 1:
        part_txt = f"其{ord_cn(idx)}"
    else:
        part_txt = f"其{ord_cn(idx)}–{ord_cn(idx + len(stanzas) - 1)}"

    sid = f' id="{esc(slide_id)}"' if slide_id else ""
    # 竖排高度上限由最长一句决定；超过基准字数时按比例缩字号，保证绝不溢出
    longest = max((len(l) for st in stanzas for l in st), default=0)
    fit = f' style="--col-font:{COL_BASE_PX * FIT_CHARS / longest:.2f}px"' if longest > FIT_CHARS else ""
    return f"""<section class="slide"{sid}{fit}>
  <div class="head">
    <span class="book">聲律發蒙</span>
    <span class="juan">{esc(rhyme['juan'])}</span>
    <span class="spacer"></span>
    <span class="rhyme">{esc(rhyme['name'])}</span>
    <span class="part">{part_txt}</span>
  </div>
  <div class="head-rule"></div>
  <div class="stage">{body}</div>
{page_footer(page_no, total_pages, page_label)}
</section>"""


def prose_slide(title, paras, page_no, total_pages, book="聲律發蒙", page_label=None):
    html_paras = []
    for p in paras:
        if p == "__RULE__":
            html_paras.append("<hr>")
        elif re.search(r"(識|書於|書于|序)$", p) and len(p) < 40:
            html_paras.append(f'<p class="sig">{esc(p)}</p>')
        else:
            html_paras.append(f"<p>{esc(p)}</p>")
    return f"""<section class="slide prose">
  <div class="head">
    <span class="book">{esc(book)}</span>
    <span class="spacer"></span>
    <span class="part">{esc(title)}</span>
  </div>
  <div class="head-rule"></div>
  <div class="stage">
    {''.join(html_paras)}
  </div>
{page_footer(page_no, total_pages, page_label)}
</section>"""


def cover_slide(juan, rhyme_names, seg_count, page_count, volume_no, subtitle=""):
    """卷首扉页：书名、卷次、韵目索引。"""
    chips = "".join(f"<span>{esc(n)}</span>" for n in rhyme_names)
    sub = f'<div class="meta">{esc(subtitle)}</div>' if subtitle else ""
    return f"""<section class="slide cover">
  <div class="stage">
    <div class="c-main">
      <div class="book">聲律發蒙</div>
      <div class="c-rule"></div>
      <div class="vol">{esc(juan)}</div>
      {sub}
      <div class="meta">韻目 {len(rhyme_names)} · 對語 {seg_count} 段 · 正文 {page_count} 頁</div>
      <div class="rhymes">{chips}</div>
    </div>
    <div class="credit">元祝明撰　潘瑛續　明劉節校補<br>
      《聲律發蒙》劉節五卷本　校訂　豆瓣 @K.A.Lee</div>
  </div>
{page_footer(volume_no, 0, page_label="")}
</section>"""


def prose_groups(lines, default_title="題解"):
    """把前置/附錄散行按小标题切成 [(title, [para, ...]), ...]。"""
    paras = to_paragraphs(lines)
    groups, cur_title, buf = [], default_title, []
    for p in paras:
        if p == "__RULE__":
            buf.append(p)
            continue
        if len(p) <= 24 and re.search(r"(題解|序|目錄|說明)", p) and buf:
            groups.append((cur_title, buf))
            cur_title, buf = p, []
        elif len(p) <= 24 and re.search(r"^(聲律發蒙|聲律啟蒙)", p) and buf:
            groups.append((cur_title, buf))
            cur_title, buf = p, []
        else:
            buf.append(p)
    if buf:
        groups.append((cur_title, buf))
    return groups


def paginate_prose(groups, max_chars=450):
    """按字数把分组切成页，返回 [(title, paras), ...]。

    max_chars 为实测容量：散文页舞台高 532px、正文 22px/行高 2.05（45.1px 一行）、
    每行约 53 字，扣掉段间距后安全上限约 450 字。
    """
    pages = []
    for title, ps in groups:
        chunk, size = [], 0
        for p in ps:
            n = len(p) if p != "__RULE__" else 0
            if chunk and size + n > max_chars:
                pages.append((title, chunk))
                chunk, size = [], 0
            chunk.append(p)
            size += n
        if chunk:
            pages.append((title, chunk))
    return pages


def build_slides(rhymes, front, back, per_slide=2, only="all"):
    """先生成 slide 描述，再统一编号。"""
    slides = []

    # 前置：题解 + 序言
    if front:
        for title, ps in paginate_prose(prose_groups(front)):
            slides.append(("prose", title, ps))

    for rh in rhymes:
        sts = rh["stanzas"]
        for i in range(0, len(sts), per_slide):
            slides.append(("verse", rh, sts[i:i + per_slide], i + 1))

    if back:
        paras = to_paragraphs(back)
        if paras:
            slides.append(("prose", "附錄", paras))

    if only != "all":
        slides = [s for s in slides if (s[0] == "verse") == (only == "verse")]

    total = len(slides)
    out = []
    for n, s in enumerate(slides, 1):
        if s[0] == "verse":
            _, rh, sts, idx = s
            out.append(verse_slide(rh, sts, idx, n, total))
        else:
            _, title, ps = s
            out.append(prose_slide(title, ps, n, total))
    return out, total


DECK_JS = """
<script>
(function () {
  var slides = [].slice.call(document.querySelectorAll('.slide'));
  if (!slides.length) return;
  var bar = document.querySelector('.deck-bar');
  var hint = document.querySelector('.deck-hint');
  var prevBtn = document.querySelector('.deck-nav .prev');
  var nextBtn = document.querySelector('.deck-nav .next');
  var cur = -1;

  function fit() {
    var s = Math.min(window.innerWidth / 1280, window.innerHeight / 720);
    document.documentElement.style.setProperty('--deck-scale', s);
  }

  function show(n) {
    n = Math.max(0, Math.min(slides.length - 1, n));
    if (n === cur) return;
    slides.forEach(function (el, k) {
      el.classList.toggle('active', k === n);
      el.classList.toggle('prev', k < n);
    });
    cur = n;
    if (bar) bar.style.width = ((n + 1) / slides.length * 100) + '%';
    if (prevBtn) prevBtn.disabled = n === 0;
    if (nextBtn) nextBtn.disabled = n === slides.length - 1;
    if (history.replaceState) history.replaceState(null, '', n ? '#p' + (n + 1) : '#');
  }

  function go(d) { show(cur + d); }

  document.addEventListener('keydown', function (e) {
    if (['ArrowRight', 'ArrowDown', 'PageDown', ' ', 'Enter'].indexOf(e.key) >= 0) {
      e.preventDefault(); go(1);
    } else if (['ArrowLeft', 'ArrowUp', 'PageUp', 'Backspace'].indexOf(e.key) >= 0) {
      e.preventDefault(); go(-1);
    } else if (e.key === 'Home') { show(0); }
    else if (e.key === 'End') { show(slides.length - 1); }
    else if (e.key === 'f' || e.key === 'F') {
      if (document.fullscreenElement) document.exitFullscreen();
      else document.documentElement.requestFullscreen();
    }
  });

  document.addEventListener('click', function (e) {
    if (e.target.closest('.deck-nav')) return;
    var x = e.clientX / window.innerWidth;
    if (x < 0.22) go(-1); else go(1);
  });

  var tx = null;
  document.addEventListener('touchstart', function (e) { tx = e.touches[0].clientX; }, {passive: true});
  document.addEventListener('touchend', function (e) {
    if (tx === null) return;
    var dx = e.changedTouches[0].clientX - tx;
    if (Math.abs(dx) > 45) go(dx < 0 ? 1 : -1);
    tx = null;
  }, {passive: true});

  if (prevBtn) prevBtn.addEventListener('click', function (e) { e.stopPropagation(); go(-1); });
  if (nextBtn) nextBtn.addEventListener('click', function (e) { e.stopPropagation(); go(1); });
  window.addEventListener('resize', fit);
  document.addEventListener('fullscreenchange', fit);

  var m = /#p(\\d+)/.exec(location.hash);
  fit();
  show(m ? parseInt(m[1], 10) - 1 : 0);
  if (slides.length > 1 && hint) setTimeout(function () { hint.classList.add('fade'); }, 4200);
})();
</script>
"""


def build_html(slides, title="聲律發蒙 · 幻燈"):
    nav = ""
    if len(slides) > 1:
        nav = ('<div class="deck-hint">← → 翻頁　·　F 全螢幕　·　點擊前進</div>'
               '<div class="deck-nav"><button class="prev" title="上一頁">‹</button>'
               '<button class="next" title="下一頁">›</button></div>')
    return f"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)}</title>
<script>document.documentElement.style.setProperty('--deck-scale',
  Math.min(window.innerWidth/1280, window.innerHeight/720));</script>
<style>{CSS}</style>
</head>
<body>
{chr(10).join(slides)}
<div class="deck-bar"></div>
{nav}
{DECK_JS}
</body>
</html>
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--txt", default=None, help="输入的 txt（默认取 data/source/*.txt）")
    ap.add_argument("--out", default=str(BUILD / "声律发蒙-slides.html"))
    ap.add_argument("--limit", type=int, default=0, help="只输出前 N 页（样张用）")
    ap.add_argument("--per-slide", type=int, default=2, help="每页段数")
    ap.add_argument("--only", choices=["all", "verse", "prose"], default="all",
                    help="只输出韵文页或散文页")
    args = ap.parse_args()

    txt_path = args.txt or source_txt()
    raw = open(txt_path, encoding="utf-8").read()
    # 去掉脚本生成的尾部清单（图片/链接），只保留正文
    body = raw.split("=" * 60, 1)[1].split("=" * 60)[0]
    lines = body.split("\n")

    front, verse, back = split_front_back(lines)
    rhymes = parse_verse(verse)
    print(f"解析：前置 {len(front)} 行，韵部 {len(rhymes)} 个，"
          f"段 {sum(len(r['stanzas']) for r in rhymes)} 个，附錄 {len(back)} 行")

    bad = [(r['juan'], r['name'], len(s)) for r in rhymes for s in r['stanzas'] if not (7 <= len(s) <= 10)]
    if bad:
        print("⚠ 段行数异常：", bad[:10])
    from collections import Counter
    print("段行数分布：", Counter(len(s) for r in rhymes for s in r['stanzas']))

    slides, total = build_slides(rhymes, front, back, args.per_slide, args.only)
    if args.limit:
        slides = slides[:args.limit]
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(build_html(slides))
    print(f"✓ {args.out}（{len(slides)}/{total} 页）")


if __name__ == "__main__":
    main()
