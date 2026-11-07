#!/usr/bin/env python3
"""build.py —— 把 content/ 里的 Markdown 生成到 public/ 的静态博客。

    python build.py          # 生成站点
    python -m http.server -d public 8000   # 本地预览

不需要 Node、Ruby 或任何第三方库。部署时 GitHub Actions 会自动运行本文件。
"""

from __future__ import annotations

import json
import hashlib
import os
import re
import shutil
import sys
import tomllib
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from email.utils import format_datetime
from pathlib import Path
from urllib.parse import quote
from xml.sax.saxutils import escape as xesc

from md import Markdown

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent
CONTENT = ROOT / "content"
THEME = ROOT / "theme"
OUT = ROOT / "public"
TODAY = date.today()

PALETTES = ["clay", "olive", "dusk", "sand", "ink"]
ASSET_VER = hashlib.md5(
    (THEME / "assets" / "style.css").read_bytes()
    + (THEME / "assets" / "app.js").read_bytes()
).hexdigest()[:8]
SEASONS = {12: "冬", 1: "冬", 2: "冬", 3: "春", 4: "春", 5: "春",
           6: "夏", 7: "夏", 8: "夏", 9: "秋", 10: "秋", 11: "秋"}

CFG: dict = {}
SITE_URL = ""
POSTS: list["Post"] = []


# --------------------------------------------------------------------------- 工具
def esc(value: object) -> str:
    return html_escape(str(value))


