#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""无头 Chrome 渲染 make_slides 产物，并回吐排版量测数据（无法看图时的自查手段）。
用法: python3 render_check.py slides/preview-1.html
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import time

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

PROBE = """
<script>
window.addEventListener('load', function(){
  var out = {pages: []};
  document.querySelectorAll('.slide').forEach(function(sl, si){
    var sr = sl.getBoundingClientRect();
    var stage = sl.querySelector('.stage');
    var st = stage.getBoundingClientRect();
    var cols = [].slice.call(sl.querySelectorAll('.col'));
    var overflowY = cols.filter(function(c){return c.getBoundingClientRect().height > st.height + 0.5;}).length;
    var overflowX = cols.filter(function(c){
        var r=c.getBoundingClientRect();
        return r.left < sr.left || r.right > sr.right || r.top < sr.top || r.bottom > sr.bottom;
    }).length;
    function textRect(el){var r=document.createRange();r.selectNodeContents(el);return r.getBoundingClientRect();}
    var textRects = cols.map(textRect);
    var maxH = Math.max.apply(null, textRects.map(function(r){return r.height;}).concat([0]));
    var maxW = Math.max.apply(null, textRects.map(function(r){return r.width;}).concat([0]));
    var overText = textRects.filter(function(r){return r.bottom > st.bottom + 0.5 || r.top < st.top - 0.5;}).length;
    var rightMost = textRects.length ? Math.round(Math.max.apply(null, textRects.map(function(r){return r.right;}))) : 0;
    var leftMost = textRects.length ? Math.round(Math.min.apply(null, textRects.map(function(r){return r.left;}))) : 0;
    var rhs = sl.querySelector('.rhyme'), head = sl.querySelector('.head');
    var ncols = [].slice.call(sl.querySelectorAll('.n-col')).map(function(c){
      var l = c.querySelector('.n-list'), k = c.querySelector('.k');
      var nc = sl.querySelector('.notes');
      var notes = [].slice.call(c.querySelectorAll('.note'));
      return {k: k ? k.textContent : '', n: notes.length,
              xover: l.scrollWidth > l.clientWidth + 1,
              w: Math.round(l.clientWidth),
              notes_h: nc ? Math.round(nc.clientHeight) : 0,
              head_h: k ? Math.round(k.parentNode.getBoundingClientRect().height) : 0,
              chars: notes.reduce(function(a,x){return a + x.textContent.length;}, 0),
              h: Math.round(l.scrollHeight), avail: Math.round(l.clientHeight),
              over: l.scrollHeight > l.clientHeight + 1};
    });
    var trBox = sl.querySelector('.trans');
    var stageEl = sl.querySelector('.stage');
    var p = {
      idx: si,
      slide: [Math.round(sr.width), Math.round(sr.height)],
      stage: [Math.round(st.width), Math.round(st.height)],
      cols: cols.length,
      col_font: cols.length ? getComputedStyle(cols[0]).fontSize : null,
      col_max_h: Math.round(maxH),
      col_max_w: Math.round(maxW),
      col_text_max_h: Math.round(maxH),
      col_text_max_w: Math.round(maxW),
      text_overflow: overText,
      text_span_x: [leftMost, rightMost],
      overflow_y: overflowY,
      overflow_x: overflowX,
      stage_bottom_gap: Math.round(st.bottom - (cols.length ? Math.max.apply(null, cols.map(function(c){return c.getBoundingClientRect().bottom;})) : st.bottom)),
      head_bottom: Math.round(head.getBoundingClientRect().bottom),
      stage_top: Math.round(st.top),
      ncols: ncols,
      trans_h: trBox ? Math.round(trBox.getBoundingClientRect().height) : 0,
      stage_scroll: stageEl ? [stageEl.scrollHeight, stageEl.clientHeight] : null,
      text_sample: cols.length ? cols[0].textContent : sl.innerText.slice(0,60),
      title_font: rhs ? getComputedStyle(rhs).fontFamily : null,
      body_font_used: cols.length ? getComputedStyle(cols[0]).fontFamily : null
    };
    out.pages.push(p);
  });
  out.doc = {scrollW: document.documentElement.scrollWidth,
             scrollH: document.documentElement.scrollHeight,
             fonts: ['Songti SC','Kaiti SC','STSong'].filter(function(f){return document.fonts.check('16px "'+f+'"');})};
  var pre = document.createElement('pre');
  pre.id = '__PROBE__';
  pre.textContent = JSON.stringify(out, null, 1);
  document.body.appendChild(pre);
});
</script>
"""


