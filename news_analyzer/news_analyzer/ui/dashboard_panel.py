#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
仪表盘面板模块 - 新闻分析仪表盘的主容器

该模块实现了仪表盘面板，将新闻源概览（SourceSummaryWidget）和
话题热度树图（TreemapWidget）整合在一个垂直布局中。
负责数据的分发处理和子组件的协调更新。
"""

from typing import List, Dict, Optional
from collections import defaultdict

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QSizePolicy, QSplitter
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont

from news_analyzer.ui.theme import ThemeManager
from news_analyzer.ui.treemap_widget import TreemapWidget
from news_analyzer.ui.source_summary import SourceSummaryWidget


class DashboardPanel(QWidget):
    """
    仪表盘主面板

    垂直布局包含两个子组件：
    1. SourceSummaryWidget（顶部，固定高度约 150px）：新闻源分类概览
    2. TreemapWidget（底部，填充剩余空间）：话题热度矩形树图

    负责接收新闻数据和聚类数据，处理后分发给对应的子组件。

    Signals:
        topic_clicked(dict): 从 TreemapWidget 转发的话题点击信号
    """

    # 话题点击信号，从 TreemapWidget 转发
    topic_clicked = pyqtSignal(dict)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)

        # 加载状态标志
        self._is_loading = False

        # 初始化 UI 布局和子组件
        self._init_ui()

        # 连接主题切换信号
        ThemeManager.instance().theme_changed.connect(self._on_theme_changed)

    def _init_ui(self):
        """
        初始化 UI 布局

        创建垂直布局，上方放置 SourceSummaryWidget，下方放置左右分割的双 TreemapWidget。
        """
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # ---- 新闻源概览区域（固定高度 ~150px）----
        self._source_summary = SourceSummaryWidget(self)
        self._source_summary.setFixedHeight(150)
        layout.addWidget(self._source_summary)

        # ---- 左右分割的双 TreemapWidget ----
        treemap_splitter = QSplitter(Qt.Horizontal)

        en_container, self._treemap_en = self._create_treemap_container("🌐 英文热点")
        zh_container, self._treemap_zh = self._create_treemap_container("中文热点")
        treemap_splitter.addWidget(en_container)
        treemap_splitter.addWidget(zh_container)

        treemap_splitter.setSizes([1, 1])
        layout.addWidget(treemap_splitter, 1)

        # 转发两个 treemap 的 topic_clicked 信号
        self._treemap_en.topic_clicked.connect(self.topic_clicked)
        self._treemap_zh.topic_clicked.connect(self.topic_clicked)

        # ---- 加载状态提示标签（默认隐藏）----
        self._loading_label = QLabel('数据加载中...', self)
        self._loading_label.setAlignment(Qt.AlignCenter)
        font = QFont()
        font.setPointSize(14)
        self._loading_label.setFont(font)
        self._loading_label.setVisible(False)
        # 加载标签覆盖在内容上方
        self._loading_label.setStyleSheet(
            'background-color: rgba(0, 0, 0, 120); color: white; '
            'border-radius: 8px; padding: 20px;'
        )

    @staticmethod
    def _create_treemap_container(header_text: str):
        """创建带标题的 TreemapWidget 容器

        Args:
            header_text: 显示在 TreemapWidget 上方的标题文本

        Returns:
            tuple[QWidget, TreemapWidget]: (容器 widget, 内部 TreemapWidget)
        """
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        header = QLabel(header_text)
        header.setAlignment(Qt.AlignCenter)
        header.setObjectName("treemap_header")
        layout.addWidget(header)

        treemap = TreemapWidget(container)
        treemap.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout.addWidget(treemap, 1)

        return container, treemap

    def refresh(self, news_items: List[Dict],
                en_clusters: List[Dict], zh_clusters: List[Dict]):
        """
        刷新仪表盘数据

        根据新闻列表计算各类别统计数据，更新 SourceSummaryWidget；
        将英文/中文聚类数据分别传给对应 TreemapWidget。

        Args:
            news_items: 新闻数据列表
            en_clusters: 英文新闻聚类数据列表
            zh_clusters: 中文新闻聚类数据列表
        """
        # 隐藏加载状态
        self.set_loading(False)

        # 计算新闻源统计数据并更新概览
        source_stats = self._calculate_source_stats(news_items)
        self._source_summary.set_data(source_stats)

        # 分别更新英文/中文话题热度树图
        self._treemap_en.set_data(en_clusters)
        self._treemap_zh.set_data(zh_clusters)

    def _calculate_source_stats(self, news_items: List[Dict]) -> List[Dict]:
        """
        计算各类别的新闻统计数据

        按类别分组新闻条目，统计每个类别的文章数量、最新更新时间和相关新闻源。

        Args:
            news_items: 新闻数据列表

        Returns:
            统计结果列表，每个字典包含：
                - category (str): 类别名称
                - count (int): 文章数量
                - latest_time (str): 最新文章的发布时间
                - sources (list[str]): 该类别下的去重新闻源列表
        """
        if not news_items:
            return []

        # 按类别分组
        category_groups = defaultdict(list)
        for item in news_items:
            category = item.get('category', '未分类')
            category_groups[category].append(item)

        stats = []
        for category, items in category_groups.items():
            # 统计文章数量
            count = len(items)

            # 查找最新发布时间
            times = [item.get('pub_date', '') for item in items if item.get('pub_date')]
            latest_time = ''
            if times:
                # 按字符串排序取最新时间（假设时间格式一致可比较）
                latest_time = max(times)

            # 收集去重的新闻源（字段名为 source_name，兼容旧版 source）
            sources = list(set(
                item.get('source_name') or item.get('source', '')
                for item in items
                if item.get('source_name') or item.get('source')
            ))

            stats.append({
                'category': category,
                'count': count,
                'latest_time': latest_time,
                'sources': sources,
            })

        # 按文章数量降序排列
        stats.sort(key=lambda x: x['count'], reverse=True)

        return stats

    def set_loading(self, loading: bool):
        """
        设置加载状态

        当数据正在处理时，显示半透明遮罩和加载提示文字。

        Args:
            loading: 是否处于加载状态
        """
        self._is_loading = loading
        self._loading_label.setVisible(loading)

        if loading:
            # 将加载标签居中覆盖在面板上方
            self._loading_label.setGeometry(
                self.width() // 2 - 100,
                self.height() // 2 - 30,
                200, 60
            )

    def resizeEvent(self, event):
        """
        组件尺寸变化事件

        更新加载标签的位置，使其始终居中。
        """
        super().resizeEvent(event)
        if self._is_loading:
            self._loading_label.setGeometry(
                self.width() // 2 - 100,
                self.height() // 2 - 30,
                200, 60
            )

    def _on_theme_changed(self, is_dark: bool):
        """
        主题切换回调

        更新加载标签的样式以适配新主题。

        Args:
            is_dark: 是否切换为深色主题
        """
        if is_dark:
            self._loading_label.setStyleSheet(
                'background-color: rgba(0, 0, 0, 120); color: white; '
                'border-radius: 8px; padding: 20px;'
            )
        else:
            self._loading_label.setStyleSheet(
                'background-color: rgba(255, 255, 255, 180); color: #333; '
                'border-radius: 8px; padding: 20px;'
            )