def html_escape(value: str) -> str:
    return (value.replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def plain(html_text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html_text)
    return re.sub(r"\s+", " ", text).strip()


def slugify(value: str, fallback: str = "tag") -> str:
    s = value.lower().strip()
    s = re.sub(r"[^\w\u4e00-\u9fff \-]", "", s)
    s = re.sub(r"\s+", "-", s).strip("-")
    return s or fallback


def short_date(d: date) -> str:
    return f"{d.year}.{d.month:02d}.{d.day:02d}"


def long_date(d: date) -> str:
    return f"{d.year} 年 {d.month} 月 {d.day} 日"


def season(d: date) -> str:
    return SEASONS[d.month]


def abs_url(path: str = "") -> str:
    if not SITE_URL:
        return ""
    if not path:
        return SITE_URL + "/"
    return f"{SITE_URL}/{path.lstrip('/')}"


def encoded(path: str = "") -> str:
    """把中文路径按 RFC 3986 编码，用于 RSS / sitemap / canonical。"""
    raw = abs_url(path)
    return "".join(ch if ord(ch) < 128 else quote(ch) for ch in raw)


def reading_minutes(html_body: str) -> int:
    text = plain(html_body)
    cjk = len(re.findall(r"[\u4e00-\u9fff]", text))
    words = len(re.findall(r"[A-Za-z0-9]+", text))
    minutes = round(cjk / 380 + words / 220)
    return max(1, minutes)


def rebase(html_text: str, root: str) -> str:
    """把正文里以 / 开头的图片、链接改写成相对路径，兼容项目页子目录。"""
    if not root:
        return html_text
    return re.sub(r'(src|href)="/(?!/)', rf'\1="{root}', html_text)


def initial_of(title: str) -> str:
    for ch in title:
        if ch.strip() and ch not in "《“\"'（(":
            return ch
    return "·"


def write(rel: str, text: str) -> Path:
    path = OUT / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


# --------------------------------------------------------------------------- 内容
@dataclass
class Post:
    slug: str
    title: str
    date: date
    tags: list[str]
    deck: str
    cover: str
    body: str
    toc: list[dict]
    minutes: int
    featured: bool = False
    draft: bool = False
    source: str = ""

    @property
    def url(self) -> str:
        return f"posts/{self.slug}/"

    @property
    def tag(self) -> str:
        return self.tags[0] if self.tags else "随笔"


def load_config() -> dict:
    with (ROOT / "blog.toml").open("rb") as fh:
        cfg = tomllib.load(fh)
    cfg.setdefault("title", "我的博客")
    cfg.setdefault("display", cfg["title"])
    cfg.setdefault("tagline", "")
    cfg.setdefault("description", "")
    cfg.setdefault("author", "")
    cfg.setdefault("role", "写字的人")
    cfg.setdefault("bio", "")
    cfg.setdefault("start_year", TODAY.year)
    cfg.setdefault("url", "")
    cfg.setdefault("email", "")
    cfg.setdefault("github", "")
    cfg.setdefault("quote", "")
    cfg.setdefault("quote_by", "")
    return cfg


def parse_post(path: Path) -> Post:
    raw = path.read_text(encoding="utf-8")
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", raw, re.S)
    if not match:
        raise SystemExit(f"[错误] {path.name} 缺少 --- 包裹的 front matter")
    try:
        meta = tomllib.loads(match.group(1))
    except tomllib.TOMLDecodeError as exc:
        raise SystemExit(f"[错误] {path.name} 的 front matter 不是合法 TOML：{exc}")

    body_src = match.group(2)
    if not str(meta.get("date", "")).strip():
        raise SystemExit(f"[错误] {path.name} 缺少 date")

    raw_date = meta["date"]
    if isinstance(raw_date, str):
        post_date = date.fromisoformat(raw_date)
    elif isinstance(raw_date, datetime):
        post_date = raw_date.date()
    else:
        post_date = raw_date

    stem = path.stem
    stem = re.sub(r"^\d{4}-\d{2}-\d{2}-", "", stem)
    slug = slugify(str(meta.get("slug") or stem), fallback="post")

    renderer = Markdown()
    body = renderer.render(body_src)
    toc = [
        {"level": int(m.group(1)), "id": m.group(2),
         "text": plain(m.group(3))}
        for m in re.finditer(r'<h([23]) id="([^"]+)">(.*?)</h\1>', body, re.S)
    ]
    tags = meta.get("tags") or []
    if isinstance(tags, str):
        tags = [tags]

    deck = str(meta.get("deck") or "").strip()
    if not deck:
        first_p = re.search(r"<p>(.*?)</p>", body, re.S)
        deck = plain(first_p.group(1))[:70] if first_p else ""

    cover = str(meta.get("cover") or "").strip()
    if cover not in PALETTES:
        cover = PALETTES[sum(ord(c) for c in slug) % len(PALETTES)]

    return Post(
        slug=slug,
        title=str(meta.get("title") or stem),
        date=post_date,
        tags=[str(t) for t in tags],
        deck=deck,
        cover=cover,
        body=body,
        toc=toc,
        minutes=reading_minutes(body),
        featured=bool(meta.get("featured", False)),
        draft=bool(meta.get("draft", False)),
        source=path.name,
    )


def load_posts() -> list[Post]:
    posts = [parse_post(p) for p in sorted((CONTENT / "posts").glob("*.md"))]
    if os.environ.get("BUILD_DRAFTS") != "1":
        posts = [p for p in posts if not p.draft]
    posts.sort(key=lambda p: (p.date, p.slug), reverse=True)
    seen: dict[str, int] = {}
    for post in posts:
        seen[post.slug] = seen.get(post.slug, 0) + 1
        if seen[post.slug] > 1:
            raise SystemExit(f"[错误] 文章 slug 重复：{post.slug}（{post.source}）")
    return posts


def tag_counts() -> list[tuple[str, int]]:
    counts: dict[str, int] = {}
    for post in POSTS:
        for tag in post.tags:
            counts[tag] = counts.get(tag, 0) + 1
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))


# --------------------------------------------------------------------------- 组件
FAVICON_SVG = (
    "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'>"
    "<rect width='64' height='64' rx='13' fill='#b04a2f'/>"
    "<text x='32' y='46' font-family='Georgia,serif' font-size='38' "
    "fill='#f8f1e6' text-anchor='middle'>L</text></svg>"
)
FAVICON = "data:image/svg+xml," + quote(FAVICON_SVG, safe="")

THEME_SCRIPT = (
    "<script>(()=>{const r=document.documentElement;r.classList.add('js');"
    "try{const q=new URLSearchParams(location.search).get('theme');"
    "const s=localStorage.getItem('theme');"
    "const d=matchMedia('(prefers-color-scheme: dark)').matches;"
    "r.dataset.theme=q||s||(d?'dark':'light');}catch(e){}})();</script>"
)