def probe(html_path, chrome=CHROME):
    src = open(html_path, encoding="utf-8").read()
    tmp = os.path.join(tempfile.gettempdir(), "probe_" + os.path.basename(html_path))
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(src.replace("</body>", PROBE + "</body>"))
    cmd = [
        chrome, "--headless=old", "--disable-gpu", "--no-sandbox",
        "--disable-breakpad", "--disable-crash-reporter",
        "--no-first-run", "--no-default-browser-check",
        "--user-data-dir=/tmp/dsh-chrome", "--virtual-time-budget=2500",
        "--window-size=1328,768", "--dump-dom", "file://" + tmp,
    ]
    # headless old 模式 dump 完不会自行退出，超时后取已捕获的输出
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=25)
        dom = r.stdout
    except subprocess.TimeoutExpired as e:
        dom = e.stdout.decode("utf-8", "replace") if isinstance(e.stdout, bytes) else (e.stdout or "")
    m = re.search(r'<pre id="__PROBE__">(.*?)</pre>', dom, re.S)
    if not m:
        print("PROBE FAILED\n", dom[-1500:], file=sys.stderr)
        return None
    import html as _h
    return json.loads(_h.unescape(m.group(1)))


def screenshot(html_path, png_path, width=1328, height=768, scale=1.5, profile=None):
    cmd = [
        CHROME, "--headless=old", "--disable-gpu", "--no-sandbox",
        "--disable-breakpad", "--disable-crash-reporter",
        "--no-first-run", "--no-default-browser-check",
        "--hide-scrollbars", f"--user-data-dir={profile or '/tmp/dsh-chrome'}",
        "--virtual-time-budget=3000", f"--force-device-scale-factor={scale}",
        f"--window-size={width},{height}", f"--screenshot={png_path}",
        "file://" + os.path.abspath(html_path),
    ]
    try:
        subprocess.run(cmd, capture_output=True, text=True, timeout=25)
    except subprocess.TimeoutExpired:
        pass          # headless old 模式截完图常不退出，超时即走
    return os.path.exists(png_path)


DECK_PROBE = """
<script>
window.addEventListener('load', function () {
  var out = {errors: []};
  window.addEventListener('error', function (e) { out.errors.push(String(e.message)); });
  var slides = [].slice.call(document.querySelectorAll('.slide'));
  out.count = slides.length;
  out.scale = getComputedStyle(document.documentElement).getPropertyValue('--deck-scale').trim();
  function idx() { for (var i = 0; i < slides.length; i++) if (slides[i].classList.contains('active')) return i; return -1; }
  out.active = idx();
  var r = slides[out.active].getBoundingClientRect();
  out.activeRect = [Math.round(r.left), Math.round(r.top), Math.round(r.width), Math.round(r.height)];
  out.viewport = [window.innerWidth, window.innerHeight];
  out.visible = slides.map(function (el) { return getComputedStyle(el).visibility; });
  document.dispatchEvent(new KeyboardEvent('keydown', {key: 'ArrowRight'}));
  out.afterRight = idx();
  document.dispatchEvent(new KeyboardEvent('keydown', {key: 'ArrowRight'}));
  document.dispatchEvent(new KeyboardEvent('keydown', {key: 'ArrowRight'}));
  out.afterRight3 = idx();
  document.dispatchEvent(new KeyboardEvent('keydown', {key: 'ArrowLeft'}));
  out.afterLeft = idx();
  document.dispatchEvent(new KeyboardEvent('keydown', {key: 'Home'}));
  out.afterHome = idx();
  out.barWidth = document.querySelector('.deck-bar').style.width;
  out.hasNav = !!document.querySelector('.deck-nav');
  var pre = document.createElement('pre'); pre.id = '__PROBE__';
  pre.textContent = JSON.stringify(out); document.body.appendChild(pre);
});
</script>
"""


