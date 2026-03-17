#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
话题详情面板

点击 Treemap 话题块后展示的详情视图：
关键词、热度值、收藏按钮、趋势折线图、相关新闻列表。
"""

from typing import Optional, List, Dict

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QFrame,
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont

from news_analyzer.ui.theme import ThemeManager
from news_analyzer.ui.trend_chart import TrendChartWidget
from news_analyzer.storage.bookmark_store import BookmarkStore


class TopicDetailPanel(QWidget):
    """
    话题详情面板

    Signals:
        news_item_selected(dict): 用户双击某条关联新闻时发出
        bookmark_toggled(str): 收藏状态变更时发出（关键词）
    """

    news_item_selected = pyqtSignal(dict)
    bookmark_toggled = pyqtSignal(str)
    back_requested = pyqtSignal()

    def __init__(self, bookmark_store: BookmarkStore,
                 parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._bookmark_store = bookmark_store
        self._current_cluster: Optional[Dict] = None
        self._news_items: List[Dict] = []
        self._init_ui()
        ThemeManager.instance().theme_changed.connect(self._on_theme_changed)

    # ------------------------------------------------------------------
    # UI 初始化
    # ------------------------------------------------------------------
    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # ---- 顶部：返回按钮 + 关键词 + 热度标签 + 收藏按钮 ----
        header = QHBoxLayout()

        self._back_btn = QPushButton("← 返回")
        self._back_btn.setFixedWidth(72)
        self._back_btn.clicked.connect(self.back_requested)
        header.addWidget(self._back_btn)

        self._keyword_label = QLabel("—")
        kw_font = QFont()
        kw_font.setPointSize(16)
        kw_font.setBold(True)
        self._keyword_label.setFont(kw_font)
        self._keyword_label.setWordWrap(True)
        header.addWidget(self._keyword_label, 1)

        self._heat_badge = QLabel("热度 0")
        self._heat_badge.setAlignment(Qt.AlignCenter)
        self._heat_badge.setFixedSize(80, 28)
        header.addWidget(self._heat_badge)

        self._bookmark_btn = QPushButton("☆ 收藏")
        self._bookmark_btn.setFixedWidth(84)
        self._bookmark_btn.clicked.connect(self._toggle_bookmark)
        header.addWidget(self._bookmark_btn)

        layout.addLayout(header)

        # ---- 相关关键词 ----
        self._related_label = QLabel("")
        self._related_label.setWordWrap(True)
        self._related_label.setObjectName("related_label")
        layout.addWidget(self._related_label)

        # ---- 分割线 ----
        layout.addWidget(self._make_divider())

        # ---- 趋势图 ----
        trend_header = QLabel("频率趋势（近30天）")
        trend_header.setObjectName("section_label")
        layout.addWidget(trend_header)

        self._trend_chart = TrendChartWidget(self)
        self._trend_chart.setFixedHeight(160)
        layout.addWidget(self._trend_chart)

        # ---- 分割线 ----
        layout.addWidget(self._make_divider())

        # ---- 相关新闻列表 ----
        news_header = QLabel("相关新闻")
        news_header.setObjectName("section_label")
        layout.addWidget(news_header)

        self._news_list = QListWidget()
        self._news_list.setAlternatingRowColors(True)
        self._news_list.itemDoubleClicked.connect(self._on_news_double_clicked)
        layout.addWidget(self._news_list, 1)

        self._apply_theme()

    def _make_divider(self) -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setObjectName("divider")
        return line

    # ------------------------------------------------------------------
    # 公开接口
    # ------------------------------------------------------------------
    def set_topic(self, cluster_data: Dict,
                  news_items: List[Dict] = None,
                  trend_data: List[Dict] = None):
        """
        展示话题详情

        Args:
            cluster_data: 聚类数据字典（keyword, heat, related_keywords, news_indices, …）
            news_items: 全量新闻，用于过滤关联新闻（可选）
            trend_data: 趋势数据 [{'date': 'YYYYMMDD', 'count': int}]（可选）
        """
        self._current_cluster = cluster_data
        self._news_items = news_items or []

        keyword = cluster_data.get('keyword', '—')
        heat = cluster_data.get('heat', 0)
        related = cluster_data.get('related_keywords', [])

        self._keyword_label.setText(keyword)
        self._heat_badge.setText(f"热度 {heat:.0f}")
        self._related_label.setText(
            "相关词：" + "  ·  ".join(related[:8]) if related else ""
        )

        self._update_bookmark_btn(keyword)
        self._trend_chart.set_keyword(keyword)
        if trend_data:
            self._trend_chart.set_data(trend_data)

        # 填充相关新闻
        self._news_list.clear()
        indices = cluster_data.get('news_indices', [])
        shown = 0
        for idx in indices:
            if idx < len(self._news_items):
                item_data = self._news_items[idx]
                title = item_data.get('title', '无标题')
                source = item_data.get('source', item_data.get('source_name', ''))
                date = (item_data.get('pub_date', '') or '')[:16]
                list_item = QListWidgetItem(f"{title}\n  {source}  {date}")
                list_item.setData(Qt.UserRole, item_data)
                self._news_list.addItem(list_item)
                shown += 1
                if shown >= 50:
                    break

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------
    def _update_bookmark_btn(self, keyword: str):
        if self._bookmark_store.is_bookmarked(keyword):
            self._bookmark_btn.setText("★ 已收藏")
        else:
            self._bookmark_btn.setText("☆ 收藏")

    def _toggle_bookmark(self):
        if not self._current_cluster:
            return
        keyword = self._current_cluster.get('keyword', '')
        if not keyword:
            return
        if self._bookmark_store.is_bookmarked(keyword):
            self._bookmark_store.remove_bookmark(keyword)
        else:
            self._bookmark_store.add_bookmark(keyword)
        self._update_bookmark_btn(keyword)
        self.bookmark_toggled.emit(keyword)

    def _on_news_double_clicked(self, item: QListWidgetItem):
        news = item.data(Qt.UserRole)
        if news:
            self.news_item_selected.emit(news)

    def _apply_theme(self):
        tm = ThemeManager.instance()
        accent = tm.get_color_hex('accent')
        text_sec = tm.get_color_hex('text_secondary')
        border = tm.get_color_hex('border')

        self._heat_badge.setStyleSheet(
            f"background-color: {accent}; color: #ffffff; "
            f"border: 1px solid {accent}; border-radius: 14px; "
            f"font-size: 11px; font-weight: bold;"
        )
        self._related_label.setStyleSheet(
            f"color: {text_sec}; font-size: 12px;"
        )
        for lbl in self.findChildren(QLabel):
            if lbl.objectName() == 'section_label':
                lbl.setStyleSheet(
                    f"color: {text_sec}; font-size: 11px; font-weight: bold;"
                )
        for frm in self.findChildren(QFrame):
            if frm.objectName() == 'divider':
                frm.setStyleSheet(f"color: {border};")

    def _on_theme_changed(self, is_dark: bool):
        self._apply_theme()
