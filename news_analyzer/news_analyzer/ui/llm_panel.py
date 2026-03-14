# -*- coding: utf-8 -*-
"""
LLM 分层分析面板

选择新闻后自动展示摘要 + 关键观点（快速分析），
用户可点击"深度分析"按钮触发深度分析 + 事实核查。
"""

import logging
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout,
                             QPushButton, QLabel, QTextBrowser, QProgressBar,
                             QFrame, QScrollArea)
from PyQt5.QtCore import Qt, QThread, pyqtSignal


# ---------------------------------------------------------------------------
# 分析工作线程：在后台调用 LLM API，完成后通过信号返回结果
# ---------------------------------------------------------------------------
class AnalysisThread(QThread):
    """分析线程 —— 执行单种类型的 LLM 分析"""

    analysis_complete = pyqtSignal(str, str)   # (analysis_type, result_html)
    analysis_error = pyqtSignal(str, str)      # (analysis_type, error_msg)

    def __init__(self, llm_client, news_item, analysis_type):
        super().__init__()
        self.llm_client = llm_client
        self.news_item = news_item
        self.analysis_type = analysis_type

    def run(self):
        try:
            result = self.llm_client.analyze_news(self.news_item, self.analysis_type)
            self.analysis_complete.emit(self.analysis_type, result)
        except Exception as e:
            self.analysis_error.emit(self.analysis_type, str(e))


