#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
趋势折线图组件

使用 pyqtgraph 绘制关键词频率随时间变化的折线图。
若 pyqtgraph 未安装，显示友好的提示消息。
"""

from typing import List, Dict, Optional

from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont

from news_analyzer.ui.theme import ThemeManager

try:
    import pyqtgraph as pg
    _HAS_PYQTGRAPH = True
except ImportError:
    _HAS_PYQTGRAPH = False


class TrendChartWidget(QWidget):
    """
    关键词频率趋势折线图

    Signals:
        point_clicked(str, int): 点击某个数据点时发出 (date, count)
    """

    point_clicked = pyqtSignal(str, int)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._keyword = ""
        self._data: List[Dict] = []
        self._plot_widget = None
        self._init_ui()
        ThemeManager.instance().theme_changed.connect(self._on_theme_changed)

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        if _HAS_PYQTGRAPH:
            pg.setConfigOptions(antialias=True)
            self._plot_widget = pg.PlotWidget()
            self._plot_widget.setMenuEnabled(False)
            self._plot_widget.setMouseEnabled(x=False, y=False)
            self._plot_widget.showGrid(x=True, y=True, alpha=0.25)
            self._plot_widget.setLabel('left', '文章数量')
            self._plot_widget.setLabel('bottom', '日期')
            layout.addWidget(self._plot_widget)
            self._apply_chart_theme()
        else:
            msg = QLabel("请安装 pyqtgraph 以查看趋势图\npip install pyqtgraph")
            msg.setAlignment(Qt.AlignCenter)
            font = QFont()
            font.setPointSize(12)
            msg.setFont(font)
            layout.addWidget(msg)

    def _apply_chart_theme(self):
        if not self._plot_widget:
            return
        tm = ThemeManager.instance()
        bg = tm.get_color_hex('bg_card')
        text_color = tm.get_color_hex('text_secondary')
        self._plot_widget.setBackground(bg)
        pen = pg.mkPen(color=text_color, width=1)
        for axis_name in ('left', 'bottom'):
            axis = self._plot_widget.getAxis(axis_name)
            axis.setPen(pen)
            axis.setTextPen(pg.mkPen(color=text_color))

    def set_keyword(self, keyword: str):
        """设置当前追踪的关键词（更新图表标题）"""
        self._keyword = keyword
        if self._plot_widget:
            self._plot_widget.setTitle(
                f'关键词趋势: {keyword}',
                color=ThemeManager.instance().get_color_hex('text_primary'),
                size='11pt',
            )

    def set_data(self, data: List[Dict]):
        """
        更新图表数据

        Args:
            data: [{'date': 'YYYYMMDD', 'count': int}, ...]
        """
        self._data = data
        self._refresh_plot()

    def _refresh_plot(self):
        if not self._plot_widget or not _HAS_PYQTGRAPH:
            return

        self._plot_widget.clear()

        if not self._data:
            return

        counts = [d['count'] for d in self._data]
        x = list(range(len(counts)))
        dates = [d['date'] for d in self._data]

        # 每隔几格显示一个日期标签
        step = max(1, len(dates) // 6)
        ticks = [(i, dates[i][-4:]) for i in range(0, len(dates), step)]
        self._plot_widget.getAxis('bottom').setTicks([ticks])

        accent = ThemeManager.instance().get_color_hex('accent')
        pen = pg.mkPen(color=accent, width=2)

        # 填充面积（fillLevel=0）
        fill_color = ThemeManager.instance().get_color('accent')
        fill_color.setAlpha(60)

        curve = pg.PlotDataItem(
            x, counts,
            pen=pen,
            fillLevel=0,
            brush=pg.mkBrush(fill_color),
            symbol='o',
            symbolSize=5,
            symbolBrush=accent,
            symbolPen=pg.mkPen(None),
        )
        self._plot_widget.addItem(curve)

    def _on_theme_changed(self, is_dark: bool):
        self._apply_chart_theme()
        self._refresh_plot()
