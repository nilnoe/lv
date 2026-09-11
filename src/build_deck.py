#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""按卷批量生成原文 deck（五卷 → 五个 HTML）。

每卷结构：
    封面页（韵目索引）
    [卷一] 前置页（題解、五篇序）
    正文页（每页 2 段，竖排右起）

页码约定（详见 docs/内容与页码约定.md）：
    正文页按「卷内独立序号」编号，形如 `卷一 · 3 / 30`，
    因此日后插入注解页不会使原有页码移位。
    注解页将用子编号 `卷一 · 3 · 注 2`，未产出前留空。

用法：
    python3 src/build_deck.py                # 出全部五卷 + index.html
    python3 src/build_deck.py --volume 1     # 只出卷一
    python3 src/build_deck.py --slots        # 每页原文后插入空白注解占位页
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import OrderedDict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from paths import BUILD, source_txt  # noqa: E402
from make_slides import (  # noqa: E402
    build_html, cover_slide, esc, paginate_prose, parse_verse, prose_groups,
    prose_slide, split_front_back, verse_slide,
)

CN = "一二三四五"


def load_book(txt_path=None):
    """解析全书，返回 (前置散行, {卷名: [韵部,...]}, 附錄散行)。"""
    raw = open(txt_path or source_txt(), encoding="utf-8").read()
    body = raw.split("=" * 60, 1)[1].split("=" * 60)[0]
    front, verse, back = split_front_back(body.split("\n"))
    volumes: "OrderedDict[str, list]" = OrderedDict()
    for r in parse_verse(verse):
        volumes.setdefault(r["juan"] or "卷一", []).append(r)
    return front, volumes, back


def slot_slide(juan, page_label, target_id, note="此頁為注解與翻譯預留"):
    """注解占位页：页码留空由调用方决定。"""
    return f"""<section class="slide prose slot" id="{esc(target_id)}-slot">
  <div class="head">
    <span class="book">聲律發蒙</span>
    <span class="juan">{esc(juan)}</span>
    <span class="spacer"></span>
    <span class="part">注譯 · 待補</span>
  </div>
  <div class="head-rule"></div>
  <div class="stage" style="display:flex;align-items:center;justify-content:center">
    <p style="text-indent:0;text-align:center;color:#8b7a66;font-size:20px;letter-spacing:.3em">
      {esc(note)}</p>
  </div>
  <div class="foot">
    <span class="seal">發蒙</span>
    <span>《聲律發蒙》劉節五卷本 · 校訂 豆瓣 @K.A.Lee</span>
    <span class="spacer"></span>
    <span class="pg">{esc(page_label)}</span>
  </div>
</section>"""


