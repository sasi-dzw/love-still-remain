#!/usr/bin/env python3
"""检查生成结果：内部链接、锚点、RSS 和 sitemap。

    python scripts/check.py
"""

from __future__ import annotations

import html.parser
import posixpath
import sys
import urllib.parse
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PUBLIC = ROOT / "public"
ORIGIN = "https://example.invalid"


class PageParser(html.parser.HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str]] = []
        self.ids: set[str] = set()
        self.title = ""
        self.h1 = 0
        self._in_title = False

    def handle_starttag(self, tag: str, attrs) -> None:
        data = dict(attrs)
        if data.get("id"):
            self.ids.add(data["id"])
        if tag == "title":
            self._in_title = True
        if tag == "h1":
            self.h1 += 1
        for attr in ("href", "src"):
            value = data.get(attr)
            if value:
                self.links.append((tag, value))

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title += data


def page_url(path: Path) -> str:
    rel = path.relative_to(PUBLIC).as_posix()
    if rel.endswith("index.html"):
        rel = rel[: -len("index.html")]
    return "/" + rel


def resolve(url: str, base: str) -> str | None:
    if url.startswith(("#", "mailto:", "tel:", "javascript:", "data:")):
        return None
    if url.startswith("//"):
        return None
    parts = urllib.parse.urlsplit(url)
    if parts.scheme in ("http", "https"):
        return None
    joined = urllib.parse.urljoin(ORIGIN + base, url)
    path = urllib.parse.urlsplit(joined).path
    return urllib.parse.unquote(path)


def main() -> None:
    if not PUBLIC.is_dir():
        sys.exit("先运行 python build.py")

    pages: dict[str, PageParser] = {}
    files = sorted(PUBLIC.rglob("*.html"))
    for path in files:
        parser = PageParser()
        parser.feed(path.read_text(encoding="utf-8"))
        pages[page_url(path)] = parser

    errors: list[str] = []
    warnings: list[str] = []
    checked = 0

    for url, parser in pages.items():
        if not parser.title.strip():
            errors.append(f"{url} 缺少 <title>")
        if parser.h1 != 1:
            warnings.append(f"{url} 有 {parser.h1} 个 <h1>")
        for tag, raw in parser.links:
            target = resolve(raw, url)
            if target is None:
                continue
            if target.endswith("/") or not posixpath.splitext(target)[1]:
                candidate = (target.rstrip("/") + "/index.html").lstrip("/")
            else:
                candidate = target.lstrip("/")
            fs_path = PUBLIC / candidate
            checked += 1
            if not fs_path.exists():
                errors.append(f"{url} → 链接失效 {raw}（找不到 {candidate}）")
                continue
            fragment = urllib.parse.urlsplit(
                urllib.parse.urljoin(ORIGIN + url, raw)
            ).fragment
            if fragment and tag == "a":
                target_url = target if target.endswith("/") else target
                target_parser = pages.get(target_url)
                if target_parser and urllib.parse.unquote(fragment) not in target_parser.ids:
                    errors.append(f"{url} → 锚点不存在 {raw}")

    for name in ("feed.xml", "sitemap.xml"):
        path = PUBLIC / name
        if not path.exists():
            errors.append(f"缺少 {name}")
            continue
        try:
            ET.parse(path)
        except ET.ParseError as exc:
            errors.append(f"{name} XML 解析失败：{exc}")

    print(f"检查了 {len(pages)} 个页面、{checked} 条内部链接")
    for warning in warnings:
        print(f"  ! {warning}")
    if errors:
        print(f"\n发现 {len(errors)} 个问题：")
        for error in errors[:40]:
            print(f"  ✗ {error}")
        sys.exit(1)
    print("✓ 没有发现失效链接或锚点")


if __name__ == "__main__":
    main()
