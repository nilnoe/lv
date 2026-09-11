#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""源文本结构校验：按「八聯」体例逐段核对句式字数。

体例（《四庫全書總目》：「自一字七字至隔句各押一韻」）：
    1. 三字對   8 字   南對北，北對東。
    2. 五言     6 字   物外對寰中。
    3. 五言對  12 字   君臣對父子，海嶽對雷風。
    4. 三字對   8 字   堯舜德，禹湯功。
    5. 五言     6 字   孔子對周公。
    6. 五言對  12 字   六經千古在，五典百王同。
    7. 七言對  16 字   天地無心成化育，聖賢有道繼鴻濛。
    8. 四六長句 12–15 字
    9. 四六長句 12–15 字

用法：
    python3 src/check_source.py            # 校验 data/source/*.txt
    python3 src/check_source.py --fix      # 仅报告，不自动改（保留接口）
"""

from __future__ import annotations

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_deck import load_book  # noqa: E402

# 位置 → (最小字数, 最大字数, 说明)
PATTERN = [
    (7, 9, "三字對"),
    (5, 6, "五言"),
    (11, 13, "五言對"),
    (7, 9, "三字對"),
    (5, 6, "五言"),
    (11, 13, "五言對"),
    (15, 16, "七言對"),
    (11, 15, "四六長句"),
    (11, 15, "四六長句"),
]


# 作者用部件描述代替生僻字：`「艹項」`、`<禾夅>` 各代表 1 个字
COMPONENT = re.compile(r"「[^」]{1,4}」|<[^>]{1,4}>")


def normalize(line: str) -> str:
    """把部件描述折叠为单字占位，便于按字数核对句式。"""
    return COMPONENT.sub("〇", line)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--txt", default=None)
    args = ap.parse_args()

    _front, volumes, _back = load_book(args.txt)
    problems = []
    seg_count = 0

    for juan, rhymes in volumes.items():
        for rh in rhymes:
            for si, stanza in enumerate(rh["stanzas"], 1):
                seg_count += 1
                where = f"{juan}·{rh['name']}·第{si}段"
                if len(stanza) != len(PATTERN):
                    problems.append((where, f"段内 {len(stanza)} 行，应为 {len(PATTERN)} 行",
                                     " / ".join(stanza)))
                    continue
                for li, (line, (lo, hi, desc)) in enumerate(zip(stanza, PATTERN), 1):
                    n = len(normalize(line))
                    if not (lo <= n <= hi):
                        problems.append(
                            (where, f"第{li}行（{desc}）{n} 字，应在 {lo}–{hi} 字", line))

    # 作者自用的部件记字（非错误，单独列出备查）
    rare = []
    for juan, rhymes in volumes.items():
        for rh in rhymes:
            for si, stanza in enumerate(rh["stanzas"], 1):
                for li, line in enumerate(stanza, 1):
                    for m in COMPONENT.finditer(line):
                        rare.append((f"{juan}·{rh['name']}·第{si}段 第{li}行", m.group(0), line))

    print(f"校验 {seg_count} 段 / {seg_count * len(PATTERN)} 行")
    if rare:
        print(f"部件记字 {len(rare)} 处（作者原样，未改动）：")
        for where, mark, line in rare:
            print(f"  · {where}  {mark}")
            print(f"      {line}")
    if not problems:
        print("结构全部合规 ✓")
        return 0
    print(f"发现 {len(problems)} 处异常：")
    for where, why, line in problems:
        print(f"  ✗ {where}：{why}")
        print(f"      {line}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
