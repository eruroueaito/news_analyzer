# 新闻聚合与分析系统 — 项目进度文档

> 生成日期：2026-03-17
> 最后更新：2026-03-17（Bug修复轮次）
> 基于分支：`claude/dazzling-euler`

---

## 1. 项目概览

### 项目名称
新闻聚合与分析系统（News Analyzer v2.0）

### 技术栈

| 层次 | 技术 |
|------|------|
| UI 框架 | PyQt5（QMainWindow、QTabWidget、QSplitter、QThread、pyqtSignal） |
| 文本向量化 | scikit-learn（TfidfVectorizer） |
| 中文分词 | jieba |
| 聚类算法 | scikit-learn（KMeans，k-means++ 初始化） |
| 热点图绘制 | squarify（TreemapWidget 内部使用） |
| 网络请求 | 标准库 urllib（urlopen、Request） |
| XML 解析 | 标准库 xml.etree.ElementTree |
| 并发处理 | concurrent.futures（ThreadPoolExecutor）+ PyQt5 QThread |
| 持久化 | PyQt5 QSettings（JSON 式平台原生存储） |
| 稀疏矩阵 | scipy.sparse |

### 整体架构

系统采用**分层 MVC 架构**，核心分为四层：

1. **采集层**（`collectors/`）：RSS 多源抓取、默认源管理
2. **处理层**（`processing/`）：TF-IDF 向量化、KMeans 聚类、热度计算
3. **存储层**（`storage/`）：新闻缓存、热点历史、收藏书签
4. **界面层**（`ui/`）：四标签页主窗口、仪表盘热点图、话题详情、RSS 健康检测、LLM 设置

UI 中使用两个核心后台线程（QThread 子类）实现非阻塞操作：
- `FetchWorker`：异步 RSS 抓取，每完成一个源即通过 `items_fetched` 信号实时推送中间结果
- `VectorWorker`：异步向量化与聚类，英文/中文分路处理，完成后通过 `clusters_ready` 信号更新仪表盘

---

## 2. 已完成功能清单

### 2.1 RSS 多源采集
- **所在文件**：`news_analyzer/collectors/rss_collector.py`
- **核心实现**：
  - `RSSCollector` 类，`_fetch_rss(source)` 方法同时支持标准 RSS 格式（`<rss>` 根节点）和 Atom 格式（`feed` 根节点）
  - 使用 `urllib.request.urlopen` 配合自定义 `ssl.SSLContext`（`check_hostname=False`，`CERT_NONE`）规避证书验证问题
  - 请求带 `User-Agent` 头部以降低被屏蔽风险
  - `_remove_duplicates()` 以新闻标题为键去重

### 2.2 默认新闻源列表（含 lang 字段）
- **所在文件**：`news_analyzer/collectors/default_sources.py`
- **核心实现**：
  - `get_default_sources()` 返回约 55 条预设源，按类别组织（综合新闻、国际新闻、科技新闻、商业与金融、政治新闻、科学新闻、体育新闻、娱乐新闻、健康与医疗、文化与教育）
  - 每条源均显式声明 `lang` 字段（`'zh'` 或 `'en'`）
  - `initialize_sources(rss_collector)` 批量注册到 `RSSCollector`，返回成功添加的源数量
  - `RSSCollector.add_source()` 若未传 `lang`，通过检测名称是否含汉字（`\u4e00-\u9fff`）自动判定语言

### 2.3 逐源渐进式加载
- **所在文件**：`rss_collector.py`（`fetch_all_progressive`）+ `main_window.py`（`FetchWorker`、`_on_partial_fetch`）
- **核心实现**：
  - `fetch_all_progressive(on_source_done)` 每完成一个 RSS 源后立即调用回调函数，传入截至当前已去重的全量新闻列表
  - `FetchWorker.items_fetched` 信号在每个源完成后触发，`_on_partial_fetch` 在主线程实时更新新闻列表 UI，无需等待全部源完成