def nav_html(root: str, active: str) -> str:
    items = [("archive/", "归档", "archive"), ("tags/", "标签", "tags"),
             ("about/", "关于", "about")]
    parts = []
    for href, label, key in items:
        current = ' aria-current="page"' if key == active else ""
        parts.append(f'<a href="{root}{href}"{current}>{label}</a>')
    parts.append(f'<a class="nav-rss" href="{root}feed.xml">RSS</a>')
    return "\n      ".join(parts)


def header_html(root: str, active: str = "") -> str:
    home = root or "./"
    return f"""<header class="site-head">
  <div class="shell head-inner">
    <a class="brand" href="{home}">
      <span class="brand-title">{esc(CFG['title'])}</span>
      <span class="brand-kicker">Personal Journal</span>
    </a>
    <nav class="site-nav" id="site-nav" aria-label="主导航">
      {nav_html(root, active)}
    </nav>
    <div class="head-tools">
      <button class="theme-toggle" type="button" aria-label="切换深浅色模式" title="切换深浅色模式">
        <span class="icon-moon" aria-hidden="true">☾</span><span class="icon-sun" aria-hidden="true">☀</span>
      </button>
      <button class="nav-toggle" type="button" aria-expanded="false" aria-controls="site-nav" aria-label="打开导航菜单">
        <span></span><span></span>
      </button>
    </div>
  </div>
</header>"""


def footer_html(root: str, depth: int) -> str:
    year = TODAY.year
    span = f"{CFG['start_year']}–{year}" if year != CFG["start_year"] else str(year)
    return f"""<footer class="site-foot">
  <div class="shell foot-inner">
    <div class="foot-brand">
      <span class="foot-title">{esc(CFG['title'])}</span>
      <p class="foot-tagline">{esc(CFG['tagline'])}</p>
    </div>
    <nav class="foot-nav" aria-label="页脚导航">
      <a href="{root}archive/">归档</a>
      <a href="{root}tags/">标签</a>
      <a href="{root}about/">关于</a>
      <a href="{root}feed.xml">RSS</a>
    </nav>
    <p class="foot-note">© {span} {esc(CFG['author'])}<br>由 GitHub Pages 托管 · 用 Python 生成</p>
  </div>
</footer>"""


def layout(*, title: str, description: str, depth: int, body: str,
           path: str = "", body_class: str = "", head_extra: str = "",
           nav: str = "", og_type: str = "website") -> str:
    root = "../" * depth
    canonical = encoded(path)
    canonical_tag = f'<link rel="canonical" href="{canonical}">' if canonical else ""
    og_url = f'<meta property="og:url" content="{canonical}">' if canonical else ""
    og = f"""<meta property="og:site_name" content="{esc(CFG['title'])}">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(description)}">
<meta property="og:type" content="{og_type}">
{og_url}
<meta name="twitter:card" content="summary">"""
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light dark">
<title>{esc(title)}</title>
<meta name="description" content="{esc(description)}">
<meta name="author" content="{esc(CFG['author'])}">
<meta name="theme-color" content="#f6efe4" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#171310" media="(prefers-color-scheme: dark)">
{canonical_tag}
{og}
<link rel="stylesheet" href="{root}assets/style.css?v={ASSET_VER}">
<link rel="alternate" type="application/rss+xml" title="{esc(CFG['title'])} · RSS" href="{root}feed.xml">
<link rel="icon" href="{FAVICON}">
{THEME_SCRIPT}
{head_extra}
</head>
<body class="{body_class}">
<a class="skip-link" href="#main">跳到正文</a>
{header_html(root, nav)}
{body}
{footer_html(root, depth)}
<script src="{root}assets/app.js?v={ASSET_VER}" defer></script>
</body>
</html>
"""


def cover_html(post: "Post", extra: str = "") -> str:
    return (f'<div class="cover cover--{post.cover} {extra}" '
            f'data-initial="{esc(initial_of(post.title))}" aria-hidden="true">'
            '<span class="ring"></span></div>')


def meta_html(post: "Post") -> str:
    return (f'<p class="meta"><time datetime="{post.date.isoformat()}">'
            f'{short_date(post.date)}</time><span class="dot">·</span>'
            f'{post.minutes} 分钟阅读</p>')


def tag_links(post: "Post", root: str) -> str:
    return " ".join(
        f'<a class="tag" href="{root}tags/{slugify(t)}/">{esc(t)}</a>'
        for t in post.tags
    )


# --------------------------------------------------------------------------- 首页
def feature_html(post: "Post") -> str:
    return f"""<section class="feature shell reveal">
  <a class="feature-visual" href="{post.url}" tabindex="-1" aria-hidden="true">
    {cover_html(post, "cover--lg")}
  </a>
  <div class="feature-body">
    <p class="kicker">封面文章<span class="slash">/</span>{esc(post.tag)}</p>
    <h2 class="feature-title"><a href="{post.url}">{esc(post.title)}</a></h2>
    <p class="feature-deck">{esc(post.deck)}</p>
    {meta_html(post)}
    <a class="more" href="{post.url}"><span>继续阅读</span><span class="arrow">→</span></a>
  </div>
