import json
import os
from PySide6.QtWidgets import (
    QDialog, QFormLayout, QLineEdit, QComboBox, QSpinBox,
    QDialogButtonBox, QVBoxLayout, QHBoxLayout, QLabel, QWidget
)
from PySide6.QtCore import Qt

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CONFIG_PATH = os.path.join(BASE_DIR, "config", "info.json")

class ConfigDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.resize(500, 400)
        self.config = self._load_config()
        self._init_ui()

    def _load_config(self):
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        return {
            "api_keys": {"deepseek_key": "", "qwen_key": ""},
            "model": "qwen3.7-max",
            "memory_rounds": 50,
            "thinking_level": "high",
            "max_tokens": 65536,
            "qwen_workspace_id": ""
        }

    def _save_config(self):
        os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(self.config, f, ensure_ascii=False, indent=2)

    def _init_ui(self):
        layout = QVBoxLayout(self)
        form = QFormLayout()

        # ---- API Keys ----
        self.deepseek_key_edit = QLineEdit(self.config["api_keys"].get("deepseek_key", ""))
        self.qwen_key_edit = QLineEdit(self.config["api_keys"].get("qwen_key", ""))

        # ---- 模型选择 ----
        self.model_combo = QComboBox()
        self.model_combo.addItems(["qwen3.7-max", "deepseek-v4-pro"])
        self.model_combo.setCurrentText(self.config.get("model", "qwen3.7-max"))

        # ---- 通用配置 ----
        self.memory_spin = QSpinBox()
        self.memory_spin.setRange(1, 1000)
        self.memory_spin.setValue(self.config.get("memory_rounds", 50))

        self.max_tokens_spin = QSpinBox()
        self.max_tokens_spin.setRange(1, 1000000)
        self.max_tokens_spin.setValue(self.config.get("max_tokens", 65536))

        # ---- Qwen Workspace ID（动态显示） ----
        workspace_container = QWidget()
        workspace_layout = QHBoxLayout(workspace_container)
        workspace_layout.setContentsMargins(0, 0, 0, 0)
        workspace_layout.addWidget(QLabel("Qwen Workspace ID:"))
        self.workspace_id_edit = QLineEdit(self.config.get("qwen_workspace_id", ""))
        workspace_layout.addWidget(self.workspace_id_edit)
        self.workspace_container = workspace_container

        # ---- 思考强度（DeepSeek 专用，动态显示） ----
        thinking_container = QWidget()
        thinking_layout = QHBoxLayout(thinking_container)
        thinking_layout.setContentsMargins(0, 0, 0, 0)
        thinking_layout.addWidget(QLabel("思考强度:"))
        self.thinking_combo = QComboBox()
        self.thinking_combo.addItems(["low", "medium", "high"])
        self.thinking_combo.setCurrentText(self.config.get("thinking_level", "high"))
        thinking_layout.addWidget(self.thinking_combo)
        self.thinking_container = thinking_container

        # ---- 添加所有行 ----
        form.addRow("DeepSeek API Key:", self.deepseek_key_edit)
        form.addRow("Qwen API Key:", self.qwen_key_edit)
        form.addRow("模型选择:", self.model_combo)
        form.addRow(self.workspace_container)          # 整行作为容器
        form.addRow(self.thinking_container)           # 整行作为容器
        form.addRow("记忆轮数:", self.memory_spin)
        form.addRow("Max Tokens:", self.max_tokens_spin)

        # ---- 模型切换事件 ----
        self.model_combo.currentTextChanged.connect(self._on_model_changed)
        self._on_model_changed(self.model_combo.currentText())   # 初始化状态

        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_model_changed(self, model):
        """根据模型显示/隐藏相关配置行"""
        is_qwen = model.startswith("qwen")
        # Workspace ID 仅 Qwen 需要
        self.workspace_container.setVisible(is_qwen)
        # 思考强度仅 DeepSeek 需要
        self.thinking_container.setVisible(not is_qwen)

    def _on_accept(self):
        self.config["api_keys"]["deepseek_key"] = self.deepseek_key_edit.text()
        self.config["api_keys"]["qwen_key"] = self.qwen_key_edit.text()
        self.config["qwen_workspace_id"] = self.workspace_id_edit.text()
        self.config["model"] = self.model_combo.currentText()
        self.config["memory_rounds"] = self.memory_spin.value()
        self.config["thinking_level"] = self.thinking_combo.currentText()
        self.config["max_tokens"] = self.max_tokens_spin.value()
        self._save_config()
        self.accept()