### 2.4 自动刷新
- **所在文件**：`news_analyzer/ui/main_window.py`
- **核心实现**：
  - 启动后 `QTimer.singleShot(800, self.refresh_news)` 延迟 800ms 触发首次刷新（确保 UI 渲染完毕）
  - `self._auto_refresh_timer`：间隔 5 分钟（`5 * 60 * 1000` ms）循环定时刷新
  - `refresh_news()` 检查 `_fetch_worker.isRunning()` 防止重复触发

### 2.5 TF-IDF 向量化
- **所在文件**：`news_analyzer/processing/vectorizer.py`
- **核心实现**：
  - `NewsVectorizer` 封装 `sklearn.TfidfVectorizer`，配置：`max_features=5000`，`max_df=0.5`，`min_df=2`
  - 自定义 `_tokenize(text)` 函数：先去除 HTML 实体，再用 jieba 分词，最后通过正则 `_VALID_TOKEN_RE` 过滤——只保留 2+ 汉字词或 3+ 字母英文词，拒绝纯数字、单字符、标点
  - 英文词统一转小写以归一化（`America` / `american` → `america`）
  - `fit_transform(news_items)` 将每条新闻的 `title + description` 拼接成文档进行向量化，返回稀疏矩阵
  - `get_top_keywords(tfidf_matrix, indices, n)` 对指定行索引的子矩阵按列求和后取 Top-N

### 2.6 KMeans 聚类与热度计算
- **所在文件**：`news_analyzer/processing/clusterer.py`
- **核心实现**：
  - `NewsClusterer.cluster()` 执行 KMeans（`k-means++` 初始化，`max_iter=300`，`n_init=10`，`random_state=42`）
  - 聚类数自动计算：`min(max(5, int(sqrt(n_items / 3))), 25)`，范围限制在 5~25
  - `_calculate_heat()` 热度公式：`文章数量 × 来源多样性数量 × 时效性权重`
  - 时效性权重使用指数衰减：`weight = 0.1 + 0.9 × 2^(-hours_ago / 72)`，半衰期约 3 天
  - 聚类按热度降序排列后重新赋 `cluster_id`（热度排名即 ID）
  - 15 色调色板 `CLUSTER_COLOR_PALETTE`，循环分配颜色

### 2.7 前缀去重（英文词派生形式过滤）
- **所在文件**：`news_analyzer/processing/clusterer.py`
- **核心实现**：
  - `_dedup_prefix_keywords(keywords)` 函数：若词 B 以长度≥4 的词 A 为前缀（B≠A），则认为 B 是 A 的派生形式，丢弃 B，保留 A
  - 示例：`["america", "american"] → ["america"]`，`["iran", "iranian"] → ["iran"]`
  - 在 `_extract_cluster_keywords()` 中对主关键词和关联关键词列表统一去重

### 2.8 英文/中文分开聚类
- **所在文件**：`news_analyzer/ui/main_window.py`（`VectorWorker`）
- **核心实现**：
  - `VectorWorker.run()` 按每条新闻的 `lang` 字段将新闻列表分为 `en_items` 和 `zh_items`
  - 两组各自独立调用 `_cluster_items()`（每路创建独立的 `NewsVectorizer` + `NewsClusterer`）
  - 各路不足 5 条时跳过聚类，返回空列表
  - 完成后通过 `clusters_ready(en_clusters, zh_clusters)` 信号同时传回两组结果

### 2.9 双语 Treemap 热点图
- **所在文件**：`news_analyzer/ui/dashboard_panel.py`
- **核心实现**：
  - `DashboardPanel` 使用 `QSplitter(Qt.Horizontal)` 水平分割，左侧英文热点（标题："🌐 英文热点"），右侧中文热点（标题："中文热点"），初始等宽（`setSizes([1, 1])`）
  - 每侧通过 `_create_treemap_container()` 静态方法创建带标题的 `TreemapWidget` 容器
  - `refresh(news_items, en_clusters, zh_clusters)` 分别调用 `_treemap_en.set_data(en_clusters)` 和 `_treemap_zh.set_data(zh_clusters)`
  - 两个 treemap 的 `topic_clicked` 信号都转发到 `DashboardPanel.topic_clicked`
  - 顶部固定高度 150px 的 `SourceSummaryWidget` 显示各分类新闻源统计
  - 加载中显示半透明遮罩标签，随窗口尺寸变化居中

