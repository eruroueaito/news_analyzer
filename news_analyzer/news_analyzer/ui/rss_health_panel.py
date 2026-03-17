#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
RSS 订阅健康检测面板

功能：
  - 列出所有 RSS 订阅源及其健康状态（✓ / ✗）
  - 一键检测所有订阅源的可访问性（并发检测，大幅降低等待时间）
  - 对失效源由 AI 自动搜索替代链接（每天只执行一次，60 秒超时）
  - 用户确认后更新 RSSCollector 中的 URL
"""

import re
import ssl
import datetime
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse
from urllib.request import urlopen, Request
from urllib.error import URLError

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QSizePolicy,
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QSettings
from PyQt5.QtGui import QColor

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 共享 HTTP 工具
# ---------------------------------------------------------------------------

def _make_ssl_context() -> ssl.SSLContext:
    """创建忽略证书验证的 SSL 上下文（供所有 HTTP 请求共用）"""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


_USER_AGENT = 'Mozilla/5.0 (compatible; NewsAnalyzer-RSSCheck/1.0)'


def _fetch_url(url: str, timeout: int = 10) -> bytes:
    """发起带 SSL 容错的 GET 请求，返回响应体字节串。

    Raises:
        Exception: 网络错误或非 200 状态码
    """
    req = Request(url, headers={'User-Agent': _USER_AGENT})
    with urlopen(req, context=_make_ssl_context(), timeout=timeout) as resp:
        if resp.status != 200:
            raise OSError(f"HTTP {resp.status}")
        return resp.read()


# ---------------------------------------------------------------------------
# HealthCheckWorker — 并发检测所有源
# ---------------------------------------------------------------------------

class HealthCheckWorker(QThread):
    """并发检测全部 RSS 源的可访问性

    Signals:
        source_result(str, bool): (url, is_ok)  每完成一个源发出一次
        finished_all():           全部检测完成
    """

    source_result = pyqtSignal(str, bool)
    finished_all  = pyqtSignal()

    _MAX_WORKERS = 8   # 并发线程数上限

    def __init__(self, sources, parent=None):
        super().__init__(parent)
        self._sources = sources  # list of source dicts

    def run(self):
        def _check(source):
            url = source.get('url', '')
            try:
                _fetch_url(url, timeout=5)
                return url, True
            except Exception:
                return url, False

        with ThreadPoolExecutor(max_workers=self._MAX_WORKERS) as pool:
            futures = {pool.submit(_check, s): s for s in self._sources}
            for fut in as_completed(futures):
                url, ok = fut.result()
                self.source_result.emit(url, ok)

        self.finished_all.emit()


# ---------------------------------------------------------------------------
# AISearchWorker — 用 LLM 为失效源搜索新 URL
# ---------------------------------------------------------------------------

class AISearchWorker(QThread):
    """利用 LLM 为失效的 RSS 源搜索新订阅链接

    步骤：
      1. 尝试抓取源站首页，从 <link rel="alternate" type="application/rss+xml"> 提取 href
      2. 若步骤 1 无结果，调用 LLM API 询问（60s 超时）

    Signals:
        search_result(str, str): (original_url, found_url) — found_url 为空表示未找到
    """

    search_result = pyqtSignal(str, str)

    def __init__(self, source, llm_client, parent=None):
        super().__init__(parent)
        self._source = source
        self._llm_client = llm_client

    def run(self):
        url  = self._source.get('url', '')
        name = self._source.get('name', '')
        found = ''

        try:
            found = self._scrape_rss_link(url)
            if not found and self._llm_client and self._llm_client.api_key:
                found = self._ask_llm(url, name)
            # 验证候选 URL 是否真实可访问且返回 RSS/Atom 内容
            if found and not self._validate_feed_url(found):
                logger.warning("AI 建议的 URL 验证未通过，丢弃: %s", found)
                found = ''
        except Exception as e:
            logger.error("AISearchWorker 异常: %s", e)

        self.search_result.emit(url, found)

    # ------------------------------------------------------------------
    def _scrape_rss_link(self, feed_url: str) -> str:
        """从源站首页提取 RSS <link> 标签"""
        try:
            parsed   = urlparse(feed_url)
            base_url = f"{parsed.scheme}://{parsed.netloc}"
            html     = _fetch_url(base_url, timeout=10).decode('utf-8', errors='ignore')

            pattern = re.compile(
                r'<link[^>]+type=["\']application/(?:rss|atom)\+xml["\'][^>]*href=["\']([^"\']+)["\']',
                re.IGNORECASE,
            )
            match = pattern.search(html)
            if match:
                href = match.group(1)
                if href.startswith('http'):
                    return href
                if href.startswith('//'):
                    return f"{parsed.scheme}:{href}"
                if href.startswith('/'):
                    return f"{base_url}{href}"
        except Exception as e:
            logger.debug("抓取首页 RSS 链接失败: %s", e)
        return ''

    def _validate_feed_url(self, url: str) -> bool:
        """验证 URL 是否可访问且响应体包含 RSS/Atom 特征标签"""
        try:
            data = _fetch_url(url, timeout=8)
            snippet = data[:2048].decode('utf-8', errors='ignore').lower()
            return any(tag in snippet for tag in ('<rss', '<feed', '<channel', 'application/rss'))
        except Exception as e:
            logger.debug("feed URL 验证失败 %s: %s", url, e)
            return False

    def _ask_llm(self, feed_url: str, name: str) -> str:
        """通过 LLM 搜索新 RSS URL"""
        parsed   = urlparse(feed_url)
        base_url = f"{parsed.scheme}://{parsed.netloc}"
        prompt = (
            f'Find the current RSS or Atom feed URL for the news source "{name}" '
            f'(website: {base_url}). '
            f'Reply with ONLY the URL, nothing else. '
            f'If you cannot find it, reply with "NOT_FOUND".'
        )
        try:
            response = self._llm_client.chat(
                messages=[{"role": "user", "content": prompt}],
                timeout=60,
            )
            text = (response or '').strip()
            if text.startswith('http'):
                return text
        except Exception as e:
            logger.error("LLM 搜索 RSS URL 失败: %s", e)
        return ''


# ---------------------------------------------------------------------------
# RSSHealthPanel
# ---------------------------------------------------------------------------

class RSSHealthPanel(QWidget):
    """RSS 订阅健康检测面板"""

    # 列索引常量
    COL_STATUS   = 0
    COL_NAME     = 1
    COL_CATEGORY = 2
    COL_ACTION   = 3

    _ROW_HEIGHT = 32

    def __init__(self, rss_collector, llm_client, parent=None):
        super().__init__(parent)
        self._collector      = rss_collector
        self._llm_client     = llm_client
        self._health_worker  = None
        self._ai_workers: dict[str, AISearchWorker] = {}
        self._url_to_row: dict[str, int]            = {}
        self._pending_urls: dict[str, str]          = {}
        self._init_ui()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # ---- 顶部工具栏 ----
        toolbar = QHBoxLayout()
        self._check_btn = QPushButton("检测所有订阅")
        self._check_btn.clicked.connect(self.check_all_sources)
        toolbar.addWidget(self._check_btn)

        self._last_check_label = QLabel("最后检测: —")
        toolbar.addWidget(self._last_check_label)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        # ---- 订阅表格 ----
        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(["状态", "来源名称", "分类", "操作"])
        self._table.horizontalHeader().setSectionResizeMode(self.COL_STATUS,   QHeaderView.Fixed)
        self._table.horizontalHeader().setSectionResizeMode(self.COL_NAME,     QHeaderView.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(self.COL_CATEGORY, QHeaderView.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(self.COL_ACTION,   QHeaderView.ResizeToContents)
        self._table.setColumnWidth(self.COL_STATUS, 48)
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setSelectionMode(QAbstractItemView.SingleSelection)
        self._table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout.addWidget(self._table, 1)

        self._populate_table()

    def _populate_table(self):
        """填充订阅源列表（初始状态均为 ? 待检测）"""
        self._table.setRowCount(0)
        self._url_to_row.clear()

        for source in self._collector.get_sources():
            row = self._table.rowCount()
            self._table.insertRow(row)
            self._table.setRowHeight(row, self._ROW_HEIGHT)
            self._url_to_row[source['url']] = row

            status_item = QTableWidgetItem("?")
            status_item.setTextAlignment(Qt.AlignCenter)
            self._table.setItem(row, self.COL_STATUS, status_item)

            name_item = QTableWidgetItem(source.get('name', source['url']))
            name_item.setData(Qt.UserRole, source['url'])
            self._table.setItem(row, self.COL_NAME, name_item)

            self._table.setItem(row, self.COL_CATEGORY,
                                QTableWidgetItem(source.get('category', '')))
            self._table.setItem(row, self.COL_ACTION, QTableWidgetItem(""))

        # 显示上次检测时间
        last = QSettings("NewsAnalyzer", "NewsAggregator").value(
            "rss_health/last_check_date", ""
        )
        if last:
            self._last_check_label.setText(f"最后检测: {last}")

    # ------------------------------------------------------------------
    # 每日自动检测
    # ------------------------------------------------------------------

    def showEvent(self, event):
        super().showEvent(event)
        self._maybe_auto_check()

    def _maybe_auto_check(self):
        settings = QSettings("NewsAnalyzer", "NewsAggregator")
        today = datetime.date.today().isoformat()
        if settings.value("rss_health/last_check_date", "") != today:
            self.check_all_sources()
            settings.setValue("rss_health/last_check_date", today)

    # ------------------------------------------------------------------
    # 健康检测
    # ------------------------------------------------------------------

    def check_all_sources(self):
        if self._health_worker and self._health_worker.isRunning():
            return

        # 重置所有行
        for row in range(self._table.rowCount()):
            item = self._table.item(row, self.COL_STATUS)
            if item:
                item.setText("?")
                item.setForeground(QColor("#888888"))
            self._table.setItem(row, self.COL_ACTION, QTableWidgetItem(""))

        self._pending_urls.clear()
        self._check_btn.setEnabled(False)
        self._check_btn.setText("检测中…")

        sources = self._collector.get_sources()
        self._health_worker = HealthCheckWorker(sources, self)
        self._health_worker.source_result.connect(self._on_source_checked)
        self._health_worker.finished_all.connect(self._on_check_all_done)
        self._health_worker.start()

        today = datetime.date.today().isoformat()
        QSettings("NewsAnalyzer", "NewsAggregator").setValue(
            "rss_health/last_check_date", today
        )
        self._last_check_label.setText(f"最后检测: {today}")

    def _on_source_checked(self, url: str, is_ok: bool):
        row = self._url_to_row.get(url)
        if row is None:
            return
        item = self._table.item(row, self.COL_STATUS)
        if item is None:
            return

        if is_ok:
            item.setText("✓")
            item.setForeground(QColor("#2A9D8F"))
        else:
            item.setText("✗")
            item.setForeground(QColor("#E63946"))
            self._set_action_button(row, url)

    def _on_check_all_done(self):
        self._check_btn.setEnabled(True)
        self._check_btn.setText("检测所有订阅")

    # ------------------------------------------------------------------
    # AI 搜索
    # ------------------------------------------------------------------

    def _set_action_button(self, row: int, url: str):
        btn = QPushButton("AI搜索新链接")
        btn.setFixedHeight(24)
        btn.clicked.connect(lambda: self._ai_search_url(url))
        self._table.setCellWidget(row, self.COL_ACTION, btn)

    def _ai_search_url(self, url: str):
        existing = self._ai_workers.get(url)
        if existing and existing.isRunning():
            return

        row = self._url_to_row.get(url)
        if row is not None:
            self._table.setCellWidget(row, self.COL_ACTION,
                                      self._make_status_label("搜索中…"))

        source = next(
            (s for s in self._collector.get_sources() if s['url'] == url), None
        )
        if not source:
            return

        worker = AISearchWorker(source, self._llm_client, self)
        worker.search_result.connect(self._on_ai_result)
        # 线程结束后自动从字典移除，防止内存泄漏
        worker.finished.connect(lambda u=url: self._ai_workers.pop(u, None))
        self._ai_workers[url] = worker
        worker.start()

    def _on_ai_result(self, original_url: str, new_url: str):
        row = self._url_to_row.get(original_url)
        if row is None:
            return

        if not new_url:
            self._table.setCellWidget(row, self.COL_ACTION,
                                      self._make_status_label("未找到替代链接"))
            return

        self._pending_urls[original_url] = new_url
        self._show_confirm_buttons(row, original_url, new_url)

    def _show_confirm_buttons(self, row: int, old_url: str, new_url: str):
        container = QWidget()
        h = QHBoxLayout(container)
        h.setContentsMargins(2, 0, 2, 0)
        h.setSpacing(4)

        short = new_url[:40] + "…" if len(new_url) > 40 else new_url
        lbl = QLabel(f"建议: {short}")
        lbl.setToolTip(new_url)
        h.addWidget(lbl, 1)

        update_btn = QPushButton("更新")
        update_btn.setFixedWidth(48)
        update_btn.clicked.connect(lambda: self._confirm_update(old_url, new_url))
        h.addWidget(update_btn)

        ignore_btn = QPushButton("忽略")
        ignore_btn.setFixedWidth(48)
        ignore_btn.clicked.connect(lambda: self._ignore_suggestion(old_url))
        h.addWidget(ignore_btn)

        self._table.setCellWidget(row, self.COL_ACTION, container)
        self._table.resizeRowToContents(row)

    def _confirm_update(self, old_url: str, new_url: str):
        if self._collector.update_source_url(old_url, new_url):
            row = self._url_to_row.pop(old_url, None)
            if row is not None:
                self._url_to_row[new_url] = row
                name_item = self._table.item(row, self.COL_NAME)
                if name_item:
                    name_item.setData(Qt.UserRole, new_url)
                status_item = self._table.item(row, self.COL_STATUS)
                if status_item:
                    status_item.setText("?")
                    status_item.setForeground(QColor("#888888"))
                self._table.setCellWidget(row, self.COL_ACTION,
                                          self._make_status_label("已更新 ✓"))
        self._pending_urls.pop(old_url, None)

    def _ignore_suggestion(self, old_url: str):
        row = self._url_to_row.get(old_url)
        if row is not None:
            self._set_action_button(row, old_url)
        self._pending_urls.pop(old_url, None)

    # ------------------------------------------------------------------
    # 工具
    # ------------------------------------------------------------------

    @staticmethod
    def _make_status_label(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setAlignment(Qt.AlignCenter)
        return lbl
