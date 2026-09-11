#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""导出 PDF：五卷分册 + 五卷合訂本。

思路：不做 PDF 合并（macOS 无 pdfunite 等无依赖工具），
而是为合订本单独生成**一份 HTML**（总目页 + 五卷全部幻灯片），
再由无头 Chrome 各自打印成 PDF——一份 HTML 对应一份 PDF，天然无需合并。

页面尺寸由 CSS `@page{size:338.667mm 190.5mm}` 决定（1280×720px @96dpi），
一页一张幻灯片，无页眉页脚。

用法：
    python3 src/build_pdf.py              # 五卷分册 + 合訂本
    python3 src/build_pdf.py --volume 1   # 只出卷一
    python3 src/build_pdf.py --only-combined
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from paths import BUILD, ROOT  # noqa: E402
from build_deck import build_volume, load_book  # noqa: E402
from make_slides import build_html, cover_slide, esc  # noqa: E402
from render_check import CHROME  # noqa: E402

PDF_DIR = BUILD / "pdf"


def master_cover(volumes, page_total_all, seg_total_all):
    """合订本总目页：五卷一览。"""
    rows = []
    for vi, (juan, rhymes) in enumerate(volumes.items(), 1):
        seg = sum(len(r["stanzas"]) for r in rhymes)
        pages = sum((len(r["stanzas"]) + 1) // 2 for r in rhymes)
        names = "、".join(r["name"] for r in rhymes)
        rows.append(
            f'<div class="m-row"><span class="m-juan">{esc(juan)}</span>'
            f'<span class="m-names">{esc(names)}</span>'
            f'<span class="m-count">{seg} 段 · {pages} 頁</span></div>'
        )
    return f"""<section class="slide cover master">
  <style>
    .master .stage{{inset:64px 56px 48px}}
    .master .m-list{{margin-top:30px;width:100%;max-width:1000px}}
    .master .m-row{{display:flex;align-items:baseline;gap:18px;padding:9px 0;
      border-bottom:1px solid rgba(90,70,45,.16)}}
    .master .m-juan{{font-family:"Kaiti SC","STKaiti",serif;font-size:21px;
      color:var(--cinnabar);letter-spacing:.2em;min-width:62px}}
    .master .m-names{{flex:1;font-size:13px;color:var(--ink);opacity:.86;
      letter-spacing:.04em;text-align:left}}
    .master .m-count{{font-size:12px;color:var(--ink-soft);letter-spacing:.1em;
      white-space:nowrap}}
  </style>
  <div class="stage">
    <div class="c-main">
      <div class="book">聲律發蒙</div>
      <div class="c-rule"></div>
      <div class="vol">五卷合訂</div>
      <div class="meta">韻目 106 · 對語 {seg_total_all} 段 · 正文 {page_total_all} 頁</div>
      <div class="m-list">{''.join(rows)}</div>
    </div>
    <div class="credit">元祝明撰　潘瑛續　明劉節校補<br>
      《聲律發蒙》劉節五卷本　校訂　豆瓣 @K.A.Lee</div>
  </div>
</section>"""


def pdf_complete(path):
    """PDF 以 %%EOF 收尾即视为写完。"""
    try:
        size = os.path.getsize(path)
        if size < 1024:
            return False
        with open(path, "rb") as f:
            f.seek(max(0, size - 2048))
            return b"%%EOF" in f.read()
    except OSError:
        return False


def html_to_pdf(html_path, pdf_path, timeout=600):
    """打印 PDF。Chrome 打完不会自行退出，故轮询文件完成即收工。"""
    os.makedirs(os.path.dirname(pdf_path), exist_ok=True)
    if os.path.exists(pdf_path):
        os.remove(pdf_path)
    cmd = [
        CHROME, "--headless=old", "--disable-gpu", "--no-sandbox",
        "--disable-breakpad", "--disable-crash-reporter", "--no-first-run",
        "--no-default-browser-check", "--user-data-dir=/tmp/dsh-pdf",
        "--virtual-time-budget=6000", "--no-pdf-header-footer",
        f"--print-to-pdf={pdf_path}", "file://" + os.path.abspath(html_path),
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    deadline = time.time() + timeout
    while time.time() < deadline:
        if pdf_complete(pdf_path):
            break
        if proc.poll() is not None:
            break
        time.sleep(0.4)
    for stop in (proc.terminate, proc.kill):
        try:
            stop()
            proc.wait(timeout=5)
            break
        except Exception:
            continue
    return pdf_complete(pdf_path)


def pdf_pages(path):
    """粗略读出 PDF 页数（/Type /Page 计数）。"""
    data = open(path, "rb").read()
    return data.count(b"/Type /Page") - data.count(b"/Type /Pages")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--volume", type=int, default=0, help="只出某一卷（1-5）")
    ap.add_argument("--only-combined", action="store_true")
    args = ap.parse_args()

    front, volumes, _back = load_book()
    os.makedirs(PDF_DIR, exist_ok=True)
    results = []

    if not args.only_combined:
        for vi, (juan, rhymes) in enumerate(volumes.items(), 1):
            if args.volume and vi != args.volume:
                continue
            html = BUILD / f"{juan}.html"
            if not html.exists():
                raise SystemExit(f"缺少 {html}，请先跑 make deck")
            pdf = PDF_DIR / f"{juan}.pdf"
            ok = html_to_pdf(html, pdf)
            results.append((f"{juan}", pdf, ok))

    if not args.volume:
        # 合订本：总目页 + 五卷全部内容
        slides = [master_cover(
            volumes,
            sum(sum((len(r["stanzas"]) + 1) // 2 for r in rs) for rs in volumes.values()),
            sum(sum(len(r["stanzas"]) for r in rs) for rs in volumes.values()),
        )]
        for vi, (juan, rhymes) in enumerate(volumes.items(), 1):
            vol_slides, _pt, _st = build_volume(
                vi, juan, rhymes, front_lines=front if vi == 1 else None)
            slides += vol_slides
        combined_html = BUILD / "五卷合訂本.html"
        combined_html.write_text(
            build_html(slides, "聲律發蒙 · 五卷合訂本"), encoding="utf-8")
        pdf = PDF_DIR / "聲律發蒙·五卷合訂本.pdf"
        ok = html_to_pdf(combined_html, pdf, timeout=300)
        results.append(("合訂本", pdf, ok))

    print()
    for label, pdf, ok in results:
        if ok:
            size = os.path.getsize(pdf) / 1024 / 1024
            n = pdf_pages(pdf)
            print(f"  {'✓' if n else '?'} {label:<6} {pdf.name:<28} "
                  f"{n:>3} 页  {size:.1f} MB")
        else:
            print(f"  ✗ {label} 生成失败")
    return 0 if all(r[2] for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