### 2.10 话题详情面板与返回按钮
- **所在文件**：`news_analyzer/ui/topic_detail.py`
- **核心实现**：
  - `TopicDetailPanel` 包含：顶部"← 返回"按钮（发出 `back_requested` 信号）、关键词大字标签、热度徽章、收藏按钮（☆/★ 切换）
  - 相关关键词行（最多显示 8 个，以"·"分隔）
  - `TrendChartWidget`（近30天频率趋势折线图，固定高度 160px）
  - `QListWidget` 相关新闻列表（最多显示 50 条，双击触发 `news_item_selected` 信号并跳转到"新闻"标签页）
  - 点击 treemap → `_on_topic_clicked()` → `topic_detail_panel.set_topic()` → 主窗口 splitter 调整为 60%/40% 显示详情
  - 点击返回 → `_on_topic_detail_back()` → 隐藏详情面板，splitter 恢复为 100%/0%

### 2.11 RSS 健康检测面板
- **所在文件**：`news_analyzer/ui/rss_health_panel.py`
- **核心实现**：
  - `HealthCheckWorker`：使用 `ThreadPoolExecutor(max_workers=8)` 并发检测所有 RSS 源可访问性（超时 5s），每完成一个源发出 `source_result(url, is_ok)` 信号
  - 检测结果：成功标记绿色"✓"，失败标记红色"✗"并显示"AI搜索新链接"按钮
  - `AISearchWorker`：先尝试从源站首页 HTML 中提取 `<link rel="alternate" type="application/rss+xml">` 标签；若无结果，调用 LLM API（60s 超时）搜索新订阅链接
  - 找到替代链接后显示确认/忽略按钮；用户确认后调用 `RSSCollector.update_source_url()` 更新 URL
  - **每日一次自动检测**：`showEvent` 触发 `_maybe_auto_check()`，通过 `QSettings` 中 `rss_health/last_check_date` 键与今日日期比对，不同则自动执行
  - 所有 HTTP 请求使用忽略证书验证的 SSL 上下文（`_make_ssl_context()`）
  - 已完成 worker 通过 `finished` 信号自动从 `_ai_workers` 字典清除，防止内存泄漏

### 2.12 LLM 设置对话框（含 RSS 订阅检测 Tab）
- **所在文件**：`news_analyzer/ui/llm_settings.py`
- **核心实现**：
  - `APIConfigPanel` 可复用面板：包含 API URL、密钥（密码模式）、模型名称、认证方式（Bearer Token / Anthropic API-Key Header / 自定义 Header）、预设按钮（GPT-4o、GPT-3.5、Claude、Ollama）
  - `LLMSettingsDialog` 包含五个 Tab：摘要 API、分析 API、向量 API、高级设置（温度、最大 Token、系统提示、超时、重试次数）、RSS订阅检测
  - 向后兼容：若新版键 `llm/summary/api_url` 不存在，自动从旧键 `llm/api_url` 迁移
  - `save_settings()` 同时将摘要 API 配置同步到环境变量 `LLM_API_URL`、`LLM_API_KEY`、`LLM_MODEL`
  - "测试连接"按钮针对当前激活的 API Tab 发起实际连接测试

