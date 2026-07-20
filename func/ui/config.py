import json
import os
from PySide6.QtWidgets import (
    QDialog, QFormLayout, QLineEdit, QComboBox, QSpinBox,
    QDialogButtonBox, QVBoxLayout, QHBoxLayout, QLabel, QWidget,
    QPushButton, QCheckBox
)
from PySide6.QtCore import Qt

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CONFIG_PATH = os.path.join(BASE_DIR, "config", "info.json")

from func.chatbot.port import PLATFORM_MODELS

PLATFORMS = list(PLATFORM_MODELS.keys())

class ConfigDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.resize(520, 420)
        self.config = self._load_config()
        self._init_ui()

    def _load_config(self):
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        return {
            "api_keys": {p: "" for p in PLATFORMS},
            "platform": "阿里",
            "model": "qwen-max",
            "memory_rounds": 50,
            "thinking_level": "high",
            "max_tokens": 65536,
        }

    def _save_config(self):
        os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(self.config, f, ensure_ascii=False, indent=2)

    def _init_ui(self):
        layout = QVBoxLayout(self)
        form = QFormLayout()

        api_keys = self.config.get("api_keys", {})

        self.platform_combo = QComboBox()
        self.platform_combo.addItems(PLATFORMS)
        self.platform_combo.setCurrentText(self.config.get("platform", "阿里"))

        self.model_combo = QComboBox()
        self.model_combo.setEditable(True)
        self.model_combo.setInsertPolicy(QComboBox.NoInsert)
        self._update_model_list(self.platform_combo.currentText())
        self.model_combo.setCurrentText(self.config.get("model", "qwen-max"))

        self.key_edits = {}
        for p in PLATFORMS:
            edit = QLineEdit(api_keys.get(p, ""))
            edit.setEchoMode(QLineEdit.Password)
            self.key_edits[p] = edit

        self.memory_spin = QSpinBox()
        self.memory_spin.setRange(1, 1000)
        self.memory_spin.setValue(self.config.get("memory_rounds", 50))

        self.max_tokens_spin = QSpinBox()
        self.max_tokens_spin.setRange(1, 1000000)
        self.max_tokens_spin.setValue(self.config.get("max_tokens", 65536))

        thinking_container = QWidget()
        thinking_layout = QHBoxLayout(thinking_container)
        thinking_layout.setContentsMargins(0, 0, 0, 0)
        thinking_layout.addWidget(QLabel("思考强度:"))
        self.thinking_combo = QComboBox()
        self.thinking_combo.addItems(["low", "medium", "high"])
        self.thinking_combo.setCurrentText(self.config.get("thinking_level", "high"))
        thinking_layout.addWidget(self.thinking_combo)
        self.thinking_container = thinking_container

        form.addRow("AI 平台:", self.platform_combo)
        for p in PLATFORMS:
            form.addRow(f"{p} API Key:", self.key_edits[p])
        form.addRow("模型:", self.model_combo)
        form.addRow(self.thinking_container)
        form.addRow("记忆轮数:", self.memory_spin)
        form.addRow("Max Tokens:", self.max_tokens_spin)

        self.platform_combo.currentTextChanged.connect(self._on_platform_changed)

        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_platform_changed(self, platform):
        self._update_model_list(platform)

    def _update_model_list(self, platform):
        current = self.model_combo.currentText()
        self.model_combo.clear()
        models = PLATFORM_MODELS.get(platform, [])
        self.model_combo.addItems(models)
        if current in models:
            self.model_combo.setCurrentText(current)
        elif current:
            self.model_combo.setCurrentText(current)

    def _on_accept(self):
        keys = self.config.get("api_keys", {})
        for p, edit in self.key_edits.items():
            keys[p] = edit.text()
        self.config["api_keys"] = keys
        self.config["platform"] = self.platform_combo.currentText()
        self.config["model"] = self.model_combo.currentText()
        self.config["memory_rounds"] = self.memory_spin.value()
        self.config["thinking_level"] = self.thinking_combo.currentText()
        self.config["max_tokens"] = self.max_tokens_spin.value()
        self._save_config()
        self.accept()


