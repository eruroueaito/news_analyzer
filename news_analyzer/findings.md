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

---

## F9 — NewsReaderWidget 内容无分段的根因

**调查日期**：2026-03-17

### 数据特征（实测）

| 来源 | HTML 标签 | `\n` 换行 | 长度 |
|------|-----------|-----------|------|
| BBC中文网 | ✗ | 0 | 3007 |
| FT中文网  | ✗ | 0 | 63   |
| Solidot  | ✗ | 0 | 218  |

RSS `description` 字段经过抓取器处理后已为**纯文本、无换行、无 HTML 标签**。

### 为何显示为一整块

- `set_news()` 中：`safe_html = self._sanitize_html(description)` → description 本身无 HTML 标签，函数直接返回原字符串
- `self._content.setHtml(safe_html)` 把纯文本当 HTML 渲染 → HTML 渲染器将所有连续空白折叠为单个空格 → 整段文字连成一块

### 正确修复思路

1. **检测内容类型**：`re.search(r'<[a-zA-Z][^>]*>', text)` 判断是否含 HTML 标签
2. **纯文本路径**：按中文句末标点（`。？！…`）+ 空白分句，然后将短句合并为"段落"（`min_para_chars=150`），包裹 `<p>` 标签后 setHtml
3. **HTML 路径**：保持现有 `sanitize_html` + `setHtml` 逻辑
4. **排版 CSS**：用 `document().setDefaultStyleSheet()` 设置 `p { margin-bottom:0.9em }` 和 `body { line-height:1.7 }`
   - 注意：`QTextDocument.setDefaultStyleSheet()` 支持 `line-height`，与 widget 级 QSS 不同
   - 必须在 `setHtml()` **之前**调用，或只调用一次（Qt 保证持久生效）

### 测试结果（BBC中文，3007 字符）

算法参数 `min_para_chars=150` → 16 个段落，每段 150–307 字，阅读体验良好。
