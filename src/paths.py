# -*- coding: utf-8 -*-
"""统一路径解析：所有脚本共用，避免各自 glob 相对路径。

无论从哪个工作目录调用，路径都以仓库根为基准。
"""
from __future__ import annotations

from pathlib import Path

# src/paths.py -> 仓库根
ROOT = Path(__file__).resolve().parents[1]

DOCS = ROOT / "docs"
SRC = ROOT / "src"
DATA = ROOT / "data"
SOURCE = DATA / "source"            # 抓取落地的原始文本
ANNOTATIONS = DATA / "annotations"  # 注譯内容（JSON）
RESEARCH = ROOT / "research"
REPORTS = RESEARCH / "考據報告"      # 考据报告
CACHE = RESEARCH / "原文緩存"        # 考据时抓取的原文缓存

BUILD = ROOT / "build"              # 构建产物
BUILD_PNG = BUILD / "png"           # 逐页截图
SAMPLES = BUILD / "样本"             # 样张


def source_txt() -> Path:
    """默认数据源：data/source 下的第一部 txt。"""
    files = sorted(SOURCE.glob("*.txt"))
    if not files:
        raise SystemExit(f"未找到数据源：{SOURCE}/*.txt")
    return files[0]


def ensure_dirs() -> None:
    for d in (SOURCE, ANNOTATIONS, BUILD, BUILD_PNG):
        d.mkdir(parents=True, exist_ok=True)