</section>"""


def card_html(post: "Post") -> str:
    return f"""<article class="card reveal">
  <a class="card-visual" href="{post.url}" tabindex="-1" aria-hidden="true">
    {cover_html(post, "cover--sm")}
  </a>
  <div class="card-body">
    <p class="kicker">{esc(post.tag)}</p>
    <h3 class="card-title"><a href="{post.url}">{esc(post.title)}</a></h3>
    <p class="card-deck">{esc(post.deck)}</p>
    {meta_html(post)}
  </div>
</article>"""


def page_home() -> str:
    featured = next((p for p in POSTS if p.featured), POSTS[0])
    rest = [p for p in POSTS if p is not featured][:4]
    counts = tag_counts()[:10]
    chips = "".join(
        f'<a class="chip" href="tags/{slugify(t)}/">{esc(t)}<span>{n}</span></a>'
        for t, n in counts
    )
    grid = ""
    if rest:
        grid = f"""<section class="section shell">
  <div class="section-head">
    <h2 class="section-title"><span class="section-no">02</span>近期文章</h2>
    <a class="section-link" href="archive/">全部归档 <span class="arrow">→</span></a>
  </div>
  <div class="post-grid">
    {''.join(card_html(p) for p in rest)}
  </div>
</section>"""

    quote_band = ""
    if CFG["quote"]:
        quote_band = f"""<section class="quote-band reveal">
  <div class="shell">
    <blockquote>“{esc(CFG['quote'])}”</blockquote>
    <cite>— {esc(CFG['quote_by'])}</cite>
  </div>
</section>"""

    body = f"""<main id="main">
  <section class="masthead shell">
    <p class="eyebrow">个人小刊<span class="dot">·</span>{TODAY.year} 年 {season(TODAY)}</p>
    <h1 class="display">{CFG['display']}</h1>
    <p class="tagline">{esc(CFG['tagline'])}</p>
    <p class="lede">{esc(CFG['description'])}</p>
    <div class="ornament" aria-hidden="true"><span></span><b>◆</b><span></span></div>
  </section>

  {feature_html(featured)}

  {grid}

  {quote_band}

  <section class="section shell">
    <div class="section-head">
      <h2 class="section-title"><span class="section-no">03</span>旧页索引</h2>
      <a class="section-link" href="tags/">按标签浏览 <span class="arrow">→</span></a>
    </div>
    <div class="tag-cloud">{chips}</div>
  </section>

  <section class="about-band shell reveal">
    <div class="about-card">
      <div class="monogram" aria-hidden="true">{esc(CFG['author'][:1].upper() or '·')}</div>
      <p class="kicker">关于编者</p>
      <h2>{esc(CFG['author'])}</h2>
      <p>{esc(CFG['bio'])}</p>
      <a class="more" href="about/"><span>了解更多</span><span class="arrow">→</span></a>
    </div>
    <div class="subscribe-card">
      <p class="kicker">订阅</p>
      <h2>把新文章收进阅读器</h2>
      <p>本站提供 RSS：没有邮件，没有追踪，也没有算法。</p>
      <a class="button" href="feed.xml">订阅 RSS <span>↗</span></a>
      <p class="fineprint">或者，偶尔来看看。</p>
    </div>
  </section>