### 2.13 停用词优化
- **所在文件**：`news_analyzer/processing/vectorizer.py`
- **核心实现**：
  - 中文停用词 `CHINESE_STOP_WORDS`：代词、助词、介词、连词、副词、量词、方位词、高频动词、月份（一月~十二月）、新闻套话（"表示"、"指出"、"报道"、"宣布"等）
  - 英文停用词 `_GENERIC_ENGLISH_STOP_WORDS`：月份全称与缩写（january~december、jan~dec）、星期（monday~sunday）、序数词、数量词（million、billion 等）、新闻套话形容词与动词
  - 合并 sklearn 内置 `ENGLISH_STOP_WORDS`，最终 `ALL_STOP_WORDS` 三路合并为一个 set，预转换为 `_ALL_STOP_WORDS_LIST` 模块级一次性计算避免重复开销

---

## 3. 文件结构与职责

### `news_analyzer/ui/main_window.py`
**职责**：应用程序入口与全局协调

| 类/函数 | 职责 |
|---------|------|
| `FetchWorker(QThread)` | 异步 RSS 抓取，支持逐源渐进（`items_fetched`）和全量完成（`finished`）两个信号 |
| `VectorWorker(QThread)` | 异步 TF-IDF + KMeans，英/中分路处理，通过 `clusters_ready` 信号返回双语聚类结果 |
| `AddSourceDialog(QDialog)` | 用户手动添加 RSS 源的输入对话框 |
| `MainWindow(QMainWindow)` | 四标签页（首页/新闻/追踪/历史）主窗口，协调所有子面板、刷新逻辑、主题切换、设置持久化 |
| `_build_home_tab()` | 构建首页：`DashboardPanel` + `TopicDetailPanel`，通过 `QSplitter` 水平排列 |
| `_build_news_tab()` | 构建新闻页：搜索栏 + 分类侧边栏 + 新闻列表 + 聊天/分析右侧面板 |
| `refresh_news()` | 启动 `FetchWorker`，防止并发重复触发 |
| `_start_vector_worker()` | 启动 `VectorWorker`，若上一次尚在运行则先强制终止 |
| `_on_clusters_ready()` | 接收聚类结果，更新 `DashboardPanel`，保存热点历史 |
| `_on_topic_clicked()` | 话题块点击处理：查询趋势数据，展开 `TopicDetailPanel` |

### `news_analyzer/ui/dashboard_panel.py`
**职责**：仪表盘主面板，整合新闻源统计与双语热点图

| 类/方法 | 职责 |
|---------|------|
| `DashboardPanel(QWidget)` | 垂直布局：顶部 `SourceSummaryWidget`（固定 150px）+ 底部双栏 Treemap |
| `_create_treemap_container()` | 静态工厂方法，创建带标题的 `TreemapWidget` 容器 |
| `refresh()` | 计算各类别统计数据，分别更新两个 `TreemapWidget` |
| `_calculate_source_stats()` | 按 category 分组统计：文章数、最新时间、新闻源列表 |
| `set_loading()` | 显示/隐藏半透明加载遮罩标签 |

### `news_analyzer/ui/rss_health_panel.py`
**职责**：RSS 订阅源健康检测与自动修复

| 类/函数 | 职责 |
|---------|------|
| `_make_ssl_context()` | 共用 SSL 上下文工厂（忽略证书验证） |
| `_fetch_url()` | 共用 HTTP GET 工具函数 |
| `HealthCheckWorker(QThread)` | 8 线程并发检测所有 RSS 源可访问性 |
| `AISearchWorker(QThread)` | 依次尝试：HTML 抓取 RSS link 标签 → LLM API 查询，返回替代 URL |
| `RSSHealthPanel(QWidget)` | 订阅源列表表格（4列：状态/名称/分类/操作），每日自动检测逻辑 |

### `news_analyzer/ui/llm_settings.py`
**职责**：语言模型 API 多端点配置界面

| 类/方法 | 职责 |
|---------|------|
| `APIConfigPanel(QWidget)` | 单端点配置面板（URL/Key/Model/认证方式/预设），可复用 |
| `LLMSettingsDialog(QDialog)` | 五 Tab 对话框（摘要/分析/向量 API + 高级设置 + RSS检测），含向后兼容迁移逻辑 |
| `save_settings()` | 保存到 QSettings 并同步环境变量 |
| `_test_connection()` | 针对当前 Tab 的 API 端点发起实际连接测试 |