def build_volume(vol_no, juan, rhymes, front_lines=None, per_slide=2, slots=False):
    """返回该卷的 slides 列表（HTML 片段）。"""
    seg_total = sum(len(r["stanzas"]) for r in rhymes)
    # 分页不跨韵部：每个韵部另起一页，故总页数是逐韵取整之和
    page_total = sum((len(r["stanzas"]) + per_slide - 1) // per_slide for r in rhymes)
    slides = []

    # 1) 封面
    slides.append(cover_slide(
        juan, [r["name"] for r in rhymes], seg_total, page_total, vol_no,
        subtitle={1: "上平聲", 2: "下平聲", 3: "上聲", 4: "去聲", 5: "入聲"}.get(vol_no, ""),
    ))

    # 2) 前置（仅卷一）
    if front_lines:
        pages = paginate_prose(prose_groups(front_lines))
        for i, (title, paras) in enumerate(pages, 1):
            slides.append(prose_slide(
                title, paras, i, len(pages),
                page_label=f"{juan} · 前置 {i} / {len(pages)}",
            ))

    # 3) 正文
    page_no = 0
    for rh in rhymes:
        sts = rh["stanzas"]
        for i in range(0, len(sts), per_slide):
            page_no += 1
            chunk = sts[i:i + per_slide]
            sid = f"j{vol_no}-{rh['name']}-{i + 1}"
            label = f"{juan} · {page_no} / {page_total}"
            slides.append(verse_slide(
                rh, chunk, i + 1, page_no, page_total,
                page_label=label, slide_id=sid,
            ))
            if slots:
                slides.append(slot_slide(juan, f"{juan} · {page_no} · 注", sid))
    return slides, page_total, seg_total


INDEX_CSS = """
body{display:block;padding:0;background:
  radial-gradient(ellipse at 50% 40%, #241f1a 0%, #16130f 55%, #0d0b09 100%);min-height:100vh}
.wrap{max-width:760px;margin:0 auto;padding:70px 28px 90px;color:#efe6d6;
  font-family:"Songti SC","STSong",serif}
h1{font-family:"Kaiti SC","STKaiti",serif;font-size:44px;letter-spacing:.42em;
  font-weight:400;text-align:center;margin:0 0 10px}
.sub{text-align:center;color:#a99c8b;font-size:13.5px;letter-spacing:.24em;margin-bottom:52px}
a.vol{display:flex;align-items:baseline;gap:18px;text-decoration:none;color:#efe6d6;
  padding:18px 22px;margin-bottom:12px;border:1px solid rgba(246,239,225,.14);
  border-radius:4px;background:rgba(246,239,225,.035);transition:.18s}
a.vol:hover{background:rgba(168,51,31,.22);border-color:rgba(246,239,225,.34)}
a.vol .n{font-family:"Kaiti SC","STKaiti",serif;font-size:27px;color:#d8705a;
  letter-spacing:.2em;min-width:74px}
a.vol .t{font-size:15px;color:#cfc3b0;flex:1}
a.vol .c{font-size:12.5px;color:#8b7f6e;letter-spacing:.12em}
.foot-note{margin-top:44px;text-align:center;color:#7d7263;font-size:12.5px;letter-spacing:.16em;line-height:2}
"""


def build_index(volumes_meta):
    rows = "".join(
        f'<a class="vol" href="{esc(fn)}"><span class="n">{esc(juan)}</span>'
        f'<span class="t">{esc(rhyme_txt)}</span>'
        f'<span class="c">{segs} 段 · {pages} 頁</span></a>'
        for juan, fn, rhyme_txt, segs, pages in volumes_meta
    )
    return f"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>聲律發蒙 · 總目</title>
<style>{INDEX_CSS}</style>
</head>
<body>
<div class="wrap">
  <h1>聲律發蒙</h1>
  <div class="sub">元祝明撰　潘瑛續　明劉節校補　·　原文五卷</div>
  {rows}
  <div class="foot-note">《聲律發蒙》劉節五卷本　校訂　豆瓣 @K.A.Lee<br>
    注解與翻譯另行逐篇推進，頁碼已按卷內獨立編號預留</div>
</div>
</body>
</html>
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--txt", default=None)
    ap.add_argument("--volume", type=int, default=0, help="只出某一卷（1-5），0 为全部")
    ap.add_argument("--per-slide", type=int, default=2)
    ap.add_argument("--slots", action="store_true", help="每页原文后插入空白注解占位页")
    ap.add_argument("--outdir", default=str(BUILD))
    args = ap.parse_args()

    front, volumes, _back = load_book(args.txt)
    os.makedirs(args.outdir, exist_ok=True)
    meta = []
    for vi, (juan, rhymes) in enumerate(volumes.items(), 1):
        if args.volume and vi != args.volume:
            continue
        slides, page_total, seg_total = build_volume(
            vi, juan, rhymes,
            front_lines=front if vi == 1 else None,
            per_slide=args.per_slide, slots=args.slots,
        )
        fn = f"{juan}.html"
        out = os.path.join(args.outdir, fn)
        title = f"聲律發蒙 · {juan}"
        open(out, "w", encoding="utf-8").write(build_html(slides, title))
        names = "、".join(r["name"] for r in rhymes)
        meta.append((juan, fn, names, seg_total, page_total))
        front_n = len(slides) - page_total - 1
        front_txt = f" + 前置{front_n}" if front_n else ""
        print(f"  ✓ {out}  {len(slides)} 页（封面1{front_txt} + 正文{page_total}）  {seg_total} 段")

    if not args.volume:
        idx = os.path.join(args.outdir, "index.html")
        open(idx, "w", encoding="utf-8").write(build_index(meta))
        print(f"  ✓ {idx}")
    print(f"合计正文 {sum(m[4] for m in meta)} 页 / {sum(m[3] for m in meta)} 段")


if __name__ == "__main__":
    main()