class MemoryConfigDialog(QDialog):
    """对话级记忆概括配置对话框"""

    def __init__(self, parent=None, memory_config=None):
        super().__init__(parent)
        self.setWindowTitle("记忆概括设置")
        self.resize(420, 300)
        self.mem_cfg = memory_config or {
            "enabled": False,
            "summarize_after": 10,
            "max_summary_chars": 2000,
            "merge_every": 5,
            "summaries": []
        }
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        form = QFormLayout()

        # 开关
        from PySide6.QtWidgets import QCheckBox
        self.enabled_check = QCheckBox("启用记忆概括")
        self.enabled_check.setChecked(self.mem_cfg.get("enabled", False))
        form.addRow(self.enabled_check)

        # 概括轮次
        self.summarize_spin = QSpinBox()
        self.summarize_spin.setRange(2, 200)
        self.summarize_spin.setValue(self.mem_cfg.get("summarize_after", 10))
        form.addRow("每 N 轮概括一次:", self.summarize_spin)

        # 概括字数
        self.chars_spin = QSpinBox()
        self.chars_spin.setRange(200, 20000)
        self.chars_spin.setValue(self.mem_cfg.get("max_summary_chars", 2000))
        form.addRow("概括字数上限:", self.chars_spin)

        # 合并段数
        self.merge_spin = QSpinBox()
        self.merge_spin.setRange(2, 50)
        self.merge_spin.setValue(self.mem_cfg.get("merge_every", 5))
        form.addRow("N 段后合并:", self.merge_spin)

        layout.addLayout(form)

        # 现有概括摘要
        summaries = self.mem_cfg.get("summaries", [])
        if summaries:
            info_label = QLabel(f"当前已有 {len(summaries)} 段概括")
            info_label.setStyleSheet("color: #666; font-size: 12px;")
            layout.addWidget(info_label)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_accept(self):
        self.mem_cfg["enabled"] = self.enabled_check.isChecked()
        self.mem_cfg["summarize_after"] = self.summarize_spin.value()
        self.mem_cfg["max_summary_chars"] = self.chars_spin.value()
        self.mem_cfg["merge_every"] = self.merge_spin.value()
        self.accept()

    def get_config(self):
        return self.mem_cfg


class ModelConfigDialog(QDialog):
    """对话级模型绑定对话框"""

    def __init__(self, parent=None, current_platform=None, current_model=None, is_enabled=True):
        super().__init__(parent)
        self.setWindowTitle("对话模型设置")
        self.resize(420, 240)
        self._current_platform = current_platform or "阿里"
        self._current_model = current_model or "qwen-max"
        self._enabled = is_enabled
        self._cleared = False
        self._init_ui()

    def _init_ui(self):
        from PySide6.QtWidgets import QCheckBox
        layout = QVBoxLayout(self)

        # 启用开关
        self.enabled_check = QCheckBox("为此对话绑定独立模型（关闭则使用全局模型）")
        self.enabled_check.setChecked(self._enabled)
        self.enabled_check.toggled.connect(self._on_enabled_toggled)
        layout.addWidget(self.enabled_check)

        form = QFormLayout()

        self.platform_combo = QComboBox()
        self.platform_combo.addItems(PLATFORMS)
        self.platform_combo.setCurrentText(self._current_platform)

        self.model_combo = QComboBox()
        self.model_combo.setEditable(True)
        self.model_combo.setInsertPolicy(QComboBox.NoInsert)
        self._update_model_list(self.platform_combo.currentText())
        self.model_combo.setCurrentText(self._current_model)

        form.addRow("AI 平台:", self.platform_combo)
        form.addRow("模型:", self.model_combo)

        self.platform_combo.currentTextChanged.connect(self._on_platform_changed)

        layout.addLayout(form)

        # 初始状态：如果未启用则禁用选择框
        self._on_enabled_toggled(self._enabled)

        # 清除绑定按钮
        clear_btn = QPushButton("恢复为全局默认")
        clear_btn.setStyleSheet("color: #888; font-size: 12px;")
        clear_btn.clicked.connect(self._on_clear)
        layout.addWidget(clear_btn)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_enabled_toggled(self, checked):
        """当开关切换时，启用/禁用平台与模型选择框"""
        self.platform_combo.setEnabled(checked)
        self.model_combo.setEnabled(checked)

    def _on_platform_changed(self, platform):
        self._update_model_list(platform)

    def _update_model_list(self, platform):
        current = self.model_combo.currentText()
        self.model_combo.clear()
        models = PLATFORM_MODELS.get(platform, [])
        self.model_combo.addItems(models)
        if current in models:
            self.model_combo.setCurrentText(current)
        elif current:
            self.model_combo.setCurrentText(current)

    def _on_clear(self):
        self._cleared = True
        self.accept()

    def _on_accept(self):
        self._enabled = self.enabled_check.isChecked()
        self.accept()

    def is_cleared(self):
        return self._cleared

    def is_enabled(self):
        return self._enabled

    def get_values(self):
        return self.platform_combo.currentText(), self.model_combo.currentText()
