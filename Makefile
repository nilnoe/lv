# 《聲律發蒙》幻灯片 · 构建入口
#
#   make            出五卷原文
#   make check      全量质检：源文本体例 + 排版（交付前必跑）
#   make annot      出注譯样张
#   make slots      带注解占位页的版本
#   make sample     逐页截图
#   make clean      清理产物

PY      := python3
DECK    := build/卷一.html build/卷二.html build/卷三.html build/卷四.html build/卷五.html
ANNOT   := data/annotations/1-一東.json

.PHONY: all deck slots annot check sample clean help

all: deck

help:
	@grep -E '^#   make' Makefile | sed 's/^#   //'

deck:
	$(PY) src/build_deck.py

slots:
	$(PY) src/build_deck.py --slots

annot:
	$(PY) src/make_annot.py $(ANNOT) --out build/样本/一東注譯四頁.html

check:
	$(PY) src/check_source.py
	$(PY) src/check_deck.py

sample: deck
	$(PY) -c "import sys; sys.path.insert(0,'src'); \
from render_check import screenshot_slides; \
screenshot_slides('build/卷一.html','build/png/卷一'); \
screenshot_slides('build/卷四.html','build/png/卷四')"

clean:
	rm -rf build
	find . -name __pycache__ -type d -exec rm -rf {} +
