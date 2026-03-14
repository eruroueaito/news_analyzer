#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
主题管理模块 - 提供应用程序的主题和颜色管理

该模块实现了 ThemeManager 单例类，用于管理深色/浅色主题切换，
并提供统一的颜色查询接口供所有 UI 组件使用。
"""

from PyQt5.QtCore import QObject, pyqtSignal
from PyQt5.QtGui import QColor


class ThemeManager(QObject):
    """
    主题管理器（单例模式）

    负责管理应用程序的主题状态（深色/浅色），并提供统一的颜色查询接口。
    当主题切换时，会发出 theme_changed 信号，通知所有已连接的组件刷新样式。
    """

    # 主题切换信号，参数为是否为深色主题
    theme_changed = pyqtSignal(bool)

    _instance = None

    # 深色主题颜色定义
    _dark_colors = {
        'text_primary': QColor(240, 240, 240),        # 主要文字颜色
        'text_secondary': QColor(180, 180, 180),      # 次要文字颜色
        'text_muted': QColor(130, 130, 130),          # 弱化文字颜色
        'background': QColor(30, 30, 30),             # 主背景色
        'surface': QColor(45, 45, 48),                # 表面/卡片背景色
        'border': QColor(60, 60, 65),                 # 边框颜色
        'hover': QColor(70, 70, 75),                  # 悬停高亮色
        'accent': QColor(100, 140, 230),              # 强调色
    }

    # 浅色主题颜色定义
    _light_colors = {
        'text_primary': QColor(30, 30, 30),           # 主要文字颜色
        'text_secondary': QColor(80, 80, 80),         # 次要文字颜色
        'text_muted': QColor(140, 140, 140),          # 弱化文字颜色
        'background': QColor(245, 245, 245),          # 主背景色
        'surface': QColor(255, 255, 255),             # 表面/卡片背景色
        'border': QColor(210, 210, 210),              # 边框颜色
        'hover': QColor(230, 230, 230),               # 悬停高亮色
        'accent': QColor(60, 110, 210),               # 强调色
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self._is_dark = True  # 默认深色主题

    @classmethod
    def instance(cls):
        """获取 ThemeManager 单例实例"""
        if cls._instance is None:
            cls._instance = ThemeManager()
        return cls._instance

    def is_dark(self) -> bool:
        """返回当前是否为深色主题"""
        return self._is_dark

    def set_dark(self, dark: bool):
        """设置主题模式并发出变更信号"""
        if self._is_dark != dark:
            self._is_dark = dark
            self.theme_changed.emit(dark)

    def toggle_theme(self):
        """切换深色/浅色主题"""
        self.set_dark(not self._is_dark)

    def get_color(self, name: str) -> QColor:
        """
        根据名称获取当前主题下的颜色

        Args:
            name: 颜色名称，如 'text_primary', 'background' 等

        Returns:
            QColor: 对应的颜色对象
        """
        colors = self._dark_colors if self._is_dark else self._light_colors
        return colors.get(name, QColor(128, 128, 128))
