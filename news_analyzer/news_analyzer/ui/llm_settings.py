# -*- coding: utf-8 -*-
"""
语言模型设置对话框（多 API 配置版）

支持为摘要、分析、向量处理分别配置不同的 API 端点和认证方式。
认证方式支持 Bearer Token、API Key Header（Anthropic 风格）、自定义 Header。
"""

import os
import logging
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
                             QLineEdit, QComboBox, QPushButton, QLabel,
                             QMessageBox, QGroupBox, QCheckBox, QTabWidget,
                             QWidget)
from PyQt5.QtCore import QSettings, Qt


# ---------------------------------------------------------------------------
# 单个 API 配置面板（可复用于摘要/分析/向量三个 Tab）
# ---------------------------------------------------------------------------
class APIConfigPanel(QWidget):
    """单个 API 端点的配置面板

    包含 URL、Key、Model、认证方式、预设按钮等控件。
    """

    def __init__(self, config_prefix: str, parent=None):
        """
        Args:
            config_prefix: QSettings 中的键前缀，如 'llm/summary'
        """
        super().__init__(parent)
        self.config_prefix = config_prefix
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # ---- API 设置组 ----
        api_group = QGroupBox("API 设置")
        api_layout = QFormLayout()
        api_layout.setSpacing(8)
        api_layout.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)

        self.api_url = QLineEdit()
        self.api_url.setPlaceholderText("例如: https://api.openai.com/v1/chat/completions")
        api_layout.addRow("API 端点 URL:", self.api_url)

        self.api_key = QLineEdit()
        self.api_key.setEchoMode(QLineEdit.Password)
        self.api_key.setPlaceholderText("输入 API 密钥")
        api_layout.addRow("API 密钥:", self.api_key)

        self.model_name = QLineEdit()
        self.model_name.setPlaceholderText("例如: gpt-4o")
        api_layout.addRow("模型名称:", self.model_name)

        # 认证方式下拉
        self.auth_type = QComboBox()
        self.auth_type.addItem("Bearer Token", "bearer_token")
        self.auth_type.addItem("API Key Header (Anthropic)", "api_key_header")
        self.auth_type.addItem("自定义 Header", "custom_header")
        self.auth_type.currentIndexChanged.connect(self._on_auth_type_changed)
        api_layout.addRow("认证方式:", self.auth_type)

        # 自定义 Header 名（仅 custom_header 模式可见）
        self.custom_header_name = QLineEdit()
        self.custom_header_name.setPlaceholderText("例如: X-Custom-Auth")
        self.custom_header_name.setVisible(False)
        self.custom_header_label = QLabel("Header 名:")
        self.custom_header_label.setVisible(False)
        api_layout.addRow(self.custom_header_label, self.custom_header_name)

        self.save_key = QCheckBox("保存 API 密钥（明文存储）")
        api_layout.addRow("", self.save_key)

        api_group.setLayout(api_layout)
        layout.addWidget(api_group)

        # ---- 预设模型组 ----
        presets_group = QGroupBox("预设模型")
        presets_layout = QHBoxLayout()
        presets_layout.setSpacing(8)

        for name, slot in [
            ("OpenAI GPT-4o", self._preset_openai_4o),
            ("GPT-3.5", self._preset_openai_35),
            ("Claude", self._preset_claude),
            ("Ollama", self._preset_ollama),
        ]:
            btn = QPushButton(name)
            btn.clicked.connect(slot)
            presets_layout.addWidget(btn)

        presets_group.setLayout(presets_layout)
        layout.addWidget(presets_group)

        layout.addStretch()

    # ---- 认证方式切换 ----
    def _on_auth_type_changed(self, index):
        is_custom = self.auth_type.currentData() == "custom_header"
        self.custom_header_name.setVisible(is_custom)
        self.custom_header_label.setVisible(is_custom)

    # ---- 预设填充 ----
    def _preset_openai_4o(self):
        self.api_url.setText("https://api.openai.com/v1/chat/completions")
        self.model_name.setText("gpt-4o")
        self.auth_type.setCurrentIndex(0)  # Bearer Token

    def _preset_openai_35(self):
        self.api_url.setText("https://api.openai.com/v1/chat/completions")
        self.model_name.setText("gpt-3.5-turbo")
        self.auth_type.setCurrentIndex(0)

    def _preset_claude(self):
        self.api_url.setText("https://api.anthropic.com/v1/messages")
        self.model_name.setText("claude-sonnet-4-20250514")
        self.auth_type.setCurrentIndex(1)  # API Key Header

    def _preset_ollama(self):
        self.api_url.setText("http://localhost:11434/api/chat")
        self.model_name.setText("llama3")
        self.auth_type.setCurrentIndex(0)

    # ---- 加载 / 保存 ----
    def load_from_settings(self, settings: QSettings):
        """从 QSettings 加载配置"""
        p = self.config_prefix
        self.api_url.setText(settings.value(f"{p}/api_url", ""))
        self.model_name.setText(settings.value(f"{p}/model_name", ""))

        save_key = settings.value(f"{p}/save_key", False, type=bool)
        self.save_key.setChecked(save_key)
        if save_key:
            self.api_key.setText(settings.value(f"{p}/api_key", ""))

        auth = settings.value(f"{p}/auth_type", "bearer_token")
        idx = self.auth_type.findData(auth)
        if idx >= 0:
            self.auth_type.setCurrentIndex(idx)

        self.custom_header_name.setText(settings.value(f"{p}/custom_header", ""))

    def save_to_settings(self, settings: QSettings):
        """将配置保存到 QSettings"""
        p = self.config_prefix
        settings.setValue(f"{p}/api_url", self.api_url.text())
        settings.setValue(f"{p}/model_name", self.model_name.text())
        settings.setValue(f"{p}/save_key", self.save_key.isChecked())
        settings.setValue(f"{p}/auth_type", self.auth_type.currentData())
        settings.setValue(f"{p}/custom_header", self.custom_header_name.text())

        if self.save_key.isChecked():
            settings.setValue(f"{p}/api_key", self.api_key.text())
        else:
            settings.remove(f"{p}/api_key")

    def get_config(self) -> dict:
        """返回当前面板的配置字典"""
        return {
            "api_url": self.api_url.text(),
            "api_key": self.api_key.text(),
            "model": self.model_name.text(),
            "auth_type": self.auth_type.currentData(),
            "custom_header": self.custom_header_name.text(),
        }


