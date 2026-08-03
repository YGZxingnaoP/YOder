/**
 * 对话管理器
 */
export class ChatManager {
    constructor(configManager, uiManager) {
        this.configManager = configManager;
        this.uiManager = uiManager;
        this.abortController = null;  // 用于停止AI输出
        this.isStreaming = false;
        
        // 从 localStorage 恢复上次活跃的对话ID
        this._currentChatId = localStorage.getItem('lastChatId') || null;
    }
    
    get currentChatId() {
        return this._currentChatId;
    }
    
    set currentChatId(val) {
        this._currentChatId = val;
        if (val) {
            localStorage.setItem('lastChatId', val);
        } else {
            localStorage.removeItem('lastChatId');
        }
    }
    
    async createNewChat() {
        try {
            const response = await fetch('/api/chats', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name: '新对话' })
            });
            
            const data = await response.json();
            this.currentChatId = data.chat_id;  // 自动持久化
            
            // 清空消息区
            document.getElementById('messages').innerHTML = '';
            
            // 刷新侧边栏对话列表
            if (window.app) {
                window.app.loadChatList();
            }
            
            console.log('新建对话成功:', data);
        } catch (error) {
            console.error('新建对话失败:', error);
        }
    }
    
    /**
     * 切换到已有对话
     */
    async switchChat(chatId) {
        this.currentChatId = chatId;  // 自动持久化
        
        // 清空并加载对话历史
        document.getElementById('messages').innerHTML = '';
        // 清空工具记录面板
        this.uiManager.clearToolRecords();
        
        // 加载已保存的文件列表
        if (window.app) {
            window.app.loadSavedFiles(chatId);
        }
        
        try {
            const response = await fetch(`/api/chats/${chatId}/history`);
            if (response.ok) {
                const messages = await response.json();
                let roundIdx = 0;
                for (let i = 0; i < messages.length; i++) {
                    const msg = messages[i];
                    if (msg.role === 'user') {
                        // 处理旧格式（content 内含文件文本）的兼容：如有 files 则用卡片模式，否则回退原始显示
                        const hasFilesField = (msg.files_full && msg.files_full.length > 0) || (msg.files && msg.files.length > 0);
                        if (hasFilesField) {
                            const userFiles = (msg.files_full || msg.files || []).map(f => ({
                                name: f.name || '?',
                                size: f.size || 0,
                                content: f.content || ''
                            }));
                            this.uiManager.addUserMessageWithFiles(msg.content || '', userFiles, roundIdx);
                        } else {
                            this.uiManager.addMessage(msg.content || '', msg.role, roundIdx);
                        }
                        roundIdx++;
                    } else if (msg.role === 'assistant') {
                        let displayContent = msg.content || '';
                        
                        // 工具调用记录 → 侧边栏
                        const hasToolCalls = msg.tool_calls && msg.tool_calls.length > 0;
                        if (hasToolCalls) {
                            // 捕获此轮工具调用前的思考内容和输出内容
                            const thinkSnap = msg.thinking || '';
                            const contentSnap = msg.content || '';
                            
                            for (const tc of msg.tool_calls) {
                                const fn = tc.function || {};
                                const fnName = fn.name || 'unknown';
                                const fnArgs = fn.arguments || '';
                                
                                // 查找匹配的工具结果
                                const nextMsgs = messages.slice(i + 1);
                                const toolResult = nextMsgs.find(m =>
                                    m.role === 'tool' && m.tool_call_id === tc.id
                                );
                                const resultContent = toolResult
                                    ? (toolResult.content || '').slice(0, 10000)
                                    : '';
                                
                                const card = this.uiManager.addToolRecord(fnName, fnArgs, thinkSnap, contentSnap);
                                if (resultContent) {
                                    this.uiManager.updateToolResult(card, resultContent);
                                }
                            }
                        }
                        
                        // 有工具调用时thinking已在侧边栏卡片显示，聊天气泡不重复显示
                        const showThinking = msg.thinking && !hasToolCalls;
                        if (showThinking) {
                            const div = this.uiManager.addMessage('', msg.role);
                            this.uiManager.updateMessageWithThinking(div, msg.thinking, displayContent, false);
                        } else if (displayContent) {
                            this.uiManager.addMessage(displayContent, msg.role);
                        }
                    } else if (msg.role === 'tool') {
                        // 无匹配的工具结果（独立显示）
                        const prevAssistant = messages.slice(0, i).reverse().find(m => m.role === 'assistant');
                        const hasMatchingTc = prevAssistant && prevAssistant.tool_calls &&
                            prevAssistant.tool_calls.some(tc => tc.id === msg.tool_call_id);
                        if (!hasMatchingTc) {
                            const toolContent = msg.content || '';
                            const div = this.uiManager.addMessage(
                                `[工具结果] ${toolContent.slice(0, 500)}${toolContent.length > 500 ? '\n...(已截断)' : ''}`,
                                'assistant'
                            );
                            if (div) div.style.opacity = '0.7';
                        }
                    }
                }
            }
        } catch (error) {
            console.error('加载对话历史失败:', error);
        }
        
        // 加载记忆概括
        if (window.app) {
            window.app.loadMemory(chatId);
        }
    }
    
    /**
     * 获取当前禁用的工具列表
     */
    getDisabledTools() {
        const toolConfig = this.uiManager.getToolConfig();
        const disabled = [];
        for (const section of toolConfig) {
            for (const tool of section.tools) {
                if (!this.uiManager.isToolEnabled(tool.id)) {
                    disabled.push(tool.id);
                }
            }
        }
        return disabled;
    }
    
    async sendMessage(message, files = [], loadedFolder = '') {
        if (!this.currentChatId) {
            await this.createNewChat();
        }
        
        // 发送前自动刷新文件列表并保存路径
        if (loadedFolder || window.app?.loadedFolder) {
            await window.app?.refreshFolderSilently();
            await window.app?.saveFilesToRecord();
        }
        
        // 构建发送给后端的数据（文本和文件分离，不再拼入消息体）
        let backendFiles = [];
        if (files.length > 0) {
            backendFiles = files.map(f => ({
                name: f.name,
                size: f.size,
                content: f.content || ''
            }));
        }
        
        // 显示用户消息：文本在气泡中，文件以卡片展示
        const currentRoundIndex = document.querySelectorAll('.message.user').length;
        this.uiManager.addUserMessageWithFiles(message, files, currentRoundIndex);
        
        try {
            // 获取禁用的工具列表
            const disabledTools = this.getDisabledTools();
            
            // 创建 AbortController 用于停止
            this.abortController = new AbortController();
            this.isStreaming = true;
            this.updateStopButton(true);
            
            // 发送到后端（文本与文件分离）
            const response = await fetch('/api/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    chat_id: this.currentChatId,
                    message: message,         // 仅用户输入的文本
                    files: backendFiles,       // 文件单独发送
                    tools_enabled: this.configManager.get('tools_enabled') !== false,
                    disabled_tools: disabledTools,
                    loaded_folder: loadedFolder || ''
                }),
                signal: this.abortController.signal
            });
            
            // 多气泡模式：每轮AI响应创建独立气泡（与刷新后样式一致）
            let assistantDiv = null;   // 当前轮的气泡DOM
            let thinkingText = '';     // 当前轮的思考文本
            let contentText = '';      // 当前轮的内容文本
            let lastToolBlock = null;  // 当前工具调用块DOM元素
            let needNewBubble = false; // 工具调用完成后，下一轮需新气泡
                        
            // 流式接收响应
            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let rawStream = '';
                        
            // 辅助函数：智能创建气泡
            // - 内容到达且无气泡 → 创建新气泡
            // - 上一轮刚结束(needNewBubble) → 先关闭旧气泡，再创建新气泡
            const ensureBubble = () => {
                if (needNewBubble) {
                    // 先完成旧气泡
                    if (assistantDiv) {
                        if (thinkingText || contentText) {
                            this.uiManager.updateMessageWithThinking(assistantDiv, thinkingText, contentText, false);
                        } else {
                            assistantDiv.remove();
                        }
                    }
                    thinkingText = '';
                    contentText = '';
                    assistantDiv = null;
                    needNewBubble = false;
                }
                if (!assistantDiv) {
                    assistantDiv = this.uiManager.addMessage('', 'assistant');
                    this.uiManager.updateMessageWithThinking(assistantDiv, '', '', true);
                }
                return assistantDiv;
            };
                        
            // DOM更新节流
            let lastUpdateTime = 0;
            const UPDATE_INTERVAL = 60; // ms
            let updateTimer = null;
            let needsUpdate = false;
                        
            const doUpdate = () => {
                // 没有任何内容就不渲染（也不创建气泡）
                if (!thinkingText && !contentText) {
                    needsUpdate = false;
                    return;
                }
                const isStillThinking = !contentText;
                this.uiManager.updateMessageWithThinking(
                    ensureBubble(), thinkingText, contentText, isStillThinking
                );
                lastUpdateTime = performance.now();
                needsUpdate = false;
            };
                        
            const scheduleUpdate = () => {
                const now = performance.now();
                if (now - lastUpdateTime >= UPDATE_INTERVAL) {
                    doUpdate();
                } else if (!needsUpdate) {
                    needsUpdate = true;
                    updateTimer = setTimeout(doUpdate, UPDATE_INTERVAL - (now - lastUpdateTime));
                }
            };
                        
            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                            
                const chunk = decoder.decode(value, { stream: true });
                rawStream += chunk;
                            
                // 解析带前缀的流式内容
                // \x01 = thinking, \x02 = content, \x03 = tool_call, \x04 = tool_result
                const lines = rawStream.split(/(?=\x01|\x02|\x03|\x04)/);
                rawStream = lines.pop() || '';
                            
                for (const line of lines) {
                    if (!line) continue; // 跳过空字符串（split前导空串）
                    
                    if (line.startsWith('\x01')) {
                        // thinking到达：确保气泡已创建，累积思考文本
                        ensureBubble();
                        thinkingText += line.slice(1);
                    } else if (line.startsWith('\x02')) {
                        // content到达：写入同一气泡
                        ensureBubble();
                        contentText += line.slice(1);
                    } else if (line.startsWith('\x03')) {
                        // 工具调用信息 → 侧边栏工具记录
                        if (updateTimer) { clearTimeout(updateTimer); updateTimer = null; }
                        // 结束当前气泡（如果已有内容），但不创建新气泡
                        if (assistantDiv) {
                            this.uiManager.updateMessageWithThinking(assistantDiv, thinkingText, contentText, false);
                        }
                        // 保存快照供侧边栏卡片使用
                        const thinkSnap = thinkingText;
                        const contentSnap = contentText;
                        try {
                            const tcInfo = JSON.parse(line.slice(1));
                            const card = this.uiManager.addToolRecord(tcInfo.name, tcInfo.arguments, thinkSnap, contentSnap);
                            lastToolBlock = card;
                        } catch (e) {
                            console.error('解析工具调用信息失败:', e);
                        }
                    } else if (line.startsWith('\x04')) {
                        // 工具执行结果 → 更新侧边栏工具记录
                        if (lastToolBlock) {
                            try {
                                const trInfo = JSON.parse(line.slice(1));
                                this.uiManager.updateToolResult(lastToolBlock, trInfo.content || '');
                            } catch (e) {
                                console.error('解析工具结果失败:', e);
                            }
                        }
                        // 工具轮结束，下一轮AI响应创建新气泡
                        needNewBubble = true;
                    } else {
                        // 无前缀内容，确保气泡已创建
                        ensureBubble();
                        contentText += line;
                    }
                }
                            
                // 节流实时更新消息
                scheduleUpdate();
            }
                        
            // 清理定时器
            if (updateTimer) {
                clearTimeout(updateTimer);
                updateTimer = null;
            }
                        
            // 处理剩余的原始流
            if (rawStream) {
                if (rawStream.startsWith('\x01')) {
                    thinkingText += rawStream.slice(1);
                } else if (rawStream.startsWith('\x02')) {
                    contentText += rawStream.slice(1);
                } else {
                    contentText += rawStream;
                }
            }
                        
            // 最终更新
            if (needNewBubble) {
                // 最后一轮以工具调用结束，旧气泡已在\x03时完成渲染
                // 不创建新气泡，不重复渲染
            } else if (thinkingText || contentText) {
                this.uiManager.updateMessageWithThinking(ensureBubble(), thinkingText, contentText, false);
            } else if (assistantDiv) {
                assistantDiv.remove();
            }
            
        } catch (error) {
            if (error.name === 'AbortError') {
                // 用户主动停止或超时断开，内容已保留在DOM中
                console.log('AI输出已停止');
            } else {
                console.error('发送消息失败:', error);
                this.uiManager.addMessage('发送失败,请重试', 'assistant');
            }
        } finally {
            this.isStreaming = false;
            this.abortController = null;
            // 清理停止超时定时器
            if (this._stopTimeout) {
                clearTimeout(this._stopTimeout);
                this._stopTimeout = null;
            }
            this.updateStopButton(false);
        }
    }
    
    /**
     * 停止AI输出
     */
    async stopGeneration() {
        if (!this.isStreaming) return;
        
        // 1. 后端设置停止标志
        if (this.currentChatId) {
            try {
                await fetch(`/api/chat/stop?chat_id=${encodeURIComponent(this.currentChatId)}`, {
                    method: 'POST'
                });
            } catch (e) {
                console.error('发送停止信号失败:', e);
            }
        }
        
        // 2. 不立即abort，让后端自然检测到停止标志后保存内容并关闭流
        //    设置安全超时：如果后端15秒内没有自然结束，强制断开
        this._stopTimeout = setTimeout(() => {
            if (this.abortController) {
                console.log('后端未在15秒内结束，强制断开');
                this.abortController.abort();
            }
        }, 15000);
        
        this.updateStopButton(false);
    }
    
    /**
     * 更新停止按钮显示状态
     */
    updateStopButton(show) {
        const sendBtn = document.getElementById('send-btn');
        const stopBtn = document.getElementById('stop-btn');
        if (sendBtn) sendBtn.style.display = show ? 'none' : '';
        if (stopBtn) stopBtn.style.display = show ? '' : 'none';
    }
    
    /**
     * 重命名对话
     */
    async renameChat(chatId, newName) {
        try {
            const response = await fetch(`/api/chats/${chatId}`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name: newName })
            });
            if (response.ok) {
                if (window.app) window.app.loadChatList();
            }
        } catch (error) {
            console.error('重命名对话失败:', error);
        }
    }
    
    /**
     * 删除对话
     */
    async deleteChat(chatId) {
        try {
            const response = await fetch(`/api/chats/${chatId}`, {
                method: 'DELETE'
            });
            if (response.ok) {
                // 如果删除的是当前对话，清空
                if (this.currentChatId === chatId) {
                    this.currentChatId = null;
                    document.getElementById('messages').innerHTML = '';
                    this.uiManager.clearToolRecords();
                }
                if (window.app) window.app.loadChatList();
            }
        } catch (error) {
            console.error('删除对话失败:', error);
        }
    }
    
    /**
     * HTML转义工具
     */
    escapeHtml(str) {
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }
    
    /**
     * 删除指定轮次的对话
     * @param {string} chatId - 对话ID
     * @param {number} roundIndex - 轮次索引(0-based)
     */
    async deleteRound(chatId, roundIndex) {
        try {
            const response = await fetch(`/api/chats/${chatId}/round/${roundIndex}`, {
                method: 'DELETE'
            });
            if (response.ok) {
                // 重新加载对话历史
                if (this.currentChatId === chatId) {
                    await this.switchChat(chatId);
                }
                // 刷新记忆面板
                if (window.app) {
                    window.app.loadMemory(chatId);
                }
            }
        } catch (error) {
            console.error('删除轮次失败:', error);
        }
    }
}
