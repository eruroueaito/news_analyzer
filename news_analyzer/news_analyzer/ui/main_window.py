#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
主窗口模块 - 应用程序主界面

新布局（四标签页）：
  ├── 首页   → DashboardPanel（新闻源概览 + Treemap 热点图）+ TopicDetailPanel
  ├── 新闻   → SearchPanel + Sidebar + NewsList + 聊天/分析面板
  ├── 追踪   → TrackingPanel（收藏关键词 + 趋势图）
  └── 历史   → HistoryPanel

功能亮点：
  - 日/夜主题切换（工具栏按钮 + Ctrl+Shift+T）
  - VectorWorker 异步向量化/聚类，刷新新闻后自动更新首页
  - FetchWorker 异步 RSS 抓取，UI 不卡顿
  - HotNewsManager 7 天热点数据保留
"""

import os
import logging
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QAction, QStatusBar, QToolBar,
    QMessageBox, QDialog, QLabel, QLineEdit,
    QPushButton, QFormLayout, QTabWidget, QApplication,
    QShortcut,
)
from PyQt5.QtCore import Qt, QSize, QSettings, QThread, pyqtSignal
from PyQt5.QtGui import QKeySequence

from news_analyzer.ui.sidebar import CategorySidebar
from news_analyzer.ui.news_list import NewsListPanel
from news_analyzer.ui.search_panel import SearchPanel
from news_analyzer.ui.llm_panel import LLMPanel
from news_analyzer.ui.chat_panel import ChatPanel
from news_analyzer.ui.llm_settings import LLMSettingsDialog
from news_analyzer.ui.theme import ThemeManager
from news_analyzer.collectors.rss_collector import RSSCollector
from news_analyzer.llm.llm_client import LLMClient


# ---------------------------------------------------------------------------
# 后台工作线程
# ---------------------------------------------------------------------------

class FetchWorker(QThread):
    """异步 RSS 抓取线程"""
    progress = pyqtSignal(int, int)          # fetched, total
    finished = pyqtSignal(list)              # news_items
    error = pyqtSignal(str)

    def __init__(self, rss_collector, source_url=None, parent=None):
        super().__init__(parent)
        self._collector = rss_collector
        self._source_url = source_url

    def run(self):
        try:
            if self._source_url:
                items = self._collector.fetch_from_source(self._source_url)
            else:
                items = self._collector.fetch_all()
            self.finished.emit(items)
        except Exception as e:
            self.error.emit(str(e))


class VectorWorker(QThread):
    """异步向量化 + 聚类线程"""
    clusters_ready = pyqtSignal(list)        # list of cluster dicts
    error = pyqtSignal(str)

    def __init__(self, news_items, parent=None):
        super().__init__(parent)
        self._news_items = news_items

    def run(self):
        try:
            from news_analyzer.processing.vectorizer import NewsVectorizer
            from news_analyzer.processing.clusterer import NewsClusterer

            if not self._news_items:
                self.clusters_ready.emit([])
                return

            vectorizer = NewsVectorizer()
            matrix = vectorizer.fit_transform(self._news_items)
            if matrix is None or matrix.shape[0] == 0:
                self.clusters_ready.emit([])
                return

            feature_names = vectorizer.get_feature_names()
            clusterer = NewsClusterer()
            clusters = clusterer.cluster(matrix, self._news_items, feature_names)
            self.clusters_ready.emit(clusters)

        except ImportError:
            self.error.emit(
                "向量化模块未安装，请运行: pip install scikit-learn jieba"
            )
        except Exception as e:
            self.error.emit(str(e))


# ---------------------------------------------------------------------------
# 添加新闻源对话框
# ---------------------------------------------------------------------------

class AddSourceDialog(QDialog):
    """添加新闻源对话框"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("添加新闻源")
        self.setMinimumWidth(400)
        layout = QFormLayout(self)

        self.url_input = QLineEdit()
        layout.addRow("RSS URL:", self.url_input)

        self.name_input = QLineEdit()
        layout.addRow("名称 (可选):", self.name_input)

        self.category_input = QLineEdit()
        layout.addRow("分类:", self.category_input)

        btn_layout = QHBoxLayout()
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        add_btn = QPushButton("添加")
        add_btn.setDefault(True)
        add_btn.clicked.connect(self.accept)
        btn_layout.addWidget(add_btn)
        layout.addRow("", btn_layout)

    def get_values(self):
        return {
            'url': self.url_input.text().strip(),
            'name': self.name_input.text().strip(),
            'category': self.category_input.text().strip() or "未分类",
        }


