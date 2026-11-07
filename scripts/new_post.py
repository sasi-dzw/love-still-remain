#!/usr/bin/env python3
"""新建一篇文章。

    python scripts/new_post.py "标题"
    python scripts/new_post.py "标题" --tags 生活,随笔
    python scripts/new_post.py "标题" --slug my-post --date 2026-11-08
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
POSTS = ROOT / "content" / "posts"
PALETTES = ["clay", "olive", "dusk", "sand", "ink"]

TEMPLATE = """---
title = {title}
date = {date}
tags = [{tags}]
deck = ""
cover = "{cover}"
---

正文从这里开始。

## 小标题

写点什么。
"""


def slugify(text: str) -> str:
    s = text.strip().lower()
    s = re.sub(r"[^\w\u4e00-\u9fff \-]", "", s)
    s = re.sub(r"\s+", "-", s).strip("-")
    return s


def main() -> None:
    parser = argparse.ArgumentParser(description="新建一篇文章")
    parser.add_argument("title", help="文章标题")
    parser.add_argument("--tags", default="随笔", help="逗号分隔，例如：生活,随笔")
    parser.add_argument("--slug", default="", help="自定义 URL，例如 my-post")
    parser.add_argument("--date", default="", help="日期 YYYY-MM-DD，默认今天")
    parser.add_argument("--cover", default="", choices=["", *PALETTES])
    args = parser.parse_args()

    day = dt.date.fromisoformat(args.date) if args.date else dt.date.today()
    slug = slugify(args.slug or args.title) or f"post-{day:%Y%m%d}"
    tags = [t.strip() for t in re.split(r"[,，]", args.tags) if t.strip()] or ["随笔"]
    cover = args.cover or PALETTES[sum(ord(c) for c in slug) % len(PALETTES)]

    POSTS.mkdir(parents=True, exist_ok=True)
    path = POSTS / f"{day.isoformat()}-{slug}.md"
    if path.exists():
        sys.exit(f"[错误] 文件已存在：{path}")

    content = TEMPLATE.format(
        title=json.dumps(args.title, ensure_ascii=False),
        date=day.isoformat(),
        tags=", ".join(json.dumps(t, ensure_ascii=False) for t in tags),
        cover=cover,
    )
    path.write_text(content, encoding="utf-8", newline="\n")

    print(f"✓ 已创建 {path.relative_to(ROOT)}")
    print("  接下来：填好 front matter 和正文，然后")
    print("    python build.py")
    print("    git add -A && git commit -m \"新文章\" && git push")


if __name__ == "__main__":
    main()