COLLIDE_PROBE = """
<script>
window.addEventListener('load', function () {
  function R(el) { var r = el.getBoundingClientRect();
    return {l: r.left, t: r.top, r: r.right, b: r.bottom, w: r.width, h: r.height}; }
  function overlap(a, b) {
    var ox = Math.min(a.r, b.r) - Math.max(a.l, b.l);
    var oy = Math.min(a.b, b.b) - Math.max(a.t, b.t);
    return (ox > 0.6 && oy > 0.6) ? [Math.round(ox * 10) / 10, Math.round(oy * 10) / 10] : null;
  }
  var out = [];
  document.querySelectorAll('.slide').forEach(function (sl, si) {
    sl.querySelectorAll('.note, .pair, .srcbar, .n-head, .trans').forEach(function (n, ni) {
      var kids = [].slice.call(n.querySelectorAll('.num, .tag, b, .py'));
      for (var i = 0; i < kids.length; i++) {
        for (var j = i + 1; j < kids.length; j++) {
          var o = overlap(R(kids[i]), R(kids[j]));
          if (o) out.push({
            slide: si + 1, block: n.className, i: kids[i].className + '|' + kids[i].textContent.slice(0, 8),
            j: kids[j].className + '|' + kids[j].textContent.slice(0, 8), ox: o[0], oy: o[1]
          });
        }
      }
    });
  });
  var pre = document.createElement('pre'); pre.id = '__PROBE__';
  pre.textContent = JSON.stringify(out); document.body.appendChild(pre);
});
</script>
"""


def collide_test(html_path, width=1440, height=900):
    src = open(html_path, encoding="utf-8").read()
    tmp = os.path.join(tempfile.gettempdir(), "collide.html")
    open(tmp, "w", encoding="utf-8").write(src.replace("</body>", COLLIDE_PROBE + "</body>"))
    cmd = [CHROME, "--headless=old", "--disable-gpu", "--no-sandbox",
           "--disable-breakpad", "--disable-crash-reporter", "--no-first-run",
           "--no-default-browser-check", "--user-data-dir=/tmp/dsh-collide",
           "--window-size=%d,%d" % (width, height), "--virtual-time-budget=2500",
           "--dump-dom", "file://" + tmp]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=25)
        dom = r.stdout
    except subprocess.TimeoutExpired as e:
        dom = e.stdout.decode("utf-8", "replace") if isinstance(e.stdout, bytes) else (e.stdout or "")
    m = re.search(r'<pre id="__PROBE__">(.*?)</pre>', dom, re.S)
    if not m:
        return None
    import html as _h
    return json.loads(_h.unescape(m.group(1)))


def deck_test(html_path, width=1440, height=900):
    src = open(html_path, encoding="utf-8").read()
    tmp = os.path.join(tempfile.gettempdir(), "decktest.html")
    open(tmp, "w", encoding="utf-8").write(src.replace("</body>", DECK_PROBE + "</body>"))
    cmd = [CHROME, "--headless=old", "--disable-gpu", "--no-sandbox",
           "--disable-breakpad", "--disable-crash-reporter", "--no-first-run",
           "--no-default-browser-check", "--user-data-dir=/tmp/dsh-decktest",
           "--window-size=%d,%d" % (width, height), "--virtual-time-budget=2500",
           "--dump-dom", "file://" + tmp]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=25)
        dom = r.stdout
    except subprocess.TimeoutExpired as e:
        dom = e.stdout.decode("utf-8", "replace") if isinstance(e.stdout, bytes) else (e.stdout or "")
    m = re.search(r'<pre id="__PROBE__">(.*?)</pre>', dom, re.S)
    if not m:
        return None
    import html as _h
    return json.loads(_h.unescape(m.group(1)))


def screenshot_slides(html_path, outdir):
    """把多页 deck 拆成单页 HTML 分别截图，便于逐页查看。"""
    src = open(html_path, encoding="utf-8").read()
    head = src.split("</head>")[0] + "</head>"
    body = src.split("<body>", 1)[1].rsplit("</body>", 1)[0]
    slides = re.findall(r"<section class=\"slide.*?</section>", body, re.S)
    os.makedirs(outdir, exist_ok=True)
    outs = []
    for i, sl in enumerate(slides, 1):
        tmp = os.path.join(tempfile.gettempdir(), f"deck_{i}.html")
        # 强制 1:1，避免无头视口偏小触发 deck 缩放而留下黑边
        open(tmp, "w", encoding="utf-8").write(
            head + "<style>.slide{transform:none!important;top:0!important;left:0!important}"
            "body{background:#f6efe1!important}</style><body>" + sl +
            "<script>document.querySelector('.slide').classList.add('active');</script>"
            "</body></html>")
        png = os.path.join(outdir, f"page-{i}.png")
        if os.path.exists(png):
            os.remove(png)
        ok = screenshot(tmp, png, width=1280, height=720, scale=1.5,
                        profile=f"/tmp/dsh-chrome-{i}")
        outs.append((png, ok))
        time.sleep(1)
    return outs


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "slides/preview-1.html"
    data = probe(path)
    if data:
        print(json.dumps(data, ensure_ascii=False, indent=1))