### `news_analyzer/ui/topic_detail.py`
**职责**：话题详情侧边面板

| 类/方法 | 职责 |
|---------|------|
| `TopicDetailPanel(QWidget)` | 展示话题关键词、热度、相关词、趋势折线图、关联新闻列表 |
| `set_topic()` | 接收聚类数据（cluster_data）、全量新闻、趋势数据，更新所有子组件 |
| `_toggle_bookmark()` | 通过 `BookmarkStore` 切换收藏状态，发出 `bookmark_toggled` 信号 |
| `back_requested` 信号 | 点击"← 返回"按钮时发出，主窗口收到后隐藏详情面板 |

### `news_analyzer/collectors/rss_collector.py`
**职责**：RSS/Atom 新闻抓取与内存缓存

| 类/方法 | 职责 |
|---------|------|
| `RSSCollector` | 新闻源管理（增删查）、新闻缓存（`news_cache`） |
| `add_source()` | 注册新闻源，支持 `lang` 自动检测（汉字判断） |
| `fetch_all_progressive()` | 逐源抓取，每源完成后回调，供 `FetchWorker` 使用；最终结果复用循环中间值，避免重复去重 |
| `_fetch_rss()` | 底层 HTTP 请求 + XML 解析，支持 RSS 和 Atom 两种格式 |
| `_parse_rss_item()` | 解析 `<item>` 节点，HTML 标签清理，含 `lang` 字段 |
| `_parse_atom_entry()` | 解析 Atom `<entry>` 节点，优先 `content` 其次 `summary`，含 `lang` 字段 |
| `update_source_url()` | 用于 RSS 健康检测面板更新失效源 URL |
| `_remove_duplicates()` | 以标题为键去重 |

### `news_analyzer/collectors/default_sources.py`
**职责**：预设新闻源定义与批量注册

| 函数 | 职责 |
|------|------|
| `get_default_sources()` | 返回约 55 条跨语言、跨类别的预设 RSS 源列表，每条含 `lang` 字段 |
| `initialize_sources()` | 批量调用 `RSSCollector.add_source()`，返回成功数量 |

### `news_analyzer/processing/vectorizer.py`
**职责**：新闻文本 TF-IDF 向量化

| 常量/函数/类 | 职责 |
|---------|------|
| `CHINESE_STOP_WORDS` | 中文停用词集合（含月份、新闻套话） |
| `_GENERIC_ENGLISH_STOP_WORDS` | 英文通用停用词集合（含月份、星期、序数词） |
| `ALL_STOP_WORDS` | 三路合并后的完整停用词集合（模块级预计算） |
| `_ALL_STOP_WORDS_LIST` | `ALL_STOP_WORDS` 的 list 形式，供 `TfidfVectorizer` 直接使用 |
| `_tokenize(text)` | jieba 分词 + 正则过滤（2+汉字 或 3+英文字母） |
| `NewsVectorizer` | 封装 `TfidfVectorizer`，提供 `fit_transform()` 和 `get_top_keywords()` |

### `news_analyzer/processing/clusterer.py`
**职责**：KMeans 新闻聚类与热度评分

| 常量/函数/类 | 职责 |
|---------|------|
| `CLUSTER_COLOR_PALETTE` | 15 色可视化调色板 |
| `_dedup_prefix_keywords()` | 移除关键词列表中的前缀派生词（如 american → america） |
| `NewsClusterer` | KMeans 聚类主类 |
| `cluster()` | 主入口：聚类 → 关键词提取 → 热度计算 → 按热度排序 |
| `_auto_detect_clusters()` | 公式：`min(max(5, int(sqrt(n/3))), 25)` |
| `_extract_cluster_keywords()` | 从聚类中心向量取 Top-N 词，前缀去重后返回（主词，关联词列表） |
| `_calculate_heat()` | 热度 = 文章数 × 来源多样性 × 时效性权重 |
| `_recency_weight()` | 指数衰减：`0.1 + 0.9 × 2^(-hours_ago/72)`，半衰期 72 小时；支持 ISO 8601 与 RFC 2822 双格式解析 |

