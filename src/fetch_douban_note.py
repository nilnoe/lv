#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
豆瓣日记（note）抓取脚本 —— 汇总为纯文本 txt，便于后续数据处理。

特点：
  * 纯标准库实现，无需 pip 安装任何依赖
  * 优先走移动端 rexxar API（m.douban.com），绕开网页版反爬跳转
  * API 失败时回退到 www.douban.com 页面解析
  * 正文按段落/标题/列表还原换行，保留可读结构
  * 同时落地原始 JSON / HTML，方便后续做结构化处理

用法：
  python3 fetch_douban_note.py https://www.douban.com/note/845112386/?_i=91012580ikDObq
  python3 fetch_douban_note.py 845112386 844770214 --outdir data
  python3 fetch_douban_note.py --list urls.txt        # 每行一个链接
"""

import argparse
import gzip
import html
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from html.parser import HTMLParser

UA_MOBILE = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1"
)
UA_DESKTOP = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

API_URL = "https://m.douban.com/rexxar/api/v2/note/{nid}?for_mobile=1"
PAGE_URL = "https://www.douban.com/note/{nid}/"
NOTE_URL = "https://www.douban.com/note/{nid}/"


# --------------------------------------------------------------------------
# 网络
# --------------------------------------------------------------------------
def http_get(url, referer=None, mobile=True, timeout=30):
    """GET 一个 URL，返回 (状态码, 解码后的文本)。不抛异常，失败返回 (None, None)。"""
    headers = {
        "User-Agent": UA_MOBILE if mobile else UA_DESKTOP,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip",
        "Connection": "close",
    }
    if referer:
        headers["Referer"] = referer
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            if resp.headers.get("Content-Encoding") == "gzip":
                raw = gzip.decompress(raw)
            return resp.status, raw.decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        body = e.read()
        if e.headers.get("Content-Encoding") == "gzip":
            try:
                body = gzip.decompress(body)
            except OSError:
                pass
        return e.code, body.decode("utf-8", errors="replace")
    except Exception as e:  # noqa: BLE001
        print(f"  ! 请求失败 {url}: {e}", file=sys.stderr)
        return None, None


def extract_note_id(text):
    """从链接或纯数字中取出日记 id。"""
    m = re.search(r"/note/(\d+)", text)
    if m:
        return m.group(1)
    m = re.fullmatch(r"\s*(\d{6,})\s*", text)
    return m.group(1) if m else None


# --------------------------------------------------------------------------
# HTML -> 文本
# --------------------------------------------------------------------------
BLOCK_TAGS = {
    "p", "div", "br", "hr", "li", "ul", "ol", "dl", "dt", "dd",
    "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "pre",
    "table", "tr", "td", "th", "section", "article", "figure", "figcaption",
}
SKIP_TAGS = {"script", "style", "noscript", "svg"}
HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}


class NoteHTMLParser(HTMLParser):
    """把日记正文 HTML 转成保留段落结构的纯文本，并收集链接。"""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []          # 文本片段
        self.links = []          # (锚文本, href) 按出现顺序
        self.images = []         # 图片地址
        self._skip_depth = 0
        self._link_stack = []    # 正在处理的 <a>
        self._heading_depth = 0
        self._link_buf = None

    # -- 工具 -------------------------------------------------------------
    def _newline(self, times=1):
        self.parts.append("\n" * times)

    def _last_is_newline(self):
        return not self.parts or self.parts[-1].endswith("\n")

    # -- 事件 -------------------------------------------------------------
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in SKIP_TAGS:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return

        if tag == "br":
            self._newline()
        elif tag == "img":
            src = a.get("src") or a.get("data-src") or ""
            alt = (a.get("alt") or "").strip()
            if src:
                self.images.append(src)
            self.parts.append(f"【图片：{alt}】" if alt else "【图片】")
        elif tag == "a":
            href = (a.get("href") or "").strip()
            self._link_stack.append(href)
            self._link_buf = []
        elif tag in HEADING_TAGS:
            if not self._last_is_newline():
                self._newline()
            self._heading_depth += 1
            self.parts.append("#" * int(tag[1]) + " ")
        elif tag in BLOCK_TAGS and not self._last_is_newline():
            self._newline()

    def handle_endtag(self, tag):
        if tag in SKIP_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)
            return
        if self._skip_depth:
            return

        if tag == "a":
            href = self._link_stack.pop() if self._link_stack else ""
            anchor = "".join(self._link_buf or []).strip()
            if href:
                self.links.append((anchor, href))
            self._link_buf = None
        elif tag in HEADING_TAGS:
            self._heading_depth = max(0, self._heading_depth - 1)
            self.parts.append("\n")
        elif tag in BLOCK_TAGS:
            self._newline()

    def handle_data(self, data):
        if self._skip_depth:
            return
        if not data:
            return
        if self._link_buf is not None:
            self._link_buf.append(data)
        self.parts.append(data)

    # -- 结果 -------------------------------------------------------------
    def text(self):
        raw = "".join(self.parts)
        raw = raw.replace("\xa0", " ").replace("\u3000", " ")
        raw = re.sub(r"[ \t]+\n", "\n", raw)
        raw = re.sub(r"[ \t]{2,}", " ", raw)
        raw = re.sub(r"\n{3,}", "\n\n", raw)
        lines = [ln.strip() for ln in raw.split("\n")]
        # 合并因行内标签产生的空行，但保留段落间空行
        out = []
        for ln in lines:
            if ln == "" and out and out[-1] == "":
                continue
            out.append(ln)
        return "\n".join(out).strip()


def html_to_text(fragment):
    p = NoteHTMLParser()
    p.feed(fragment)
    p.close()
    return p.text(), p.links, p.images


def strip_tags(fragment):
    return html.unescape(re.sub(r"<[^>]+>", "", fragment or "")).strip()


# --------------------------------------------------------------------------
# 抓取
# --------------------------------------------------------------------------
def fetch_via_api(nid):
    """移动端 rexxar API，返回 dict 或 None。"""
    status, body = http_get(
        API_URL.format(nid=nid), referer=NOTE_URL.format(nid=nid), mobile=True
    )
    if status == 200 and body and body.lstrip().startswith("{"):
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            return None, body
        if data.get("id") or data.get("title"):
            return data, body
    return None, body


def fetch_via_page(nid):
    """回退方案：解析 www 页面（可能被反爬拦截）。"""
    status, body = http_get(PAGE_URL.format(nid=nid), mobile=False)
    if status != 200 or not body or "sec.douban.com" in body[:2000]:
        return None, body

    def pick(pattern):
        m = re.search(pattern, body, re.S)
        return html.unescape(m.group(1)).strip() if m else ""

    content = ""
    m = re.search(r'<div[^>]+class="[^"]*note-content[^"]*"[^>]*>(.*?)</div>\s*</div>', body, re.S)
    if m:
        content = m.group(1)
    data = {
        "id": nid,
        "title": pick(r'<h1[^>]*>\s*(.*?)\s*</h1>') or pick(r"<title>(.*?)</title>").split(" - ")[0],
        "content": content,
        "author": {"name": pick(r'<span[^>]+class="[^"]*from[^"]*"[^>]*>.*?<a[^>]*>(.*?)</a>')},
        "create_time": pick(r'<span[^>]+class="[^"]*pubtime[^"]*"[^>]*>(.*?)</span>'),
        "url": NOTE_URL.format(nid=nid),
    }
    return data, body


# --------------------------------------------------------------------------
# 输出
# --------------------------------------------------------------------------
def safe_filename(name, maxlen=80):
    name = re.sub(r'[\\/:*?"<>|\r\n\t]+', "_", name or "untitled").strip(" .")
    name = re.sub(r"\s+", " ", name)
    if not name:
        name = "untitled"
    return name[:maxlen]


def build_txt(meta):
    lines = [
        f"标题: {meta['title']}",
        f"作者: {meta['author']}",
    ]
    if meta.get("author_url"):
        lines.append(f"作者主页: {meta['author_url']}")
    lines.append(f"原文链接: {meta['url']}")
    if meta.get("create_time"):
        lines.append(f"发布时间: {meta['create_time']}")
    if meta.get("update_time"):
        lines.append(f"最后更新: {meta['update_time']}")
    if meta.get("ip_location"):
        lines.append(f"IP属地: {meta['ip_location']}")
    if meta.get("tags"):
        lines.append("标签: " + "、".join(meta["tags"]))
    if meta.get("stats"):
        stats = "，".join(f"{k}: {v}" for k, v in meta["stats"].items() if v not in (None, ""))
        if stats:
            lines.append(f"数据: {stats}")
    lines.append(f"正文长度: {len(meta['content_text'])} 字（含空白）")
    lines.append(f"抓取时间: {meta['fetched_at']}")
    lines.append("=" * 60)
    lines.append("")
    lines.append(meta["content_text"])
    lines.append("")

    if meta.get("images"):
        lines += ["", "=" * 60, f"图片（{len(meta['images'])} 张）", ""]
        lines += [f"[{i}] {u}" for i, u in enumerate(meta["images"], 1)]

    links = meta.get("links") or []
    if links:
        lines += ["", "=" * 60, f"正文链接（{len(links)} 条）", ""]
        seen = set()
        idx = 0
        for anchor, href in links:
            key = (anchor, href)
            if key in seen:
                continue
            seen.add(key)
            idx += 1
            lines.append(f"[{idx}] {anchor or '(无锚文本)'} -> {href}")
    return "\n".join(lines).rstrip() + "\n"


def process(target, outdir, keep_raw=True, sleep=2.0):
    nid = extract_note_id(target)
    if not nid:
        print(f"! 无法识别日记 id: {target}", file=sys.stderr)
        return None
    print(f"→ 抓取 note/{nid}")

    data, raw_body = fetch_via_api(nid)
    src = "rexxar-api"
    if not data:
        print("  · API 不可用，回退网页解析")
        data, raw_body = fetch_via_page(nid)
        src = "html-page"
    if not data:
        print(f"  ! note/{nid} 抓取失败（可能被反爬拦截或已删除）", file=sys.stderr)
        return None

    content_html = data.get("content") or ""
    if not content_html and data.get("abstract"):
        content_html = f"<p>{data['abstract']}</p>"
    content_text, links, images = html_to_text(content_html)

    author = data.get("author") or {}
    if isinstance(author, str):
        author = {"name": author}
    photos = [p.get("url") or p.get("large") or p.get("raw") for p in (data.get("photos") or []) if isinstance(p, dict)]
    images = [u for u in images if u] + [u for u in photos if u]

    meta = {
        "id": nid,
        "title": data.get("title") or f"note-{nid}",
        "author": author.get("name") or "",
        "author_url": author.get("url") or "",
        "url": data.get("url") or NOTE_URL.format(nid=nid),
        "create_time": data.get("create_time") or "",
        "update_time": data.get("edit_time") if data.get("edit_time") not in (None, "None") else "",
        "ip_location": data.get("ip_location") or "",
        "tags": [t.get("name") for t in (data.get("tags") or []) if isinstance(t, dict) and t.get("name")],
        "stats": {
            "阅读": data.get("read_count"),
            "评论": data.get("comments_count"),
            "点赞": data.get("likers_count"),
            "转发": data.get("reshares_count"),
        },
        "content_text": content_text,
        "links": links,
        "images": images,
        "source": src,
        "fetched_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }

    os.makedirs(outdir, exist_ok=True)
    base = f"{safe_filename(meta['title'])}-{nid}"
    txt_path = os.path.join(outdir, base + ".txt")
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(build_txt(meta))

    if keep_raw:
        rawdir = os.path.join(outdir, "raw")
        os.makedirs(rawdir, exist_ok=True)
        with open(os.path.join(rawdir, base + ".json"), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        meta_out = {k: v for k, v in meta.items() if k != "content_text"}
        meta_out["content_text_len"] = len(content_text)
        with open(os.path.join(rawdir, base + ".meta.json"), "w", encoding="utf-8") as f:
            json.dump(meta_out, f, ensure_ascii=False, indent=2)
        if content_html:
            with open(os.path.join(rawdir, base + ".content.html"), "w", encoding="utf-8") as f:
                f.write(content_html)

    print(f"  ✓ {txt_path}  ({len(content_text)} 字, {len(links)} 链接, {len(images)} 图)")
    time.sleep(sleep)
    return txt_path


def main():
    ap = argparse.ArgumentParser(description="抓取豆瓣日记并汇总为 txt")
    ap.add_argument("targets", nargs="*", help="日记链接或纯数字 id")
    ap.add_argument("--list", dest="listfile", help="包含链接的文件，每行一个")
    ap.add_argument("--outdir", default="douban_txt", help="输出目录（默认 douban_txt）")
    ap.add_argument("--no-raw", action="store_true", help="不保存原始 JSON/HTML")
    ap.add_argument("--sleep", type=float, default=2.0, help="多篇之间的间隔秒数")
    args = ap.parse_args()

    targets = list(args.targets)
    if args.listfile:
        with open(args.listfile, encoding="utf-8") as f:
            targets += [ln.strip() for ln in f if ln.strip() and not ln.startswith("#")]
    if not targets:
        ap.error("请至少给一个链接/ID，或用 --list 指定文件")

    results = [process(t, args.outdir, keep_raw=not args.no_raw, sleep=args.sleep) for t in targets]
    ok = [r for r in results if r]
    print(f"\n完成：成功 {len(ok)}/{len(targets)}，输出目录 {os.path.abspath(args.outdir)}")


if __name__ == "__main__":
    main()
