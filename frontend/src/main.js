/**
 * YOder前端主入口
 */
import 'highlight.js/styles/atom-one-dark.css';
import { WebGLBackground } from './webgl/background.js';
import { ChatManager } from './managers/chatManager.js';
import { UIManager } from './managers/uiManager.js';
import { ConfigManager } from './managers/configManager.js';

class YOderApp {
    constructor() {
        this.webgl = null;
        this.chatManager = null;
        this.uiManager = null;
        this.configManager = null;
        this.buttonStates = new Map();
        this.leftSidebarVisible = true;
        this.rightSidebarVisible = true;
        this.wallpaperType = 'webgl';
        this._wpStatus = {};  // 壁纸状态缓存（从 status.json 读取）
        
        // 连点计数器（壁纸彩蛋）
        this.sendClickCount = 0;
        this.sendClickTimer = null;
        
        // 文件附件暂存
        this.pendingFiles = [];
        
        this.init();
    }
    
    async init() {
        console.log('YOder前端初始化...');
        
        // 1. 初始化WebGL背景
        const canvas = document.getElementById('webgl-bg');
        this.webgl = new WebGLBackground(canvas);
        
        // 2. 初始化配置管理器
        this.configManager = new ConfigManager();
        await this.configManager.loadConfig();
        
        // 3. 初始化UI管理器
        this.uiManager = new UIManager(this.configManager);
        
        // 4. 初始化管理对话
        this.chatManager = new ChatManager(this.configManager, this.uiManager);
        
        // 5. 绑定事件
        this.bindEvents();
        
        // 6. 初始化侧边栏状态
        this.updateSidebarLayout();
        
        // 7. 恢复壁纸设置（异步从 status.json 加载）
        await this.restoreWallpaper();
        
        // 8. 加载对话列表并恢复上次对话
        await this.loadChatList();
        
        // 尝试恢复上次活跃的对话
        if (this.chatManager.currentChatId) {
            try {
                const response = await fetch(`/api/chats/${this.chatManager.currentChatId}/history`);
                if (response.ok) {
                    const messages = await response.json();
                    if (messages.length > 0) {
                        this.chatManager.switchChat(this.chatManager.currentChatId);
                    } else {
                        // 对话存在但为空，清空UI
                        this.chatManager.currentChatId = null;
                    }
                } else {
                    // 对话不存在（已被删除）
                    this.chatManager.currentChatId = null;
                }
            } catch (e) {
                console.error('恢复对话失败:', e);
                this.chatManager.currentChatId = null;
            }
        }
        
        console.log('YOder前端初始化完成');
    }
    
