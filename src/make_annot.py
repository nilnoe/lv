#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成「注譯頁組」：
  第 1 页  原文（复用 make_slides.verse_slide，绝不改动）
  第 2 页  譯文 + 題旨・補說 + 入聲字表
  第 3 页  其一 · 詳注（典源／語詞注音／對仗與平仄）
  第 4 页  其二 · 詳注（同上）

内容全部来自 annotations/*.json，与排版解耦。

用法:
  python3 make_annot.py annotations/yidong-1.json --out slides/preview-2.html
"""

import argparse
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from paths import BUILD, source_txt  # noqa: E402
from make_slides import (  # noqa: E402
    build_html, esc, parse_verse, split_front_back, verse_slide,
)

ANNO_CSS = """
/* ================= 注譯頁 ================= */
.anno .stage{position:absolute;top:106px;bottom:56px;left:52px;right:52px;
  display:flex;flex-direction:column;gap:11px}

/* ---------- 譯文 ---------- */
.trans{display:flex;gap:24px;padding:11px 16px 12px;border-radius:3px;
  background:linear-gradient(180deg,rgba(255,255,255,.62),rgba(255,255,255,.32));
  border:1px solid rgba(90,70,45,.16);border-left:3px solid var(--cinnabar);
  box-shadow:0 1px 2px rgba(120,95,60,.06)}
.trans .t-col{flex:1;min-width:0}
.trans .t-head{font-family:"Kaiti SC","STKaiti",serif;font-size:13.5px;color:var(--cinnabar);
  letter-spacing:.24em;margin-bottom:4px}
.trans p{font-size:17.5px;line-height:1.78;color:#332d26;text-align:justify;
  font-family:"Songti SC","STSong",serif}

/* ---------- 注釋欄 ---------- */
.notes{flex:1;display:flex;gap:0;min-height:0}
.n-col{flex:1 1 0;min-width:0;display:flex;flex-direction:column;padding:0 15px}
.n-col:first-child{padding-left:0}
.n-col:last-child{padding-right:0}
.n-col + .n-col{border-left:1px solid var(--line)}
.n-head{display:flex;align-items:center;gap:8px;margin-bottom:8px}
.n-head .k{font-family:"Kaiti SC","STKaiti",serif;font-size:14px;color:var(--cinnabar);
  letter-spacing:.16em;white-space:nowrap}
.n-head .rule{flex:1;height:1px;background:var(--line)}
.n-list{overflow:hidden}
.note{margin-bottom:6.5px;font-size:12.9px;line-height:1.5;color:#332d26;
  text-align:justify;text-indent:-1.15em;padding-left:1.15em;
  overflow-wrap:anywhere;word-break:break-word}
