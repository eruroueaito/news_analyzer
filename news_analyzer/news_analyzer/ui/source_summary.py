#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
新闻源概览组件模块 - 显示各类别新闻源的统计卡片

该模块实现了一个水平可滚动的新闻源统计卡片行，每张卡片展示一个新闻类别的
文章数量、最新更新时间等信息。卡片使用自定义绘制，支持深色/浅色主题。
"""

from typing import List, Dict, Optional

from PyQt5.QtWidgets import (
    QWidget, QHBoxLayout, QScrollArea, QFrame, QSizePolicy
)
from PyQt5.QtCore import Qt, QRectF, QSize
from PyQt5.QtGui import (
    QPainter, QColor, QFont, QFontMetrics, QLinearGradient,
    QPen, QBrush, QPaintEvent
)

from news_analyzer.ui.theme import ThemeManager


class SourceCard(QFrame):
    """
    单个新闻源统计卡片

    使用 QPainter 自定义绘制，展示以下信息：
    - 类别名称（粗体大号）
    - 文章数量（特大号）
    - 最新更新时间（小号）

    卡片拥有渐变背景和圆角边框，支持主题自适应。
    """

    # 固定卡片尺寸
    CARD_WIDTH = 220
    CARD_HEIGHT = 130

    # 圆角半径
    CORNER_RADIUS = 12

    def __init__(self, data: Dict, parent: Optional[QWidget] = None):
        """
        初始化卡片

        Args:
            data: 包含以下键的字典：
                - category (str): 新闻类别名称
                - count (int): 文章数量
                - latest_time (str): 最新更新时间
                - sources (list[str]): 新闻源列表
            parent: 父组件
        """
        super().__init__(parent)

        # 保存卡片数据
        self._data = data

        # 设置固定大小
        self.setFixedSize(self.CARD_WIDTH, self.CARD_HEIGHT)

        # 去除默认边框样式，完全由 paintEvent 控制绘制
        self.setFrameShape(QFrame.NoFrame)

    def paintEvent(self, event: QPaintEvent):
        """
        自定义绘制卡片

        绘制内容包括：
        1. 渐变背景（深色主题：蓝→紫，浅色主题：暖米色）
        2. 类别名称（粗体，大号字体）
        3. 文章数量（特大号字体）
        4. 最新更新时间（小号字体）
        """
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        theme = ThemeManager.instance()
        is_dark = theme.is_dark()

        w = self.width()
        h = self.height()
        card_rect = QRectF(0, 0, w, h)

        # ---- 绘制渐变背景 ----
        gradient = QLinearGradient(0, 0, w, h)
        if is_dark:
            # 深色主题：蓝色到紫色渐变
            gradient.setColorAt(0, QColor(45, 65, 120, 200))
            gradient.setColorAt(1, QColor(85, 50, 120, 200))
        else:
            # 浅色主题：暖米色渐变
            gradient.setColorAt(0, QColor(245, 235, 215, 220))
            gradient.setColorAt(1, QColor(235, 220, 200, 220))

        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(gradient))
        painter.drawRoundedRect(card_rect, self.CORNER_RADIUS, self.CORNER_RADIUS)

        # 获取文字颜色
        text_primary = theme.get_color('text_primary')
        text_secondary = theme.get_color('text_secondary')
        text_muted = theme.get_color('text_muted')

        # 内边距
        margin = 16

        # ---- 绘制类别名称（粗体，大号）----
        category = self._data.get('category', '未知')
        font_category = QFont()
        font_category.setPointSize(13)
        font_category.setBold(True)

        painter.setFont(font_category)
        painter.setPen(text_primary)

        fm_cat = QFontMetrics(font_category)
        elided_cat = fm_cat.elidedText(category, Qt.ElideRight, w - 2 * margin)
        painter.drawText(
            QRectF(margin, margin, w - 2 * margin, fm_cat.height()),
            Qt.AlignLeft | Qt.AlignVCenter,
            elided_cat
        )

        # ---- 绘制文章数量（特大号字体）----
        count = self._data.get('count', 0)
        font_count = QFont()
        font_count.setPointSize(28)
        font_count.setBold(True)

        painter.setFont(font_count)
        painter.setPen(text_primary)

        fm_count = QFontMetrics(font_count)
        count_text = str(count)
        count_y = margin + fm_cat.height() + 6
        painter.drawText(
            QRectF(margin, count_y, w - 2 * margin, fm_count.height()),
            Qt.AlignLeft | Qt.AlignVCenter,
            count_text
        )

        # 在数量旁边加上"篇"字
        font_unit = QFont()
        font_unit.setPointSize(11)
        painter.setFont(font_unit)
        painter.setPen(text_secondary)

        unit_x = margin + fm_count.width(count_text) + 4
        fm_unit = QFontMetrics(font_unit)
        painter.drawText(
            QRectF(unit_x, count_y + fm_count.height() - fm_unit.height() - 4,
                   w - unit_x - margin, fm_unit.height()),
            Qt.AlignLeft | Qt.AlignVCenter,
            '篇'
        )

        # ---- 绘制最新更新时间（小号字体）----
        latest_time = self._data.get('latest_time', '')
        if latest_time:
            font_time = QFont()
            font_time.setPointSize(9)

            painter.setFont(font_time)
            painter.setPen(text_muted)

            fm_time = QFontMetrics(font_time)
            time_text = f'最新: {latest_time}'
            elided_time = fm_time.elidedText(time_text, Qt.ElideRight, w - 2 * margin)
            painter.drawText(
                QRectF(margin, h - margin - fm_time.height(),
                       w - 2 * margin, fm_time.height()),
                Qt.AlignLeft | Qt.AlignVCenter,
                elided_time
            )

        painter.end()

    def update_data(self, data: Dict):
        """
        更新卡片数据并重绘

        Args:
            data: 新的卡片数据字典
        """
        self._data = data
        self.update()


class SourceSummaryWidget(QWidget):
    """
    新闻源概览组件

    使用水平可滚动区域展示一组新闻源统计卡片。
    每张卡片代表一个新闻类别，显示该类别的文章数量和最新更新时间。
    """

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)

        # 卡片列表，用于后续更新
        self._cards: List[SourceCard] = []

        # 初始化 UI 布局
        self._init_ui()

        # 连接主题切换信号
        ThemeManager.instance().theme_changed.connect(self._on_theme_changed)

    def _init_ui(self):
        """
        初始化 UI 布局

        创建一个水平可滚动区域，内部使用 QHBoxLayout 排列卡片。
        """
        # 主布局
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # 滚动区域
        self._scroll_area = QScrollArea()
        self._scroll_area.setWidgetResizable(True)
        self._scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll_area.setFrameShape(QFrame.NoFrame)

        # 滚动区域内的容器组件
        self._container = QWidget()
        self._card_layout = QHBoxLayout(self._container)
        self._card_layout.setContentsMargins(8, 8, 8, 8)
        self._card_layout.setSpacing(12)
        # 在右侧添加弹性空间，使卡片靠左排列
        self._card_layout.addStretch()

        self._scroll_area.setWidget(self._container)
        main_layout.addWidget(self._scroll_area)

    def set_data(self, source_stats: List[Dict]):
        """
        设置新闻源统计数据并刷新卡片

        清除旧卡片后，为每条统计数据创建新的 SourceCard 并添加到布局中。

        Args:
            source_stats: 统计数据列表，每个字典包含：
                - category (str): 新闻类别
                - count (int): 文章数量
                - latest_time (str): 最新更新时间
                - sources (list[str]): 新闻源列表
        """
        # 清除旧卡片
        self._clear_cards()

        # 创建新卡片
        for stat in source_stats:
            card = SourceCard(stat, self._container)
            # 在弹性空间之前插入卡片
            self._card_layout.insertWidget(self._card_layout.count() - 1, card)
            self._cards.append(card)

    def _clear_cards(self):
        """
        清除所有现有卡片

        从布局中移除并销毁所有 SourceCard 实例。
        """
        for card in self._cards:
            self._card_layout.removeWidget(card)
            card.deleteLater()
        self._cards.clear()

    def _on_theme_changed(self, is_dark: bool):
        """
        主题切换回调

        当全局主题变化时，更新所有卡片的绘制。

        Args:
            is_dark: 是否切换为深色主题
        """
        for card in self._cards:
            card.update()
