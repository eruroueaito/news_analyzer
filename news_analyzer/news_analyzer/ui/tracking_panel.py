#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
收藏追踪面板

左侧：已收藏的关键词列表。
右侧：选中关键词的趋势图和统计数字，支持时间范围切换。
"""

from typing import Optional

from PyQt5.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QListWidget, QListWidgetItem,
    QLabel, QPushButton, QSplitter, QComboBox,
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont

from news_analyzer.ui.theme import ThemeManager
from news_analyzer.ui.trend_chart import TrendChartWidget
from news_analyzer.storage.bookmark_store import BookmarkStore


class TrackingPanel(QWidget):
    """
    收藏话题追踪面板

    Signals:
        keyword_news_requested(str): 用户请求某关键词的相关新闻时发出
        bookmark_changed(): 收藏列表发生变动时发出
    """

    keyword_news_requested = pyqtSignal(str)
    bookmark_changed = pyqtSignal()

    def __init__(self, bookmark_store: BookmarkStore,
                 hot_news_manager=None,
                 parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._bookmark_store = bookmark_store
        self._hot_news_manager = hot_news_manager
        self._current_keyword: Optional[str] = None
        self._init_ui()
        ThemeManager.instance().theme_changed.connect(self._on_theme_changed)

    # ------------------------------------------------------------------
    # UI 初始化
    # ------------------------------------------------------------------
    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # ---- 标题 ----
        title = QLabel("话题追踪")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title.setFont(title_font)
        layout.addWidget(title)

        # ---- 主分割器：左侧书签列表 | 右侧趋势图 ----
        splitter = QSplitter(Qt.Horizontal)

        # 左侧
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(6)

        list_label = QLabel("已收藏关键词")
        list_label.setObjectName("section_label")
        left_layout.addWidget(list_label)

        self._bookmarks_list = QListWidget()
        self._bookmarks_list.currentItemChanged.connect(self._on_keyword_selected)
        left_layout.addWidget(self._bookmarks_list)

        btn_row = QHBoxLayout()
        self._delete_btn = QPushButton("删除收藏")
        self._delete_btn.clicked.connect(self._delete_selected)
        btn_row.addWidget(self._delete_btn)

        self._view_news_btn = QPushButton("查看相关新闻")
        self._view_news_btn.clicked.connect(self._view_news)
        btn_row.addWidget(self._view_news_btn)
        left_layout.addLayout(btn_row)

        splitter.addWidget(left)

        # 右侧
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)

        chart_header = QHBoxLayout()
        self._chart_title = QLabel("选择关键词以查看趋势")
        self._chart_title.setObjectName("section_label")
        chart_header.addWidget(self._chart_title, 1)

        self._days_combo = QComboBox()
        self._days_combo.addItem("近7天", 7)
        self._days_combo.addItem("近14天", 14)
        self._days_combo.addItem("近30天", 30)
        self._days_combo.currentIndexChanged.connect(self._refresh_chart)
        chart_header.addWidget(self._days_combo)
        right_layout.addLayout(chart_header)

        self._trend_chart = TrendChartWidget(self)
        right_layout.addWidget(self._trend_chart, 1)

        self._stats_label = QLabel("")
        self._stats_label.setObjectName("stats_label")
        self._stats_label.setWordWrap(True)
        right_layout.addWidget(self._stats_label)

        splitter.addWidget(right)
        splitter.setSizes([220, 580])
        layout.addWidget(splitter, 1)

        self.refresh_bookmarks()
        self._apply_theme()

    # ------------------------------------------------------------------
    # 公开接口
    # ------------------------------------------------------------------
    def refresh_bookmarks(self):
        """刷新收藏关键词列表"""
        self._bookmarks_list.clear()
        bookmarks = self._bookmark_store.get_bookmarks()
        if bookmarks:
            for bm in bookmarks:
                item = QListWidgetItem(bm['keyword'])
                item.setData(Qt.UserRole, bm)
                self._bookmarks_list.addItem(item)
        else:
            placeholder = QListWidgetItem("暂无收藏话题")
            placeholder.setFlags(Qt.NoItemFlags)
            self._bookmarks_list.addItem(placeholder)

    def set_hot_news_manager(self, manager):
        """注入 HotNewsManager（可在初始化后延迟设置）"""
        self._hot_news_manager = manager

    # ------------------------------------------------------------------
    # 内部槽
    # ------------------------------------------------------------------
    def _on_keyword_selected(self, current, _previous):
        if not current:
            return
        kw = current.text()
        if kw == "暂无收藏话题":
            return
        self._current_keyword = kw
        self._chart_title.setText(f"频率趋势：{kw}")
        self._trend_chart.set_keyword(kw)
        self._refresh_chart()

    def _refresh_chart(self):
        if not self._current_keyword or not self._hot_news_manager:
            self._stats_label.setText(
                "暂无历史数据（需先刷新新闻积累数据）" if self._current_keyword else ""
            )
            return
        days = self._days_combo.currentData()
        data = self._hot_news_manager.get_keyword_frequency(self._current_keyword, days=days)
        self._trend_chart.set_data(data)

        total = sum(d['count'] for d in data)
        peak = max((d['count'] for d in data), default=0)
        self._stats_label.setText(f"近{days}天共出现 {total} 次，峰值 {peak} 次/天")

    def _delete_selected(self):
        item = self._bookmarks_list.currentItem()
        if not item or item.text() == "暂无收藏话题":
            return
        self._bookmark_store.remove_bookmark(item.text())
        self.refresh_bookmarks()
        self._current_keyword = None
        self._chart_title.setText("选择关键词以查看趋势")
        self._stats_label.setText("")
        self.bookmark_changed.emit()

    def _view_news(self):
        if self._current_keyword:
            self.keyword_news_requested.emit(self._current_keyword)

    def _apply_theme(self):
        tm = ThemeManager.instance()
        text_sec = tm.get_color_hex('text_secondary')
        for lbl in self.findChildren(QLabel):
            obj = lbl.objectName()
            if obj in ('section_label', 'stats_label'):
                lbl.setStyleSheet(
                    f"color: {text_sec}; font-size: {'11px; font-weight: bold;' if obj == 'section_label' else '12px;'}"
                )

    def _on_theme_changed(self, is_dark: bool):
        self._apply_theme()