---

## 4. 关键数据流

### 完整流程：RSS 抓取 → 分词聚类 → 热点图展示

```
启动 / 定时器触发
       │
       ▼
MainWindow.refresh_news()
  └─ 创建并启动 FetchWorker
           │
           │ (后台线程)
           ▼
     RSSCollector.fetch_all_progressive(callback)
       ├─ 遍历每个 source
       ├─ _fetch_rss(source) → HTTP GET → XML 解析
       │   └─ 返回 [news_item, ...]  (每条含 lang 字段)
       ├─ _remove_duplicates() → 全量去重（复用结果，最后一次即为最终值）
       └─ callback(unique_news) → FetchWorker.items_fetched 信号
                │
                ▼ (主线程，每源完成一次)
          MainWindow._on_partial_fetch()
            └─ NewsListPanel.update_news()  ← 实时更新新闻列表 UI

  (全部源完成后)
       │
       ▼ FetchWorker.finished 信号
  MainWindow._on_fetch_finished()
    ├─ storage.save_news()
    ├─ chat_panel.set_available_news_titles()
    └─ _start_vector_worker(news_items)
              │
              │ (后台线程)
              ▼
        VectorWorker.run()
          ├─ en_items = [n for n if lang == 'en']
          ├─ zh_items = [n for n if lang == 'zh']
          │
          ├─ _cluster_items(en_items):
          │   ├─ NewsVectorizer.fit_transform()
          │   │   └─ _tokenize() → jieba + 正则过滤 → TF-IDF 矩阵
          │   └─ NewsClusterer.cluster(matrix, items, feature_names)
          │       ├─ KMeans(k-means++, n_clusters 自动计算)
          │       ├─ 每个聚类：提取关键词（前缀去重）
          │       └─ 计算热度（文章数 × 多样性 × 时效性衰减）
          │
          └─ 同上处理 zh_items
                    │
                    ▼ VectorWorker.clusters_ready(en_clusters, zh_clusters)
              MainWindow._on_clusters_ready()
                └─ DashboardPanel.refresh(news_items, en_clusters, zh_clusters)
                    ├─ _calculate_source_stats() → SourceSummaryWidget.set_data()
                    ├─ _treemap_en.set_data(en_clusters)  ← 左侧英文热点图
                    └─ _treemap_zh.set_data(zh_clusters)  ← 右侧中文热点图

用户点击 Treemap 色块
       │
       ▼ TreemapWidget.topic_clicked → DashboardPanel.topic_clicked
         → MainWindow._on_topic_clicked()
           ├─ HotNewsManager.get_keyword_frequency(keyword, days=30) → trend_data
           ├─ TopicDetailPanel.set_topic(cluster_data, news_items, trend_data)
           └─ 展开首页 Splitter（60% 仪表盘 / 40% 详情）

用户点击"← 返回"
       │
       ▼ TopicDetailPanel.back_requested → MainWindow._on_topic_detail_back()
         └─ 隐藏 TopicDetailPanel，Splitter 恢复为 100%/0%
```

---

## 5. 已修复问题 & 遗留问题

### ✅ 5.1 去重逻辑优化（已修复）
- **文件**：`rss_collector.py` → `_remove_duplicates()`
- **修复**：去重键从原始标题字符串改为规范化形式（`' '.join(title.lower().split())`），消除大小写和空白差异导致的重复条目

### ✅ 5.2 RSS 日期格式与时效性权重不兼容（已修复）
- **文件**：`clusterer.py` → `_recency_weight()`
- **修复**：新增 RFC 2822 回退解析（`email.utils.parsedate_to_datetime`）。优先尝试 ISO 8601（Atom 格式），失败后自动降级解析 RSS 标准格式（`Mon, 17 Mar 2026 12:00:00 GMT`），热度衰减权重恢复正常

