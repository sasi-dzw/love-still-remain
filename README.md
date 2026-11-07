# love still remain

sasi 的个人博客：一个温暖纸张质感的静态小刊，零依赖，推送到 GitHub 就自动发布。

![首页预览](docs/preview.jpg)

## 它有什么

- **纯 Python 标准库**生成，不需要 Node、Ruby、数据库或任何第三方包
- 首页 / 文章 / 归档 / 标签 / 关于 / 404，全部静态 HTML
- 深色模式、响应式布局、阅读进度条、文章目录、代码复制按钮
- RSS、sitemap、robots.txt、JSON-LD、Open Graph
- 文章用 Markdown 写，图片放 `static/images/` 即可
- 所有站内链接都是相对路径：仓库名、自定义域名怎么换都不会挂

## 目录结构

```
love-still-remain/
├─ build.py              # 生成器：Markdown → public/
├─ md.py                 # 零依赖 Markdown 渲染
├─ blog.toml             # 站名、作者、简介、网址
├─ content/
│  ├─ posts/             # 文章（Markdown + TOML front matter）
│  └─ about.md           # 关于页
├─ theme/assets/         # style.css / app.js / theme.js
├─ static/               # 原样复制到站点根目录（放图片）
├─ public/               # 生成结果（已 gitignore）
├─ scripts/
│  ├─ new_post.py        # 新建文章
│  └─ check.py           # 检查失效链接和锚点
└─ .github/workflows/pages.yml
```

## 本地预览

需要 Python 3.11 或更高版本。

```bash
python build.py
python -m http.server 8000 -d public
```

然后打开 <http://localhost:8000>。

## 第一次发布到 GitHub

仓库已经在本地初始化并提交好了，只差一个远程地址。

### 1. 新建仓库

打开 <https://github.com/new>：

- Repository name 填 `love-still-remain`（想用别的名字也行，记得同步改第 4 步）
- 选 **Public**
- 不要勾选 “Add a README file”

### 2. 推送

在项目目录里执行（把 `你的用户名` 换成 GitHub 用户名）：

```bash
git remote add origin https://github.com/你的用户名/love-still-remain.git
git branch -M main
git push -u origin main
```

第一次推送会弹出浏览器让你登录 GitHub，授权即可。Windows 上用的是 Git Credential Manager，登录一次以后就不用再输密码。

### 3. 开启 GitHub Pages

打开仓库的 **Settings → Pages**，把 **Build and deployment → Source** 选成 **GitHub Actions**。

> 工作流里其实带了 `enablement: true`，通常第一次运行就能自动开启；如果 Action 报 “Get Pages site failed”，就是这一步没做，手动选一下然后 re-run 即可。

### 4. 访问并改网址

推送后打开仓库的 **Actions** 标签，等 `Deploy blog` 变成绿色，然后访问：

```
https://你的用户名.github.io/love-still-remain/
```

最后把 `blog.toml` 里的 `url` 改成这个地址（只影响 RSS、sitemap 和分享卡片里的绝对链接，站内导航不受影响），提交推送即可。

## 以后写文章

### 方式一：在网页上写（不用装任何东西）

1. 打开仓库的 `content/posts` 目录
2. 点 **Add file → Create new file**
3. 文件名写成 `2026-11-08-my-post.md`
4. 粘贴下面的模板，改掉标题和正文
5. 点 **Commit changes**
6. 等一两分钟，Actions 自动构建，刷新网站就能看到

```markdown
---
title = "文章标题"
date = 2026-11-08
tags = ["随笔"]
deck = "一句话摘要，会显示在列表和标题下面。"
cover = "clay"
---

正文从这里开始。

## 一个小标题

写点什么。
```

### 方式二：在本地写

```bash
python scripts/new_post.py "文章标题" --tags 生活,随笔
python build.py
```

然后提交推送：

```bash
git add -A
git commit -m "新文章：文章标题"
git push
```

## 文章格式

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `title` | 是 | 标题 |
| `date` | 是 | 日期，格式 `2026-11-08` |
| `tags` | 否 | 标签数组，例如 `["生活", "随笔"]` |
| `deck` | 否 | 摘要；不写会自动取正文第一段 |
| `cover` | 否 | 封面配色：`clay` / `olive` / `dusk` / `sand` / `ink` |
| `featured` | 否 | 设为 `true` 会成为首页封面文章 |
| `draft` | 否 | 设为 `true` 暂不发布 |

正文支持标题、粗体、斜体、列表、引用、表格、代码块、链接、图片、分隔线。文件开头的 `---` 和结尾的 `---` 之间就是上面的配置，不要删掉。

## 改成自己的

- **站名、署名、简介、题词**：`blog.toml`
- **配色**：`theme/assets/style.css` 顶部的 `:root`（纸色、墨色、强调色）
- **封面配色**：同文件里的 `.cover--clay` 等五组
- **导航和页面结构**：`build.py` 里的 `header_html` / `page_home`

## 图片

把图片放进 `static/images/`，然后在文章里写：

```markdown
![海边的傍晚](/images/sunset.jpg "傍晚六点")
```

构建时会自动把 `/images/...` 改写成适合当前页面层级的相对路径，所以仓库放在子路径下也不会裂图。

## 常见问题

**Action 第一次运行失败？**
大概率是 Pages 还没开。去 Settings → Pages 把 Source 选成 GitHub Actions，然后在 Actions 页面点 **Re-run all jobs**。

**访问 404？**
确认 Pages 的 Source 是 GitHub Actions，并且部署已经完成；地址要带结尾斜杠：`https://用户名.github.io/仓库名/`。

**页面没有样式？**
先强制刷新（Ctrl+F5）。静态资源带了内容哈希，正常不会缓存旧版本。

**RSS 里的链接是旧地址？**
改 `blog.toml` 的 `url` 后重新推送；GitHub Actions 部署时会用真实地址覆盖。

**想换主题或加评论？**
评论可以接 Giscus（基于 GitHub Discussions）；想用现成主题体系也可以整体迁到 Hexo/Hugo，Markdown 文章基本可以直接搬。

## 安全

这套站点的攻击面很小，但不是「绝对安全」，几件事说明白：

- **纯静态**：没有服务端、数据库、登录、表单、评论，SQLi / RCE / 越权这类漏洞没有载体
- **正文默认转义 HTML**：在 WP 里贴 `<script>`、`onerror` 之类只会显示成文字；`javascript:`、`data:` 链接会被过滤
- **全站 CSP**：只允许同源脚本和样式，禁止内联脚本、iframe、表单提交
- **没有第三方 JS / CSS / 字体**，不使用 Cookie（主题偏好存在 localStorage）

仍需自己注意：

- GitHub 账号是整条链路的关键，务必开双重验证（2FA / Passkey）
- 仓库是公开的：`draft = true` 只是不在网站显示，源码仍然可见；不要提交真实 flag、密钥或未公开题目的敏感内容
- 删除的文章仍留在 git 历史里
- GitHub Pages 不能自定义 HTTP 响应头，CSP 是通过 `<meta>` 实现的，`frame-ancestors`、HSTS 这类头用不了
- 不要上传来源不明的 SVG（同源托管，直接打开时可能执行脚本）
- Actions 用的是版本标签（`@v4`）而不是 commit SHA，供应链要求高的话可以自己改成 SHA 固定

## 版权

代码以 MIT 协议开源，见 `LICENSE`。文章内容 © 2026 sasi，未经许可请勿转载。