.note .num{color:var(--cinnabar);font-weight:600;font-family:"Kaiti SC",serif}
.note b{color:#1f1a15;font-weight:600}
.note .tag{display:inline-block;font-size:10.5px;line-height:1.5;padding:0 3px;
  border:1px solid rgba(168,51,31,.45);border-radius:2px;color:var(--cinnabar);
  margin-right:3px;vertical-align:1px;letter-spacing:.06em;font-family:"Kaiti SC",serif}
.note .src{color:#7a6c5b}
/* text-indent 可继承，而 .tag 是 inline-block（块容器），会把 -1.15em 悬挂缩进
   施加到胶囊内部文字上，使标签左移压住序号。此处必须归零。 */
.note .tag,.note .ru,.note b,.pair .t,.pair .d{text-indent:0}
.note .py{color:#8a6a2f;font-family:"Times New Roman",serif;font-size:12.2px}
.note .ru{color:#fff;background:var(--cinnabar);border-radius:2px;padding:0 2.5px;
  font-size:11.5px;margin-left:1px;font-family:"Kaiti SC",serif}

/* 對仗舉隅：詞條＋理據 */
.pair{margin-bottom:5px;font-size:12.7px;line-height:1.45;color:#3a332b;
  padding-left:1.05em;text-indent:-1.05em;overflow-wrap:anywhere}
.pair .t{color:var(--cinnabar);font-weight:600}
.pair .d{color:#453d33}

/* ---------- 入聲字腳條 ---------- */
.rusheng{display:flex;align-items:center;flex-wrap:wrap;gap:5px 8px;padding:6px 13px;
  border-radius:3px;background:rgba(168,51,31,.055);border:1px solid rgba(168,51,31,.18)}
.rusheng .lbl{font-family:"Kaiti SC","STKaiti",serif;font-size:12.5px;color:var(--cinnabar);
  letter-spacing:.1em;margin-right:2px;white-space:nowrap}
.rusheng .chip{font-size:14.5px;color:#2b2621;line-height:1.2;white-space:nowrap}
.rusheng .chip .p{font-family:"Times New Roman",serif;font-size:10.5px;color:#8a6a2f}
.rusheng .chip .r{font-family:"Kaiti SC",serif;font-size:10.5px;color:#8b7a66}

/* ---------- 詳注頁：原文條 ---------- */
.srcbar{display:flex;align-items:baseline;gap:12px;padding:7px 14px;border-radius:3px;
  background:rgba(90,70,45,.05);border:1px solid rgba(90,70,45,.13)}
.srcbar .lbl{font-family:"Kaiti SC","STKaiti",serif;font-size:12.5px;color:var(--cinnabar);
  letter-spacing:.14em;white-space:nowrap}
.srcbar .txt{font-size:14.5px;line-height:1.55;color:#2b2621}
.srcbar .txt em{font-style:normal;color:#fff;background:var(--cinnabar);border-radius:2px;
  padding:0 2px;margin:0 .5px}
.srcbar .legend{margin-left:auto;font-size:11px;color:#8b7a66;white-space:nowrap}
"""


# --------------------------------------------------------------------------
def render_notes(items, start=1):
    out = []
    for i, it in enumerate(items):
        tag = f'<span class="tag">{esc(it["tag"])}</span>' if it.get("tag") else ""
        term = f'<b>{esc(it["term"])}</b>　' if it.get("term") else ""
        out.append(
            f'<div class="note"><span class="num">{start + i}</span> {tag}{term}{it["text"]}</div>'
        )
    return "".join(out)


def render_columns(columns, start=1):
    cols, n = [], start
    for col in columns:
        if col.get("pairs") is not None:
            inner = "".join(
                f'<div class="pair"><span class="t">{esc(p["t"])}</span>'
                f'<span class="d">　{esc(p["d"])}</span></div>'
                for p in col["pairs"]
            )
        else:
            inner = render_notes(col["notes"], n)
            n += len(col["notes"])
        style = f' style="flex:{col["flex"]} 1 0"' if col.get("flex") else ""
        cols.append(
            f'<div class="n-col"{style}><div class="n-head"><span class="k">{esc(col["title"])}</span>'
            f'<span class="rule"></span></div><div class="n-list">{inner}</div></div>'
        )
    return "".join(cols), n


def rusheng_bar(items):
    chips = "".join(
        f'<span class="chip">{esc(r["ch"])}<span class="p"> {esc(r.get("py",""))}</span>'
        f'<span class="r"> {esc(r.get("rhyme",""))}</span></span>'
        for r in items
    )
    return f'<div class="rusheng"><span class="lbl">入聲字</span>{chips}</div>'


def head_block(juan, rhyme, right, book="聲律發蒙"):
    return f"""  <div class="head">
    <span class="book">{esc(book)}</span>
    <span class="juan">{esc(juan)}</span>
    <span class="spacer"></span>
    <span class="rhyme">{esc(rhyme)}</span>
    <span class="part">{esc(right)}</span>
  </div>
  <div class="head-rule"></div>"""


def foot_block(page_no, total_pages):
    return f"""  <div class="foot">
    <span class="seal">發蒙</span>
    <span>《聲律發蒙》劉節五卷本 · 校訂 豆瓣 @K.A.Lee</span>
    <span class="spacer"></span>
    <span class="pg">{page_no} / {total_pages}</span>
  </div>"""


def trans_page(data, juan, rhyme, page_no, total_pages):
    trans = "".join(
        f'<div class="t-col"><div class="t-head">{esc(t["label"])}</div>'
        f'<p>{t["text"]}</p></div>'
        for t in data["trans"]
    )
    cols, _ = render_columns(data.get("columns", []))
    rus = rusheng_bar(data.get("rusheng", [])) if data.get("rusheng") else ""
    return f"""<section class="slide anno page-trans">
{head_block(juan, rhyme, "譯文")}
  <div class="stage">
    <div class="trans">{trans}</div>
    <div class="notes">{cols}</div>
    {rus}
  </div>
{foot_block(page_no, total_pages)}
</section>"""


def mark_rusheng(text, ruset):
    """把入聲字標朱（僅用於詳注頁的原文條，第 1 页原文不动）。"""
    return "".join(f"<em>{ch}</em>" if ch in ruset else ch for ch in text)


def notes_page(data, juan, rhyme, page_no, total_pages):
    src = "　".join(data["lines"])
    src_html = mark_rusheng(src, set(data.get("rusheng_set", "")))
    cols, _ = render_columns(data.get("columns", []))
    return f"""<section class="slide anno">
{head_block(juan, rhyme, data["label"] + " · 詳注")}
  <div class="stage">
    <div class="srcbar"><span class="lbl">原文</span><span class="txt">{src_html}</span>
      <span class="legend">朱色即中古入聲字</span></div>
    <div class="notes">{cols}</div>
  </div>
{foot_block(page_no, total_pages)}
</section>"""


# --------------------------------------------------------------------------
def load_verse(txt_path, juan, rhyme, first=1, count=2):
    raw = open(txt_path, encoding="utf-8").read()
    body = raw.split("=" * 60, 1)[1].split("=" * 60)[0]
    _front, verse, _back = split_front_back(body.split("\n"))
    for r in parse_verse(verse):
        if r["name"] == rhyme and (not juan or r["juan"] == juan):
            return r, r["stanzas"][first - 1: first - 1 + count]
    raise SystemExit(f"未找到韵部 {juan} {rhyme}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("json_path")
    ap.add_argument("--txt", default=None)
    ap.add_argument("--out", default=str(BUILD / "样本" / "一東注譯四頁.html"))
    ap.add_argument("--juan", default="卷一")
    ap.add_argument("--rhyme", default="一東")
    ap.add_argument("--first", type=int, default=1)
    ap.add_argument("--count", type=int, default=2)
    args = ap.parse_args()

    txt = args.txt or source_txt()
    rhyme, stanzas = load_verse(txt, args.juan, args.rhyme, args.first, args.count)
    data = json.load(open(args.json_path, encoding="utf-8"))

    pages = data["pages"]
    total = 2 + len(pages.get("stanzas", []))
    slides = [verse_slide(rhyme, stanzas, args.first, 1, total)]
    slides.append(trans_page(pages["trans"], args.juan, args.rhyme, 2, total))
    for i, st in enumerate(pages.get("stanzas", []), start=3):
        slides.append(notes_page(st, args.juan, args.rhyme, i, total))

    doc = build_html(slides, "聲律發蒙 · 一東 · 原文與注譯").replace(
        "</style>", ANNO_CSS + "</style>"
    )
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    open(args.out, "w", encoding="utf-8").write(doc)
    print(f"✓ {args.out}（{len(slides)} 页）")


if __name__ == "__main__":
    main()