</main>"""
    return layout(
        title=f"{CFG['title']} · {CFG['tagline']}",
        description=CFG["description"],
        depth=0,
        body=body,
        path="",
        body_class="page-home",
        head_extra=json_ld({
            "@context": "https://schema.org",
            "@type": "WebSite",
            "name": CFG["title"],
            "description": CFG["description"],
            "url": abs_url(),
            "inLanguage": "zh-CN",
        }),
    )


# --------------------------------------------------------------------------- 文章页
def toc_html(post: "Post") -> str:
    if len([t for t in post.toc if t["level"] == 2]) < 2:
        return ""
    items = "".join(
        f'<li class="toc-l{t["level"]}"><a href="#{t["id"]}">{esc(t["text"])}</a></li>'
        for t in post.toc
    )
    return f"""<aside class="toc" aria-label="文章目录">
  <p class="toc-title">目录</p>
  <ol class="toc-list">{items}</ol>
</aside>"""


def pager_html(post: "Post") -> str:
    idx = POSTS.index(post)
    newer = POSTS[idx - 1] if idx > 0 else None
    older = POSTS[idx + 1] if idx + 1 < len(POSTS) else None
    if not newer and not older:
        return ""
    parts = []
    if newer:
        parts.append(f"""<a class="pager-link" href="../../{newer.url}">
  <span class="pager-label">← 前一篇</span>
  <span class="pager-title">{esc(newer.title)}</span>
</a>""")
    else:
        parts.append('<span class="pager-spacer"></span>')
    if older:
        parts.append(f"""<a class="pager-link pager-next" href="../../{older.url}">
  <span class="pager-label">后一篇 →</span>
  <span class="pager-title">{esc(older.title)}</span>
</a>""")
    return f'<nav class="pager" aria-label="文章导航">{"".join(parts)}</nav>'


def page_post(post: "Post") -> str:
    toc = toc_html(post)
    grid_class = "article-body shell" if toc else "article-body shell no-toc"
    ld = json_ld({
        "@context": "https://schema.org",
        "@type": "BlogPosting",
        "headline": post.title,
        "description": post.deck,
        "datePublished": post.date.isoformat(),
        "dateModified": post.date.isoformat(),
        "author": {"@type": "Person", "name": CFG["author"]},
        "publisher": {"@type": "Person", "name": CFG["author"]},
        "mainEntityOfPage": abs_url(post.url),
        "inLanguage": "zh-CN",
    })
    article_html = rebase(post.body, "../../")
    body = f"""<div class="progress" aria-hidden="true"><span id="progress-bar"></span></div>
<main id="main">
  <article class="post">
    <header class="article-head narrow">
      <p class="kicker"><a href="../../tags/{slugify(post.tag)}/">{esc(post.tag)}</a><span class="slash">/</span>{post.minutes} 分钟阅读</p>
      <h1 class="article-title">{esc(post.title)}</h1>
      <p class="article-deck">{esc(post.deck)}</p>
      <div class="article-meta">
        <span>文 / {esc(CFG['author'])}</span>
        <span class="dot">·</span>
        <time datetime="{post.date.isoformat()}">{long_date(post.date)}</time>
      </div>
    </header>

    <div class="article-cover" aria-hidden="true">{cover_html(post, "cover--wide")}</div>

    <div class="{grid_class}">
      <div class="prose">
        {article_html}
        <div class="end-mark" aria-hidden="true">◆</div>
      </div>
      {toc}
    </div>

    <footer class="article-foot narrow">
      {pager_html(post)}
      <p class="article-cta">谢谢你读到这里。<a href="../../archive/">去翻翻旧页 <span class="arrow">→</span></a></p>
    </footer>
  </article>
</main>"""
    return layout(
        title=f"{post.title} · {CFG['title']}",
        description=post.deck,
        depth=2,
        body=body,
        path=post.url,
        body_class="page-post",
        nav="",
        og_type="article",
        head_extra=(
            f'<meta property="article:published_time" content="{post.date.isoformat()}">'
            + "".join(f'<meta property="article:tag" content="{esc(t)}">' for t in post.tags)
            + ld
        ),
    )


# --------------------------------------------------------------------------- 归档
def archive_rows(posts: list["Post"], root: str = "") -> str:
    rows = []
    for post in posts:
        tags = "".join(f'<span>{esc(t)}</span>' for t in post.tags)
        rows.append(f"""<a class="row" href="{root}{post.url}">
  <time class="row-date" datetime="{post.date.isoformat()}">{post.date.month:02d}.{post.date.day:02d}</time>
  <span class="row-title">{esc(post.title)}</span>
  <span class="row-tags">{tags}</span>
