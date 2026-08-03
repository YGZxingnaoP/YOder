/**
 * UI管理器
 */
import { marked } from 'marked';
import { markedHighlight } from 'marked-highlight';
import hljs from 'highlight.js';

export class UIManager {
    constructor(configManager) {
        this.configManager = configManager;
        this.toolStates = {}; // 工具开关状态 { toolId: true/false }
        this.toolsLoaded = false;
        this.setupMarked();
    }
    
    setupMarked() {
        marked.use(markedHighlight({
            langPrefix: 'hljs language-',
            highlight(code, lang) {
                if (lang && hljs.getLanguage(lang)) {
                    return hljs.highlight(code, { language: lang }).value;
                }
                return hljs.highlightAuto(code).value;
            }
        }));
        
        marked.setOptions({
            breaks: true,
            gfm: true
        });
    }
    
    renderMessage(content, role) {
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${role}`;
        messageDiv.innerHTML = marked(content || '');
        
        // 为代码块添加复制按钮
        messageDiv.querySelectorAll('pre').forEach(pre => {
            const copyBtn = document.createElement('button');
            copyBtn.className = 'glass-btn copy-btn';
            copyBtn.textContent = '复制';
            copyBtn.onclick = () => {
                const code = pre.querySelector('code').textContent;
                navigator.clipboard.writeText(code);
                copyBtn.textContent = '已复制';
                setTimeout(() => copyBtn.textContent = '复制', 2000);
            };
            pre.appendChild(copyBtn);
        });
        
        return messageDiv;
    }
    
    addMessage(content, role, roundIndex = -1) {
        const messagesDiv = document.getElementById('messages');
        const messageDiv = this.renderMessage(content, role);
        
        // 为用户消息添加删除按钮
        if (role === 'user' && roundIndex >= 0) {
            messageDiv.dataset.roundIndex = roundIndex;
            const deleteBtn = document.createElement('button');
            deleteBtn.className = 'round-delete-btn';
            deleteBtn.textContent = '✕';
            deleteBtn.title = '删除此轮对话';
            deleteBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                const chatId = window.app?.chatManager?.currentChatId;
                if (chatId && confirm('确定删除此轮对话？')) {
                    window.app.chatManager.deleteRound(chatId, roundIndex);
                }
            });
            messageDiv.appendChild(deleteBtn);
        }
        
        messagesDiv.appendChild(messageDiv);
        
        // 滚动到底部
        const container = document.getElementById('messages-container');
        container.scrollTop = container.scrollHeight;
        
        return messageDiv;
    }
    
    /**
     * 用户消息（含文件附件卡片）
     * @param {string} text - 用户输入的文本
     * @param {Array} files - [{name, size, content}]
     * @param {number} roundIndex
     */
    addUserMessageWithFiles(text, files, roundIndex) {
        const messagesDiv = document.getElementById('messages');
        const messageDiv = document.createElement('div');
        messageDiv.className = 'message user';
        
        let html = '';
        if (text) {
            html += `<div class="message-content">${marked(text)}</div>`;
        }
        if (files && files.length > 0) {
            html += '<div class="file-cards">';
            for (const f of files) {
                const sizeStr = f.size > 1024 ? `${(f.size/1024).toFixed(1)}KB` : `${f.size}B`;
                const safeName = this.escapeHtml(f.name || '?');
                const safeContent = f.content || '';
                html += `<div class="file-card" data-filename="${safeName}" data-content="${this.escapeHtml(safeContent)}">
                    <span class="file-card-icon">📎</span>
                    <span class="file-card-name">${safeName}</span>
                    <span class="file-card-size">${sizeStr}</span>
                </div>`;
            }
            html += '</div>';
        }
        messageDiv.innerHTML = html;
        
        // 删除按钮
        if (roundIndex >= 0) {
            messageDiv.dataset.roundIndex = roundIndex;
            const deleteBtn = document.createElement('button');
            deleteBtn.className = 'round-delete-btn';
            deleteBtn.textContent = '✕';
            deleteBtn.title = '删除此轮对话';
            deleteBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                const chatId = window.app?.chatManager?.currentChatId;
                if (chatId && confirm('确定删除此轮对话？')) {
                    window.app.chatManager.deleteRound(chatId, roundIndex);
                }
            });
            messageDiv.appendChild(deleteBtn);
        }
        
        // 文件卡片点击 → 弹窗显示内容
        messageDiv.querySelectorAll('.file-card').forEach(card => {
            card.addEventListener('click', () => {
                this.showFileContentModal(
                    card.dataset.filename,
                    // data-content 已被 escapeHtml 处理，反转义
                    new DOMParser().parseFromString(card.dataset.content, 'text/html').body.textContent || ''
                );
            });
        });
        
        messagesDiv.appendChild(messageDiv);
        
        const container = document.getElementById('messages-container');
        container.scrollTop = container.scrollHeight;
        
        return messageDiv;
    }
    
    /**
     * 显示文件附件内容弹窗
     */
    showFileContentModal(filename, content) {
        let modal = document.getElementById('file-content-modal');
        if (!modal) {
            // 动态创建弹窗
            modal = document.createElement('div');
            modal.id = 'file-content-modal';
            modal.className = 'tool-modal-overlay';
            modal.innerHTML = `
                <div class="tool-modal-box" style="max-width:800px;">
                    <div class="tool-modal-header">
                        <span id="file-modal-title">📎 文件</span>
                        <button class="tool-modal-close file-modal-close">×</button>
                    </div>
                    <div id="file-modal-body" class="tool-modal-body" style="max-height:70vh;overflow-y:auto;"></div>
                </div>`;
            document.body.appendChild(modal);
            
            // 关闭事件
            modal.querySelector('.file-modal-close').addEventListener('click', () => {
                modal.style.display = 'none';
            });
            modal.addEventListener('click', (e) => {
                if (e.target === modal) modal.style.display = 'none';
            });
        }
        
        const title = modal.querySelector('#file-modal-title');
        const body = modal.querySelector('#file-modal-body');
        title.textContent = `📎 ${filename}`;
        body.innerHTML = `<pre class="file-content-pre">${this.escapeHtml(content || '(空文件)')}</pre>`;
        modal.style.display = 'flex';
    }
    
    updateMessage(messageDiv, newContent) {
        messageDiv.innerHTML = marked(newContent || '');
        
        // 重新添加复制按钮
        messageDiv.querySelectorAll('pre').forEach(pre => {
            const copyBtn = document.createElement('button');
            copyBtn.className = 'glass-btn copy-btn';
            copyBtn.textContent = '复制';
            copyBtn.onclick = () => {
                const code = pre.querySelector('code').textContent;
                navigator.clipboard.writeText(code);
                copyBtn.textContent = '已复制';
                setTimeout(() => copyBtn.textContent = '复制', 2000);
            };
            pre.appendChild(copyBtn);
        });
        
        // 滚动到底部
        const container = document.getElementById('messages-container');
        container.scrollTop = container.scrollHeight;
    }
    
    /**
     * 更新消息（带思考内容折叠）
     */
    updateMessageWithThinking(messageDiv, thinkingText, contentText, isStillThinking) {
        let html = '';
        
        // 思考内容折叠区
        if (thinkingText) {
            const openAttr = isStillThinking ? ' open' : '';
            const statusLabel = isStillThinking ? '[ 思考中... ]' : '[ 思考过程 ]';
            const escapedThinking = marked(thinkingText);
            html += `<details class="thinking-block"${openAttr}>
                <summary class="thinking-summary">${statusLabel}</summary>
                <div class="thinking-content">${escapedThinking}</div>
            </details>`;
        } else if (isStillThinking) {
            // 还没收到任何内容，显示思考中指示器
            html += `<details class="thinking-block" open>
                <summary class="thinking-summary">[ 思考中... ]</summary>
                <div class="thinking-content"><span class="thinking-loading">●●●</span></div>
            </details>`;
        }
        
        // 正文内容
        if (contentText) {
            html += `<div class="message-content">${marked(contentText)}</div>`;
        }
        
        messageDiv.innerHTML = html;
        
        // 为代码块添加复制按钮
        messageDiv.querySelectorAll('pre').forEach(pre => {
            const copyBtn = document.createElement('button');
            copyBtn.className = 'glass-btn copy-btn';
            copyBtn.textContent = '复制';
            copyBtn.onclick = () => {
                const code = pre.querySelector('code').textContent;
                navigator.clipboard.writeText(code);
                copyBtn.textContent = '已复制';
                setTimeout(() => copyBtn.textContent = '复制', 2000);
            };
            pre.appendChild(copyBtn);
        });
        
        // 滚动到底部
        const container = document.getElementById('messages-container');
        container.scrollTop = container.scrollHeight;
    }
    
    showSettingsModal(type) {
        const modal = document.getElementById('settings-modal');
        const title = document.getElementById('modal-title');
        const body = document.getElementById('modal-body');
        
        switch (type) {
            case 'global':
                title.textContent = '全局设置';
                body.innerHTML = this.renderGlobalSettings();
                this.bindGlobalSettingsEvents();
                break;
            case 'chat':
                title.textContent = '对话设置';
                body.innerHTML = this.renderChatSettings();
                this.bindChatSettingsEvents();
                break;
            case 'web_search':
                title.textContent = '联网搜索设置';
                body.innerHTML = this.renderWebSearchSettings();
                break;
            case 'web_browse':
                title.textContent = '网页分析设置';
                body.innerHTML = this.renderWebBrowseSettings();
                this.bindWebBrowseEvents();
                break;
            case 'toolbox':
                title.textContent = '工具箱';
                // 异步加载工具状态后渲染
                this.loadAndRenderToolbox(body);
                break;
        }
        
        modal.style.display = 'flex';
    }
    
    // ═══════════════════════════════════════════
    // 全局设置
    // ═══════════════════════════════════════════
    
    renderGlobalSettings() {
        const currentPlatform = this.configManager.get('platform') || '阿里';
        const platforms = ['阿里', 'DeepSeek', '智谱', 'Kimi'];
        
        // 所有平台的API Key输入框
        const apiKeysHtml = platforms.map(p => {
            const key = this.configManager.getApiKey(p);
            const isCurrent = (p === currentPlatform);
            return `
                <div class="form-group" style="${isCurrent ? '' : 'opacity: 0.6;'}">
                    <label>${p} API Key ${isCurrent ? '（当前）' : ''}</label>
                    <input type="password" class="api-key-input" data-platform="${p}" value="${key}" placeholder="输入 ${p} 平台的 API Key">
                </div>
            `;
        }).join('');
        
        return `
            <div class="settings-form">
                <div class="form-group">
                    <label>当前使用平台</label>
                    <select id="global-platform-select">
                        ${platforms.map(p => `<option value="${p}" ${p === currentPlatform ? 'selected' : ''}>${p}</option>`).join('')}
                    </select>
                </div>
                ${apiKeysHtml}
                <div class="form-group">
                    <label>模型</label>
                    <input type="text" id="global-model-input" value="${this.configManager.get('model') || ''}" placeholder="如 qwen-max, deepseek-chat">
                </div>
                <div class="form-group">
                    <label>Max Tokens</label>
                    <input type="number" id="global-max-tokens-input" value="${this.configManager.get('max_tokens') || 65536}">
                </div>
                <div class="form-group">
                    <label>Temperature: <span id="global-temp-value">${this.configManager.get('temperature') || 0.7}</span></label>
                    <input type="range" id="global-temperature-input" min="0" max="2" step="0.1" value="${this.configManager.get('temperature') || 0.7}">
                </div>
                <div class="form-group">
                    <label>思考深度</label>
                    <select id="global-thinking-level">
                        <option value="low" ${this.configManager.get('thinking_level') === 'low' ? 'selected' : ''}>低 - 快速响应</option>
                        <option value="medium" ${this.configManager.get('thinking_level') === 'medium' ? 'selected' : ''}>中 - 平衡</option>
                        <option value="high" ${(!this.configManager.get('thinking_level') || this.configManager.get('thinking_level') === 'high') ? 'selected' : ''}>高 - 深度思考</option>
                    </select>
                </div>
                <div class="form-group">
                    <label>Agent模式</label>
                    <select id="global-agent-mode">
                        <option value="code" ${this.configManager.get('agent_mode') === 'code' ? 'selected' : ''}>代码模式</option>
                        <option value="article" ${this.configManager.get('agent_mode') === 'article' ? 'selected' : ''}>文章模式</option>
                        <option value="rp" ${this.configManager.get('agent_mode') === 'rp' ? 'selected' : ''}>RP模式</option>
                    </select>
                </div>
                <button class="glass-btn" id="global-save-btn">保存全局设置</button>
            </div>
        `;
    }
    
    bindGlobalSettingsEvents() {
        // 平台切换 → 高亮当前平台的API Key区域
        const platformSelect = document.getElementById('global-platform-select');
        if (platformSelect) {
            platformSelect.addEventListener('change', () => {
                const p = platformSelect.value;
                document.querySelectorAll('.api-key-input').forEach(input => {
                    const group = input.closest('.form-group');
                    if (input.dataset.platform === p) {
                        group.style.opacity = '1';
                        // 更新"当前"标记
                        group.querySelector('label').innerHTML = `${input.dataset.platform} API Key（当前）`;
                    } else {
                        group.style.opacity = '0.6';
                        group.querySelector('label').innerHTML = `${input.dataset.platform} API Key`;
                    }
                });
            });
        }
        
        // 温度滑块实时更新
        const tempInput = document.getElementById('global-temperature-input');
        const tempValue = document.getElementById('global-temp-value');
        if (tempInput && tempValue) {
            tempInput.addEventListener('input', () => {
                tempValue.textContent = tempInput.value;
            });
        }
        
        // 保存按钮
        const saveBtn = document.getElementById('global-save-btn');
        if (saveBtn) {
            saveBtn.addEventListener('click', () => {
                const platform = platformSelect.value;
                // 收集所有平台的API Key
                document.querySelectorAll('.api-key-input').forEach(input => {
                    this.configManager.setApiKey(input.dataset.platform, input.value);
                });
                this.configManager.config.platform = platform;
                this.configManager.config.model = document.getElementById('global-model-input').value;
                this.configManager.config.max_tokens = parseInt(document.getElementById('global-max-tokens-input').value) || 65536;
                this.configManager.config.temperature = parseFloat(document.getElementById('global-temperature-input').value) || 0.7;
                this.configManager.config.thinking_level = document.getElementById('global-thinking-level').value;
                this.configManager.config.agent_mode = document.getElementById('global-agent-mode').value;
                // 一次性保存
                this.configManager.saveConfig();
                saveBtn.textContent = '已保存 ✓';
                setTimeout(() => saveBtn.textContent = '保存全局设置', 2000);
            });
        }
    }
    
    // ═══════════════════════════════════════════
    // 对话设置（支持独立绑定模型）
    // ═══════════════════════════════════════════
    
    renderChatSettings() {
        const hasChat = !!window.app?.chatManager?.currentChatId;
        return `
            <div class="settings-form">
                <div class="form-group">
                    <label>记忆轮数</label>
                    <input type="number" id="chat-memory-rounds-input" value="${this.configManager.get('memory_rounds') || 50}">
                    <small>保留最近N轮对话作为上下文</small>
                </div>
                <div class="form-group">
                    <label>
                        <input type="checkbox" id="chat-tools-enabled" ${(this.configManager.get('tools_enabled') ? 'checked' : '')}>
                        启用工具调用
                    </label>
                </div>
                <hr style="border: none; border-top: 1px solid rgba(0,0,0,0.1); margin: 8px 0;">
                <div class="form-group">
                    <label>
                        <input type="checkbox" id="chat-per-config-enabled">
                        为此对话绑定独立模型
                    </label>
                    <small>开启后此对话将使用独立的平台/模型配置，保存在对话记录中</small>
                </div>
                <div id="chat-per-config-section" style="display: none;">
                    <div class="form-group">
                        <label>平台</label>
                        <select id="chat-platform-select">
                            <option value="阿里">阿里</option>
                            <option value="DeepSeek">DeepSeek</option>
                            <option value="智谱">智谱</option>
                            <option value="Kimi">Kimi</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label>模型</label>
                        <input type="text" id="chat-model-input" placeholder="如 qwen-max, deepseek-chat">
                    </div>
                    <div class="form-group">
                        <label>Max Tokens</label>
                        <input type="number" id="chat-max-tokens-input" value="65536">
                    </div>
                    <div class="form-group">
                        <label>Temperature: <span id="chat-temp-value">0.7</span></label>
                        <input type="range" id="chat-temperature-input" min="0" max="2" step="0.1" value="0.7">
                    </div>
                    <div class="form-group">
                        <label>思考深度</label>
                        <select id="chat-thinking-level">
                            <option value="low">低 - 快速响应</option>
                            <option value="medium">中 - 平衡</option>
                            <option value="high" selected>高 - 深度思考</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label>Agent模式</label>
                        <select id="chat-agent-mode">
                            <option value="code">代码模式</option>
                            <option value="article">文章模式</option>
                            <option value="rp">RP模式</option>
                        </select>
                    </div>
                </div>
                <button class="glass-btn" id="chat-save-btn" ${!hasChat ? 'disabled' : ''}>保存对话设置</button>
                ${!hasChat ? '<small>请先新建对话</small>' : ''}
            </div>
        `;
    }
    
    async bindChatSettingsEvents() {
        const chatId = window.app?.chatManager?.currentChatId;
        const perConfigCheckbox = document.getElementById('chat-per-config-enabled');
        const perConfigSection = document.getElementById('chat-per-config-section');
        
        // 加载已有的对话级配置
        if (chatId) {
            try {
                const chatConfig = await this.configManager.loadChatConfig(chatId);
                if (chatConfig && Object.keys(chatConfig).length > 0) {
                    perConfigCheckbox.checked = true;
                    perConfigSection.style.display = 'block';
                    
                    if (chatConfig.platform) {
                        document.getElementById('chat-platform-select').value = chatConfig.platform;
                    }
                    if (chatConfig.model) {
                        document.getElementById('chat-model-input').value = chatConfig.model;
                    }
                    if (chatConfig.max_tokens) {
                        document.getElementById('chat-max-tokens-input').value = chatConfig.max_tokens;
                    }
                    if (chatConfig.temperature != null) {
                        document.getElementById('chat-temperature-input').value = chatConfig.temperature;
                        document.getElementById('chat-temp-value').textContent = chatConfig.temperature;
                    }
                    if (chatConfig.thinking_level) {
                        document.getElementById('chat-thinking-level').value = chatConfig.thinking_level;
                    }
                    if (chatConfig.agent_mode) {
                        document.getElementById('chat-agent-mode').value = chatConfig.agent_mode;
                    }
                }
            } catch (e) {
                console.error('加载对话配置失败:', e);
            }
        }
        
        // 开关切换
        if (perConfigCheckbox) {
            perConfigCheckbox.addEventListener('change', () => {
                perConfigSection.style.display = perConfigCheckbox.checked ? 'block' : 'none';
            });
        }
        
        // 温度滑块实时更新
        const tempInput = document.getElementById('chat-temperature-input');
        const tempValue = document.getElementById('chat-temp-value');
        if (tempInput && tempValue) {
            tempInput.addEventListener('input', () => {
                tempValue.textContent = tempInput.value;
            });
        }
        
        // 保存按钮
        const saveBtn = document.getElementById('chat-save-btn');
        if (saveBtn && chatId) {
            saveBtn.addEventListener('click', async () => {
                // 保存全局部分（静默，不逐条触发保存）
                this.configManager.set('memory_rounds', parseInt(document.getElementById('chat-memory-rounds-input').value) || 50, true);
                this.configManager.set('tools_enabled', document.getElementById('chat-tools-enabled').checked, true);
                
                // 保存对话级配置
                if (perConfigCheckbox.checked) {
                    const chatConfig = {
                        platform: document.getElementById('chat-platform-select').value,
                        model: document.getElementById('chat-model-input').value,
                        max_tokens: parseInt(document.getElementById('chat-max-tokens-input').value) || 65536,
                        temperature: parseFloat(document.getElementById('chat-temperature-input').value) || 0.7,
                        thinking_level: document.getElementById('chat-thinking-level').value,
                        agent_mode: document.getElementById('chat-agent-mode').value,
                    };
                    await this.configManager.saveChatConfig(chatId, chatConfig);
                }
                
                this.configManager.saveConfig();
                saveBtn.textContent = '已保存 ✓';
                setTimeout(() => saveBtn.textContent = '保存对话设置', 2000);
            });
        }
    }
    
    // ═══════════════════════════════════════════
    // 联网搜索/网页分析设置
    // ═══════════════════════════════════════════
    
    renderWebSearchSettings() {
        return `
            <div class="settings-form">
                <div class="form-group">
                    <label>最大结果数</label>
                    <input type="number" id="max-results-input" value="10">
                </div>
                <div class="form-group">
                    <label>搜索语言偏好</label>
                    <select id="search-lang-select">
                        <option value="zh">中文优先</option>
                        <option value="en">英文优先</option>
                        <option value="auto">自动检测</option>
                    </select>
                </div>
            </div>
        `;
    }
    
    // ═══════════════════════════════════════════
    // 网页分析 - 浏览器检测
    // ═══════════════════════════════════════════
    
    bindWebBrowseEvents() {
        const detectBtn = document.getElementById('browser-detect-btn');
        if (detectBtn) {
            detectBtn.addEventListener('click', () => this.detectBrowser());
        }
    }
    
    async detectBrowser() {
        const browserSelect = document.getElementById('browser-select');
        const resultDiv = document.getElementById('browser-detect-result');
        const detectBtn = document.getElementById('browser-detect-btn');
        const browser = browserSelect ? browserSelect.value : 'edge';
        
        detectBtn.disabled = true;
        detectBtn.textContent = '⏳ 检测中...';
        resultDiv.style.display = 'none';
        
        try {
            const response = await fetch(`/api/browser/detect?browser=${encodeURIComponent(browser)}`);
            if (!response.ok) throw new Error('检测失败');
            const data = await response.json();
            
            const browserNames = { edge: 'Microsoft Edge', chrome: 'Google Chrome', firefox: 'Mozilla Firefox' };
            const driverNames = { edge: 'msedgedriver.exe', chrome: 'chromedriver.exe', firefox: 'geckodriver.exe' };
            const bName = browserNames[browser] || browser;
            const dName = driverNames[browser] || 'WebDriver';
            
            let html = '';
            
            // 浏览器状态
            html += `<div style="margin-bottom:10px;">`;
            if (data.installed) {
                html += `<div style="color:#2a2;">✅ <b>${bName}</b> 已安装</div>`;
                html += `<div>版本: ${data.version}</div>`;
                if (data.path && data.path !== bName) html += `<div style="font-size:12px;opacity:0.7;">路径: ${data.path}</div>`;
            } else {
                html += `<div style="color:#e55;">❌ <b>${bName}</b> 未检测到</div>`;
                if (data.install_url) {
                    html += `<div><a href="${data.install_url}" target="_blank" style="color:rgba(100,150,255,0.9);">📥 下载 ${bName}</a></div>`;
                }
            }
            html += `</div>`;
            
            // WebDriver 状态
            html += `<div style="margin-bottom:10px; padding-top:8px; border-top:1px solid rgba(0,0,0,0.08);">`;
            html += `<div style="font-weight:600; margin-bottom:4px;">WebDriver: ${dName}</div>`;
            if (data.webdriver_installed) {
                html += `<div style="color:#2a2;">✅ WebDriver 已安装</div>`;
            } else {
                html += `<div style="color:#c80;">⚠️ WebDriver 未检测到</div>`;
                html += `<div style="font-size:12px; opacity:0.7; margin-top:4px;">将 ${dName} 放入项目目录或添加到系统 PATH</div>`;
            }
            html += `</div>`;
            
            // 下载链接
            if (data.webdriver_download_url || data.webdriver_official_url) {
                html += `<div style="padding-top:8px; border-top:1px solid rgba(0,0,0,0.08);">`;
                html += `<div style="font-weight:600; margin-bottom:4px;">WebDriver 下载:</div>`;
                if (data.webdriver_download_url) {
                    html += `<div><a href="${data.webdriver_download_url}" target="_blank" style="color:rgba(100,150,255,0.9); word-break:break-all;">📥 下载匹配版本 (${data.version})</a></div>`;
                }
                if (data.webdriver_official_url) {
                    html += `<div style="margin-top:4px;"><a href="${data.webdriver_official_url}" target="_blank" style="color:rgba(100,150,255,0.9);">🔗 官方下载页面</a></div>`;
                }
                html += `</div>`;
            }
            
            // 使用说明
            html += `<div style="margin-top:10px; padding:8px; background:rgba(100,150,255,0.06); border-radius:6px; font-size:12px; color:inherit; opacity:0.75;">`;
            html += `<b>使用方法:</b><br>`;
            html += `1. 下载与浏览器版本匹配的 WebDriver<br>`;
            html += `2. 解压后将 ${dName} 放入项目根目录或系统 PATH<br>`;
            html += `3. 网页分析工具将自动使用 Selenium 模式`;
            html += `</div>`;
            
            resultDiv.innerHTML = html;
            resultDiv.style.display = 'block';
        } catch (error) {
            resultDiv.innerHTML = `<div style="color:#e55;">检测出错: ${error.message}</div>`;
            resultDiv.style.display = 'block';
        } finally {
            detectBtn.disabled = false;
            detectBtn.textContent = '🔍 检测浏览器环境';
        }
    }
    
    renderWebBrowseSettings() {
        return `
            <div class="settings-form">
                <div class="form-group">
                    <label>最大内容长度</label>
                    <input type="number" id="max-length-input" value="8000">
                </div>
                <div class="form-group">
                    <label>浏览超时(秒)</label>
                    <input type="number" id="browse-timeout-input" value="30">
                </div>
                <div class="form-group" style="margin-top: 16px;">
                    <label style="font-size: 14px; font-weight: 600;">🌐 浏览器环境检测</label>
                </div>
                <div class="form-group">
                    <label>选择浏览器</label>
                    <select id="browser-select">
                        <option value="edge" selected>Microsoft Edge (默认)</option>
                        <option value="chrome">Google Chrome</option>
                        <option value="firefox">Mozilla Firefox</option>
                    </select>
                </div>
                <div class="form-group">
                    <button id="browser-detect-btn" style="width:100%; padding:8px 16px; border:1px solid rgba(100,150,255,0.4); border-radius:8px; background:rgba(100,150,255,0.1); color:inherit; cursor:pointer; font-size:13px;">
                        🔍 检测浏览器环境
                    </button>
                </div>
                <div id="browser-detect-result" style="display:none; padding:12px; border-radius:8px; background:rgba(0,0,0,0.03); font-size:13px; line-height:1.8;"></div>
            </div>
        `;
    }
    
    // ═══════════════════════════════════════════
    // 工具箱（带开关，同步后端）
    // ═══════════════════════════════════════════
    
    /**
     * 工具列表配置（id, 名称, 描述）
     */
    getToolConfig() {
        return [
            {
                section: '文件操作',
                tools: [
                    { id: 'read_file', name: '读取文件', desc: '读取指定路径的文件内容' },
                    { id: 'write_file', name: '写入文件', desc: '将内容写入指定文件' },
                    { id: 'edit_file', name: '编辑文件', desc: '对文件进行查找替换编辑' },
                ]
            },
            {
                section: '代码分析',
                tools: [
                    { id: 'global_search', name: '全局搜索', desc: '在项目中搜索匹配的文件' },
                    { id: 'regex_search', name: '正则匹配', desc: '使用正则表达式搜索代码' },
                ]
            },
            {
                section: '网络工具',
                tools: [
                    { id: 'web_search', name: '联网搜索', desc: '搜索互联网获取最新信息' },
                    { id: 'web_browse', name: '网页分析', desc: '提取网页内容进行分析' },
                ]
            }
        ];
    }
    
    /**
     * 从后端加载工具状态并渲染工具箱
     */
    async loadAndRenderToolbox(body) {
        body.innerHTML = '<div class="settings-form"><p>加载工具状态中...</p></div>';
        
        try {
            const response = await fetch('/api/tools');
            const data = await response.json();
            
            // 从后端同步工具状态到前端
            for (const tool of data.tools) {
                this.toolStates[tool.name] = tool.enabled;
            }
            this.toolsLoaded = true;
        } catch (error) {
            console.error('加载工具状态失败:', error);
        }
        
        body.innerHTML = this.renderToolbox();
        this.bindToolboxToggles();
    }
    
    renderToolbox() {
        const config = this.getToolConfig();
        const sections = config.map(section => {
            const toolItems = section.tools.map(tool => {
                const isActive = this.toolStates[tool.id] !== false; // 默认开启
                return `
                    <div class="tool-item">
                        <span class="tool-name">${tool.name}</span>
                        <span class="tool-desc">${tool.desc}</span>
                        <div class="tool-toggle ${isActive ? 'active' : ''}" data-tool-id="${tool.id}"></div>
                    </div>
                `;
            }).join('');
            
            return `
                <div class="tool-section">
                    <h3>${section.section}</h3>
                    <div class="tool-list">${toolItems}</div>
                </div>
            `;
        }).join('');
        
        return `<div class="settings-form">${sections}</div>`;
    }
    
    /**
     * 绑定工具箱开关事件 — 同步到后端 API
     */
    bindToolboxToggles() {
        document.querySelectorAll('.tool-toggle').forEach(toggle => {
            toggle.addEventListener('click', async () => {
                const toolId = toggle.dataset.toolId;
                const wasActive = toggle.classList.contains('active');
                
                // 先更新 UI（乐观更新）
                toggle.classList.toggle('active');
                const isActive = !wasActive;
                this.toolStates[toolId] = isActive;
                
                // 同步到后端
                try {
                    const response = await fetch(`/api/tools/${toolId}/toggle`, {
                        method: 'POST'
                    });
                    const result = await response.json();
                    console.log(`工具 ${toolId} → ${result.enabled ? '已启用' : '已禁用'}`);
                    
                    // 如果后端返回的状态不一致，修正 UI
                    if (result.enabled !== isActive) {
                        toggle.classList.toggle('active');
                        this.toolStates[toolId] = result.enabled;
                    }
                } catch (error) {
                    console.error(`切换工具 ${toolId} 失败:`, error);
                    // 回滚 UI
                    toggle.classList.toggle('active');
                    this.toolStates[toolId] = wasActive;
                }
            });
        });
    }
    
    /**
     * 检查工具是否启用
     */
    isToolEnabled(toolId) {
        return this.toolStates[toolId] !== false;
    }
    
    // ═══════════════════════════════════════════
    // 记忆概括面板
    // ═══════════════════════════════════════════
    
    renderMemoryPanel(data) {
        const panel = document.getElementById('summary-panel');
        if (!data || !data.total_rounds) {
            panel.innerHTML = '<div class="empty-state"><span>💭</span><p>暂无对话</p></div>';
            return;
        }
        
        let html = '';
        
        // 控制区
        html += '<div class="memory-controls">';
        html += `<div class="memory-toggle-row">
            <label><input type="checkbox" id="memory-enabled-toggle" ${data.enabled ? 'checked' : ''}> 启用记忆概括</label>
        </div>`;
        html += `<div class="memory-info-row">
            <span>总轮数: <b>${data.total_rounds}</b></span>
            <span>已概括: <b>${data.marker}</b></span>
            <span>未概括: <b>${data.unsummarized_rounds}</b></span>
        </div>`;
        html += `<div class="memory-chars-row">
            <label>字数上限: <input type="number" id="memory-max-chars" value="${data.max_summary_chars}" min="500" max="10000" step="500" style="width:80px;"></label>
            <button id="memory-save-config-btn" class="glass-btn" style="padding:4px 12px; font-size:12px;">保存配置</button>
        </div>`;
        html += `<button id="memory-summarize-btn" class="glass-btn memory-summarize-btn" ${!data.enabled || data.unsummarized_rounds <= 0 ? 'disabled' : ''}>
            ${data.unsummarized_rounds > 0 ? `✍ 开始概括 (${data.unsummarized_rounds}轮)` : '无需概括'}
        </button>`;
        html += '<div id="memory-loading" style="display:none; text-align:center; padding:8px; color:rgba(100,150,255,0.9);">⚙ AI正在概括中，请稍候...</div>';
        html += '</div>';
        
        // 概括列表
        const summaries = data.summaries || [];
        if (summaries.length === 0) {
            html += '<div class="empty-state" style="padding:20px;"><span style="font-size:32px;">💭</span><p>暂无概括</p><small>点击“开始概括”手动生成</small></div>';
        } else {
            html += summaries.map((s, i) => `
                <div class="memory-card">
                    <div class="memory-index">概括 #${i + 1} (轮次 ${s.round_start}–${s.round_end})</div>
                    <div>${s.content}</div>
                </div>
            `).join('');
        }
        
        panel.innerHTML = html;
        
        // 绑定事件
        this.bindMemoryPanelEvents(data);
    }
    
    bindMemoryPanelEvents(data) {
        const chatId = window.app?.chatManager?.currentChatId;
        if (!chatId) return;
        
        // 保存配置
        const saveConfigBtn = document.getElementById('memory-save-config-btn');
        if (saveConfigBtn) {
            saveConfigBtn.addEventListener('click', async () => {
                const enabled = document.getElementById('memory-enabled-toggle').checked;
                const maxChars = parseInt(document.getElementById('memory-max-chars').value) || 2000;
                try {
                    await fetch(`/api/chats/${chatId}/memory-config`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ enabled, max_summary_chars: maxChars })
                    });
                    saveConfigBtn.textContent = '已保存 ✓';
                    setTimeout(() => saveConfigBtn.textContent = '保存配置', 2000);
                    // 刷新面板
                    if (window.app) window.app.loadMemory(chatId);
                } catch (e) {
                    console.error('保存记忆配置失败:', e);
                }
            });
        }
        
        // 开始概括
        const summarizeBtn = document.getElementById('memory-summarize-btn');
        if (summarizeBtn) {
            summarizeBtn.addEventListener('click', async () => {
                const maxChars = parseInt(document.getElementById('memory-max-chars').value) || 2000;
                const loadingDiv = document.getElementById('memory-loading');
                summarizeBtn.disabled = true;
                loadingDiv.style.display = 'block';
                
                try {
                    const response = await fetch(`/api/chats/${chatId}/summarize`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ chat_id: chatId, max_chars: maxChars })
                    });
                    if (response.ok) {
                        // 刷新面板
                        if (window.app) window.app.loadMemory(chatId);
                    } else {
                        const err = await response.json();
                        alert(err.detail || '概括失败');
                    }
                } catch (e) {
                    console.error('概括失败:', e);
                    alert('概括失败: ' + e.message);
                } finally {
                    summarizeBtn.disabled = false;
                    loadingDiv.style.display = 'none';
                }
            });
        }
        
        // 启用开关切换时自动保存
        const enabledToggle = document.getElementById('memory-enabled-toggle');
        if (enabledToggle) {
            enabledToggle.addEventListener('change', () => {
                const maxChars = parseInt(document.getElementById('memory-max-chars').value) || 2000;
                fetch(`/api/chats/${chatId}/memory-config`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ enabled: enabledToggle.checked, max_summary_chars: maxChars })
                });
                // 更新概括按钮状态
                const sumBtn = document.getElementById('memory-summarize-btn');
                if (sumBtn) {
                    sumBtn.disabled = !enabledToggle.checked || data.unsummarized_rounds <= 0;
                }
            });
        }
    }
    
    // ═══════════════════════════════════════════
    // TODOLIST
    // ═══════════════════════════════════════════
    
    showTodolist(tasks) {
        const panel = document.getElementById('todolist-panel');
        const itemsDiv = document.getElementById('todolist-items');
        const progressSpan = document.getElementById('todolist-progress');
        
        if (tasks.length === 0) {
            panel.style.display = 'none';
            return;
        }
        
        panel.style.display = 'block';
        
        const completed = tasks.filter(t => t.status === 'completed').length;
        progressSpan.textContent = `${completed}/${tasks.length}`;
        
        itemsDiv.innerHTML = tasks.map(task => `
            <div class="todolist-item ${task.status}">
                <div class="status-icon"></div>
                <div class="task-content">
                    <div class="task-title">${task.title}</div>
                    ${task.description ? `<div class="task-desc">${task.description}</div>` : ''}
                </div>
            </div>
        `).join('');
    }
    
    // ═══════════════════════════════════════════
    // 工具记录侧边栏
    // ═══════════════════════════════════════════
    
    /**
     * HTML转义工具
     */
    escapeHtml(str) {
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }
    
    /**
     * 清空工具记录面板
     */
    clearToolRecords() {
        const list = document.getElementById('tool-records-list');
        if (list) {
            list.innerHTML = '<div class="tool-empty-state">暂无工具调用记录</div>';
        }
    }
    
    /**
     * 获取工具类型标签（读文件/写文件/搜索等）
     */
    getToolTypeTag(toolName) {
        const readTools = ['read_file'];
        const writeTools = ['write_file', 'edit_file'];
        const searchTools = ['global_search', 'regex_search'];
        const webTools = ['web_search', 'web_browse'];
        
        if (readTools.includes(toolName)) return '读文件';
        if (writeTools.includes(toolName)) return '写文件';
        if (searchTools.includes(toolName)) return '搜索';
        if (webTools.includes(toolName)) return '网络';
        return '工具';
    }
    
    /**
     * 判断工具输出是否应该显示在弹窗中
     * 只有读文件/搜索/网页分析类工具的终端输出才需要显示
     */
    shouldShowToolOutput(toolName) {
        const readTools = ['read_file', 'global_search', 'regex_search', 'web_search', 'web_browse'];
        return readTools.includes(toolName);
    }
    
    /**
     * 格式化工具输入参数为表格 HTML
     */
    formatToolInput(toolName, args) {
        try {
            let params = {};
            if (typeof args === 'string') {
                params = JSON.parse(args);
            } else {
                params = args || {};
            }
            
            // 根据工具类型美化参数名
            const labelMap = {
                // read_file
                file_path: '文件路径',
                path: '路径',
                // write_file
                content: '内容',
                // edit_file
                edits: '编辑',
                // global_search
                pattern: '匹配模式',
                directory: '目录',
                max_results: '最大结果数',
                // regex_search
                regex: '正则表达式',
                include_pattern: '包含文件',
                // web_search / web_browse
                query: '查询',
                url: '网址',
                max_results_count: '最大结果数',
                max_length: '最大长度',
            };
            
            let rows = '';
            for (const [key, value] of Object.entries(params)) {
                const label = labelMap[key] || key;
                let displayValue;
                if (typeof value === 'string') {
                    // 截断过长的内容
                    displayValue = value.length > 200 ? value.slice(0, 200) + '...' : value;
                } else if (Array.isArray(value)) {
                    displayValue = JSON.stringify(value, null, 0);
                    if (displayValue.length > 200) {
                        displayValue = displayValue.slice(0, 200) + '...';
                    }
                } else {
                    displayValue = String(value);
                }
                rows += `<tr><td class="param-name">${this.escapeHtml(label)}</td><td class="param-value">${this.escapeHtml(displayValue)}</td></tr>`;
            }
            
            if (!rows) return '';
            return `<table class="tool-input-table">${rows}</table>`;
        } catch (e) {
            // 解析失败，回退到原始字符串
            return `<table class="tool-input-table"><tr><td class="param-value">${this.escapeHtml(String(args))}</td></tr></table>`;
        }
    }
    
    /**
     * 为写文件/编辑文件提取文件路径显示
     */
    formatWriteFileResult(toolName, args) {
        try {
            const params = typeof args === 'string' ? JSON.parse(args) : args;
            const filePath = params.file_path || params.path || '';
            if (filePath) {
                return `<span style="font-size:11px; color:rgba(0,0,0,0.5); padding:4px 8px; display:block;">${this.escapeHtml(filePath)}</span>`;
            }
        } catch (e) {}
        return '';
    }
    
    /**
     * 添加工具调用记录到侧边栏
     */
    addToolRecord(name, args, thinkingContent = '', outputContent = '') {
        const list = document.getElementById('tool-records-list');
        if (!list) return null;
        
        // 移除空状态提示
        const emptyState = list.querySelector('.tool-empty-state');
        if (emptyState) emptyState.remove();
        
        const card = document.createElement('div');
        card.className = 'tool-card';
        
        const typeTag = this.getToolTypeTag(name);
        const inputTable = this.formatToolInput(name, args);
        const fileResultHtml = ['write_file', 'edit_file'].includes(name) ? this.formatWriteFileResult(name, args) : '';
        
        let html = `<div class="tool-card-header">${this.escapeHtml(name)}<span class="tool-tag">${typeTag}</span></div>`;
        html += inputTable;
        html += fileResultHtml;
        html += `<button class="tool-result-btn" disabled>执行中...</button>`;
        
        card.innerHTML = html;
        card._toolName = name;
        card._toolArgs = args;
        card._thinkingContent = thinkingContent;
        card._outputContent = outputContent;
        card._resultContent = '';
        
        // 点击卡片显示详情弹窗
        card.addEventListener('click', () => {
            this.showToolDetail(card);
        });
        
        list.appendChild(card);
        
        // 滚动到底部
        list.scrollTop = list.scrollHeight;
        
        return card;
    }
    
    /**
     * 更新工具调用结果
     */
    updateToolResult(card, content) {
        if (!card) return;
        
        const btn = card.querySelector('.tool-result-btn');
        card._resultContent = content;
        
        const toolName = card._toolName;
        
        if (!this.shouldShowToolOutput(toolName)) {
            // 写文件/编辑文件等：不显示弹窗按钮，只显示完成状态
            if (btn) {
                btn.textContent = '已完成';
                btn.disabled = true;
                btn.style.opacity = '0.5';
            }
        } else {
            // 读文件/搜索/网页分析：显示查看按钮
            if (btn) {
                btn.disabled = false;
                btn.textContent = '[ 查看输出结果 ]';
            }
        }
    }
    
    /**
     * 弹窗显示工具调用详情（思考 + 参数 + 结果）
     */
    showToolDetail(card) {
        const modal = document.getElementById('tool-output-modal');
        const title = document.getElementById('tool-modal-title');
        const body = document.getElementById('tool-modal-body');
        
        if (!modal || !title || !body) return;
        
        title.textContent = `[ ${card._toolName} ] 调用详情`;
        
        let html = '';
        
        // 1. 思考过程
        if (card._thinkingContent) {
            html += `<details class="tool-detail-section" open>
                <summary class="tool-detail-summary">💭 思考过程</summary>
                <div class="tool-detail-content">${marked(card._thinkingContent)}</div>
            </details>`;
        }
        
        // 2. AI输出内容（调用工具前的文本回复）
        if (card._outputContent) {
            html += `<details class="tool-detail-section" open>
                <summary class="tool-detail-summary">💬 AI输出</summary>
                <div class="tool-detail-content">${marked(card._outputContent)}</div>
            </details>`;
        }
        
        // 3. 工具参数
        const inputTable = this.formatToolInput(card._toolName, card._toolArgs);
        if (inputTable) {
            html += `<details class="tool-detail-section" open>
                <summary class="tool-detail-summary">🔧 工具参数</summary>
                <div class="tool-detail-content">${inputTable}</div>
            </details>`;
        }
        
        // 4. 工具执行结果
        if (card._resultContent) {
            html += `<details class="tool-detail-section" open>
                <summary class="tool-detail-summary">📤 执行结果</summary>
                <pre class="tool-detail-result">${this.escapeHtml(card._resultContent)}</pre>
            </details>`;
        } else {
            html += `<details class="tool-detail-section" open>
                <summary class="tool-detail-summary">📤 执行结果</summary>
                <div class="tool-detail-content" style="opacity:0.5;">(无结果)</div>
            </details>`;
        }
        
        body.innerHTML = html;
        modal.style.display = 'flex';
    }
}
