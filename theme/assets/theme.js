/* 在样式加载前决定主题，避免闪白 */
(() => {
  const root = document.documentElement;
  root.classList.add("js");
  try {
    const query = new URLSearchParams(location.search).get("theme");
    const stored = localStorage.getItem("theme");
    const dark = matchMedia("(prefers-color-scheme: dark)").matches;
    root.dataset.theme = query || stored || (dark ? "dark" : "light");
  } catch (error) {
    /* 存不了就跟随系统 */
  }
})();