# ---------------------------------------------------------------------------
# LLM 设置对话框（三组 API 配置 + 高级参数）
# ---------------------------------------------------------------------------
class LLMSettingsDialog(QDialog):
    """语言模型设置对话框

    三个 Tab 分别配置：摘要 API、分析 API、向量 API，
    另有高级参数 Tab（温度、Token 上限、超时等）和 RSS 订阅检测 Tab。
    """

    def __init__(self, parent=None, rss_collector=None, llm_client=None):
        super().__init__(parent)
        self.logger = logging.getLogger('news_analyzer.ui.llm_settings')
        self._rss_collector = rss_collector
        self._llm_client = llm_client

        self.setWindowTitle("语言模型设置")
        self.setMinimumWidth(600)
        self.setMinimumHeight(500)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        self._init_ui()
        self._load_settings()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # ---- 主标签页 ----
        self.tabs = QTabWidget()

        # 三组 API 配置面板
        self.summary_panel = APIConfigPanel("llm/summary")
        self.analysis_panel = APIConfigPanel("llm/analysis")
        self.vector_panel = APIConfigPanel("llm/vector")

        self.tabs.addTab(self.summary_panel, "摘要 API")
        self.tabs.addTab(self.analysis_panel, "分析 API")
        self.tabs.addTab(self.vector_panel, "向量 API")

        # 高级设置 Tab
        advanced_tab = QWidget()
        adv_layout = QVBoxLayout(advanced_tab)

        params_group = QGroupBox("模型参数")
        params_layout = QFormLayout()
        params_layout.setSpacing(8)

        self.temperature = QLineEdit("0.7")
        self.temperature.setPlaceholderText("范围: 0.0 - 1.0")
        params_layout.addRow("温度:", self.temperature)

        self.max_tokens = QLineEdit("4096")
        params_layout.addRow("最大生成长度:", self.max_tokens)

        self.system_prompt = QLineEdit()
        self.system_prompt.setPlaceholderText("为模型设置默认行为的系统提示")
        params_layout.addRow("系统提示:", self.system_prompt)

        params_group.setLayout(params_layout)
        adv_layout.addWidget(params_group)

        request_group = QGroupBox("请求设置")
        req_layout = QFormLayout()
        req_layout.setSpacing(8)

        self.timeout = QLineEdit("60")
        self.timeout.setPlaceholderText("单位: 秒")
        req_layout.addRow("请求超时:", self.timeout)

        self.retry_count = QLineEdit("3")
        req_layout.addRow("重试次数:", self.retry_count)

        request_group.setLayout(req_layout)
        adv_layout.addWidget(request_group)
        adv_layout.addStretch()

        self.tabs.addTab(advanced_tab, "高级设置")

        # RSS 订阅检测 Tab
        if self._rss_collector is not None:
            try:
                from news_analyzer.ui.rss_health_panel import RSSHealthPanel
                self._rss_health_tab = RSSHealthPanel(
                    self._rss_collector, self._llm_client
                )
                self.tabs.addTab(self._rss_health_tab, "RSS订阅检测")
            except Exception as e:
                self.logger.warning(f"RSS健康面板加载失败: {e}")

        layout.addWidget(self.tabs)

        # ---- 底部按钮 ----
        btn_layout = QHBoxLayout()

        self.test_button = QPushButton("测试连接")
        self.test_button.clicked.connect(self._test_connection)
        btn_layout.addWidget(self.test_button)

        btn_layout.addStretch()

        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        save_btn = QPushButton("保存")
        save_btn.setDefault(True)
        save_btn.clicked.connect(self.accept)
        btn_layout.addWidget(save_btn)

        layout.addLayout(btn_layout)

    # ------------------------------------------------------------------
    # 加载 / 保存
    # ------------------------------------------------------------------
    def _load_settings(self):
        settings = QSettings("NewsAnalyzer", "NewsAggregator")

        # 加载三组 API 配置
        self.summary_panel.load_from_settings(settings)
        self.analysis_panel.load_from_settings(settings)
        self.vector_panel.load_from_settings(settings)

        # 兼容旧版单一配置：如果新键不存在，从旧键迁移
        if not settings.value("llm/summary/api_url"):
            old_url = settings.value("llm/api_url", "")
            old_key = settings.value("llm/api_key", "")
            old_model = settings.value("llm/model_name", "")
            if old_url:
                self.summary_panel.api_url.setText(old_url)
                self.summary_panel.api_key.setText(old_key)
                self.summary_panel.model_name.setText(old_model)
                # 分析配置也用同一个
                self.analysis_panel.api_url.setText(old_url)
                self.analysis_panel.api_key.setText(old_key)
                self.analysis_panel.model_name.setText(old_model)

        # 高级设置
        self.temperature.setText(settings.value("llm/temperature", "0.7"))
        self.max_tokens.setText(settings.value("llm/max_tokens", "4096"))
        self.system_prompt.setText(settings.value("llm/system_prompt", ""))
        self.timeout.setText(settings.value("llm/timeout", "60"))
        self.retry_count.setText(settings.value("llm/retry_count", "3"))

    def save_settings(self):
        """保存所有设置到 QSettings 并设置环境变量"""
        settings = QSettings("NewsAnalyzer", "NewsAggregator")

        # 保存三组 API 配置
        self.summary_panel.save_to_settings(settings)
        self.analysis_panel.save_to_settings(settings)
        self.vector_panel.save_to_settings(settings)

        # 保存高级设置
        settings.setValue("llm/temperature", self.temperature.text())
        settings.setValue("llm/max_tokens", self.max_tokens.text())
        settings.setValue("llm/system_prompt", self.system_prompt.text())
        settings.setValue("llm/timeout", self.timeout.text())
        settings.setValue("llm/retry_count", self.retry_count.text())

        # 向后兼容：将摘要 API 同步到旧环境变量
        summary_cfg = self.summary_panel.get_config()
        os.environ["LLM_API_URL"] = summary_cfg["api_url"]
        os.environ["LLM_API_KEY"] = summary_cfg["api_key"]
        os.environ["LLM_MODEL"] = summary_cfg["model"]

        self.logger.info("已保存 LLM 多 API 设置")

    def get_all_configs(self) -> dict:
        """返回所有配置

        Returns:
            dict 包含 summary、analysis、vector 三组配置及高级参数
        """
        return {
            "summary": self.summary_panel.get_config(),
            "analysis": self.analysis_panel.get_config(),
            "vector": self.vector_panel.get_config(),
            "temperature": float(self.temperature.text() or "0.7"),
            "max_tokens": int(self.max_tokens.text() or "4096"),
            "system_prompt": self.system_prompt.text(),
            "timeout": int(self.timeout.text() or "60"),
            "retry_count": int(self.retry_count.text() or "3"),
        }

    # ------------------------------------------------------------------
    # 连接测试
    # ------------------------------------------------------------------
    def _test_connection(self):
        """测试当前 Tab 对应的 API 连接"""
        from news_analyzer.llm.llm_client import LLMClient

        current_idx = self.tabs.currentIndex()
        panels = [self.summary_panel, self.analysis_panel, self.vector_panel]
        if current_idx >= len(panels):
            QMessageBox.information(self, "提示", "请切换到摘要/分析/向量 API 配置标签页再测试")
            return

        panel = panels[current_idx]
        cfg = panel.get_config()

        if not cfg["api_url"] or not cfg["api_key"]:
            QMessageBox.warning(self, "输入错误", "请输入 API URL 和 API 密钥")
            return

        self.test_button.setEnabled(False)
        self.test_button.setText("正在测试...")

        try:
            client = LLMClient(
                api_key=cfg["api_key"],
                api_url=cfg["api_url"],
                model=cfg["model"]
            )
            result = client.test_connection()

            if result:
                QMessageBox.information(self, "连接成功", "已成功连接到 API 服务！")
            else:
                QMessageBox.warning(self, "连接失败", "无法连接到 API，请检查设置。")
        except Exception as e:
            QMessageBox.critical(self, "连接错误", f"测试时发生错误:\n{str(e)}")
        finally:
            self.test_button.setEnabled(True)
            self.test_button.setText("测试连接")