    bindEvents() {
        // 发送按钮
        const sendBtn = document.getElementById('send-btn');
        const input = document.getElementById('message-input');
        
        sendBtn.addEventListener('click', () => this.handleSendClick());
        
        // 停止按钮
        const stopBtn = document.getElementById('stop-btn');
        stopBtn.addEventListener('click', () => {
            this.chatManager.stopGeneration();
        });
        
        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.handleSendClick();
            }
        });
        
        // 新建对话
        document.getElementById('new-chat-btn').addEventListener('click', () => {
            this.chatManager.createNewChat();
        });
        
        // 侧边栏切换按钮
        document.getElementById('toggle-left-sidebar').addEventListener('click', () => {
            this.toggleLeftSidebar();
        });
        
        document.getElementById('toggle-right-sidebar').addEventListener('click', () => {
            this.toggleRightSidebar();
        });
        
        // 底部工具栏按钮（带开关状态）
        this.bindToggleButton('global-settings-btn', 'global', () => {
            this.uiManager.showSettingsModal('global');
        });
        
        this.bindToggleButton('chat-settings-btn', 'chat', () => {
            this.uiManager.showSettingsModal('chat');
        });
        
        this.bindToggleButton('web-search-btn', 'web_search', () => {
            this.uiManager.showSettingsModal('web_search');
        });
        
        this.bindToggleButton('web-browse-btn', 'web_browse', () => {
            this.uiManager.showSettingsModal('web_browse');
        });
        
        this.bindToggleButton('toolbox-btn', 'toolbox', () => {
            this.uiManager.showSettingsModal('toolbox');
        });
        
        this.bindToggleButton('legacy-chain-btn', 'legacy_chain', () => {
            this.configManager.toggleLegacyChain();
        });
        
        // 关闭弹窗
        document.querySelectorAll('.close-modal').forEach(btn => {
            btn.addEventListener('click', () => {
                document.getElementById('settings-modal').style.display = 'none';
                this.resetToolbarButtons();
            });
        });
        
        // 点击弹窗外部关闭
        document.getElementById('settings-modal').addEventListener('click', (e) => {
            if (e.target === e.currentTarget) {
                document.getElementById('settings-modal').style.display = 'none';
                this.resetToolbarButtons();
            }
        });
        
        // 关闭壁纸弹窗
        document.querySelectorAll('.close-wallpaper-modal').forEach(btn => {
            btn.addEventListener('click', () => {
                document.getElementById('wallpaper-modal').style.display = 'none';
            });
        });
        
        // 壁纸选项点击
        document.querySelectorAll('.wallpaper-option').forEach(option => {
            option.addEventListener('click', (e) => {
                const wallpaper = option.dataset.wallpaper;
                if (wallpaper === 'custom') {
                    document.getElementById('wallpaper-file-input').click();
                } else {
                    this.setWallpaper(wallpaper);
                }
            });
        });
        
        // 文件选择
        document.getElementById('wallpaper-file-input').addEventListener('change', (e) => {
            const file = e.target.files[0];
            if (file) {
                this.setCustomWallpaper(file);
            }
        });
        
        // 壁纸参数滑块
        const blurSlider = document.getElementById('wallpaper-blur-slider');
        const opacitySlider = document.getElementById('wallpaper-opacity-slider');
        if (blurSlider) {
            blurSlider.addEventListener('input', () => {
                const val = blurSlider.value;
                document.getElementById('blur-value-display').textContent = `${val}px`;
                document.documentElement.style.setProperty('--wp-blur', `${val}px`);
                this._wpStatus.blur = val;
                this._saveWallpaperStatus();
            });
        }
        if (opacitySlider) {
            opacitySlider.addEventListener('input', () => {
                const val = opacitySlider.value;
                document.getElementById('opacity-value-display').textContent = `${val}%`;
                this.applyWallpaperOpacity(val);
                this._wpStatus.opacity = val;
                this._saveWallpaperStatus();
            });
        }
        
        // 右侧标签切换
        document.querySelectorAll('.tab-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const tab = e.target.dataset.tab;
                document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
                document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
                e.target.classList.add('active');
                document.getElementById(`${tab}-panel`).classList.add('active');
            });
        });
        
        // 文件加载按钮
        document.getElementById('load-folder-btn').addEventListener('click', () => {
            this.loadFolder();
        });
        
        // 刷新文件列表按钮
        document.getElementById('refresh-folder-btn').addEventListener('click', () => {
            this.refreshFolder();
        });
        
        // 清除文件列表按钮
        document.getElementById('clear-folder-btn').addEventListener('click', () => {
            this.clearFolder();
        });
        
        // 文件附件按钮
        document.getElementById('attach-file-btn').addEventListener('click', () => {
            document.getElementById('chat-file-input').click();
        });
        
        // 文件选择变化
        document.getElementById('chat-file-input').addEventListener('change', (e) => {
            this.addPendingFiles(e.target.files);
            e.target.value = ''; // 重置以便重复选择同一文件
        });
        
        // 工具输出弹窗关闭按钮
        const toolModalCloseBtn = document.getElementById('tool-modal-close-btn');
        if (toolModalCloseBtn) {
            toolModalCloseBtn.addEventListener('click', () => {
                document.getElementById('tool-output-modal').style.display = 'none';
            });
        }
        // 点击弹窗背景关闭
        const toolModalOverlay = document.getElementById('tool-output-modal');
        if (toolModalOverlay) {
            toolModalOverlay.addEventListener('click', (e) => {
                if (e.target === toolModalOverlay) {
                    toolModalOverlay.style.display = 'none';
                }
            });
        }
    }
    
    /**
     * 处理发送按钮点击（含连点5次触发壁纸彩蛋）
     */
    handleSendClick() {
        const input = document.getElementById('message-input');
        const message = input.value.trim();
        
        if (message || this.pendingFiles.length > 0) {
            // 有内容或有附件，正常发送
            this.sendClickCount = 0;
            if (this.sendClickTimer) {
                clearTimeout(this.sendClickTimer);
                this.sendClickTimer = null;
            }
            input.value = '';
            const files = [...this.pendingFiles];
            this.pendingFiles = [];
            this.renderPendingFiles();
            this.chatManager.sendMessage(message, files, this.loadedFolder || '');
            return;
        }
        
        // 输入为空，计数连点
        this.sendClickCount++;
        
        if (this.sendClickTimer) {
            clearTimeout(this.sendClickTimer);
        }
        
        // 2秒内未继续点击则重置计数
        this.sendClickTimer = setTimeout(() => {
            this.sendClickCount = 0;
        }, 2000);
        
        // 连点5次触发壁纸设置
        if (this.sendClickCount >= 5) {
            this.sendClickCount = 0;
            if (this.sendClickTimer) {
                clearTimeout(this.sendClickTimer);
                this.sendClickTimer = null;
            }
            this.showWallpaperModal();
        }
    }
    
    bindToggleButton(id, stateKey, callback) {
        const btn = document.getElementById(id);
        this.buttonStates.set(stateKey, false);
        
        btn.addEventListener('click', () => {
            const currentState = this.buttonStates.get(stateKey);
            const newState = !currentState;
            this.buttonStates.set(stateKey, newState);
            
            // 更新按钮视觉状态
            if (newState) {
                btn.classList.add('active');
            } else {
                btn.classList.remove('active');
            }
            
            // 执行回调
            callback();
        });
    }
    
    toggleLeftSidebar() {
        this.leftSidebarVisible = !this.leftSidebarVisible;
        this.updateSidebarLayout();
    }
    
    toggleRightSidebar() {
        this.rightSidebarVisible = !this.rightSidebarVisible;
        this.updateSidebarLayout();
    }
    
    updateSidebarLayout() {
        const app = document.getElementById('app');
        const leftToggle = document.getElementById('toggle-left-sidebar');
        const rightToggle = document.getElementById('toggle-right-sidebar');
        
        // 更新类名
        app.classList.toggle('left-collapsed', !this.leftSidebarVisible);
        app.classList.toggle('right-collapsed', !this.rightSidebarVisible);
        
        // 更新切换按钮图标
        if (leftToggle) {
            leftToggle.querySelector('.toggle-icon').textContent = this.leftSidebarVisible ? '◀' : '▶';
        }
        if (rightToggle) {
            rightToggle.querySelector('.toggle-icon').textContent = this.rightSidebarVisible ? '▶' : '◀';
        }
    }
    
    resetToolbarButtons() {
        document.querySelectorAll('.toolbar-btn').forEach(btn => {
            btn.classList.remove('active');
        });
        this.buttonStates.forEach((_, key) => {
            this.buttonStates.set(key, false);
        });
    }
    
    showWallpaperModal() {
        document.getElementById('wallpaper-modal').style.display = 'flex';
        
        // 当自定义壁纸激活时显示参数滑块
        const isCustom = document.getElementById('app').classList.contains('custom-wallpaper');
        const paramsDiv = document.getElementById('wallpaper-custom-params');
        if (paramsDiv) {
            paramsDiv.style.display = isCustom ? 'block' : 'none';
        }
        
        // 加载壁纸历史
        this.loadWallpaperHistory();
        
        // 同步滑块到当前值（从缓存读取）
        const blurSlider = document.getElementById('wallpaper-blur-slider');
        const opacitySlider = document.getElementById('wallpaper-opacity-slider');
        if (blurSlider) {
            const savedBlur = this._wpStatus.blur || '8';
            blurSlider.value = savedBlur;
            document.getElementById('blur-value-display').textContent = `${savedBlur}px`;
        }
        if (opacitySlider) {
            const savedOpacity = this._wpStatus.opacity || '35';
            opacitySlider.value = savedOpacity;
            document.getElementById('opacity-value-display').textContent = `${savedOpacity}%`;
        }
    }
    
    /**
     * 加载已保存的壁纸历史列表
     */
    async loadWallpaperHistory() {
        const section = document.getElementById('wallpaper-history-section');
        const list = document.getElementById('wallpaper-history-list');
        if (!section || !list) return;
        
        try {
            const response = await fetch('/api/wallpapers');
            if (!response.ok) return;
            const wallpapers = await response.json();
            
            if (wallpapers.length === 0) {
                section.style.display = 'none';
                return;
            }
            
            section.style.display = 'block';
            const currentFile = this._wpStatus.file || '';
            
            list.innerHTML = wallpapers.map(wp => {
                const isActive = currentFile === wp.filename;
                return `
                    <div class="wallpaper-history-item ${isActive ? 'active' : ''}" 
                         data-filename="${wp.filename}" data-url="${wp.url}"
                         style="aspect-ratio:16/9; border-radius:6px; cursor:pointer; overflow:hidden;
                                border:2px solid ${isActive ? 'rgba(100,150,255,0.8)' : 'rgba(0,0,0,0.1)'};
                                background:url(${wp.url}) center/cover no-repeat;
                                transition:border-color 0.2s;">
                    </div>
                `;
            }).join('');
            
            // 绑定点击事件
            list.querySelectorAll('.wallpaper-history-item').forEach(item => {
                item.addEventListener('click', () => {
                    this.selectSavedWallpaper(item.dataset.url, item.dataset.filename);
                });
            });
        } catch (error) {
            console.error('加载壁纸历史失败:', error);
        }
    }
    
    /**
     * 选择已保存的壁纸
     */
    selectSavedWallpaper(url, filename) {
        let customBg = document.getElementById('custom-bg');
        if (!customBg) {
            customBg = document.createElement('div');
            customBg.id = 'custom-bg';
            document.body.insertBefore(customBg, document.body.firstChild);
        }
        customBg.style.backgroundImage = `url(${url})`;
        customBg.style.display = 'block';
        this.webgl.pause();
        document.body.style.background = 'transparent';
        document.body.classList.remove('webgl-fallback');
        const app = document.getElementById('app');
        app.classList.remove('dark-theme');
        app.classList.add('custom-wallpaper');
        
        this.restoreWallpaperParams();
        
        // 检测壁纸明暗度并自动适配主题
        this.detectWallpaperBrightness(url);
        
        document.querySelectorAll('.wallpaper-option').forEach(opt => {
            opt.classList.toggle('active', opt.dataset.wallpaper === 'custom');
        });
        
        this._wpStatus.type = 'custom';
        this._wpStatus.url = url;
        this._wpStatus.file = filename;
        delete this._wpStatus.data;
        this._saveWallpaperStatus();
        
        // 更新历史列表选中状态
        document.querySelectorAll('.wallpaper-history-item').forEach(item => {
            item.style.borderColor = item.dataset.filename === filename ? 'rgba(100,150,255,0.8)' : 'rgba(0,0,0,0.1)';
        });
        
        const paramsDiv = document.getElementById('wallpaper-custom-params');
        if (paramsDiv) paramsDiv.style.display = 'block';
        document.getElementById('wallpaper-modal').style.display = 'none';
    }
    
    setWallpaper(type) {
        this.wallpaperType = type;
        const customBg = document.getElementById('custom-bg');
        const app = document.getElementById('app');
        
        // 移除WebGL后备渐变
        document.body.classList.remove('webgl-fallback');
        
        // 更新选中状态
        document.querySelectorAll('.wallpaper-option').forEach(opt => {
            opt.classList.toggle('active', opt.dataset.wallpaper === type);
        });
        
        switch (type) {
            case 'webgl':
                this.webgl.resume();
                if (customBg) customBg.style.display = 'none';
                document.body.style.background = '#f0f0f5';
                app.classList.remove('dark-theme', 'custom-wallpaper', 'wp-light', 'wp-dark');
                break;
            case 'dark':
                this.webgl.pause();
                if (customBg) customBg.style.display = 'none';
                document.body.style.background = '#1a1a2e';
                app.classList.add('dark-theme');
                app.classList.remove('custom-wallpaper', 'wp-light', 'wp-dark');
                break;
            case 'custom':
                // 由 setCustomWallpaper 处理
                return;
        }
        
        // 保存偏好
        this._wpStatus.type = type;
        delete this._wpStatus.url;
        delete this._wpStatus.file;
        delete this._wpStatus.data;
        this._saveWallpaperStatus();
        
        // 关闭模态框
        document.getElementById('wallpaper-modal').style.display = 'none';
    }
    
    setCustomWallpaper(file) {
        const reader = new FileReader();
        reader.onload = async (e) => {
            const dataUrl = e.target.result;
            let customBg = document.getElementById('custom-bg');
            if (!customBg) {
                customBg = document.createElement('div');
                customBg.id = 'custom-bg';
                document.body.insertBefore(customBg, document.body.firstChild);
            }
            customBg.style.backgroundImage = `url(${dataUrl})`;
            customBg.style.display = 'block';
            this.webgl.pause();
            document.body.style.background = 'transparent';
            document.body.classList.remove('webgl-fallback');
            const app = document.getElementById('app');
            app.classList.remove('dark-theme');
            app.classList.add('custom-wallpaper');
            
            // 应用已保存的壁纸参数
            this.restoreWallpaperParams();
            
            // 检测壁纸明暗度并自动适配主题
            this.detectWallpaperBrightness(dataUrl);
            
            // 更新选中状态
            document.querySelectorAll('.wallpaper-option').forEach(opt => {
                opt.classList.toggle('active', opt.dataset.wallpaper === 'custom');
            });
            
            this._wpStatus.type = 'custom';
            
            // 上传壁纸到后端备份
            try {
                const formData = new FormData();
                formData.append('file', file);
                const uploadRes = await fetch('/api/wallpapers/upload', { method: 'POST', body: formData });
                if (uploadRes.ok) {
                    const uploadData = await uploadRes.json();
                    this._wpStatus.url = uploadData.url;
                    this._wpStatus.file = uploadData.filename;
                    delete this._wpStatus.data;
                } else {
                    // 上传失败，回退到存储 dataURL
                    this._wpStatus.data = dataUrl;
                }
            } catch (err) {
                this._wpStatus.data = dataUrl;
            }
            this._saveWallpaperStatus();
            
            // 刷新壁纸历史列表
            this.loadWallpaperHistory();
            
            // 显示参数滑块并关闭模态框
            const paramsDiv = document.getElementById('wallpaper-custom-params');
            if (paramsDiv) paramsDiv.style.display = 'block';
            document.getElementById('wallpaper-modal').style.display = 'none';
        };
        reader.readAsDataURL(file);
    }
    
    /**
     * 检测壁纸明暗度，自动切换 wp-light / wp-dark 类
     * 通过canvas采样计算平均亮度，阈值 128
     */
    async detectWallpaperBrightness(src) {
        return new Promise((resolve) => {
            const img = new Image();
            img.crossOrigin = 'anonymous';
            img.onload = () => {
                const canvas = document.createElement('canvas');
                const ctx = canvas.getContext('2d');
                // 缩小到 50x50 采样，足够计算平均亮度
                canvas.width = 50;
                canvas.height = 50;
                ctx.drawImage(img, 0, 0, 50, 50);
                const data = ctx.getImageData(0, 0, 50, 50).data;
                let totalBrightness = 0;
                const pixelCount = data.length / 4;
                for (let i = 0; i < data.length; i += 4) {
                    // 感知亮度公式：0.299R + 0.587G + 0.114B
                    totalBrightness += 0.299 * data[i] + 0.587 * data[i + 1] + 0.114 * data[i + 2];
                }
                const avgBrightness = totalBrightness / pixelCount;
                const app = document.getElementById('app');
                if (avgBrightness > 140) {
                    // 亮色壁纸 → 白底黑字
                    app.classList.add('wp-light');
                    app.classList.remove('wp-dark');
                } else {
                    // 暗色壁纸 → 黑底白字
                    app.classList.add('wp-dark');
                    app.classList.remove('wp-light');
                }
                // 持久化结果
                this._wpStatus.brightness = avgBrightness > 140 ? 'light' : 'dark';
                this._saveWallpaperStatus();
                console.log(`壁纸亮度: ${avgBrightness.toFixed(1)} → ${avgBrightness > 140 ? '亮色' : '暗色'}`);
                resolve(avgBrightness);
            };
            img.onerror = () => {
                // 加载失败默认暗色
                const app = document.getElementById('app');
                app.classList.add('wp-dark');
                app.classList.remove('wp-light');
                resolve(80);
            };
            img.src = src;
        });
    }
    
    /**
     * 应用壁纸明暗类（从 localStorage 恢复，避免重复计算）
     */
    applyWallpaperTheme() {
        const brightness = this._wpStatus.brightness || 'dark';
        const app = document.getElementById('app');
        if (brightness === 'light') {
            app.classList.add('wp-light');
            app.classList.remove('wp-dark');
        } else {
            app.classList.add('wp-dark');
            app.classList.remove('wp-light');
        }
    }
    
    /**
     * 启动时恢复壁纸设置
     */
    async restoreWallpaper() {
        // 从 status.json 加载壁纸状态
        try {
            const res = await fetch('/api/wallpapers/status');
            if (res.ok) {
                this._wpStatus = await res.json();
            }
        } catch (e) {
            console.warn('加载壁纸状态失败:', e);
        }
        
        const type = this._wpStatus.type;
        if (!type) return;
        
        if (type === 'custom') {
            // 优先使用URL（服务端文件），回退到 dataURL
            const url = this._wpStatus.url;
            const data = this._wpStatus.data;
            const bgSrc = url || data;
            
            if (bgSrc) {
                let customBg = document.getElementById('custom-bg');
                if (!customBg) {
                    customBg = document.createElement('div');
                    customBg.id = 'custom-bg';
                    document.body.insertBefore(customBg, document.body.firstChild);
                }
                customBg.style.backgroundImage = `url(${bgSrc})`;
                customBg.style.display = 'block';
                this.webgl.pause();
                document.body.style.background = 'transparent';
                document.getElementById('app').classList.add('custom-wallpaper');
                
                // 恢复壁纸参数（模糊度、透明度）
                this.restoreWallpaperParams();
                
                // 应用已保存的主题检测结果
                this.applyWallpaperTheme();
                
                // 异步重新检测亮度（确保最新）
                this.detectWallpaperBrightness(bgSrc);
            }
        } else {
            this.setWallpaper(type);
        }
    }
    
    /**
     * 恢复已保存的壁纸参数（模糊度、透明度）
     */
    restoreWallpaperParams() {
        const blur = this._wpStatus.blur || '8';
        document.documentElement.style.setProperty('--wp-blur', `${blur}px`);
        
        const opacity = this._wpStatus.opacity || '35';
        this.applyWallpaperOpacity(opacity);
    }
    
    /**
     * 将壁纸状态保存到 wallpapers/status.json
     */
    _saveWallpaperStatus() {
        fetch('/api/wallpapers/status', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(this._wpStatus)
        }).catch(e => console.warn('保存壁纸状态失败:', e));
    }
    
    /**
     * 应用面板透明度（通过inline style覆盖CSS）
     */
    applyWallpaperOpacity(percent) {
        const alpha = (percent / 100).toFixed(2);
        const bgColor = `rgba(0, 0, 0, ${alpha})`;
        const app = document.getElementById('app');
        if (!app.classList.contains('custom-wallpaper')) return;
        
        // 更新所有面板的背景色
        app.querySelectorAll('.sidebar, #chat-main, #input-area, .todolist-panel').forEach(el => {
            el.style.background = bgColor;
        });
    }
    
    /**
     * 加载文件夹树
     */
    async loadFolder() {
        const pathInput = document.getElementById('file-path-input');
        const path = pathInput.value.trim();
        if (!path) return;
        
        // 记录加载的文件夹路径
        this.loadedFolder = path;
        
        const fileList = document.getElementById('file-list');
        fileList.innerHTML = '<div style="padding:10px;color:rgba(0,0,0,0.5)">加载中...</div>';
        
        try {
            const response = await fetch(`/api/files?path=${encodeURIComponent(path)}`);
            if (!response.ok) {
                const err = await response.json();
                fileList.innerHTML = `<div style="padding:10px;color:#e55">${err.detail || '加载失败'}</div>`;
                return;
            }
            const data = await response.json();
            fileList.innerHTML = '';
            fileList.appendChild(this.renderFileTree(data.tree));
            
            // 保存路径到 files.json（如果当前有对话）
            if (this.chatManager?.currentChatId) {
                await this.saveFilesToRecord();
            }
        } catch (error) {
            fileList.innerHTML = `<div style="padding:10px;color:#e55">加载失败: ${error.message}</div>`;
        }
    }
    
    /**
     * 刷新文件列表（重新加载当前路径）
     */
    async refreshFolder() {
        const pathInput = document.getElementById('file-path-input');
        const path = pathInput.value.trim();
        if (!path) return;
        await this.loadFolder();
    }
    
    /**
     * 静默刷新文件树（不改变路径，不保存 files.json，供发送前自动刷新用）
     */
    async refreshFolderSilently() {
        const path = this.loadedFolder || document.getElementById('file-path-input')?.value?.trim() || '';
        if (!path) return;
        
        try {
            const response = await fetch(`/api/files?path=${encodeURIComponent(path)}`);
            if (!response.ok) return;
            const data = await response.json();
            const fileList = document.getElementById('file-list');
            if (fileList) {
                fileList.innerHTML = '';
                fileList.appendChild(this.renderFileTree(data.tree));
            }
        } catch (e) {
            // 静默失败，不影响发送流程
            console.warn('静默刷新文件树失败:', e);
        }
    }
    
    /**
     * 清除文件列表
     */
    async clearFolder() {
        const fileList = document.getElementById('file-list');
        const pathInput = document.getElementById('file-path-input');
        fileList.innerHTML = '';
        pathInput.value = '';
        this.loadedFolder = '';
        
        // 删除后端 files.json
        const chatId = this.chatManager?.currentChatId;
        if (chatId) {
            try {
                await fetch(`/api/chats/${chatId}/files`, { method: 'DELETE' });
            } catch (e) {
                console.error('清除文件列表失败:', e);
            }
        }
    }
    
    /**
     * 保存文件路径到 files.json（仅保存根目录路径，不保存完整树）
     */
    async saveFilesToRecord() {
        const chatId = this.chatManager?.currentChatId;
        const path = this.loadedFolder || '';
        if (!chatId || !path) return;
        
        try {
            await fetch(`/api/chats/${chatId}/files`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ path })
            });
        } catch (e) {
            console.error('保存文件列表失败:', e);
        }
    }
    
    /**
     * 从 files.json 加载已保存的文件列表（仅读取路径，然后从 API 刷新树）
     */
    async loadSavedFiles(chatId) {
        const fileList = document.getElementById('file-list');
        const pathInput = document.getElementById('file-path-input');
        
        try {
            const response = await fetch(`/api/chats/${chatId}/files`);
            if (!response.ok) return;
            const data = await response.json();
            
            if (data.path) {
                this.loadedFolder = data.path;
                pathInput.value = data.path;
                // 从 API 加载新鲜的文件树
                await this.refreshFolder();
            } else {
                fileList.innerHTML = '';
            }
        } catch (e) {
            console.error('加载已保存文件列表失败:', e);
        }
    }
    
    /**
     * 递归渲染文件树
     */
    renderFileTree(node) {
        const container = document.createElement('div');
        
        if (node.type === 'directory') {
            const item = document.createElement('div');
            item.className = 'file-tree-item directory';
            item.innerHTML = `<span>📁</span><span>${node.name}</span>`;
            
            const childrenDiv = document.createElement('div');
            childrenDiv.className = 'file-tree-children';
            childrenDiv.style.display = 'none';
            
            item.addEventListener('click', (e) => {
                e.stopPropagation();
                childrenDiv.style.display = childrenDiv.style.display === 'none' ? 'block' : 'none';
                item.querySelector('span').textContent = childrenDiv.style.display === 'none' ? '📁' : '📂';
            });
            
            container.appendChild(item);
            
            if (node.children) {
                for (const child of node.children) {
                    childrenDiv.appendChild(this.renderFileTree(child));
                }
            }
            container.appendChild(childrenDiv);
        } else {
            const item = document.createElement('div');
            item.className = 'file-tree-item';
            const ext = node.name.split('.').pop().toLowerCase();
            const icon = ['js','ts','py','java','cpp','c','h','cs','go','rs'].includes(ext) ? '📝' 
                       : ['html','htm'].includes(ext) ? '🌐'
                       : ['css','scss','less'].includes(ext) ? '🎨'
                       : ['json','xml','yaml','yml','toml'].includes(ext) ? '⚙'
                       : ['md','txt','log'].includes(ext) ? '📝' : '📄';
            item.innerHTML = `<span>${icon}</span><span>${node.name}</span>`;
            item.title = node.path;
            container.appendChild(item);
        }
        
        return container;
    }
    
    /**
     * 添加文件到待发送列表
     */
    addPendingFiles(fileList) {
        for (const file of fileList) {
            const reader = new FileReader();
            reader.onload = (e) => {
                this.pendingFiles.push({
                    name: file.name,
                    content: e.target.result,
                    size: file.size
                });
                this.renderPendingFiles();
            };
            reader.readAsText(file);
        }
    }
    
    /**
     * 渲染待发送文件列表
     */
    renderPendingFiles() {
        const container = document.getElementById('file-attachments');
        if (this.pendingFiles.length === 0) {
            container.style.display = 'none';
            container.innerHTML = '';
            return;
        }
        container.style.display = 'flex';
        container.innerHTML = this.pendingFiles.map((f, i) => {
            const sizeStr = f.size > 1024 ? `${(f.size/1024).toFixed(1)}KB` : `${f.size}B`;
            return `<div class="file-chip">
                <span>📎 ${f.name} (${sizeStr})</span>
                <span class="remove-file" data-index="${i}">✕</span>
            </div>`;
        }).join('');
        
        container.querySelectorAll('.remove-file').forEach(btn => {
            btn.addEventListener('click', () => {
                this.pendingFiles.splice(parseInt(btn.dataset.index), 1);
                this.renderPendingFiles();
            });
        });
    }
    
    /**
     * 加载对话记忆概括
     */
    async loadMemory(chatId) {
        const panel = document.getElementById('summary-panel');
        if (!chatId) {
            panel.innerHTML = '<div class="empty-state"><span>💭</span><p>暂无记忆概括</p></div>';
            return;
        }
        
        try {
            const response = await fetch(`/api/chats/${chatId}/memory`);
            if (!response.ok) return;
            const data = await response.json();
            
            this.uiManager.renderMemoryPanel(data);
        } catch (error) {
            console.error('加载记忆失败:', error);
        }
    }
    
    /**
     * 加载对话列表到侧边栏
     */
    async loadChatList() {
        try {
            const response = await fetch('/api/chats');
            const chats = await response.json();
            this.renderChatList(chats);
        } catch (error) {
            console.error('加载对话列表失败:', error);
        }
    }
    
    /**
     * 渲染对话列表
     */
    renderChatList(chats) {
        const chatListDiv = document.getElementById('chat-list');
        if (!chats || chats.length === 0) {
            chatListDiv.innerHTML = '<div class="empty-state"><span>💬</span><p>暂无对话</p></div>';
            return;
        }
        
        chatListDiv.innerHTML = chats.map(chat => `
            <div class="chat-item ${chat.id === this.chatManager.currentChatId ? 'active' : ''}" data-chat-id="${chat.id}">
                <span class="chat-item-name">${chat.name}</span>
                <div class="chat-item-actions">
                    <button class="chat-action-btn rename-btn" data-chat-id="${chat.id}" title="重命名">✏</button>
                    <button class="chat-action-btn delete-btn" data-chat-id="${chat.id}" title="删除">🗑</button>
                </div>
            </div>
        `).join('');
        
        // 绑定点击切换事件
        chatListDiv.querySelectorAll('.chat-item').forEach(item => {
            item.addEventListener('click', (e) => {
                // 点击按钮时不切换对话
                if (e.target.closest('.chat-action-btn')) return;
                const chatId = item.dataset.chatId;
                this.chatManager.switchChat(chatId);
                chatListDiv.querySelectorAll('.chat-item').forEach(i => i.classList.remove('active'));
                item.classList.add('active');
            });
        });
        
        // 绑定重命名按钮
        chatListDiv.querySelectorAll('.rename-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                const chatId = btn.dataset.chatId;
                const item = btn.closest('.chat-item');
                const nameSpan = item.querySelector('.chat-item-name');
                const oldName = nameSpan.textContent;
                
                // 替换为输入框
                const input = document.createElement('input');
                input.type = 'text';
                input.className = 'chat-rename-input';
                input.value = oldName;
                nameSpan.replaceWith(input);
                input.focus();
                input.select();
                
                const finishRename = async () => {
                    const newName = input.value.trim() || oldName;
                    if (newName !== oldName) {
                        await this.chatManager.renameChat(chatId, newName);
                    } else {
                        // 恢复原名称显示
                        const span = document.createElement('span');
                        span.className = 'chat-item-name';
                        span.textContent = oldName;
                        input.replaceWith(span);
                    }
                };
                
                input.addEventListener('blur', finishRename);
                input.addEventListener('keydown', (e) => {
                    if (e.key === 'Enter') {
                        e.preventDefault();
                        input.blur();
                    }
                    if (e.key === 'Escape') {
                        input.value = oldName;
                        input.blur();
                    }
                });
            });
        });
        
        // 绑定删除按钮
        chatListDiv.querySelectorAll('.delete-btn').forEach(btn => {
            btn.addEventListener('click', async (e) => {
                e.stopPropagation();
                const chatId = btn.dataset.chatId;
                if (confirm('确定删除此对话？删除后不可恢复。')) {
                    await this.chatManager.deleteChat(chatId);
                }
            });
        });
    }
}

// 启动应用
window.addEventListener('DOMContentLoaded', () => {
    window.app = new YOderApp();
});
