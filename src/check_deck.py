#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""全量排版质检：逐页检查溢出、文本越界、元素出界。

这是 docs/工程规范.md 里「质检规范」的执行者。任何一页不合格都必须先修，
再谈交付。

用法：
    python3 src/check_deck.py                 # 检查 build/卷*.html
    python3 src/check_deck.py build/卷三.html
    python3 src/check_deck.py --json          # 输出机器可读结果
"""

from __future__ import annotations

import argparse
import glob
import html as H
import json
import os
import re
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from paths import BUILD  # noqa: E402
from render_check import CHROME  # noqa: E402

PROBE = r"""
<script>
window.addEventListener('load', function () {
  function R(el) { var r = el.getBoundingClientRect();
    return {l: r.left, t: r.top, r: r.right, b: r.bottom, w: r.width, h: r.height}; }
  var issues = [];
  var slides = [].slice.call(document.querySelectorAll('.slide'));
  slides.forEach(function (sl, i) {
    var sb = R(sl);
    var id = sl.id || ('#' + (i + 1));
    var kind = sl.classList.contains('cover') ? 'cover'
             : sl.classList.contains('anno') ? 'anno'
             : sl.classList.contains('prose') ? 'prose' : 'verse';

    // 1) 任何可见内容超出幻灯片画布
    sl.querySelectorAll('.stage, .head, .foot').forEach(function (box) {
      [].slice.call(box.querySelectorAll('*')).forEach(function (el) {
        var t = (el.textContent || '').trim();
        if (!t || el.children.length) return;
        var r = R(el);
        if (r.w < 0.5 || r.h < 0.5) return;
        if (r.l < sb.l - 0.6 || r.r > sb.r + 0.6 || r.t < sb.t - 0.6 || r.b > sb.b + 0.6) {
          issues.push({id: id, kind: kind, type: 'out_of_slide', el: el.className || el.tagName,
                       text: t.slice(0, 14)});
        }
      });
    });

    // 2) 竖排正文：最长一列的文字高度不得超过舞台
    var stage = sl.querySelector('.stage');
    if (kind === 'verse' && stage) {
      var st = R(stage);
      [].slice.call(sl.querySelectorAll('.col')).forEach(function (c) {
        var r = document.createRange(); r.selectNodeContents(c);
        var tr = r.getBoundingClientRect();
        if (tr.bottom > st.b + 0.6 || tr.top < st.t - 0.6) {
          issues.push({id: id, kind: kind, type: 'col_overflow',
                       text: (c.textContent || '').slice(0, 14),
                       overBy: Math.round((tr.bottom - st.b) * 10) / 10,
                       font: getComputedStyle(c).fontSize});
        }
      });
      // 3) 横向：所有列必须在舞台宽度内
      [].slice.call(sl.querySelectorAll('.stanza')).forEach(function (g) {
        var gr = R(g);
        if (gr.l < st.l - 0.6 || gr.r > st.r + 0.6) {
          issues.push({id: id, kind: kind, type: 'stanza_overflow',
                       overBy: Math.round(Math.max(st.l - gr.l, gr.r - st.r) * 10) / 10});
        }
      });
    }

    // 3b) 任意两个叶子文本元素不得互相重叠（绝对定位串位、负缩进跑字等）
    var leaves = [];
    [].slice.call(sl.querySelectorAll('.stage *, .head *, .foot *')).forEach(function (el) {
      if (el.children.length) return;
      var t = (el.textContent || '').trim();
      if (!t || el.tagName === 'HR') return;
      var rs = [].slice.call(el.getClientRects()).filter(function (x) { return x.width > 0.5 && x.height > 0.5; });
      if (!rs.length) return;
      leaves.push({el: el, rs: rs, t: t});
    });
    for (var a = 0; a < leaves.length; a++) {
      for (var b = a + 1; b < leaves.length; b++) {
        // 用逐行 client rect 比对：行内元素跨行时 boundingRect 是并集，会产生假重叠
        var hit = 0;
        leaves[a].rs.forEach(function (A) {
          leaves[b].rs.forEach(function (B) {
            var ox = Math.min(A.right, B.right) - Math.max(A.left, B.left);
            var oy = Math.min(A.bottom, B.bottom) - Math.max(A.top, B.top);
            if (ox > 2 && oy > 2) hit = Math.max(hit, ox * oy);
          });
        });
        if (hit > 0) {
          issues.push({id: id, kind: kind, type: 'text_overlap',
                       el: (leaves[a].el.className || leaves[a].el.tagName) + ' × ' +
                           (leaves[b].el.className || leaves[b].el.tagName),
                       text: leaves[a].t.slice(0, 10) + ' / ' + leaves[b].t.slice(0, 10),
                       area: Math.round(hit)});
        }
      }
    }

    // 4) 注释块：内容不得溢出容器
    [].slice.call(sl.querySelectorAll('.n-list, .trans, .srcbar, .rusheng, .rhymes')).forEach(function (b) {
      if (b.scrollHeight > b.clientHeight + 1 || b.scrollWidth > b.clientWidth + 1) {
        issues.push({id: id, kind: kind, type: 'content_overflow', el: b.className,
                     h: [b.scrollHeight, b.clientHeight], w: [b.scrollWidth, b.clientWidth]});
      }
    });
  });
  var pre = document.createElement('pre'); pre.id = '__PROBE__';
  pre.textContent = JSON.stringify({slides: slides.length, issues: issues});
  document.body.appendChild(pre);
});
</script>
"""


def check_file(path, width=1280, height=720):
    src = open(path, encoding="utf-8").read()
    tmp = os.path.join(tempfile.gettempdir(), "checkdeck.html")
    open(tmp, "w", encoding="utf-8").write(src.replace("</body>", PROBE + "</body>"))
    cmd = [CHROME, "--headless=old", "--disable-gpu", "--no-sandbox", "--disable-breakpad",
           "--disable-crash-reporter", "--no-first-run", "--no-default-browser-check",
           "--user-data-dir=/tmp/dsh-check", f"--window-size={width},{height}",
           "--virtual-time-budget=4000", "--dump-dom", "file://" + tmp]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        dom = r.stdout
    except subprocess.TimeoutExpired as e:
        dom = e.stdout.decode("utf-8", "replace") if isinstance(e.stdout, bytes) else (e.stdout or "")
    m = re.search(r'<pre id="__PROBE__">(.*?)</pre>', dom, re.S)
    if not m:
        return None
    return json.loads(H.unescape(m.group(1)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="*", help="要检查的 html（默认 build/卷*.html）")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    args = ap.parse_args()

    files = args.files or sorted(glob.glob(str(BUILD / "卷*.html")))
    if not files:
        raise SystemExit("没有可检查的文件")

    all_results, total_issues = [], 0
    for f in files:
        res = check_file(f)
        if res is None:
            print(f"✗ {os.path.basename(f)}  质检脚本未能取到结果")
            total_issues += 1
            continue
        issues = res["issues"]
        total_issues += len(issues)
        all_results.append({"file": f, **res})
        flag = "✓" if not issues else "✗"
        print(f"{flag} {os.path.basename(f):<12} {res['slides']:>3} 页，问题 {len(issues)} 处")
        seen = {}
        for it in issues:
            key = (it["type"], it.get("el", ""))
            seen.setdefault(key, []).append(it)
        for (t, el), items in seen.items():
            sample = items[0]
            extra = f"（另有 {len(items) - 1} 处）" if len(items) > 1 else ""
            detail = sample.get("text", "") or f"{sample.get('h','')} {sample.get('w','')}"
            print(f"    · {t} {el}  {detail} {extra}")

    if args.json:
        print(json.dumps(all_results, ensure_ascii=False, indent=1))
    print(f"\n{'全部通过 ✓' if total_issues == 0 else f'共 {total_issues} 处问题'}")
    return 1 if total_issues else 0


if __name__ == "__main__":
    sys.exit(main())