# ---------------------------------------------------------------------------
# 主窗口
# ---------------------------------------------------------------------------

class MainWindow(QMainWindow):
    """应用程序主窗口"""

    def __init__(self, storage, rss_collector=None):
        super().__init__()

        self.logger = logging.getLogger('news_analyzer.ui.main_window')
        self.storage = storage
        self.rss_collector = rss_collector or RSSCollector()

        # 当前后台任务句柄
        self._fetch_worker = None
        self._vector_worker = None
        self._current_news_items = []
        self._current_clusters = []

        self.setWindowTitle("新闻聚合与分析系统")
        self.setMinimumSize(1280, 800)

        # 初始化热点管理器
        self._init_hot_news_manager()

        # 初始化收藏存储
        self._init_bookmark_store()

        # 加载 LLM 设置到环境变量
        self._load_llm_settings()

        # 共享 LLM 客户端
        self.llm_client = LLMClient.from_profile('summary')

        # 应用主题
        theme = ThemeManager.instance()
        theme.apply_to_app(QApplication.instance())
        theme.theme_changed.connect(self._on_theme_changed)

        # 初始化 UI
        self._init_ui()
        self._load_settings()
        self._sync_categories()
        self._update_status_message()

        self.logger.info("主窗口已初始化")

    # ------------------------------------------------------------------
    # 初始化辅助
    # ------------------------------------------------------------------

    def _init_hot_news_manager(self):
        try:
            from news_analyzer.processing.hot_news_manager import HotNewsManager
            self.hot_news_manager = HotNewsManager(self.storage.data_dir)
            self.hot_news_manager.cleanup_old_data()
        except Exception as e:
            self.logger.warning(f"HotNewsManager 初始化失败: {e}")
            self.hot_news_manager = None

    def _init_bookmark_store(self):
        try:
            from news_analyzer.storage.bookmark_store import BookmarkStore
            # BookmarkStore 期望 app_root（它内部会拼接 /data）
            self.bookmark_store = BookmarkStore(self.storage.app_root)
        except Exception as e:
            self.logger.warning(f"BookmarkStore 初始化失败: {e}")
            self.bookmark_store = None

    def _load_llm_settings(self):
        """从 QSettings 读取 LLM 配置并设置环境变量（向后兼容）"""
        settings = QSettings("NewsAnalyzer", "NewsAggregator")
        api_key = settings.value("llm/api_key", "")
        api_url = settings.value("llm/api_url", "")
        model_name = settings.value("llm/model_name", "")
        if api_key:
            os.environ["LLM_API_KEY"] = api_key
        if api_url:
            os.environ["LLM_API_URL"] = api_url
        if model_name:
            os.environ["LLM_MODEL"] = model_name

    def _update_status_message(self):
        if hasattr(self, 'llm_client') and self.llm_client.api_key:
            self.status_label.setText(f"语言模型已就绪: {self.llm_client.model}")
        else:
            self.status_label.setText("语言模型未配置，请设置 API 密钥")

    # ------------------------------------------------------------------
    # UI 初始化
    # ------------------------------------------------------------------

    def _init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)

        # 顶层标签页
        self.main_tabs = QTabWidget()
        self.main_tabs.setTabPosition(QTabWidget.North)
        root_layout.addWidget(self.main_tabs)

        # ---- Tab 0: 首页 ----
        self.main_tabs.addTab(self._build_home_tab(), "  首页  ")

        # ---- Tab 1: 新闻 ----
        self.main_tabs.addTab(self._build_news_tab(), "  新闻  ")

        # ---- Tab 2: 追踪 ----
        self.main_tabs.addTab(self._build_tracking_tab(), "  追踪  ")

        # ---- Tab 3: 历史 ----
        self.main_tabs.addTab(self._build_history_tab(), "  历史  ")

        # 默认打开"新闻"页（用户最常用）
        self.main_tabs.setCurrentIndex(1)

        # 创建菜单、工具栏、状态栏
        self._create_actions()
        self._create_menus()
        self._create_toolbars()
        self._create_statusbar()

    def _build_home_tab(self) -> QWidget:
        """构建首页标签页：仪表盘 + 话题详情"""
        tab = QWidget()
        layout = QHBoxLayout(tab)
        layout.setContentsMargins(0, 0, 0, 0)

        # 水平分割：左侧仪表盘 | 右侧话题详情
        splitter = QSplitter(Qt.Horizontal)

        # 仪表盘
        try:
            from news_analyzer.ui.dashboard_panel import DashboardPanel
            self.dashboard_panel = DashboardPanel()
            self.dashboard_panel.topic_clicked.connect(self._on_topic_clicked)
            splitter.addWidget(self.dashboard_panel)
        except Exception as e:
            self.logger.error(f"DashboardPanel 加载失败: {e}")
            self.dashboard_panel = None
            placeholder = QLabel(f"仪表盘加载失败: {e}")
            placeholder.setAlignment(Qt.AlignCenter)
            splitter.addWidget(placeholder)

        # 话题详情面板（初始隐藏）
        if self.bookmark_store:
            try:
                from news_analyzer.ui.topic_detail import TopicDetailPanel
                self.topic_detail_panel = TopicDetailPanel(self.bookmark_store)
                self.topic_detail_panel.news_item_selected.connect(
                    self._on_topic_news_selected
                )
                self.topic_detail_panel.bookmark_toggled.connect(
                    self._on_bookmark_toggled
                )
                splitter.addWidget(self.topic_detail_panel)
                self.topic_detail_panel.hide()
                splitter.setSizes([1, 0])
            except Exception as e:
                self.logger.error(f"TopicDetailPanel 加载失败: {e}")
                self.topic_detail_panel = None
        else:
            self.topic_detail_panel = None

        layout.addWidget(splitter)
        self._home_splitter = splitter
        return tab

    def _build_news_tab(self) -> QWidget:
        """构建新闻标签页：原有 SearchPanel + Splitter 布局"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 0, 0, 0)

        # 搜索面板
        self.search_panel = SearchPanel()
        self.search_panel.search_requested.connect(self.search_news)
        layout.addWidget(self.search_panel)

        # 主分割器
        splitter = QSplitter(Qt.Horizontal)

        # 左侧分类侧边栏
        self.sidebar = CategorySidebar()
        self.sidebar.category_selected.connect(self.filter_by_category)
        splitter.addWidget(self.sidebar)

        # 中间新闻列表
        self.news_list = NewsListPanel()
        self.news_list.item_selected.connect(self._on_news_selected)
        self.news_list.news_updated.connect(self._update_chat_panel_news)
        splitter.addWidget(self.news_list)

        # 右侧聊天/分析标签页
        self.right_panel = QTabWidget()

        self.chat_panel = ChatPanel()
        self.chat_panel.llm_client = self.llm_client

        self.llm_panel = LLMPanel()
        self.llm_panel.llm_client = self.llm_client

        self.right_panel.addTab(self.chat_panel, "聊天")
        self.right_panel.addTab(self.llm_panel, "分析")
        splitter.addWidget(self.right_panel)

        splitter.setSizes([200, 500, 500])
        layout.addWidget(splitter, 1)
        return tab

    def _build_tracking_tab(self) -> QWidget:
        """构建追踪标签页"""
        if self.bookmark_store:
            try:
                from news_analyzer.ui.tracking_panel import TrackingPanel
                self.tracking_panel = TrackingPanel(
                    self.bookmark_store,
                    self.hot_news_manager,
                )
                self.tracking_panel.keyword_news_requested.connect(
                    self._search_keyword_news
                )
                return self.tracking_panel
            except Exception as e:
                self.logger.error(f"TrackingPanel 加载失败: {e}")

        self.tracking_panel = None
        placeholder = QLabel("追踪功能不可用")
        placeholder.setAlignment(Qt.AlignCenter)
        return placeholder

    def _build_history_tab(self) -> QWidget:
        """构建历史标签页"""
        try:
            from news_analyzer.ui.history_panel import HistoryPanel
            self.history_panel = HistoryPanel(self.storage)
            self.history_panel.history_loaded.connect(self.load_history_news)
            return self.history_panel
        except ImportError:
            self.history_panel = None
            placeholder = QLabel("历史模块未找到")
            placeholder.setAlignment(Qt.AlignCenter)
            return placeholder

    # ------------------------------------------------------------------
    # 菜单 / 工具栏 / 状态栏
    # ------------------------------------------------------------------

    def _create_actions(self):
        self.add_source_action = QAction("添加新闻源", self)
        self.add_source_action.setStatusTip("添加新的 RSS 新闻源")
        self.add_source_action.triggered.connect(self.add_news_source)

        self.refresh_action = QAction("刷新新闻", self)
        self.refresh_action.setStatusTip("获取最新新闻")
        self.refresh_action.triggered.connect(self.refresh_news)

        self.settings_action = QAction("设置", self)
        self.settings_action.setStatusTip("修改应用程序设置")
        self.settings_action.triggered.connect(self.show_settings)

        self.llm_settings_action = QAction("语言模型设置", self)
        self.llm_settings_action.setStatusTip("配置语言模型 API 设置")
        self.llm_settings_action.triggered.connect(self._show_llm_settings)

        self.theme_action = QAction("☀ 切换日间模式", self)
        self.theme_action.setStatusTip("在日间/夜间主题之间切换 (Ctrl+Shift+T)")
        self.theme_action.triggered.connect(self._toggle_theme)
        self._update_theme_action_text()

        self.exit_action = QAction("退出", self)
        self.exit_action.triggered.connect(self.close)

        self.about_action = QAction("关于", self)
        self.about_action.triggered.connect(self.show_about)

        # 快捷键
        QShortcut(QKeySequence("Ctrl+Shift+T"), self).activated.connect(
            self._toggle_theme
        )

    def _create_menus(self):
        file_menu = self.menuBar().addMenu("文件")
        file_menu.addAction(self.add_source_action)
        file_menu.addAction(self.refresh_action)
        file_menu.addSeparator()
        file_menu.addAction(self.exit_action)

        tools_menu = self.menuBar().addMenu("工具")
        tools_menu.addAction(self.settings_action)
        tools_menu.addAction(self.llm_settings_action)

        view_menu = self.menuBar().addMenu("视图")
        view_menu.addAction(self.theme_action)

        help_menu = self.menuBar().addMenu("帮助")
        help_menu.addAction(self.about_action)

    def _create_toolbars(self):
        toolbar = self.addToolBar("主工具栏")
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(24, 24))
        toolbar.addAction(self.add_source_action)
        toolbar.addAction(self.refresh_action)
        toolbar.addSeparator()
        toolbar.addAction(self.llm_settings_action)
        toolbar.addSeparator()
        toolbar.addAction(self.theme_action)

    def _create_statusbar(self):
        self.status_label = QLabel("就绪")
        self.statusBar().addPermanentWidget(self.status_label)

    # ------------------------------------------------------------------
    # 主题切换
    # ------------------------------------------------------------------

    def _toggle_theme(self):
        ThemeManager.instance().toggle_theme()

    def _update_theme_action_text(self):
        if ThemeManager.instance().is_dark():
            self.theme_action.setText("☀ 切换日间模式")
        else:
            self.theme_action.setText("🌙 切换夜间模式")

    def _on_theme_changed(self, is_dark: bool):
        ThemeManager.instance().apply_to_app(QApplication.instance())
        self._update_theme_action_text()

    # ------------------------------------------------------------------
    # 设置加载 / 保存
    # ------------------------------------------------------------------

    def _load_settings(self):
        settings = QSettings("NewsAnalyzer", "NewsAggregator")
        geometry = settings.value("geometry")
        if geometry:
            self.restoreGeometry(geometry)
        sources = settings.value("user_rss_sources", [])
        if sources:
            for source in sources:
                self.rss_collector.add_source(
                    source['url'], source['name'], source['category']
                )

    def _sync_categories(self):
        categories = {s['category'] for s in self.rss_collector.get_sources()}
        for cat in sorted(categories):
            self.sidebar.add_category(cat)
        self.logger.info(f"同步了 {len(categories)} 个分类到侧边栏")

    def _save_settings(self):
        settings = QSettings("NewsAnalyzer", "NewsAggregator")
        settings.setValue("geometry", self.saveGeometry())
        user_sources = [
            s for s in self.rss_collector.get_sources()
            if s.get('is_user_added', False)
        ]
        settings.setValue("user_rss_sources", user_sources)

    # ------------------------------------------------------------------
    # 新闻刷新（异步）
    # ------------------------------------------------------------------

    def refresh_news(self, source_url=None):
        """异步刷新新闻（FetchWorker）"""
        if self._fetch_worker and self._fetch_worker.isRunning():
            return  # 避免重复触发

        self.status_label.setText("正在获取新闻...")
        self.refresh_action.setEnabled(False)

        self._fetch_worker = FetchWorker(self.rss_collector, source_url, self)
        self._fetch_worker.finished.connect(self._on_fetch_finished)
        self._fetch_worker.error.connect(self._on_fetch_error)
        self._fetch_worker.start()

    def _on_fetch_finished(self, news_items):
        self.refresh_action.setEnabled(True)
        count = len(news_items)
        self.status_label.setText(f"已获取 {count} 条新闻")
        self._current_news_items = news_items

        # 更新新闻列表 UI
        self.news_list.update_news(news_items)
        self.chat_panel.set_available_news_titles(news_items)

        # 保存到存储
        self.storage.save_news(news_items)

        # 触发向量化/聚类（异步）
        self._start_vector_worker(news_items)

        # 更新热点数据（用上次聚类结果，若无则传空）
        if self.hot_news_manager:
            self.hot_news_manager.update_daily_hot(news_items, self._current_clusters)

        self.logger.info(f"已刷新新闻，获取了 {count} 条")

    def _on_fetch_error(self, msg):
        self.refresh_action.setEnabled(True)
        QMessageBox.warning(self, "刷新失败", f"获取新闻失败: {msg}")
        self.status_label.setText("刷新失败")
        self.logger.error(f"刷新新闻失败: {msg}")

    # ------------------------------------------------------------------
    # 向量化/聚类（异步）
    # ------------------------------------------------------------------

    def _start_vector_worker(self, news_items):
        if self._vector_worker and self._vector_worker.isRunning():
            self._vector_worker.terminate()

        if self.dashboard_panel:
            self.dashboard_panel.set_loading(True)

        self._vector_worker = VectorWorker(news_items, self)
        self._vector_worker.clusters_ready.connect(self._on_clusters_ready)
        self._vector_worker.error.connect(self._on_vector_error)
        self._vector_worker.start()

    def _on_clusters_ready(self, clusters):
        self._current_clusters = clusters
        if self.dashboard_panel:
            self.dashboard_panel.refresh(self._current_news_items, clusters)
        self.logger.info(f"聚类完成，共 {len(clusters)} 个话题")

    def _on_vector_error(self, msg):
        if self.dashboard_panel:
            self.dashboard_panel.set_loading(False)
        self.logger.warning(f"向量化失败: {msg}")

    # ------------------------------------------------------------------
    # 话题点击
    # ------------------------------------------------------------------

    def _on_topic_clicked(self, cluster_data: dict):
        if not self.topic_detail_panel:
            return

        # 获取趋势数据
        trend_data = None
        if self.hot_news_manager:
            keyword = cluster_data.get('keyword', '')
            if keyword:
                trend_data = self.hot_news_manager.get_keyword_frequency(keyword, days=30)

        self.topic_detail_panel.set_topic(
            cluster_data,
            self._current_news_items,
            trend_data,
        )

        # 展开侧边详情面板
        self.topic_detail_panel.show()
        total = sum(self._home_splitter.sizes())
        self._home_splitter.setSizes([int(total * 0.6), int(total * 0.4)])

    def _on_topic_news_selected(self, news_item: dict):
        """从话题详情点击新闻 → 切换到"新闻"页并选中"""
        self.main_tabs.setCurrentIndex(1)
        self._on_news_selected(news_item)

    def _on_bookmark_toggled(self, keyword: str):
        """收藏状态变更时刷新追踪面板"""
        if self.tracking_panel:
            self.tracking_panel.refresh_bookmarks()

    # ------------------------------------------------------------------
    # 新闻选中 / 聊天面板更新
    # ------------------------------------------------------------------

    def _on_news_selected(self, news_item):
        self.llm_panel.analyze_news(news_item)
        self.chat_panel.set_current_news(news_item)
        if hasattr(self.chat_panel, 'context_checkbox'):
            self.chat_panel.context_checkbox.setChecked(True)

    def _update_chat_panel_news(self, news_items):
        if hasattr(self.chat_panel, 'set_available_news_titles'):
            self.chat_panel.set_available_news_titles(news_items)

    # ------------------------------------------------------------------
    # 搜索 / 分类筛选
    # ------------------------------------------------------------------

    def search_news(self, query):
        if not query:
            news_items = self.rss_collector.get_all_news()
            self.news_list.update_news(news_items)
            self.chat_panel.set_available_news_titles(news_items)
            self.status_label.setText("显示所有新闻")
            return

        self.status_label.setText(f"搜索: {query}")
        try:
            results = self.rss_collector.search_news(query)
            self.news_list.update_news(results)
            self.chat_panel.set_available_news_titles(results)
            self.status_label.setText(f"搜索 '{query}' 找到 {len(results)} 条结果")
        except Exception as e:
            QMessageBox.warning(self, "搜索失败", f"搜索新闻失败: {str(e)}")
            self.status_label.setText("搜索失败")

    def _search_keyword_news(self, keyword: str):
        """从追踪面板跳转到新闻页搜索关键词"""
        self.main_tabs.setCurrentIndex(1)
        self.search_panel.set_query(keyword)
        self.search_news(keyword)

    def filter_by_category(self, category):
        if category == "所有":
            news_items = self.rss_collector.get_all_news()
            self.news_list.update_news(news_items)
            self.chat_panel.set_available_news_titles(news_items)
            self.status_label.setText("显示所有新闻")
            return

        self.status_label.setText(f"分类: {category}")
        try:
            results = self.rss_collector.get_news_by_category(category)
            self.news_list.update_news(results)
            self.chat_panel.set_available_news_titles(results)
            self.status_label.setText(f"分类 '{category}' 包含 {len(results)} 条新闻")
        except Exception as e:
            QMessageBox.warning(self, "筛选失败", f"筛选新闻失败: {str(e)}")
            self.status_label.setText("筛选失败")

    # ------------------------------------------------------------------
    # 历史新闻加载
    # ------------------------------------------------------------------

    def load_history_news(self, news_items):
        self.news_list.update_news(news_items)
        self.rss_collector.news_cache = news_items
        self.status_label.setText(f"已加载 {len(news_items)} 条历史新闻")
        self.chat_panel.set_available_news_titles(news_items)
        self.main_tabs.setCurrentIndex(1)   # 切换到新闻页
        self.logger.info(f"从历史记录加载了 {len(news_items)} 条新闻")

    # ------------------------------------------------------------------
    # 添加新闻源
    # ------------------------------------------------------------------

    def add_news_source(self):
        dialog = AddSourceDialog(self)
        if dialog.exec_() == QDialog.Accepted:
            values = dialog.get_values()
            if not values['url']:
                QMessageBox.warning(self, "输入错误", "请输入有效的 RSS URL")
                return
            url = values['url']
            name = values['name'] or url.split("//")[-1].split("/")[0]
            category = values['category']
            try:
                self.rss_collector.add_source(url, name, category, is_user_added=True)
                self.sidebar.add_category(category)
                self.status_label.setText(f"已添加新闻源: {name}")
                self.refresh_news(url)
                self.logger.info(f"添加了新闻源: {name} ({url}), 分类: {category}")
            except Exception as e:
                QMessageBox.critical(self, "添加失败", f"无法添加新闻源: {str(e)}")

    # ------------------------------------------------------------------
    # 设置对话框
    # ------------------------------------------------------------------

    def show_settings(self):
        QMessageBox.information(self, "设置", "设置功能开发中...")

    def _show_llm_settings(self):
        dialog = LLMSettingsDialog(self)
        if dialog.exec_():
            dialog.save_settings()
            self._load_llm_settings()
            self.llm_client = LLMClient.from_profile('summary')
            self.llm_panel.llm_client = self.llm_client
            self.chat_panel.llm_client = self.llm_client
            self._update_status_message()
            self.logger.info("语言模型设置已更新")

    def show_about(self):
        QMessageBox.about(
            self, "关于",
            "新闻聚合与分析系统 v2.0\n\n"
            "功能：RSS 抓取、TF-IDF 聚类热点图、日/夜主题切换、\n"
            "话题追踪、LLM 分析与聊天。\n\n"
            "支持 Windows / macOS / Linux。"
        )

    # ------------------------------------------------------------------
    # 关闭事件
    # ------------------------------------------------------------------

    def closeEvent(self, event):
        self._save_settings()
        reply = QMessageBox.question(
            self, '确认退出', "确定要退出程序吗?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self.logger.info("应用程序关闭")
            event.accept()
        else:
            event.ignore()