### ✅ 5.3 VectorWorker 强制终止风险（已修复）
- **文件**：`main_window.py` → `VectorWorker`、`_start_vector_worker()`
- **修复**：添加 `_cancelled` 标志和 `cancel()` 方法；`_start_vector_worker()` 改为调用 `cancel()` + `wait(3000ms)`，让线程在检查点自然退出，替代原来的 `terminate()`

### ✅ 5.5 `DashboardPanel._calculate_source_stats()` 字段名错误（已修复）
- **文件**：`dashboard_panel.py` → `_calculate_source_stats()`
- **修复**：统计来源时改为 `item.get('source_name') or item.get('source', '')`，`SourceSummaryWidget` 的来源列表现在可正常填充

### ✅ 5.6 中文聚类在源较少时始终为空（已修复）
- **文件**：`main_window.py` → `VectorWorker._cluster_items()`
- **修复**：最小文章数阈值由 5 降为 3（`_MIN_ITEMS_FOR_CLUSTER = 3`），减少中文热点图空白概率

### ✅ 5.7 AI 搜索结果无有效性验证（已修复）
- **文件**：`rss_health_panel.py` → `AISearchWorker`
- **修复**：新增 `_validate_feed_url()` 方法，对 AI 返回的 URL 做快速抓取（8s 超时），检查响应内容是否包含 `<rss`、`<feed`、`<channel` 等 RSS/Atom 特征标签；验证失败则丢弃候选 URL，不向用户展示确认按钮

### ⚠️ 5.4 `source` 字段命名不一致（待处理）
- **文件**：`rss_collector.py`（字段为 `source_name`）vs `topic_detail.py`（同时查找 `source` 和 `source_name`）
- **现状**：`topic_detail.py` 已有兼容处理，`dashboard_panel.py` 中的字段名错误已修复（见 5.5），整体影响有限，但字段命名规范化仍建议在后续重构中统一为 `source_name`

### ⚠️ 5.8 `show_settings()` 未实现（待处理）
- **文件**：`main_window.py` → `show_settings()`
- **现状**：当前仅显示"设置功能开发中..."弹窗，通用设置页面（主题偏好、刷新间隔、最大新闻数等）尚未实现

---

## 6. 运行方式

### 环境准备

```bash
# 建议 Python 3.10+
pip install PyQt5 scikit-learn jieba scipy squarify
```

### 启动命令

```bash
# 在项目根目录（含 news_analyzer/ 包的父目录）执行
cd /path/to/news_analyzer
python -m news_analyzer
```

### 首次启动流程

1. 主窗口初始化，默认打开"新闻"标签页
2. 800ms 后自动调用 `refresh_news()`，启动后台 `FetchWorker`
3. 每完成一个 RSS 源，新闻列表实时更新（渐进式加载）
4. 全部源完成后启动 `VectorWorker` 进行向量化与聚类
5. 聚类完成后"首页"标签页的双语热点 Treemap 自动更新
6. 此后每 5 分钟自动重复步骤 2~5

### LLM 配置

启动后点击工具栏"语言模型设置"，在对话框中：
- 选择"摘要 API"标签页，填入 API URL、密钥、模型名称
- 可使用预设按钮快速填入 OpenAI / Claude / Ollama 配置
- 点击"测试连接"验证后保存

### RSS 健康检测

工具栏 → 语言模型设置 → "RSS订阅检测"标签页 → 点击"检测所有订阅"
（或面板首次显示时，若今日尚未检测则自动触发）

---

## 7. 规划中功能（v2.1）

> 规划日期：2026-03-17
> 详细方案见 `task_plan.md`，调查记录见 `findings.md`

### 7.1 补充停用词（少数派、用户）
- **范围**：`vectorizer.py` → `CHINESE_STOP_WORDS`，加入 `"少数派"`, `"用户"`, `"编辑部"`, `"本文"`
- **状态**：✅ 已完成

