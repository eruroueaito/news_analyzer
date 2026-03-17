# Findings — News Analyzer v2.1

> 调查日期：2026-03-17

---

## F1 — 热度 badge 不可读的根因

**文件**：`topic_detail.py` → `_apply_theme()` → `self._heat_badge.setStyleSheet(...)`

```python
self._heat_badge.setStyleSheet(
    f"background-color: {accent}22; color: {accent}; "
    ...
)
```

- `{accent}22` = accent 色 + hex alpha 值 `22`（= 13.3% 不透明度）→ 几乎透明的浅色背景
- `color: {accent}` = 文字颜色与背景同色系（同一个 accent 颜色）
- 当 theme 的 accent 色为橙/棕/金色时，文字与背景几乎无法区分
- **Fix**：`background-color: {accent}; color: #ffffff;`（实心背景 + 白色文字）

---

## F2 — 收藏按钮旁的神秘按钮是 `_heat_badge`

截图中"收藏"按钮左侧的棕色矩形就是 `_heat_badge`（`QLabel`，`setFixedSize(80, 28)`）。
它显示"热度 xxx"但颜色问题导致文字不可见。不是一个无功能的按钮，而是一个 QLabel 样式问题。

---

## F3 — 今日缓存机制可利用现有 `save_news` / `load_news`

`NewsStorage.save_news()` 已经存储到 `data/news/news_YYYYMMDD_HHMMSS.json`。
`load_news(filename=None)` 加载最新文件。

**可行方案**：
- 新增 `save_today_news()` 用固定名 `news_today_YYYYMMDD.json`（每次覆盖），便于 `load_today_news()` 按日期精确匹配，不依赖"最新文件"这一模糊逻辑

**已有 `list_news_files()`** 返回排序后的文件名列表，可用于清理旧的 today 缓存文件。

---

## F4 — `fetch_all_progressive` 去重依赖 `_remove_duplicates`

```python
# 每完成一源后
unique_so_far = self._remove_duplicates(all_news)
```

`_remove_duplicates` 使用规范化标题（`' '.join(title.lower().split())`）作为去重键。
若 `all_news` 初始值填入缓存条目，新抓取的重复项会被自然过滤，无需改动去重逻辑。

这意味着：在 `fetch_all_progressive` 中加入 `seed_items` 参数，把今日缓存作为初始值传入，即可实现"只追加新条目"的增量效果。

---

## F5 — `NewsReaderWidget` 已有类似实现可参考

`chat_panel.py` 中的 `QTextBrowser` 用于显示 LLM 回复，已经处理了富文本渲染。
`news_list.py` 中每条 `NewsListItem` 已经把 `title`、`source_name`、`pub_date` 格式化为多行文本。

`NewsReaderWidget` 的内容区可复用 `QTextBrowser`，通过 `setHtml()` 渲染 description 字段（RSS 条目的 description 通常含 HTML 标签）。

---

## F6 — `QDesktopServices.openUrl` 已在项目中使用

搜索结果：`news_list.py` 中有 `QDesktopServices.openUrl(QUrl(link))` 的调用模式。
`NewsReaderWidget` 的"打开原文"功能可直接复用该模式。

---

## F7 — main_window 右侧面板当前结构

```python
self.right_panel = QTabWidget()
self.chat_panel = ChatPanel()
self.llm_panel = LLMPanel()
self.right_panel.addTab(self.chat_panel, "聊天")
self.right_panel.addTab(self.llm_panel, "分析")
splitter.addWidget(self.right_panel)
splitter.setSizes([200, 500, 500])
```

改造方案：用 `QStackedWidget` 替换，不改变 splitter 结构，保持宽度比例不变。

---

## F8 — `_on_news_selected` 当前只调用 llm_panel 和 chat_panel

```python
def _on_news_selected(self, news_item):
    self.llm_panel.analyze_news(news_item)
    self.chat_panel.set_current_news(news_item)
    if hasattr(self.chat_panel, 'context_checkbox'):
        self.chat_panel.context_checkbox.setChecked(True)
```

改造后需要新增：`self.news_reader.set_news(news_item)` 并切换 stacked widget 到阅读页面（仅当用户没有主动切到分析模式时）。