</a>""")
    return "\n".join(rows)


def page_archive() -> str:
    years: dict[int, list["Post"]] = {}
    for post in POSTS:
        years.setdefault(post.date.year, []).append(post)
    blocks = []
    for year in sorted(years, reverse=True):
        blocks.append(f"""<section class="year">
  <h2 class="year-num" aria-label="{year} 年">{year}</h2>
  <div class="year-list">
    {archive_rows(years[year], root='../')}
  </div>
</section>""")
    body = f"""<main id="main" class="page">
  <header class="page-head shell">
    <p class="eyebrow">Archive</p>
    <h1>归档</h1>
    <p class="page-lede">共 {len(POSTS)} 篇，按年份排列。也可以<a href="../tags/">按标签浏览</a>。</p>
  </header>
  <div class="shell archive">
    {''.join(blocks)}
  </div>
</main>"""
    return layout(
        title=f"归档 · {CFG['title']}",
        description=f"{CFG['title']} 的全部文章归档。",
        depth=1,
        body=body,
        path="archive/",
        body_class="page-archive",
        nav="archive",
    )


# --------------------------------------------------------------------------- 标签
def page_tags() -> str:
    counts = tag_counts()
    chips = "".join(
        f'<a class="tag-chip" href="{slugify(t)}/"><span class="tag-name">{esc(t)}</span>'
        f'<span class="tag-count">{n}</span></a>'
        for t, n in counts
    )
    body = f"""<main id="main" class="page">
  <header class="page-head shell">
    <p class="eyebrow">Tags</p>
    <h1>标签</h1>
    <p class="page-lede">一共 {len(counts)} 个标签，{len(POSTS)} 篇文章。挑一个顺眼的翻翻。</p>
  </header>
  <div class="shell">
    <div class="tag-wall">{chips}</div>
  </div>
</main>"""
    return layout(
        title=f"标签 · {CFG['title']}",
        description=f"{CFG['title']} 的全部标签。",
        depth=1,
        body=body,
        path="tags/",
        body_class="page-tags",
        nav="tags",
    )


def page_tag(tag: str) -> str:
    posts = [p for p in POSTS if tag in p.tags]
    body = f"""<main id="main" class="page">
  <header class="page-head shell">
    <p class="eyebrow">Tag</p>
    <h1>标签：{esc(tag)}</h1>
    <p class="page-lede">{len(posts)} 篇文章。<a href="../">← 回到全部标签</a></p>
  </header>
  <div class="shell">
    <div class="year-list tag-posts">
      {archive_rows(posts, root='../../')}
    </div>
  </div>
</main>"""
    return layout(
        title=f"{tag} · {CFG['title']}",
        description=f"标签「{tag}」下的全部文章。",
        depth=2,
        body=body,
        path=f"tags/{slugify(tag)}/",
        body_class="page-tag",
        nav="tags",
    )


# --------------------------------------------------------------------------- 关于
def page_about() -> str:
    raw = (CONTENT / "about.md").read_text(encoding="utf-8")
    raw = re.sub(r"^---\s*\n.*?\n---\s*\n?", "", raw, flags=re.S)
    about = rebase(Markdown().render(raw), "../")
    links = []
    if CFG["email"]:
        links.append(f'<a href="mailto:{esc(CFG["email"])}">写信</a>')
    if CFG["github"]:
        links.append(f'<a href="{esc(CFG["github"])}" rel="me">GitHub</a>')
    links.append('<a href="../feed.xml">RSS</a>')
    link_html = '<span class="dot">·</span>'.join(links)
    body = f"""<main id="main" class="page">
  <header class="page-head shell">
    <p class="eyebrow">About</p>
    <h1>关于</h1>
  </header>
  <div class="shell about-layout">
    <aside class="about-side">
      <div class="portrait" aria-hidden="true"><span>{esc(CFG['author'][:1].lower() or '·')}</span></div>
      <p class="about-name">{esc(CFG['author'])}</p>
      <p class="about-role">{esc(CFG['role'])}</p>
      <p class="about-links">{link_html}</p>
    </aside>
    <div class="prose about-prose">
      {about}
    </div>
  </div>
