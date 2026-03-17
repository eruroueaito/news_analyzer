# Task Plan — News Analyzer v2.1 新功能

> 创建日期：2026-03-17
> 分支：`claude/dazzling-euler`

---

## Phase 1 — 快速修复（低风险，无新文件）

### 1.1 补充中文停用词
- **文件**：`news_analyzer/processing/vectorizer.py`
- **修改**：`CHINESE_STOP_WORDS` 集合添加 `"少数派"`, `"用户"`, `"编辑部"`, `"本文"`
- **验证**：`ast.parse` 语法检查

### 1.2 修复热度 badge 颜色对比度
- **文件**：`news_analyzer/ui/topic_detail.py`
- **问题**：`_heat_badge` 使用 `color: {accent}` + `background: {accent}22`，accent 与背景色近似，文字不可读
- **修改**：改为实心背景（`background: {accent}`）+ 白色文字（`color: #fff`），保留圆角边框样式
- **验证**：视觉确认 badge 文字可读

---

## Phase 2 — 新闻阅读器（中等风险，新文件 + 修改 main_window）

### 2.1 新建 `news_analyzer/ui/news_reader.py`
- **`NewsReaderWidget(QWidget)`** 展示选中新闻的详情
  - 顶部工具栏：标题（粗体），右侧"🔍 分析"按钮 + "🌐 打开原文"按钮
  - 内容区：`QTextBrowser`（渲染 HTML），显示 description/content 字段
  - 元信息行：source_name, pub_date（小字，次要色）
  - 空状态：显示"点击左侧新闻以阅读原文"提示
  - `analyze_requested = pyqtSignal()` 信号
  - `set_news(news_item: dict)` 公开方法
  - `_open_in_browser()` 用 `QDesktopServices.openUrl()` 打开原文链接

### 2.2 修改 `main_window.py` → `_build_news_tab()`
- 将现有 `self.right_panel`（QTabWidget 聊天/分析）改为 `QStackedWidget`：
  - 页面 0（索引 0）：`NewsReaderWidget`（默认显示）
  - 页面 1（索引 1）：原 QTabWidget（聊天 + 分析），顶部加"← 返回阅读"按钮
- 连接信号：
  - `news_reader.analyze_requested` → 切换到页面 1，同时触发 `self.llm_panel.analyze_news(current_item)`
  - "← 返回阅读"按钮 → 切换回页面 0
- `_on_news_selected(item)` 同时调用 `news_reader.set_news(item)` 并确保显示页面 0
- 保持 `llm_panel` 和 `chat_panel` 的 `llm_client` 赋值不变

---

## Phase 3 — 当日新闻缓存（中等风险，修改存储 + 启动逻辑）

### 3.1 修改 `NewsStorage` (`news_storage.py`)
- 新增方法 `save_today_news(news_items)` → 固定文件名 `news_today_YYYYMMDD.json`（`data/news/` 目录）
- 新增方法 `load_today_news()` → 检查 `news_today_{today}.json` 是否存在，是则加载并返回；否则返回 `[]`
- 新增方法 `cleanup_old_today_cache(keep_days=3)` → 删除 `news_today_*` 文件中超出 `keep_days` 天的旧文件（防止无限积累）

### 3.2 修改 `RSSCollector.fetch_all_progressive()`
- 添加可选参数 `seed_items: list = None`
- 若传入 `seed_items`，则初始化 `all_news = list(seed_items)` 替代空列表开始，已知标题自然被 `_remove_duplicates` 去重，新条目被追加
- 好处：首轮回调立即能返回缓存 + 新抓取的合并结果

### 3.3 修改 `MainWindow.__init__` 启动逻辑
- 在 `QTimer.singleShot(800, self.refresh_news)` **之前**插入：
  ```python
  cached = self.storage.load_today_news()
  if cached:
      self._current_news_items = cached
      self.news_list.update_news(cached)
      self.chat_panel.set_available_news_titles(cached)
      self._start_vector_worker(cached)  # 立即用缓存构建 Treemap
  ```
- `_on_fetch_finished` 末尾增加 `self.storage.save_today_news(news_items)`
- `refresh_news()` 在有缓存时传入 `seed_items` 给 `FetchWorker`，使 `FetchWorker` 再传给 `fetch_all_progressive`

### 3.4 修改 `FetchWorker`
- `__init__` 增加 `seed_items: list = None` 参数
- `run()` 将 `seed_items` 传给 `fetch_all_progressive(callback, seed_items=...)`

---

## 实施顺序

| 步骤 | Phase | 预计改动 |
|------|-------|---------|
| 1 | 1.1 停用词 | vectorizer.py，1行 |
| 2 | 1.2 badge修复 | topic_detail.py，2行 |
| 3 | 2.1 NewsReaderWidget | 新文件 ~100行 |
| 4 | 2.2 main_window 接入 | main_window.py，~30行 |
| 5 | 3.1 NewsStorage 扩展 | news_storage.py，~40行 |
| 6 | 3.2 RSSCollector seed | rss_collector.py，~10行 |
| 7 | 3.3~3.4 启动逻辑 | main_window.py，~15行 |

---

## 决策记录

- **新闻阅读器位置**：放在"新闻"标签页右侧面板（原聊天框位置），不新建标签页，保持布局紧凑
- **缓存粒度**：以"天"为单位（`news_today_YYYYMMDD.json`），不细分到小时，简化逻辑
- **增量机制**：依靠已有的标题去重实现，不新增"上次抓取时间戳"比对，避免复杂性
- **badge修复**：改为实心背景而非透明，彻底解决对比度问题，与现有 theme 颜色一致
