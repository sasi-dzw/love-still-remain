/* app.js —— 主题切换、移动端导航、阅读进度、代码复制、滚动出现 */
(() => {
  const html = document.documentElement;
  const header = document.querySelector(".site-head");
  const navToggle = document.querySelector(".nav-toggle");
  const themeToggle = document.querySelector(".theme-toggle");

  /* --------------------------------------------------------------- 主题切换 */
  const label = (theme) =>
    theme === "dark" ? "切换到浅色模式" : "切换到深色模式";

  if (themeToggle) {
    themeToggle.setAttribute("aria-label", label(html.dataset.theme));
    themeToggle.addEventListener("click", () => {
      const next = html.dataset.theme === "dark" ? "light" : "dark";
      html.dataset.theme = next;
      try {
        localStorage.setItem("theme", next);
      } catch (err) {
        /* 隐私模式下存不了，忽略 */
      }
      themeToggle.setAttribute("aria-label", label(next));
    });
  }

  /* --------------------------------------------------------------- 移动导航 */
  if (navToggle && header) {
    const close = () => {
      header.classList.remove("nav-open");
      navToggle.setAttribute("aria-expanded", "false");
    };
    navToggle.addEventListener("click", () => {
      const open = header.classList.toggle("nav-open");
      navToggle.setAttribute("aria-expanded", String(open));
    });
    header.querySelectorAll(".site-nav a").forEach((a) => {
      a.addEventListener("click", close);
    });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") close();
    });
    document.addEventListener("click", (e) => {
      if (!header.contains(e.target)) close();
    });
  }

  /* -------------------------------------------------- 阅读进度 + 目录高亮 */
  const bar = document.getElementById("progress-bar");
  const headings = [...document.querySelectorAll(".prose h2[id], .prose h3[id]")];
  const tocLinks = new Map(
    [...document.querySelectorAll(".toc a")].map((a) => [
      decodeURIComponent(a.getAttribute("href").slice(1)),
      a,
    ])
  );

  const onScroll = () => {
    if (bar) {
      const max = document.documentElement.scrollHeight - window.innerHeight;
      bar.style.transform = `scaleX(${max > 0 ? Math.min(1, window.scrollY / max) : 0})`;
    }
    if (tocLinks.size && headings.length) {
      let current = headings[0].id;
      for (const heading of headings) {
        if (heading.getBoundingClientRect().top <= 140) current = heading.id;
        else break;
      }
      tocLinks.forEach((link, id) => {
        link.classList.toggle("is-active", id === current);
      });
    }
  };

  let ticking = false;
  window.addEventListener(
    "scroll",
    () => {
      if (ticking) return;
      ticking = true;
      requestAnimationFrame(() => {
        onScroll();
        ticking = false;
      });
    },
    { passive: true }
  );
  onScroll();

  /* --------------------------------------------------------------- 代码复制 */
  document.querySelectorAll("[data-copy-btn]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const block = btn.closest(".code-block");
      const code = block && block.querySelector("code");
      if (!code) return;
      const text = code.textContent;
      try {
        await navigator.clipboard.writeText(text);
      } catch (err) {
        const ta = document.createElement("textarea");
        ta.value = text;
        ta.setAttribute("readonly", "");
        ta.style.cssText = "position:fixed;opacity:0;left:-9999px";
        document.body.appendChild(ta);
        ta.select();
        try {
          document.execCommand("copy");
        } catch (e) {
          /* 复制失败就保持原样 */
        }
        ta.remove();
      }
      const original = btn.textContent;
      btn.textContent = "已复制";
      btn.disabled = true;
      setTimeout(() => {
        btn.textContent = original;
        btn.disabled = false;
      }, 1600);
    });
  });

  /* --------------------------------------------------------------- 滚动出现 */
  const reveals = document.querySelectorAll(".reveal");
  if (reveals.length) {
    if ("IntersectionObserver" in window) {
      const io = new IntersectionObserver(
        (entries) => {
          entries.forEach((entry) => {
            if (entry.isIntersecting) {
              entry.target.classList.add("is-visible");
              io.unobserve(entry.target);
            }
          });
        },
        { rootMargin: "0px 0px -6% 0px", threshold: 0.04 }
      );
      reveals.forEach((el) => io.observe(el));
    } else {
      reveals.forEach((el) => el.classList.add("is-visible"));
    }
  }
})();
