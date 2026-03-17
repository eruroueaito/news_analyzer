#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
新闻原文阅读器

在"新闻"标签页右侧面板中作为默认视图展示当前选中新闻的详情：
标题、来源、日期、摘要/正文（HTML 渲染），以及"分析"与"打开原文"按钮。
"""

from typing import Optional, Dict

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTextBrowser, QSizePolicy,
)
from PyQt5.QtCore import Qt, pyqtSignal, QUrl
from PyQt5.QtGui import QFont, QDesktopServices

from news_analyzer.ui.theme import ThemeManager


class NewsReaderWidget(QWidget):
    """新闻原文阅读器

    Signals:
        analyze_requested(): 用户点击"分析"按钮时发出，通知外部切换到分析面板
    """

    analyze_requested = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._current_news: Optional[Dict] = None
        self._init_ui()
        ThemeManager.instance().theme_changed.connect(self._apply_theme)

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # ---- 顶部工具栏 ----
        toolbar = QHBoxLayout()
        toolbar.setSpacing(6)

        self._analyze_btn = QPushButton("🔍 分析")
        self._analyze_btn.setFixedHeight(28)
        self._analyze_btn.setEnabled(False)
        self._analyze_btn.clicked.connect(self.analyze_requested)
        toolbar.addWidget(self._analyze_btn)

        self._open_btn = QPushButton("🌐 打开原文")
        self._open_btn.setFixedHeight(28)
        self._open_btn.setEnabled(False)
        self._open_btn.clicked.connect(self._open_in_browser)
        toolbar.addWidget(self._open_btn)

        toolbar.addStretch()
        layout.addLayout(toolbar)

        # ---- 标题 ----
        self._title_label = QLabel("")
        self._title_label.setWordWrap(True)
        self._title_label.setObjectName("reader_title")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        self._title_label.setFont(title_font)
        layout.addWidget(self._title_label)

        # ---- 元信息行（来源 + 日期）----
        self._meta_label = QLabel("")
        self._meta_label.setObjectName("reader_meta")
        layout.addWidget(self._meta_label)

        # ---- 正文内容（QTextBrowser 支持基本 HTML）----
        self._content = QTextBrowser()
        self._content.setOpenLinks(False)       # 链接由 _open_in_browser 处理
        self._content.setReadOnly(True)
        self._content.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._content.setObjectName("reader_content")
        layout.addWidget(self._content, 1)

        # ---- 空状态提示（默认显示）----
        self._empty_label = QLabel("点击左侧新闻条目以阅读原文")
        self._empty_label.setAlignment(Qt.AlignCenter)
        self._empty_label.setObjectName("reader_empty")
        layout.addWidget(self._empty_label)
        self._empty_label.setVisible(True)
        self._content.setVisible(False)
        self._title_label.setVisible(False)
        self._meta_label.setVisible(False)

        self._apply_theme()

    # ------------------------------------------------------------------
    # 公开接口
    # ------------------------------------------------------------------

    def set_news(self, news_item: Optional[Dict]):
        """填充新闻内容

        Args:
            news_item: 新闻数据字典（含 title, description, link, source_name, pub_date）
        """
        self._current_news = news_item

        if not news_item:
            self._show_empty()
            return

        title = news_item.get('title', '无标题')
        source = news_item.get('source_name') or news_item.get('source', '')
        date = (news_item.get('pub_date', '') or '')[:16]
        description = news_item.get('description', '') or news_item.get('content', '') or ''
        link = news_item.get('link', '')

        self._title_label.setText(title)
        self._meta_label.setText(
            f"<b>{source}</b>  ·  {date}" if source else date
        )

        # 渲染正文（保留来自 RSS 的基本 HTML，去除脚本标签）
        safe_html = self._sanitize_html(description)
        if safe_html.strip():
            self._content.setHtml(safe_html)
        else:
            self._content.setPlainText("（无摘要内容）")

        # 切换可见性
        self._empty_label.setVisible(False)
        self._title_label.setVisible(True)
        self._meta_label.setVisible(True)
        self._content.setVisible(True)

        self._analyze_btn.setEnabled(True)
        self._open_btn.setEnabled(bool(link))

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    def _show_empty(self):
        self._empty_label.setVisible(True)
        self._title_label.setVisible(False)
        self._meta_label.setVisible(False)
        self._content.setVisible(False)
        self._analyze_btn.setEnabled(False)
        self._open_btn.setEnabled(False)

    def _open_in_browser(self):
        if self._current_news:
            link = self._current_news.get('link', '')
            if link:
                QDesktopServices.openUrl(QUrl(link))

    @staticmethod
    def _sanitize_html(html: str) -> str:
        """移除 <script>/<style> 标签，保留其他 HTML"""
        import re
        html = re.sub(r'<script[^>]*>.*?</script>', '', html,
                      flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r'<style[^>]*>.*?</style>', '', html,
                      flags=re.DOTALL | re.IGNORECASE)
        return html

    def _apply_theme(self, is_dark: bool = False):
        tm = ThemeManager.instance()
        text_sec  = tm.get_color_hex('text_secondary')   # '#6B6560' / '#8B949E'
        text_main = tm.get_color_hex('text_primary')     # '#2D2D2A' / '#E6EDF3'
        border    = tm.get_color_hex('border')           # '#E0DBD4' / '#30363D'
        bg_card   = tm.get_color_hex('bg_card')          # '#FFFFFF'  / '#161B22'

        self._meta_label.setStyleSheet(
            f"color: {text_sec}; font-size: 12px;"
        )
        self._empty_label.setStyleSheet(
            f"color: {text_sec}; font-size: 13px;"
        )
        # QTextBrowser: 使用正确的颜色键；Qt 不支持 line-height，去掉它
        self._content.setStyleSheet(
            f"QTextBrowser {{"
            f"  background-color: {bg_card}; color: {text_main}; "
            f"  border: 1px solid {border}; border-radius: 4px; "
            f"  padding: 8px; font-size: 13px;"
            f"}}"
        )