# ---------------------------------------------------------------------------
# LLM 分层分析面板
# ---------------------------------------------------------------------------
class LLMPanel(QWidget):
    """分层 LLM 分析面板

    第一层（自动触发）：摘要 + 关键观点
    第二层（按钮触发）：深度分析 + 事实核查
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        self.logger = logging.getLogger('news_analyzer.ui.llm_panel')
        self.llm_client = None          # 由 MainWindow 注入
        self.current_news = None
        self._threads = []              # 保持线程引用防止回收

        self._init_ui()

    # ------------------------------------------------------------------
    # UI 初始化
    # ------------------------------------------------------------------
    def _init_ui(self):
        """初始化分层分析界面"""
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # ---- 标题 ----
        title = QLabel("新闻分析")
        title.setProperty("heading", True)
        layout.addWidget(title)

        # ---- 第一层：摘要 + 关键观点（自动执行） ----
        self.quick_status = QLabel("请选择新闻进行分析")
        layout.addWidget(self.quick_status)

        self.quick_progress = QProgressBar()
        self.quick_progress.setRange(0, 0)
        self.quick_progress.setVisible(False)
        layout.addWidget(self.quick_progress)

        # 摘要结果区
        self.summary_label = QLabel("摘要")
        self.summary_label.setProperty("sectionTitle", True)
        self.summary_label.setVisible(False)
        layout.addWidget(self.summary_label)

        self.summary_browser = QTextBrowser()
        self.summary_browser.setOpenExternalLinks(True)
        self.summary_browser.setVisible(False)
        self.summary_browser.setMaximumHeight(250)
        layout.addWidget(self.summary_browser)

        # 关键观点结果区
        self.perspectives_label = QLabel("关键观点")
        self.perspectives_label.setProperty("sectionTitle", True)
        self.perspectives_label.setVisible(False)
        layout.addWidget(self.perspectives_label)

        self.perspectives_browser = QTextBrowser()
        self.perspectives_browser.setOpenExternalLinks(True)
        self.perspectives_browser.setVisible(False)
        self.perspectives_browser.setMaximumHeight(250)
        layout.addWidget(self.perspectives_browser)

        # ---- 分隔线 ----
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        layout.addWidget(separator)

        # ---- 第二层：深度分析按钮 ----
        self.deep_button = QPushButton("深度分析")
        self.deep_button.setToolTip("执行深度分析和事实核查（需要更多时间）")
        self.deep_button.setEnabled(False)
        self.deep_button.clicked.connect(self._on_deep_analyze)
        layout.addWidget(self.deep_button)

        self.deep_progress = QProgressBar()
        self.deep_progress.setRange(0, 0)
        self.deep_progress.setVisible(False)
        layout.addWidget(self.deep_progress)

        # 深度分析结果区
        self.deep_label = QLabel("深度分析")
        self.deep_label.setProperty("sectionTitle", True)
        self.deep_label.setVisible(False)
        layout.addWidget(self.deep_label)

        self.deep_browser = QTextBrowser()
        self.deep_browser.setOpenExternalLinks(True)
        self.deep_browser.setVisible(False)
        self.deep_browser.setMaximumHeight(250)
        layout.addWidget(self.deep_browser)

        # 事实核查结果区
        self.fact_label = QLabel("事实核查")
        self.fact_label.setProperty("sectionTitle", True)
        self.fact_label.setVisible(False)
        layout.addWidget(self.fact_label)

        self.fact_browser = QTextBrowser()
        self.fact_browser.setOpenExternalLinks(True)
        self.fact_browser.setVisible(False)
        self.fact_browser.setMaximumHeight(250)
        layout.addWidget(self.fact_browser)

        layout.addStretch()

    # ------------------------------------------------------------------
    # 公共接口
    # ------------------------------------------------------------------
    def analyze_news(self, news_item):
        """新闻被选中时调用，自动触发摘要 + 关键观点

        Args:
            news_item: 新闻数据字典
        """
        self.current_news = news_item

        # 重置所有结果区域
        self._reset_results()

        title_text = news_item.get('title', '无标题')[:40]
        self.quick_status.setText(f"正在分析: {title_text}...")
        self.quick_progress.setVisible(True)

        # 并发启动摘要和关键观点分析
        self._start_analysis('摘要')
        self._start_analysis('关键观点')

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------
    def _reset_results(self):
        """重置所有结果区域为初始状态"""
        for browser in [self.summary_browser, self.perspectives_browser,
                        self.deep_browser, self.fact_browser]:
            browser.setHtml("")
            browser.setVisible(False)

        for label in [self.summary_label, self.perspectives_label,
                      self.deep_label, self.fact_label]:
            label.setVisible(False)

        self.deep_button.setEnabled(False)
        self.deep_progress.setVisible(False)
        self._quick_done_count = 0   # 跟踪快速分析完成数

    def _start_analysis(self, analysis_type):
        """启动指定类型的后台分析线程"""
        if not self.llm_client or not self.current_news:
            return

        thread = AnalysisThread(self.llm_client, self.current_news, analysis_type)
        thread.analysis_complete.connect(self._on_result)
        thread.analysis_error.connect(self._on_error)
        thread.finished.connect(lambda: self._cleanup_thread(thread))
        self._threads.append(thread)
        thread.start()

    def _cleanup_thread(self, thread):
        """线程结束后从列表中移除"""
        if thread in self._threads:
            self._threads.remove(thread)

    def _on_deep_analyze(self):
        """用户点击"深度分析"按钮"""
        if not self.current_news:
            return

        self.deep_button.setEnabled(False)
        self.deep_progress.setVisible(True)

        self._start_analysis('深度分析')
        self._start_analysis('事实核查')

    def _on_result(self, analysis_type, result_html):
        """处理分析结果

        Args:
            analysis_type: 分析类型名称
            result_html: 结果 HTML 内容
        """
        # 根据类型路由到对应浏览器
        mapping = {
            '摘要': (self.summary_label, self.summary_browser),
            '关键观点': (self.perspectives_label, self.perspectives_browser),
            '深度分析': (self.deep_label, self.deep_browser),
            '事实核查': (self.fact_label, self.fact_browser),
        }

        if analysis_type in mapping:
            label, browser = mapping[analysis_type]
            label.setVisible(True)
            browser.setHtml(result_html)
            browser.setVisible(True)

        # 检查快速分析是否全部完成
        if analysis_type in ('摘要', '关键观点'):
            self._quick_done_count = getattr(self, '_quick_done_count', 0) + 1
            if self._quick_done_count >= 2:
                self.quick_progress.setVisible(False)
                self.quick_status.setText("快速分析完成")
                self.deep_button.setEnabled(True)

        # 检查深度分析是否全部完成
        if analysis_type in ('深度分析', '事实核查'):
            deep_done = self.deep_browser.isVisible() and self.fact_browser.isVisible()
            if deep_done:
                self.deep_progress.setVisible(False)

        self.logger.info(f"{analysis_type}分析完成")

    def _on_error(self, analysis_type, error_msg):
        """处理分析错误"""
        mapping = {
            '摘要': (self.summary_label, self.summary_browser),
            '关键观点': (self.perspectives_label, self.perspectives_browser),
            '深度分析': (self.deep_label, self.deep_browser),
            '事实核查': (self.fact_label, self.fact_browser),
        }

        if analysis_type in mapping:
            label, browser = mapping[analysis_type]
            label.setVisible(True)
            browser.setHtml(f"<p style='color:red;'>分析失败: {error_msg}</p>")
            browser.setVisible(True)

        # 同样处理进度条隐藏逻辑
        if analysis_type in ('摘要', '关键观点'):
            self._quick_done_count = getattr(self, '_quick_done_count', 0) + 1
            if self._quick_done_count >= 2:
                self.quick_progress.setVisible(False)
                self.quick_status.setText("分析完成（部分失败）")
                self.deep_button.setEnabled(True)

        if analysis_type in ('深度分析', '事实核查'):
            if self.deep_browser.isVisible() and self.fact_browser.isVisible():
                self.deep_progress.setVisible(False)

        self.logger.error(f"{analysis_type}分析失败: {error_msg}")
