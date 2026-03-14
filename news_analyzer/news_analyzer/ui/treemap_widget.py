#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
树状图组件模块 - 使用 QPainter 绘制新闻话题热度矩形树图

该模块实现了自定义的矩形树图（Treemap）组件，用于可视化新闻话题聚类的热度分布。
每个矩形块代表一个话题聚类，面积与热度成正比，颜色由聚类分配的颜色决定。
支持鼠标悬停高亮和点击交互。

使用 squarify 库计算矩形布局，QPainter 进行自定义绘制。
"""

from typing import List, Dict, Optional

import squarify
from PyQt5.QtWidgets import QWidget, QToolTip
from PyQt5.QtCore import Qt, QRectF, pyqtSignal, QPointF
from PyQt5.QtGui import (
    QPainter, QPaintEvent, QColor, QFont, QFontMetrics,
    QPen, QBrush, QMouseEvent, QResizeEvent
)

from news_analyzer.ui.theme import ThemeManager


class TreemapWidget(QWidget):
    """
    矩形树图组件

    使用 squarify 算法将话题聚类数据可视化为面积比例的矩形块。
    每个块显示主关键词、相关关键词和热度值。

    Signals:
        topic_clicked(dict): 当用户点击某个话题块时发出，携带该聚类的完整数据字典
    """

    # 话题点击信号，携带被点击聚类的完整数据
    topic_clicked = pyqtSignal(dict)

    # 矩形块之间的间距（像素）
    BLOCK_PADDING = 3

    # 圆角半径
    CORNER_RADIUS = 6

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)

        # 聚类数据列表，每个元素包含 keyword, related_keywords, heat, color, news_indices
        self._clusters: List[Dict] = []

        # squarify 计算出的矩形布局列表
        self._rects: List[Dict] = []

        # 当前鼠标悬停的矩形块索引，-1 表示无悬停
        self._hovered_index: int = -1

        # 启用鼠标追踪以支持悬停检测
        self.setMouseTracking(True)

        # 设置最小尺寸，确保组件有足够空间绘制
        self.setMinimumSize(200, 150)

        # 连接主题切换信号，主题变化时重绘
        ThemeManager.instance().theme_changed.connect(self._on_theme_changed)

    def set_data(self, clusters: List[Dict]):
        """
        设置聚类数据并刷新显示

        Args:
            clusters: 聚类数据列表，每个字典包含以下键：
                - keyword (str): 主关键词
                - related_keywords (list[str]): 相关关键词列表
                - heat (float): 热度值（用于决定矩形面积）
                - color (str|QColor): 该聚类的显示颜色
                - news_indices (list[int]): 关联新闻的索引列表
        """
        self._clusters = clusters or []
        self._hovered_index = -1
        self._calculate_layout()
        self.update()

    def _calculate_layout(self):
        """
        根据当前组件尺寸和聚类数据，使用 squarify 计算矩形布局

        将聚类热度值归一化后，映射到组件的可用绘制区域中。
        每个矩形都会应用内边距以产生视觉间隔。
        """
        self._rects = []

        if not self._clusters:
            return

        # 获取可用绘制区域的宽高
        w = self.width()
        h = self.height()

        if w <= 0 or h <= 0:
            return

        # 提取热度值作为面积权重
        values = [max(c.get('heat', 1), 0.1) for c in self._clusters]

        # 使用 squarify 归一化尺寸并计算布局
        normalized = squarify.normalize_sizes(values, w, h)
        rects = squarify.squarify(normalized, 0, 0, w, h)

        self._rects = rects

    def paintEvent(self, event: QPaintEvent):
        """
        自定义绘制事件

        遍历所有矩形块，使用 QPainter 绘制：
        - 带圆角的半透明彩色背景
        - 居中显示的主关键词（大号粗体）
        - 主关键词下方的相关关键词（小号字体）
        - 右下角的热度数值
        - 悬停时的高亮边框
        """
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        theme = ThemeManager.instance()

        # 如果没有数据，显示提示文字
        if not self._clusters or not self._rects:
            self._draw_empty_state(painter, theme)
            painter.end()
            return

        # 获取主题颜色
        text_primary_color = theme.get_color('text_primary')
        text_secondary_color = theme.get_color('text_secondary')
        text_muted_color = theme.get_color('text_muted')

        # 准备字体
        font_large = QFont()
        font_large.setPointSize(14)
        font_large.setBold(True)

        font_small = QFont()
        font_small.setPointSize(9)

        font_heat = QFont()
        font_heat.setPointSize(8)
        font_heat.setBold(True)

        pad = self.BLOCK_PADDING

        for i, (rect_data, cluster) in enumerate(zip(self._rects, self._clusters)):
            # 获取矩形区域，应用内边距
            x = rect_data['x'] + pad
            y = rect_data['y'] + pad
            w = rect_data['dx'] - 2 * pad
            h = rect_data['dy'] - 2 * pad

            if w <= 0 or h <= 0:
                continue

            block_rect = QRectF(x, y, w, h)

            # 解析聚类颜色并设置半透明
            color = self._parse_color(cluster.get('color', '#4A90D9'))
            color.setAlpha(160)

            # 绘制圆角矩形背景
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(color))
            painter.drawRoundedRect(block_rect, self.CORNER_RADIUS, self.CORNER_RADIUS)

            # 如果当前块被悬停，绘制高亮边框
            if i == self._hovered_index:
                highlight_color = QColor(color)
                highlight_color.setAlpha(255)
                pen = QPen(highlight_color, 2.5)
                painter.setPen(pen)
                painter.setBrush(Qt.NoBrush)
                painter.drawRoundedRect(block_rect, self.CORNER_RADIUS, self.CORNER_RADIUS)

            # 计算文字绘制区域（留出内边距）
            text_margin = 8
            text_rect = QRectF(
                x + text_margin, y + text_margin,
                w - 2 * text_margin, h - 2 * text_margin
            )

            if text_rect.width() <= 0 or text_rect.height() <= 0:
                continue

            # ---- 绘制主关键词（居中，大号粗体）----
            keyword = cluster.get('keyword', '')
            painter.setFont(font_large)
            painter.setPen(text_primary_color)

            # 计算主关键词的绘制位置（水平居中，垂直偏上）
            fm_large = QFontMetrics(font_large)
            keyword_height = fm_large.height()

            # 根据块的高度决定关键词的垂直位置
            keyword_y_offset = text_rect.height() * 0.3
            keyword_rect = QRectF(
                text_rect.x(),
                text_rect.y() + keyword_y_offset - keyword_height / 2,
                text_rect.width(),
                keyword_height
            )

            # 如果文字太长则省略
            elided_keyword = fm_large.elidedText(
                keyword, Qt.ElideRight, int(text_rect.width())
            )
            painter.drawText(keyword_rect, Qt.AlignCenter, elided_keyword)

            # ---- 绘制相关关键词（主关键词下方，小号字体）----
            related = cluster.get('related_keywords', [])
            if related and text_rect.height() > keyword_height + 20:
                painter.setFont(font_small)
                painter.setPen(text_secondary_color)
                fm_small = QFontMetrics(font_small)

                # 最多显示 2-3 个相关关键词
                display_keywords = related[:3]
                related_text = '  '.join(display_keywords)
                elided_related = fm_small.elidedText(
                    related_text, Qt.ElideRight, int(text_rect.width())
                )

                related_rect = QRectF(
                    text_rect.x(),
                    keyword_rect.bottom() + 4,
                    text_rect.width(),
                    fm_small.height()
                )
                painter.drawText(related_rect, Qt.AlignCenter, elided_related)

            # ---- 绘制热度值（右下角）----
            heat_value = cluster.get('heat', 0)
            heat_text = f'{heat_value:.0f}' if isinstance(heat_value, float) else str(heat_value)

            painter.setFont(font_heat)
            painter.setPen(text_muted_color)
            fm_heat = QFontMetrics(font_heat)

            heat_rect = QRectF(
                text_rect.right() - fm_heat.width(heat_text) - 2,
                text_rect.bottom() - fm_heat.height(),
                fm_heat.width(heat_text) + 2,
                fm_heat.height()
            )
            painter.drawText(heat_rect, Qt.AlignRight | Qt.AlignBottom, heat_text)

        painter.end()

    def _draw_empty_state(self, painter: QPainter, theme: ThemeManager):
        """
        绘制空数据状态的提示文字

        当没有聚类数据时，在组件中央显示"暂无数据"。
        """
        text_color = theme.get_color('text_muted')
        painter.setPen(text_color)

        font = QFont()
        font.setPointSize(16)
        painter.setFont(font)

        painter.drawText(self.rect(), Qt.AlignCenter, '暂无数据')

    def _parse_color(self, color_value) -> QColor:
        """
        将颜色值解析为 QColor 对象

        支持字符串格式（如 '#4A90D9'）和 QColor 对象。

        Args:
            color_value: 颜色字符串或 QColor 对象

        Returns:
            QColor: 解析后的颜色对象
        """
        if isinstance(color_value, QColor):
            return QColor(color_value)
        if isinstance(color_value, str):
            return QColor(color_value)
        # 默认蓝色
        return QColor('#4A90D9')

    def mouseMoveEvent(self, event: QMouseEvent):
        """
        鼠标移动事件处理

        检测鼠标位置是否在某个矩形块内，更新悬停高亮状态。
        当悬停块发生变化时触发重绘。
        """
        pos = event.pos()
        new_hovered = -1

        pad = self.BLOCK_PADDING
        for i, rect_data in enumerate(self._rects):
            x = rect_data['x'] + pad
            y = rect_data['y'] + pad
            w = rect_data['dx'] - 2 * pad
            h = rect_data['dy'] - 2 * pad

            block_rect = QRectF(x, y, w, h)
            if block_rect.contains(QPointF(pos)):
                new_hovered = i
                break

        # 仅在悬停块变化时重绘，避免不必要的性能开销
        if new_hovered != self._hovered_index:
            self._hovered_index = new_hovered
            self.update()

        super().mouseMoveEvent(event)

    def mousePressEvent(self, event: QMouseEvent):
        """
        鼠标点击事件处理

        当用户点击某个矩形块时，发出 topic_clicked 信号，
        携带该聚类的完整数据字典。
        """
        if event.button() == Qt.LeftButton and 0 <= self._hovered_index < len(self._clusters):
            clicked_cluster = self._clusters[self._hovered_index]
            self.topic_clicked.emit(clicked_cluster)

        super().mousePressEvent(event)

    def resizeEvent(self, event: QResizeEvent):
        """
        组件尺寸变化事件

        当组件尺寸改变时，重新计算矩形布局以适应新的可用空间。
        """
        super().resizeEvent(event)
        self._calculate_layout()
        self.update()

    def _on_theme_changed(self, is_dark: bool):
        """
        主题切换回调

        当全局主题发生变化时触发重绘，使文字颜色适配新主题。

        Args:
            is_dark: 是否切换为深色主题
        """
        self.update()