</main>"""
    return layout(
        title=f"关于 · {CFG['title']}",
        description=f"关于 {CFG['author']} 和这本小刊。",
        depth=1,
        body=body,
        path="about/",
        body_class="page-about",
        nav="about",
    )


# --------------------------------------------------------------------------- 404
def page_404() -> str:
    body = """<main id="main" class="page not-found">
  <div class="shell">
    <p class="eyebrow">Lost</p>
    <h1 class="nf-code">404</h1>
    <p class="nf-text">这一页大概被折进了别的地方。<br>不如回到开头，重新翻一页。</p>
    <a class="button" href="./">回到首页 <span>→</span></a>
  </div>
</main>"""
    return layout(
        title="页面不存在 · " + CFG["title"],
        description="页面不存在。",
        depth=0,
        body=body,
        body_class="page-404",
    )


# --------------------------------------------------------------------------- 订阅
def json_ld(data: dict) -> str:
    return ('<script type="application/ld+json">'
            + json.dumps(data, ensure_ascii=False)
            + "</script>")


def feed_xml() -> str:
    items = []
    for post in POSTS:
        pub = format_datetime(datetime.combine(post.date, time(8, 0), tzinfo=timezone.utc))
        items.append(f"""<item>
  <title>{xesc(post.title)}</title>
  <link>{xesc(encoded(post.url))}</link>
  <guid isPermaLink="true">{xesc(encoded(post.url))}</guid>
  <pubDate>{pub}</pubDate>
  <description>{xesc(post.deck)}</description>
</item>""")
    latest = POSTS[0].date if POSTS else TODAY
    built = format_datetime(datetime.combine(latest, time(8, 0), tzinfo=timezone.utc))
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
<channel>
  <title>{xesc(CFG['title'])}</title>
  <link>{xesc(encoded())}</link>
  <description>{xesc(CFG['description'])}</description>
  <language>zh-CN</language>
  <lastBuildDate>{built}</lastBuildDate>
  <atom:link href="{xesc(encoded('feed.xml'))}" rel="self" type="application/rss+xml"/>
  {''.join(items)}
</channel>
</rss>
"""


def sitemap_xml() -> str:
    urls = [("", TODAY), ("archive/", TODAY), ("tags/", TODAY), ("about/", TODAY)]
    urls += [(p.url, p.date) for p in POSTS]
    urls += [(f"tags/{slugify(t)}/", TODAY) for t, _ in tag_counts()]
    entries = "".join(
        f"<url><loc>{xesc(encoded(path))}</loc>"
        f"<lastmod>{day.isoformat()}</lastmod></url>"
        for path, day in urls
    )
    return ('<?xml version="1.0" encoding="UTF-8"?>'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            f"{entries}</urlset>")


def robots_txt() -> str:
    lines = ["User-agent: *", "Allow: /"]
    if SITE_URL:
        lines += ["", f"Sitemap: {abs_url('sitemap.xml')}"]
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- 主流程
def main() -> None:
    global CFG, SITE_URL, POSTS
    CFG = load_config()
    SITE_URL = (os.environ.get("SITE_URL") or CFG.get("url") or "").rstrip("/")
    POSTS = load_posts()
    if not POSTS:
        raise SystemExit("[错误] content/posts 里还没有文章")

    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    shutil.copytree(THEME / "assets", OUT / "assets")
    if (ROOT / "static").is_dir():
        shutil.copytree(ROOT / "static", OUT, dirs_exist_ok=True)
    (OUT / ".nojekyll").write_text("", encoding="utf-8")

    write("index.html", page_home())
    write("archive/index.html", page_archive())
    write("tags/index.html", page_tags())
    write("about/index.html", page_about())
    write("404.html", page_404())
    for post in POSTS:
        write(f"posts/{post.slug}/index.html", page_post(post))
    for tag, _ in tag_counts():
        write(f"tags/{slugify(tag)}/index.html", page_tag(tag))

    write("feed.xml", feed_xml())
    write("sitemap.xml", sitemap_xml())
    write("robots.txt", robots_txt())

    pages = 5 + len(POSTS) + len(tag_counts())
    print(f"✓ 已生成 {pages} 个页面，{len(POSTS)} 篇文章")
    print(f"  输出目录：{OUT}")
    if SITE_URL:
        print(f"  站点地址：{SITE_URL}/")


if __name__ == "__main__":
    main()
