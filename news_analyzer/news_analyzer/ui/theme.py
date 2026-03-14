#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
主题管理模块 - 提供应用程序的主题和颜色管理

该模块实现了 ThemeManager 单例类，用于管理深色/浅色主题切换，
并提供统一的颜色查询接口和 QSS 样式表生成功能。
"""

import platform
from PyQt5.QtCore import QObject, pyqtSignal, QSettings
from PyQt5.QtGui import QColor


def _detect_font_family() -> str:
    """根据操作系统返回合适的字体族"""
    system = platform.system()
    if system == "Darwin":
        return "'PingFang SC', 'Helvetica Neue', 'Segoe UI', sans-serif"
    elif system == "Windows":
        return "'Microsoft YaHei', 'Segoe UI', 'PingFang SC', sans-serif"
    else:
        return "'Noto Sans CJK SC', 'WenQuanYi Micro Hei', 'Segoe UI', sans-serif"


FONT_FAMILY = _detect_font_family()


class ThemeManager(QObject):
    """
    主题管理器（单例模式）

    负责管理应用程序的主题状态（深色/浅色），并提供统一的颜色查询接口
    和 QSS 样式表生成功能。当主题切换时，发出 theme_changed 信号通知所有组件。
    主题偏好保存到 QSettings，启动时自动恢复。
    """

    theme_changed = pyqtSignal(bool)
    _instance = None

    # 深色主题 QColor（QPainter 绘制使用）
    _dark_colors = {
        'text_primary': QColor(230, 237, 243),
        'text_secondary': QColor(139, 148, 158),
        'text_muted': QColor(100, 110, 120),
        'background': QColor(13, 17, 23),
        'surface': QColor(22, 27, 34),
        'border': QColor(48, 54, 61),
        'hover': QColor(28, 33, 40),
        'accent': QColor(88, 166, 255),
    }

    # 浅色主题 QColor（Claude App 暖棕风格）
    _light_colors = {
        'text_primary': QColor(45, 45, 42),
        'text_secondary': QColor(107, 101, 96),
        'text_muted': QColor(160, 150, 140),
        'background': QColor(250, 249, 246),
        'surface': QColor(255, 255, 255),
        'border': QColor(224, 219, 212),
        'hover': QColor(232, 227, 220),
        'accent': QColor(180, 132, 92),
    }

    # 深色主题十六进制色（QSS 生成用）
    _dark_hex = {
        'bg_primary': '#0D1117',
        'bg_card': '#161B22',
        'bg_input': '#21262D',
        'border': '#30363D',
        'accent': '#58A6FF',
        'accent_purple': '#8B5CF6',
        'accent_orange': '#F97316',
        'text_primary': '#E6EDF3',
        'text_secondary': '#8B949E',
        'hover': '#1C2128',
        'button_bg': '#21262D',
        'button_hover': '#30363D',
        'button_border': '#30363D',
        'tab_selected': '#161B22',
        'tab_border': '#30363D',
        'scrollbar_handle': '#484F58',
        'selection': '#2F4F6F',
        'statusbar_bg': '#010409',
        'menubar_bg': '#0D1117',
    }

    # 浅色主题十六进制色（Claude App 暖棕风格）
    _light_hex = {
        'bg_primary': '#FAF9F6',
        'bg_card': '#FFFFFF',
        'bg_input': '#F0EDE8',
        'border': '#E0DBD4',
        'accent': '#B4845C',
        'accent_purple': '#9B7EC8',
        'accent_orange': '#DA7756',
        'text_primary': '#2D2D2A',
        'text_secondary': '#6B6560',
        'hover': '#E8E3DC',
        'button_bg': '#EDE8E1',
        'button_hover': '#E0DBD4',
        'button_border': '#D5CFC8',
        'tab_selected': '#FFFFFF',
        'tab_border': '#E0DBD4',
        'scrollbar_handle': '#C8C3BC',
        'selection': '#F0E6D8',
        'statusbar_bg': '#F0EDE8',
        'menubar_bg': '#FAF9F6',
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        settings = QSettings("NewsAnalyzer", "NewsAggregator")
        self._is_dark = settings.value("theme/is_dark", True, type=bool)

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
        """设置主题模式，持久化偏好，并发出变更信号"""
        if self._is_dark != dark:
            self._is_dark = dark
            settings = QSettings("NewsAnalyzer", "NewsAggregator")
            settings.setValue("theme/is_dark", dark)
            self.theme_changed.emit(dark)

    def toggle_theme(self):
        """切换深色/浅色主题"""
        self.set_dark(not self._is_dark)

    def get_color(self, name: str) -> QColor:
        """根据名称获取当前主题下的 QColor"""
        colors = self._dark_colors if self._is_dark else self._light_colors
        return colors.get(name, QColor(128, 128, 128))

    def get_color_hex(self, name: str) -> str:
        """根据名称获取当前主题下的十六进制颜色字符串"""
        hexes = self._dark_hex if self._is_dark else self._light_hex
        return hexes.get(name, '#808080')

    def get_stylesheet(self) -> str:
        """生成当前主题的完整 QSS 样式表"""
        h = self._dark_hex if self._is_dark else self._light_hex
        f = FONT_FAMILY
        return f"""
        QMainWindow, QDialog, QWidget {{
            background-color: {h['bg_primary']};
            color: {h['text_primary']};
            font-family: {f};
            font-size: 13px;
        }}
        QMainWindow::separator {{ background: {h['border']}; width: 1px; height: 1px; }}

        QMenuBar {{
            background-color: {h['menubar_bg']};
            color: {h['text_primary']};
            border-bottom: 1px solid {h['border']};
            padding: 2px;
        }}
        QMenuBar::item:selected {{ background-color: {h['hover']}; border-radius: 4px; }}
        QMenu {{
            background-color: {h['bg_card']};
            color: {h['text_primary']};
            border: 1px solid {h['border']};
            border-radius: 6px;
            padding: 4px;
        }}
        QMenu::item:selected {{ background-color: {h['hover']}; border-radius: 4px; }}

        QToolBar {{
            background-color: {h['bg_card']};
            border-bottom: 1px solid {h['border']};
            spacing: 4px;
            padding: 4px;
        }}
        QToolBar QToolButton {{
            background-color: transparent;
            color: {h['text_primary']};
            border: none;
            padding: 4px 8px;
            border-radius: 4px;
        }}
        QToolBar QToolButton:hover {{ background-color: {h['hover']}; }}

        QStatusBar {{
            background-color: {h['statusbar_bg']};
            color: {h['text_secondary']};
            border-top: 1px solid {h['border']};
        }}

        QTabWidget::pane {{
            border: 1px solid {h['tab_border']};
            background-color: {h['bg_card']};
        }}
        QTabBar::tab {{
            background-color: {h['bg_input']};
            color: {h['text_secondary']};
            border: 1px solid {h['tab_border']};
            border-bottom: none;
            border-top-left-radius: 4px;
            border-top-right-radius: 4px;
            padding: 6px 16px;
            margin-right: 2px;
        }}
        QTabBar::tab:selected {{
            background-color: {h['tab_selected']};
            color: {h['text_primary']};
        }}
        QTabBar::tab:hover:!selected {{
            background-color: {h['hover']};
            color: {h['text_primary']};
        }}

        QPushButton {{
            background-color: {h['button_bg']};
            color: {h['text_primary']};
            border: 1px solid {h['button_border']};
            border-radius: 6px;
            padding: 5px 14px;
        }}
        QPushButton:hover {{ background-color: {h['button_hover']}; border-color: {h['accent']}; }}
        QPushButton:pressed {{ background-color: {h['hover']}; }}
        QPushButton:default {{ border-color: {h['accent']}; color: {h['accent']}; }}

        QLineEdit, QTextEdit, QPlainTextEdit {{
            background-color: {h['bg_input']};
            color: {h['text_primary']};
            border: 1px solid {h['border']};
            border-radius: 6px;
            padding: 5px 8px;
            selection-background-color: {h['selection']};
        }}
        QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {{ border-color: {h['accent']}; }}
        QComboBox {{
            background-color: {h['bg_input']};
            color: {h['text_primary']};
            border: 1px solid {h['border']};
            border-radius: 6px;
            padding: 4px 8px;
        }}
        QComboBox:hover {{ border-color: {h['accent']}; }}
        QComboBox QAbstractItemView {{
            background-color: {h['bg_card']};
            color: {h['text_primary']};
            border: 1px solid {h['border']};
            selection-background-color: {h['hover']};
        }}

        QListWidget, QTreeWidget, QListView, QTreeView {{
            background-color: {h['bg_card']};
            color: {h['text_primary']};
            border: 1px solid {h['border']};
            border-radius: 6px;
            outline: none;
        }}
        QListWidget::item:hover, QListView::item:hover {{ background-color: {h['hover']}; }}
        QListWidget::item:selected, QListView::item:selected {{
            background-color: {h['selection']};
            color: {h['text_primary']};
        }}

        QScrollBar:vertical {{
            background-color: transparent; width: 8px; margin: 0;
        }}
        QScrollBar::handle:vertical {{
            background-color: {h['scrollbar_handle']};
            min-height: 30px; border-radius: 4px;
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        QScrollBar:horizontal {{
            background-color: transparent; height: 8px; margin: 0;
        }}
        QScrollBar::handle:horizontal {{
            background-color: {h['scrollbar_handle']};
            min-width: 30px; border-radius: 4px;
        }}
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}

        QSplitter::handle {{ background-color: {h['border']}; }}
        QSplitter::handle:horizontal {{ width: 1px; }}
        QSplitter::handle:vertical {{ height: 1px; }}

        QGroupBox {{
            border: 1px solid {h['border']};
            border-radius: 6px;
            margin-top: 8px;
            padding-top: 8px;
            color: {h['text_secondary']};
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            subcontrol-position: top left;
            padding: 0 6px;
            color: {h['text_secondary']};
        }}

        QCheckBox, QRadioButton {{ color: {h['text_primary']}; spacing: 8px; }}
        QLabel {{ color: {h['text_primary']}; background-color: transparent; }}

        QProgressBar {{
            background-color: {h['bg_input']};
            border: 1px solid {h['border']};
            border-radius: 4px;
            text-align: center;
            color: {h['text_primary']};
        }}
        QProgressBar::chunk {{ background-color: {h['accent']}; border-radius: 4px; }}
        """

    def apply_to_app(self, app):
        """将当前主题的 QSS 应用到整个 QApplication"""
        app.setStyleSheet(self.get_stylesheet())
