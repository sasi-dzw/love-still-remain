"""md.py —— 一个零依赖的小型 Markdown 渲染器。

只实现个人博客真正会用到的语法，避免引入第三方依赖：

* 标题（# ~ ####，自动生成锚点）
* 段落（单个换行转为 <br>，方便中文分行）
* 粗体 / 斜体 / 删除线 / 行内代码
* 围栏代码块（带语言标签与复制按钮）
* 有序、无序列表
* 引用块（可嵌套多段）
* 表格
* 分隔线
* 图片（自动包成 <figure> 并附图注）
* 链接、裸链接、少量内联 HTML
"""

from __future__ import annotations

import html
import re
from urllib.parse import urlsplit

_escape = html.escape


class Markdown:
    def __init__(self) -> None:
        self._tokens: list[str] = []
        self._ids: set[str] = set()

    # ------------------------------------------------------------------ 入口
    def render(self, text: str) -> str:
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        lines = text.split("\n")
        return "\n".join(self._blocks(lines)).strip()

    # ------------------------------------------------------------ 占位符机制
    def _keep(self, value: str) -> str:
        self._tokens.append(value)
        return f"\x00{len(self._tokens) - 1}\x00"

    def _restore(self, text: str) -> str:
        for _ in range(20):
            if "\x00" not in text:
                break
            new = re.sub(r"\x00(\d+)\x00", lambda m: self._tokens[int(m.group(1))], text)
            if new == text:
                break
            text = new
        return text

    # ---------------------------------------------------------------- 行内
    @staticmethod
    def _safe_url(url: str) -> str | None:
        """只放行 http(s)、mailto、相对路径；挡掉 javascript:、data: 等。"""
        value = url.strip()
        if not value:
            return None
        if value.startswith(("#", "/", "./", "../")):
            if value.startswith("/\\"):
                return None
            return value
        scheme = urlsplit(value).scheme.lower()
        if scheme in ("http", "https", "mailto"):
            return value
        if scheme:
            return None
        # 没有 scheme 的写法，但冒号出现在路径前（如 javascript:alert）
        if ":" in value.split("/", 1)[0]:
            return None
        return value

    def _inline(self, text: str) -> str:
        # 1. 行内代码（最先保护，内部不再解析任何语法）
        text = re.sub(
            r"`([^`]+)`",
            lambda m: self._keep("<code>" + _escape(m.group(1), quote=False) + "</code>"),
            text,
        )

        # 2. 图片
        def image(m: re.Match[str]) -> str:
            alt, src, caption = m.group(1), m.group(2), m.group(3) or m.group(1)
            safe = self._safe_url(src)
            if safe is None:
                return self._keep(_escape(alt))
            cap = f"<figcaption>{self._inline(caption)}</figcaption>" if caption else ""
            return self._keep(
                f'<figure><img src="{_escape(safe, quote=True)}" '
                f'alt="{_escape(alt, quote=True)}" loading="lazy" decoding="async">{cap}</figure>'
            )

        text = re.sub(
            r"!\[([^\]]*)\]\(((?:[^()\s]|\([^()]*\))+)(?:\s+\"([^\"]*)\")?\)",
            image,
            text,
        )

        # 3. 链接
        def link(m: re.Match[str]) -> str:
            label, href = m.group(1), m.group(2)
            safe = self._safe_url(href)
            if safe is None:
                return self._keep(self._inline(label))
            return self._keep(
                f'<a href="{_escape(safe, quote=True)}">{self._inline(label)}</a>'
            )

        text = re.sub(r"\[([^\]]+)\]\(((?:[^()\s]|\([^()]*\))+)\)", link, text)

        # 4. 裸链接
        text = re.sub(
            r"<((?:https?://|mailto:)[^>\s]+)>",
            lambda m: self._keep(
                f'<a href="{_escape(m.group(1), quote=True)}">{_escape(m.group(1))}</a>'
            ),
            text,
        )

        # 5. 转义剩余字符；原始 HTML 一律当文本显示，防止正文里的 payload 被执行
        text = _escape(text, quote=False)

        # 6. 强调
        text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
        text = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<em>\1</em>", text)
        text = re.sub(r"~~(.+?)~~", r"<del>\1</del>", text)

        return self._restore(text)

    # ---------------------------------------------------------------- 代码块
    def _code(self, code: str, lang: str) -> str:
        label = lang.strip() or "text"
        cls = f' class="language-{_escape(label, quote=True)}"' if lang.strip() else ""
        return (
            '<div class="code-block">'
            f'<div class="code-head"><span class="code-lang">{_escape(label)}</span>'
            '<button type="button" class="copy-btn" data-copy-btn>复制</button></div>'
            f"<pre><code{cls}>{_escape(code.rstrip(chr(10)), quote=False)}</code></pre>"
            "</div>"
        )

    # ---------------------------------------------------------------- 标题
    def _slug(self, text: str) -> str:
        s = text.lower().strip()
        s = re.sub(r"[^\w\u4e00-\u9fff \-]", "", s)
        s = re.sub(r"[\s]+", "-", s).strip("-") or "section"
        candidate, n = s, 2
        while candidate in self._ids:
            candidate = f"{s}-{n}"
            n += 1
        self._ids.add(candidate)
        return candidate

    def _heading(self, level: int, text: str) -> str:
        plain = re.sub(r"[*_`~\[\]()]", "", text).strip()
        slug = self._slug(plain)
        return f'<h{level} id="{_escape(slug, quote=True)}">{self._inline(text)}</h{level}>'

    # ---------------------------------------------------------------- 块级
    _HR = re.compile(r"^\s{0,3}([-*_])\s*(?:\1\s*){2,}$")
    _UL = re.compile(r"^\s{0,3}[-*+]\s+(.*)$")
    _OL = re.compile(r"^\s{0,3}\d{1,3}[.)]\s+(.*)$")
    _FENCE = re.compile(r"^\s{0,3}(`{3,}|~{3,})\s*([\w+#.\-]*)\s*$")
    _IMG_ONLY = re.compile(
        r"^!\[([^\]]*)\]\(((?:[^()\s]|\([^()]*\))+)(?:\s+\"([^\"]*)\")?\)$"
    )

    def _is_block_start(self, lines: list[str], i: int) -> bool:
        line = lines[i]
        if not line.strip():
            return True
        if self._FENCE.match(line) or self._HR.match(line):
            return True
        if re.match(r"^\s{0,3}#{1,4}\s+", line):
            return True
        if line.lstrip().startswith(">"):
            return True
        if self._UL.match(line) or self._OL.match(line):
            return True
        if "|" in line and i + 1 < len(lines) and self._is_table_sep(lines[i + 1]):
            return True
        return False

    @staticmethod
    def _is_table_sep(line: str) -> bool:
        s = line.strip()
        if not s or "|" not in s and "-" not in s:
            return False
        if "-" not in s:
            return False
        return bool(re.fullmatch(r"[|\-: ]+", s)) and s.count("-") >= 3

    def _blocks(self, lines: list[str]) -> list[str]:
        out: list[str] = []
        i, n = 0, len(lines)
        while i < n:
            line = lines[i]

            if not line.strip():
                i += 1
                continue

            # 围栏代码块
            m = self._FENCE.match(line)
            if m:
                fence, lang = m.group(1), m.group(2)
                i += 1
                buf: list[str] = []
                while i < n and not re.match(r"^\s{0,3}" + re.escape(fence[0]) + r"{" + str(len(fence)) + r",}\s*$", lines[i]):
                    buf.append(lines[i])
                    i += 1
                i += 1  # 跳过结束围栏
                out.append(self._code("\n".join(buf), lang))
                continue

            # 标题
            m = re.match(r"^\s{0,3}(#{1,4})\s+(.*)$", line)
            if m:
                out.append(self._heading(len(m.group(1)), m.group(2).strip()))
                i += 1
                continue

            # 分隔线
            if self._HR.match(line):
                out.append('<hr class="rule">')
                i += 1
                continue

            # 引用
            if line.lstrip().startswith(">"):
                buf = []
                while i < n:
                    cur = lines[i]
                    if cur.lstrip().startswith(">"):
                        buf.append(re.sub(r"^\s*>\s?", "", cur))
                        i += 1
                    elif buf and cur.strip():
                        buf.append(cur)  # 懒惰续行
                        i += 1
                    else:
                        break
                inner = "\n".join(self._blocks(buf))
                out.append(f'<blockquote><div class="quote-inner">{inner}</div></blockquote>')
                continue

            # 表格
            if "|" in line and i + 1 < n and self._is_table_sep(lines[i + 1]):
                header = [c.strip() for c in line.strip().strip("|").split("|")]
                aligns = []
                for cell in lines[i + 1].strip().strip("|").split("|"):
                    cell = cell.strip()
                    if cell.startswith(":") and cell.endswith(":"):
                        aligns.append("center")
                    elif cell.endswith(":"):
                        aligns.append("right")
                    else:
                        aligns.append("left")
                i += 2
                rows = []
                while i < n and "|" in lines[i] and lines[i].strip():
                    rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                    i += 1
                head = "".join(
                    f'<th style="text-align:{aligns[k] if k < len(aligns) else "left"}">{self._inline(c)}</th>'
                    for k, c in enumerate(header)
                )
                body = "".join(
                    "<tr>" + "".join(
                        f'<td style="text-align:{aligns[k] if k < len(aligns) else "left"}">{self._inline(c)}</td>'
                        for k, c in enumerate(row)
                    ) + "</tr>"
                    for row in rows
                )
                if body:
                    out.append(f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>")
                else:
                    out.append(f"<table><thead><tr>{head}</tr></thead></table>")
                continue

            # 列表
            m = self._UL.match(line) or self._OL.match(line)
            if m:
                ordered = bool(self._OL.match(line))
                items: list[str] = []
                while i < n:
                    cur = lines[i]
                    mm = self._OL.match(cur) if ordered else self._UL.match(cur)
                    if mm:
                        items.append(mm.group(1).strip())
                        i += 1
                    elif cur[:1] in (" ", "\t") and cur.strip() and items:
                        items[-1] += " " + cur.strip()
                        i += 1
                    else:
                        break
                tag = "ol" if ordered else "ul"
                lis = "".join(f"<li>{self._inline(it)}</li>" for it in items)
                out.append(f"<{tag}>{lis}</{tag}>")
                continue

            # 段落
            buf = []
            while i < n and lines[i].strip() and not self._is_block_start(lines, i):
                buf.append(lines[i].strip())
                i += 1
            # 只有一张图的段落 => 直接输出 figure
            if len(buf) == 1 and self._IMG_ONLY.match(buf[0]):
                out.append(self._inline(buf[0]))
            else:
                out.append("<p>" + "<br>\n".join(self._inline(x) for x in buf) + "</p>")

        return out