### 7.2 修复热度 badge 对比度
- **根因**：`_heat_badge` 使用 `color: {accent}` + `background: {accent}22`，同色系导致文字不可读（见 findings.md F1/F2）
- **方案**：改为 `background: {accent}; color: #fff`（实心背景 + 白色文字）
- **状态**：✅ 已完成

### 7.3 新闻原文阅读器（默认右侧面板）
- **方案**：新建 `ui/news_reader.py`（`NewsReaderWidget`），替换现有 `right_panel` QTabWidget，用 `QStackedWidget` 封装：默认显示阅读器，点击"分析"按钮切换到聊天/分析面板
- **涉及文件**：`news_reader.py`（新建）、`main_window.py`
- **状态**：✅ 已完成（含修复 QTextBrowser 颜色键名 bug）

### 7.4 当日新闻缓存（避免重复抓取）
- **方案**：`NewsStorage` 增加 `save_today_news()` / `load_today_news()`；启动时先加载今日缓存展示；`fetch_all_progressive` 接受 `seed_items` 参数，已知条目通过去重自然跳过；`FetchWorker` 传递 `seed_items`
- **涉及文件**：`news_storage.py`、`rss_collector.py`、`main_window.py`
- **状态**：✅ 已完成

---

## 8. 实施记录（2026-03-17 第二轮）

### 已完成

| # | 功能 | 文件 | 备注 |
|---|------|------|------|
| 1 | 补充停用词（少数派/用户/编辑部/本文） | `vectorizer.py` | 加入 `CHINESE_STOP_WORDS` |
| 2 | 修复热度 badge 对比度 | `topic_detail.py` | `_apply_theme()` 改实心 accent 背景 + 白字 |
| 3 | 新闻原文阅读器 | 新建 `news_reader.py`、`main_window.py` | 右侧默认阅读视图，"🔍 分析"切换 QStackedWidget |
| 4 | 当日新闻缓存 | `news_storage.py`、`rss_collector.py`、`main_window.py` | 启动即加载缓存，增量抓取，每次抓取后覆盖写缓存 |

### 关键设计决策

- **右侧面板**：用 `QStackedWidget` 替换原 `QTabWidget`；页面 0 = 阅读器（默认），页面 1 = 聊天/分析（点击"分析"进入，有"← 返回阅读"按钮）
- **阅读器不触发 LLM**：选中新闻只填充阅读器，分析逻辑推迟到用户主动点击"分析"
- **增量缓存**：`fetch_all_progressive(seed_items=...)` 将缓存条目预填入 `all_news`，新条目追加后统一去重，无需改动去重算法
- **缓存文件**：`news_today_YYYYMMDD.json`，每次 `_on_fetch_finished` 覆盖写入，3 天旧文件自动清理

---

## 9. 排版修复（2026-03-17 第三轮）

### 问题
`NewsReaderWidget` 正文显示为一整块文字，无段落分隔。

### 根因（findings.md F9）
RSS `description` 字段为纯文本（无 HTML 标签、无 `\n` 换行）。`setHtml()` 把纯文本当 HTML 渲染时，HTML 渲染引擎将所有连续空白折叠为单个空格，整段文字连成一块。

### 修复（仅改动 `news_analyzer/ui/news_reader.py`）

| 新增 | 说明 |
|------|------|
| `_render_content(text)` | 入口：检测 HTML/纯文本，调用对应路径 |
| `_split_paragraphs(text, min_para_chars=150)` | 按 `\n\n` → `\n` → 句末标点分句并合并为段落 |
| `_escape_html(text)` | 转义 `& < > "` 防止纯文本被误解析为 HTML |
| `document().setDefaultStyleSheet(...)` | `line-height: 1.7; p margin-bottom: 0.9em`（QTextDocument CSS 支持 line-height，QSS 不支持） |

### 效果
- BBC中文（3007字，无换行）→ 约 16 个段落，有明显段间距
- FT中文（63字，单句）→ 1 段，正常显示
- 含 HTML 标签的 RSS 条目 → HTML 路径正常渲染
