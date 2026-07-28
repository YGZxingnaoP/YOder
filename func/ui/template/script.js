// ====================================================================
// 1. Markdown & KaTeX 扩展
// ====================================================================
const blockMathExtension = {
    name: 'blockMath', level: 'block',
    start(src) { return src.indexOf('$$'); },
    tokenizer(src, tokens) {
        const match = src.match(/^\$\$([\s\S]+?)\$\$/);
        if (match) return { type: 'blockMath', raw: match[0], text: match[1].trim() };
        return undefined;
    },
    renderer(token) {
        try { return '<div class="katex-display">' + katex.renderToString(token.text, { displayMode: true, throwOnError: false }) + '</div>'; }
        catch (e) { return '<pre>' + token.raw + '</pre>'; }
    }
};
const inlineMathExtension = {
    name: 'inlineMath', level: 'inline',
    start(src) { return src.indexOf('$'); },
    tokenizer(src, tokens) {
        const match = src.match(/^\$([^\n$]+?)\$/);
        if (match) return { type: 'inlineMath', raw: match[0], text: match[1].trim() };
        return undefined;
    },
    renderer(token) {
        try { return katex.renderToString(token.text, { throwOnError: false }); }
        catch (e) { return token.raw; }
    }
};
var codeHighlightExtension = {
    name: 'code',
    level: 'block',
    renderer: function(token) {
        var lang = token.lang || '';
        var code = token.text;
        var highlighted;
        try {
            if (lang && hljs.getLanguage(lang)) {
                highlighted = hljs.highlight(code, { language: lang, ignoreIllegals: true }).value;
            } else {
                highlighted = hljs.highlightAuto(code).value;
            }
        } catch(e) {
            highlighted = code.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
        }
        var cls = lang ? ' class="hljs language-' + lang + '"' : ' class="hljs"';
        return '<pre><code' + cls + '>' + highlighted + '</code></pre>\n';
    }
};
marked.use({ extensions: [blockMathExtension, inlineMathExtension, codeHighlightExtension] });
marked.setOptions({ breaks: true, gfm: true });

// ====================================================================
// 2. 全局变量 & 核心连接
// ====================================================================
var bridge = null, selectedFiles = new Set(), clickCount = 0, clickTimer = null, wallpaperDialogOpen = false;
var sendDisabled = false, lastUserMessageElem = null, pendingInputText = '';
var currentAssistantMsgDiv = null, currentRawText = "";
var renderTimer = null;
var foldRenderTimer = null;
var RENDER_INTERVAL = 80;
var summaryContentCache = '';
var chainModeEnabled = false;
var activeConvName = '';  // 当前选中的对话名称，防止重复点击
var PLATFORMS = ['阿里', 'DeepSeek', '智谱', 'Kimi'];
// 多块追踪：支持思考/内容交错显示在同一个气泡
var msgBlocks = [];          // [{type, text, rawText, element, contentElement}, ...]
var currentBlockIndex = -1;
var currentBlockType = null;  // "thinking" | "content" | null
var blockIdCounter = 0;
var userScrolling = false;
var scrollCheckTimer = null;
var programScrolling = false;  // 标记程序正在执行自动滚底
var programScrollTimer = null; // 用于可靠地重置 programScrolling 标志

// 设置程序滚动标志，并使用 setTimeout 确保 scroll 事件被正确忽略
// 比 requestAnimationFrame 更可靠：setTimeout 保证最小时延，不受渲染帧时序影响
function setProgramScroll(el) {
    programScrolling = true;
    if (programScrollTimer) clearTimeout(programScrollTimer);
    el.scrollTop = el.scrollHeight;
    programScrollTimer = setTimeout(function() {
        programScrolling = false;
        programScrollTimer = null;
    }, 120);
}

// 自动滚到底部（流式输出时尊重用户滚动，不强制拽回）
function autoScrollBottom(el) {
    if (!el) return;
    // 如果用户主动滚动上去了（不在底部附近），不强制拽回
    if (userScrolling) return;
    // 检查是否在底部附近（200px 阈值，允许小幅内容增长不触发用户滚动标志）
    var distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
    if (distanceFromBottom < 200) {
        if (el.scrollHeight > el.clientHeight) {
            setProgramScroll(el);
        }
    }
}

function attemptConnection() {
    if (typeof QWebChannel === 'undefined') { setTimeout(attemptConnection, 500); return; }
    var transport = null;
    if (window.qt && window.qt.webChannelTransport) transport = window.qt.webChannelTransport;
    else if (typeof qt !== 'undefined' && qt.webChannelTransport) transport = qt.webChannelTransport;
    else { setTimeout(attemptConnection, 500); return; }
    try {
        new QWebChannel(transport, function(channel) {
            var obj = channel.objects.bridge;
            if (obj) { bridge = obj; bridge.load_conversation_list(); }
        });
    } catch (e) { setTimeout(attemptConnection, 1000); }
}
function isBridgeReady() { return !!bridge; }

// ====================================================================
// 3. 对话列表管理
// ====================================================================
function updateConversationList(convs, activeFolder) {
    if (!bridge) return;
    // 同步当前对话名称，确保 switchConv 的防重复点击正确工作
    if (activeFolder) activeConvName = activeFolder;
    var convList = document.getElementById('conv-list');
    if (!convList) return;
    convList.innerHTML = '';
    var activeLi = null;
    convs.forEach(function(name) {
        var li = document.createElement('li');
        var nameSpan = document.createElement('span');
        nameSpan.textContent = name;
        nameSpan.style.cssText = 'flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;';
        li.appendChild(nameSpan);
        var btnGroup = document.createElement('div');
        btnGroup.style.cssText = 'display:flex;gap:8px;opacity:0;transition:opacity 0.2s;';
        var renameBtn = document.createElement('button');
        renameBtn.className = 'action-btn'; renameBtn.textContent = '✎'; renameBtn.title = '重命名';
        renameBtn.addEventListener('click', function(e) { e.stopPropagation(); renameConv(name); });
        var deleteBtn = document.createElement('button');
        deleteBtn.className = 'action-btn'; deleteBtn.textContent = '🗑️'; deleteBtn.title = '删除';
        deleteBtn.addEventListener('click', function(e) {
            e.stopPropagation();
            if (confirm('确定要删除对话 "' + name + '" 吗？此操作不可恢复。')) { if (bridge) bridge.delete_folder(name); }
        });
        btnGroup.appendChild(renameBtn); btnGroup.appendChild(deleteBtn);
        li.appendChild(btnGroup);
        var isActive = (activeFolder && name === activeFolder);
        if (isActive) {
            li.classList.add('active');
            btnGroup.style.opacity = '1';
            activeLi = li;
        }
        li.addEventListener('mouseenter', function() { btnGroup.style.opacity = '1'; });
        li.addEventListener('mouseleave', function() {
            if (!li.classList.contains('active')) btnGroup.style.opacity = '0';
        });
        li.addEventListener('click', function(e) { switchConv(name, e.currentTarget); });
        convList.appendChild(li);
    });
    // 自动滚动到活跃对话，或滚动到顶部显示最新对话（最新在上方）
    if (activeLi) {
        activeLi.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    } else {
        convList.scrollTop = 0;
    }
}

function switchConv(name, liElement) {
    if (sendDisabled) { alert('正在生成回答，请稍后再试'); return; }
    if (!isBridgeReady()) return;
    // 防止重复点击同一对话（避免重复异步调用导致白屏）
    if (name === activeConvName) return;
    activeConvName = name;
    selectedFiles.clear();
    hideConfigPanel();
    setChainMode(false);
    if (bridge && bridge.save_file_selection) {
        bridge.save_file_selection(JSON.stringify(Array.from(selectedFiles)));
    }
    bridge.switch_conversation(name);
    document.querySelectorAll('#conv-list li').forEach(function(li) {
        li.classList.remove('active');
        var bg = li.querySelector('div[style*="gap"]');
        if (bg) bg.style.opacity = '0';
    });
    if (liElement) {
        liElement.classList.add('active');
        var bg = liElement.querySelector('div[style*="gap"]');
        if (bg) bg.style.opacity = '1';
    }
}
function renameConv(oldName) {
    if (!isBridgeReady()) return;
    var newName = prompt('新名称:', oldName);
    if (newName && newName !== oldName) bridge.rename_folder(oldName, newName);
}
function newConversation() {
    if (sendDisabled) return;
    if (!isBridgeReady()) return;
    if (bridge && bridge.save_file_selection) bridge.save_file_selection(JSON.stringify(Array.from(selectedFiles)));
    activeConvName = '';  // 重置，允许新建后再次点击
    bridge.switch_conversation(''); clearMessages(); clearFileTree();
    setChainMode(false);
    showConfigPanel();
    document.querySelectorAll('#conv-list li').forEach(function(li) { li.classList.remove('active'); });
}
function confirmNewConvConfig() {
    if (!isBridgeReady()) return;
    var cfg = getConvConfig();
    hideConfigPanel();
    try {
        bridge.create_initial_folder(JSON.stringify(cfg));
    } catch(e) {
        console.error('创建对话失败:', e);
    }
}

// ====================================================================
// 4. 消息渲染 & 交互 - 多块交错支持
// ====================================================================
function addUserMessage(text, filesJson) {
    var chatArea = document.getElementById('chat-area');
    if (!chatArea) return;
    var div = document.createElement('div');
    div.className = 'message user';
    div.dataset.text = text;
    div.dataset.files = filesJson || "[]";
    div.dataset.chainMode = chainModeEnabled ? '1' : '0';
    var contentDiv = document.createElement('div');
    contentDiv.className = 'content';
    var p = document.createElement('p');
    p.textContent = text;
    p.style.marginBottom = '8px';
    contentDiv.appendChild(p);
    if (filesJson) {
        try {
            var files = JSON.parse(filesJson);
            files.forEach(function(fpath) {
                var fileName = fpath.split('\\').pop().split('/').pop();
                var details = document.createElement('details');
                details.className = 'file-card';
                var summary = document.createElement('summary');
                summary.innerHTML = '📄 <strong>' + fileName + '</strong> <span class="file-path">' + fpath + '</span>';
                var pre = document.createElement('pre');
                var code = document.createElement('code');
                pre.setAttribute('data-path', fpath);
                code.textContent = "正在读取文件...";
                pre.appendChild(code);
                details.appendChild(summary);
                details.appendChild(pre);
                contentDiv.appendChild(details);
            });
        } catch(e) {}
    }
    div.innerHTML = '<div class="avatar">👤</div>';
    var deleteBtn = document.createElement('button');
    deleteBtn.className = 'msg-delete';
    deleteBtn.textContent = '✕';
    deleteBtn.title = '删除这一轮';
    deleteBtn.onclick = function(e) { e.stopPropagation(); deleteTurn(this); };
    contentDiv.appendChild(deleteBtn);
    div.appendChild(contentDiv);
    chatArea.appendChild(div);
    setProgramScroll(chatArea);
    return div;
}
function deleteTurn(btn) {
    if (sendDisabled || !isBridgeReady()) return;
    var userMsg = btn.closest('.message.user');
    if (!userMsg) return;
    
    // 【修复1】仅统计 .message.user 来计算索引，确保与后端的轮次索引语义一致
    var allUserMsgs = Array.from(document.getElementById('chat-area').querySelectorAll('.message.user'));
    var userIndex = allUserMsgs.indexOf(userMsg);
    
    if (userIndex >= 0) {
        // 调用后端删除接口，传递正确的逻辑序号
        bridge.delete_turn(String(userIndex));
        
        // 【修复2】前端同步移除 DOM，保持 UI 与后端数据一致
        var nextElem = userMsg.nextElementSibling;
        userMsg.remove();
        
        // 单轮对话通常包含 user 和 assistant，如果后面紧跟着 assistant 回复，一并移除
        if (nextElem && nextElem.classList.contains('assistant')) {
            nextElem.remove();
        }
    }
}
function regenerate(btn) {
    if (sendDisabled || !isBridgeReady()) return;
    var assistantMsg = btn.closest('.message.assistant');
    if (!assistantMsg) return;
    if (renderTimer) { clearTimeout(renderTimer); renderTimer = null; }
    currentAssistantMsgDiv = null; currentRawText = "";
    msgBlocks = []; currentBlockIndex = -1; currentBlockType = null;
    var userMsg = assistantMsg.previousElementSibling;
    while (userMsg && !userMsg.classList.contains('user')) userMsg = userMsg.previousElementSibling;
    if (!userMsg) return;
    var isChainMode = userMsg.dataset.chainMode === '1';
    sendDisabled = true;
    document.getElementById('send-btn').disabled = true;
    if (isChainMode) {
        // Agent 模式：弹出选择对话框（先不删除消息，取消时保留）
        showRegenerateDialog(userMsg.dataset.text, userMsg.dataset.files, userMsg, assistantMsg);
    } else {
        var savedText = userMsg.dataset.text;
        var savedFiles = userMsg.dataset.files;
        assistantMsg.remove();
        userMsg.remove();
        // 创建新的 user 消息 div（与正常发送流程一致）
        addUserMessage(savedText, savedFiles);
        bridge.regenerate_message(savedText, savedFiles, JSON.stringify({chainMode: false}));
    }
}

function showRegenerateDialog(text, filesJson, userMsg, assistantMsg) {
    // 移除已有弹窗
    var existing = document.getElementById('regen-dialog-overlay');
    if (existing) existing.remove();

    var overlay = document.createElement('div');
    overlay.id = 'regen-dialog-overlay';
    overlay.style.cssText = 'position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.5);display:flex;align-items:center;justify-content:center;z-index:9999;';

    var dialog = document.createElement('div');
    dialog.style.cssText = 'background:var(--bg-color, #1e1e2e);color:var(--text-color, #e0e0e0);border-radius:12px;padding:24px;min-width:320px;max-width:480px;box-shadow:0 8px 32px rgba(0,0,0,0.4);';

    dialog.innerHTML = '<h3 style="margin:0 0 16px 0;font-size:16px;">🔄 重新生成选项</h3>' +
        '<p style="margin:0 0 20px 0;font-size:13px;color:#aaa;">此对话使用了 Agent 模式，请选择重新生成的方式：</p>' +
        '<div style="display:flex;flex-direction:column;gap:10px;">' +
        '<button id="regen-normal-btn" style="padding:12px 16px;border:1px solid #555;border-radius:8px;background:transparent;color:inherit;cursor:pointer;font-size:14px;text-align:left;">💬 转换为普通对话模式</button>' +
        '<button id="regen-agent-btn" style="padding:12px 16px;border:1px solid #7c5cbf;border-radius:8px;background:rgba(124,92,191,0.15);color:inherit;cursor:pointer;font-size:14px;text-align:left;">🔗 Agent 模式重新生成（重跑四阶段）</button>' +
        '<button id="regen-cancel-btn" style="padding:8px 16px;border:none;border-radius:8px;background:transparent;color:#888;cursor:pointer;font-size:13px;">取消</button>' +
        '</div>';

    overlay.appendChild(dialog);
    document.body.appendChild(overlay);

    // 取消时恢复原消息
    function restoreMessages() {
        var chatArea = document.getElementById('chat-area');
        // 恢复 user 消息（插回到最后一条 user 消息的位置，或追加到末尾）
        if (userMsg && userMsg.parentNode === null) {
            var lastChild = chatArea.lastElementChild;
            if (lastChild) {
                chatArea.appendChild(userMsg);
            } else {
                chatArea.appendChild(userMsg);
            }
        }
        // 恢复 assistant 消息（紧跟在 user 消息后面）
        if (assistantMsg && assistantMsg.parentNode === null) {
            if (userMsg && userMsg.parentNode) {
                if (userMsg.nextSibling) {
                    chatArea.insertBefore(assistantMsg, userMsg.nextSibling);
                } else {
                    chatArea.appendChild(assistantMsg);
                }
            } else {
                chatArea.appendChild(assistantMsg);
            }
        }
    }

    // 按钮事件
    document.getElementById('regen-normal-btn').addEventListener('click', function() {
        overlay.remove();
        if (assistantMsg) assistantMsg.remove();
        if (userMsg) userMsg.remove();
        // 创建新的 user 消息 div，转为普通模式
        var newUserDiv = addUserMessage(text, filesJson);
        if (newUserDiv) newUserDiv.dataset.chainMode = '0';
        if (bridge) bridge.regenerate_as_normal(text, filesJson, '{}');
    });
    document.getElementById('regen-agent-btn').addEventListener('click', function() {
        overlay.remove();
        if (assistantMsg) assistantMsg.remove();
        if (userMsg) userMsg.remove();
        // 创建新的 user 消息 div，保持 Agent 模式
        var newUserDiv = addUserMessage(text, filesJson);
        if (newUserDiv) newUserDiv.dataset.chainMode = '1';
        if (bridge) bridge.regenerate_as_agent(text, filesJson, '{}');
    });
    document.getElementById('regen-cancel-btn').addEventListener('click', function() {
        overlay.remove();
        restoreMessages();
        enableSendButton();
    });
    overlay.addEventListener('click', function(e) {
        if (e.target === overlay) {
            overlay.remove();
            restoreMessages();
            enableSendButton();
        }
    });
}

// 核心：addBlock - 按类型创建新块或追加到当前同类型块
function addBlock(type, text) {
    var chatArea = document.getElementById('chat-area');
    if (!chatArea) return;

    // 类型切换或无块 → 创建新块
    if (currentBlockType !== type || currentBlockIndex < 0) {
        blockIdCounter++;
        var blockId = 'block-' + blockIdCounter;

        if (!currentAssistantMsgDiv) {
            var div = document.createElement('div');
            div.className = 'message assistant';
            div.innerHTML = '<div class="avatar">🤖</div><div class="content is-streaming"><span class="model-tag"></span><div class="assistant-output"></div></div>';
            currentAssistantMsgDiv = div;
            chatArea.appendChild(div);
        }

        var outputContainer = currentAssistantMsgDiv.querySelector('.assistant-output');
        var blockDiv = document.createElement('div');
        blockDiv.id = blockId;

        var blockObj = { type: type, text: '', element: blockDiv, contentElement: null, rawText: '' };

        if (type === 'thinking') {
            blockDiv.className = 'thinking-block';
            blockDiv.innerHTML = '<details class="thinking-details"><summary>思考过程</summary><div class="thinking-content"></div></details>';
            blockObj.contentElement = blockDiv.querySelector('.thinking-content');
        } else if (type.indexOf('fold:') === 0) {
            // 如果最后一个块已经是同标题的fold块，追加而非新建
            var lastFoldBlock = null;
            for (var fi = msgBlocks.length - 1; fi >= 0; fi--) {
                if (msgBlocks[fi].type && msgBlocks[fi].type.indexOf('fold:') === 0) {
                    lastFoldBlock = msgBlocks[fi];
                    break;
                }
            }
            if (lastFoldBlock && lastFoldBlock.type === type) {
                lastFoldBlock.text += text;
                lastFoldBlock.rawText += text;
                if (lastFoldBlock.contentElement) {
                    try { lastFoldBlock.contentElement.innerHTML = marked.parse(lastFoldBlock.rawText); } catch(e) { lastFoldBlock.contentElement.textContent = lastFoldBlock.rawText; }
                }
                autoScrollBottom(document.getElementById('chat-area'));
                return;
            }
            blockIdCounter++;
            var blockId = 'block-' + blockIdCounter;
            if (!currentAssistantMsgDiv) {
                var div = document.createElement('div');
                div.className = 'message assistant';
                div.innerHTML = '<div class="avatar">🤖</div><div class="content is-streaming"><span class="model-tag"></span><div class="assistant-output"></div></div>';
                currentAssistantMsgDiv = div;
                chatArea.appendChild(div);
            }
            var outputContainer = currentAssistantMsgDiv.querySelector('.assistant-output');
            var blockDiv = document.createElement('div');
            blockDiv.id = blockId;
            blockDiv.className = 'fold-block';
            var foldTitle = type.split(':')[1] || '详细内容';
            blockDiv.innerHTML = '<details class="fold-details"><summary>' + foldTitle + '</summary><div class="fold-content"></div></details>';
            var blockObj = { type: type, text: '', element: blockDiv, contentElement: blockDiv.querySelector('.fold-content'), rawText: '', foldTitle: foldTitle };
            outputContainer.appendChild(blockDiv);
            msgBlocks.push(blockObj);
            currentBlockIndex = msgBlocks.length - 1;
            currentBlockType = type;
        } else {
            blockDiv.className = 'assistant-text-block';
            blockDiv.innerHTML = '<div class="assistant-text"></div>';
            blockObj.contentElement = blockDiv.querySelector('.assistant-text');
        }

        outputContainer.appendChild(blockDiv);
        msgBlocks.push(blockObj);
        currentBlockIndex = msgBlocks.length - 1;
        currentBlockType = type;
    }

    // 追加文本到当前块
    var block = msgBlocks[currentBlockIndex];
    block.text += text;
    if (type === 'content') {
        block.rawText += text;
        if (!renderTimer) {
            renderTimer = setTimeout(function() {
                renderTimer = null;
                if (block.contentElement) {
                    // 流式输出期间增量渲染 Markdown，而非显示原始语法
                    try { block.contentElement.innerHTML = marked.parse(block.rawText); } catch(e) { block.contentElement.textContent = block.rawText; }
                    // 移除 is-streaming 以使用正常 HTML 布局（而非 pre-wrap 等宽布局）
                    var streamParent = block.contentElement.closest('.content.is-streaming');
                    if (streamParent) streamParent.classList.remove('is-streaming');
                    autoScrollBottom(chatArea);
                }
            }, RENDER_INTERVAL);
        }
    } else if (type.indexOf('fold:') === 0) {
        // 折叠块也做增量 Markdown 渲染
        block.rawText += text;
        if (!foldRenderTimer) {
            foldRenderTimer = setTimeout(function() {
                foldRenderTimer = null;
                if (block.contentElement) {
                    try { block.contentElement.innerHTML = marked.parse(block.rawText); } catch(e) { block.contentElement.textContent = block.rawText; }
                    autoScrollBottom(chatArea);
                }
            }, RENDER_INTERVAL);
        }
    } else {
        if (block.contentElement) {
            block.contentElement.textContent += text;
            autoScrollBottom(chatArea);
        }
    }
}

// 直接添加折叠块（带标题和内容，一次性）
function addFoldBlock(title, text) {
    var chatArea = document.getElementById('chat-area');
    if (!chatArea) return;
    if (!currentAssistantMsgDiv) {
        var div = document.createElement('div');
        div.className = 'message assistant';
        div.innerHTML = '<div class="avatar">🤖</div><div class="content is-streaming"><span class="model-tag"></span><div class="assistant-output"></div></div>';
        currentAssistantMsgDiv = div;
        chatArea.appendChild(div);
    }
    var outputContainer = currentAssistantMsgDiv.querySelector('.assistant-output');
    blockIdCounter++;
    var blockDiv = document.createElement('div');
    blockDiv.id = 'block-' + blockIdCounter;
    blockDiv.className = 'fold-block';
    blockDiv.innerHTML = '<details class="fold-details"><summary>' + title + '</summary><div class="fold-content"></div></details>';
    var contentEl = blockDiv.querySelector('.fold-content');
    try { contentEl.innerHTML = marked.parse(text); } catch(e) { contentEl.textContent = text; }
    outputContainer.appendChild(blockDiv);
    msgBlocks.push({ type: 'fold', text: text, rawText: text, element: blockDiv, contentElement: contentEl, foldTitle: title });
    currentBlockIndex = msgBlocks.length - 1;
    currentBlockType = 'fold';
    autoScrollBottom(chatArea);
}

// 替换指定标题的折叠块内容（用于todolist动态更新）
function replaceFoldContent(title, newText) {
    for (var i = msgBlocks.length - 1; i >= 0; i--) {
        if (msgBlocks[i].foldTitle === title) {
            var block = msgBlocks[i];
            block.text = newText;
            block.rawText = newText;
            if (block.contentElement) {
                try { block.contentElement.innerHTML = marked.parse(newText); } catch(e) { block.contentElement.textContent = newText; }
            }
            autoScrollBottom(document.getElementById('chat-area'));
            return;
        }
    }
    // 未找到匹配块，新建一个
    addFoldBlock(title, newText);
}

// 兼容层：addThinking 委托给 addBlock
function addThinking(text) {
    if (!currentAssistantMsgDiv || currentBlockType !== 'thinking') {
        addBlock('thinking', text);
        return;
    }
    var block = msgBlocks[currentBlockIndex];
    block.text += text;
    if (block.contentElement) block.contentElement.textContent += text;
    autoScrollBottom(document.getElementById('chat-area'));
}

// 兼容层：addContent 委托给 addBlock
function addContent(chunk) {
    if (!currentAssistantMsgDiv || currentBlockType !== 'content') {
        addBlock('content', chunk);
        return;
    }
    var block = msgBlocks[currentBlockIndex];
    block.rawText += chunk;
    if (!renderTimer) {
        renderTimer = setTimeout(function() {
            renderTimer = null;
            if (block.contentElement) {
                // 流式输出期间增量渲染 Markdown
                try { block.contentElement.innerHTML = marked.parse(block.rawText); } catch(e) { block.contentElement.textContent = block.rawText; }
                var streamParent2 = block.contentElement.closest('.content.is-streaming');
                if (streamParent2) streamParent2.classList.remove('is-streaming');
                autoScrollBottom(document.getElementById('chat-area'));
            }
        }, RENDER_INTERVAL);
    }
}

function addCopyButtons(container) {
    container.querySelectorAll('pre').forEach(function(pre) {
        if (pre.querySelector('.code-copy-btn')) return;
        pre.style.position = 'relative';
        var btn = document.createElement('button');
        btn.className = 'code-copy-btn';
        btn.textContent = '复制';
        btn.addEventListener('click', function(e) {
            e.stopPropagation();
            var codeElem = pre.querySelector('code');
            var text = codeElem ? codeElem.textContent : pre.textContent;
            if (bridge && bridge.copy_to_clipboard) {
                bridge.copy_to_clipboard(text);
                btn.textContent = '已复制'; btn.classList.add('copied');
                setTimeout(function() { btn.textContent = '复制'; btn.classList.remove('copied'); }, 2000);
            }
        });
        pre.appendChild(btn);
    });
}

function toggleAllFolds(btn) {
    var msgDiv = btn.closest('.message.assistant');
    if (!msgDiv) return;
    var allDetails = msgDiv.querySelectorAll('details.fold-details, details.thinking-details');
    if (allDetails.length === 0) return;
    // 判断当前状态：多数展开则折叠，多数折叠则展开
    var openCount = 0;
    allDetails.forEach(function(d) { if (d.open) openCount++; });
    var shouldOpen = openCount <= allDetails.length / 2;
    allDetails.forEach(function(d) { d.open = shouldOpen; });
    btn.textContent = shouldOpen ? '📂 全部折叠' : '📂 全部展开';
}

function finishMessage(model) {
    if (renderTimer) { clearTimeout(renderTimer); renderTimer = null; }
    if (foldRenderTimer) { clearTimeout(foldRenderTimer); foldRenderTimer = null; }

    // 渲染所有内容块为最终 Markdown（包括思考块）
    for (var i = 0; i < msgBlocks.length; i++) {
        var block = msgBlocks[i];
        if (block.contentElement) {
            block.contentElement.innerHTML = renderMarkdownFinal(block.rawText || block.text || '');
        }
    }

    if (currentAssistantMsgDiv) {
        var contentDiv = currentAssistantMsgDiv.querySelector('.content');
        if (contentDiv) contentDiv.classList.remove('is-streaming');
        var outputEl = currentAssistantMsgDiv.querySelector('.assistant-output');
        if (outputEl) addCopyButtons(outputEl);
        if (currentAssistantMsgDiv) {
            var tag = currentAssistantMsgDiv.querySelector('.model-tag');
            if (tag) tag.textContent = model;
            var actionsDiv = document.createElement('div');
            actionsDiv.className = 'msg-actions';
            var regenBtn = document.createElement('button');
            regenBtn.className = 'regen-btn';
            regenBtn.textContent = '🔄 重新生成';
            regenBtn.onclick = function(e) { e.stopPropagation(); regenerate(this); };
            actionsDiv.appendChild(regenBtn);
            // 如果存在折叠块或思考块，添加一键折叠按钮
            var hasFolds = outputEl && outputEl.querySelectorAll('.fold-block, .thinking-block').length > 0;
            if (hasFolds) {
                var foldBtn = document.createElement('button');
                foldBtn.className = 'fold-all-btn';
                foldBtn.textContent = '📂 全部折叠';
                foldBtn.onclick = function(e) { e.stopPropagation(); toggleAllFolds(this); };
                actionsDiv.appendChild(foldBtn);
            }
            contentDiv.appendChild(actionsDiv);
        }
    }

    currentAssistantMsgDiv = null;
    msgBlocks = [];
    currentBlockIndex = -1;
    currentBlockType = null;
    currentRawText = "";

    var chatArea = document.getElementById('chat-area');
    if (chatArea) setProgramScroll(chatArea);
    enableSendButton();
}

function addError(msg) {
    if (lastUserMessageElem) { lastUserMessageElem.remove(); lastUserMessageElem = null; }
    var userInput = document.getElementById('user-input');
    if (pendingInputText && userInput) { userInput.value = pendingInputText; pendingInputText = ''; }
    enableSendButton();
    var chatArea = document.getElementById('chat-area');
    if (!chatArea) return;
    var div = document.createElement('div');
    div.className = 'message assistant error-msg';
    var contentDiv = document.createElement('div');
    contentDiv.className = 'content';
    contentDiv.textContent = msg;
    div.innerHTML = '<div class="avatar">⚠️</div>';
    div.appendChild(contentDiv);
    chatArea.appendChild(div);
    setProgramScroll(chatArea);
}

// ====================================================================
// 7. 历史记录加载 - 支持多块格式
// ====================================================================
function loadHistory(messages, targetScrollTop) {
    clearMessages();
    var chatArea = document.getElementById('chat-area');
    if (!chatArea) return;
    messages.forEach(function(msg) {
        if (msg.role === 'user') {
            var div = document.createElement('div');
            div.className = 'message user';
            div.dataset.text = msg.raw_text || (typeof msg.content === 'string' ? msg.content : '');
            div.dataset.files = JSON.stringify(msg.files || []);
            div.dataset.chainMode = msg.chain_mode ? '1' : '0';
            var contentDiv = document.createElement('div');
            contentDiv.className = 'content';
            if (Array.isArray(msg.content)) {
                msg.content.forEach(function(block) {
                    if (block.type === 'text') {
                        var p = document.createElement('p'); p.textContent = block.text; p.style.marginBottom = '12px'; contentDiv.appendChild(p);
                    } else if (block.type === 'file_content') {
                        var details = document.createElement('details'); details.className = 'file-card';
                        details.innerHTML = '<summary>📄 <strong>' + block.file_name + '</strong> <span class="file-path">' + block.file_path + '</span></summary><pre data-path="' + block.file_path + '"><code>' + block.text + '</code></pre>';
                        contentDiv.appendChild(details);
                    } else if (block.type === 'image_url') {
                        var img = document.createElement('img'); img.src = block.image_url.url; img.style.cssText = 'max-width:200px;border-radius:8px;display:block;margin-bottom:8px;'; contentDiv.appendChild(img);
                    }
                });
            } else {
                contentDiv.textContent = msg.content;
                if (msg.files && msg.files.length > 0) {
                    msg.files.forEach(function(fpath) {
                        var fileName = fpath.split('\\').pop().split('/').pop();
                        var details = document.createElement('details');
                        details.className = 'file-card';
                        var summary = document.createElement('summary');
                        summary.innerHTML = '📄 <strong>' + fileName + '</strong> <span class="file-path">' + fpath + '</span>';
                        var pre = document.createElement('pre');
                        var code = document.createElement('code');
                        pre.setAttribute('data-path', fpath);
                        code.textContent = "正在读取文件...";
                        pre.appendChild(code);
                        details.appendChild(summary);
                        details.appendChild(pre);
                        contentDiv.appendChild(details);
                    });
                }
            }
            var deleteBtn = document.createElement('button');
            deleteBtn.className = 'msg-delete'; deleteBtn.textContent = '✕'; deleteBtn.onclick = function(e) { e.stopPropagation(); deleteTurn(this); };
            div.innerHTML = '<div class="avatar">👤</div>'; div.appendChild(contentDiv); contentDiv.appendChild(deleteBtn); chatArea.appendChild(div);
        } else if (msg.role === 'assistant') {
            var div = document.createElement('div'); div.className = 'message assistant';
            var contentDiv = document.createElement('div'); contentDiv.className = 'content rendered';
            var actualDiv = document.createElement('div'); actualDiv.className = 'assistant-output';

            if (msg.blocks && Array.isArray(msg.blocks) && msg.blocks.length > 0) {
                // 新格式：多块结构（思考/内容交错）
                msg.blocks.forEach(function(block) {
                    if (block.type === 'thinking') {
                        var thinkDiv = document.createElement('div');
                        thinkDiv.className = 'thinking-block';
                        var tmpThink = document.createElement('div');
                        tmpThink.innerHTML = renderMarkdownFinal(block.text || '');
                        var det = document.createElement('details');
                        det.className = 'thinking-details';
                        det.innerHTML = '<summary>思考过程</summary>';
                        var thinkContent = document.createElement('div');
                        thinkContent.className = 'thinking-content';
                        while (tmpThink.firstChild) thinkContent.appendChild(tmpThink.firstChild);
                        det.appendChild(thinkContent);
                        thinkDiv.appendChild(det);
                        actualDiv.appendChild(thinkDiv);
                    } else if (block.type === 'content') {
                        var contentBlock = document.createElement('div');
                        contentBlock.className = 'assistant-text-block';
                        var tempDiv = document.createElement('div');
                        tempDiv.innerHTML = renderMarkdownFinal(block.text || '');
                        contentBlock.innerHTML = tempDiv.innerHTML;
                        actualDiv.appendChild(contentBlock);
                    } else if (block.type === 'fold') {
                        var foldBlock = document.createElement('div');
                        foldBlock.className = 'fold-block';
                        var foldTitle = block.foldTitle || '详细内容';
                        var foldDet = document.createElement('details');
                        foldDet.className = 'fold-details';
                        foldDet.innerHTML = '<summary>' + foldTitle + '</summary>';
                        var foldContent = document.createElement('div');
                        foldContent.className = 'fold-content';
                        var foldTmp = document.createElement('div');
                        foldTmp.innerHTML = renderMarkdownFinal(block.text || '');
                        while (foldTmp.firstChild) foldContent.appendChild(foldTmp.firstChild);
                        foldDet.appendChild(foldContent);
                        foldBlock.appendChild(foldDet);
                        actualDiv.appendChild(foldBlock);
                    }
                });
            } else {
                // 兼容旧格式
                if (msg.thinking) {
                    var tmpThink2 = document.createElement('div');
                    tmpThink2.innerHTML = renderMarkdownFinal(msg.thinking || '');
                    var thinkBlock = document.createElement('div');
                    thinkBlock.className = 'thinking-block';
                    var det2 = document.createElement('details');
                    det2.className = 'thinking-details';
                    det2.innerHTML = '<summary>思考过程</summary>';
                    var thinkContent2 = document.createElement('div');
                    thinkContent2.className = 'thinking-content';
                    while (tmpThink2.firstChild) thinkContent2.appendChild(tmpThink2.firstChild);
                    det2.appendChild(thinkContent2);
                    thinkBlock.appendChild(det2);
                    actualDiv.appendChild(thinkBlock);
                }
                var tempDiv = document.createElement('div');
                tempDiv.innerHTML = renderMarkdownFinal(msg.content || '');
                while (tempDiv.firstChild) actualDiv.appendChild(tempDiv.firstChild);
            }

            var modelTagSpan = document.createElement('span');
            modelTagSpan.className = 'model-tag';
            modelTagSpan.textContent = msg.model || '';
            actualDiv.insertBefore(modelTagSpan, actualDiv.firstChild);
            addCopyButtons(actualDiv); contentDiv.appendChild(actualDiv);
            div.innerHTML = '<div class="avatar">🤖</div>'; div.appendChild(contentDiv);
            var actionsDiv = document.createElement('div'); actionsDiv.className = 'msg-actions';
            actionsDiv.innerHTML = '<button class="regen-btn" onclick="event.stopPropagation(); regenerate(this)">🔄 重新生成</button>';
            // 如果存在折叠块或思考块，添加一键折叠按钮
            if (actualDiv.querySelectorAll('.fold-block, .thinking-block').length > 0) {
                var foldBtn = document.createElement('button');
                foldBtn.className = 'fold-all-btn';
                foldBtn.textContent = '📂 全部折叠';
                foldBtn.onclick = function(e) { e.stopPropagation(); toggleAllFolds(this); };
                actionsDiv.appendChild(foldBtn);
            }
            contentDiv.appendChild(actionsDiv); chatArea.appendChild(div);
        }
    });
    
    // 智能滚动恢复：如果有目标位置则滚动到目标位置，否则滚动到底部
    if (typeof targetScrollTop === 'number' && targetScrollTop > 0) {
        // 延迟执行确保DOM完全渲染
        setTimeout(function() {
            if (chatArea) {
                programScrolling = true;
                if (programScrollTimer) clearTimeout(programScrollTimer);
                chatArea.scrollTop = targetScrollTop;
                programScrollTimer = setTimeout(function() {
                    programScrolling = false;
                    programScrollTimer = null;
                }, 120);
            }
        }, 50);
    } else {
        setProgramScroll(chatArea);
        // 延迟兑底：DOM 渲染（markdown/代码高亮）完成后 scrollHeight 才准确
        setTimeout(function() { setProgramScroll(chatArea); }, 100);
    }
    // 强制重置视口，防止大内容导致整体偏移
    resetViewport();
    setTimeout(resetViewport, 100);
    
    sendDisabled = false; document.getElementById('send-btn').disabled = false;
}

function clearMessages() {
    if (renderTimer) { clearTimeout(renderTimer); renderTimer = null; }
    var chatArea = document.getElementById('chat-area');
    if (chatArea) chatArea.innerHTML = '';
    currentAssistantMsgDiv = null; currentRawText = '';
    msgBlocks = []; currentBlockIndex = -1; currentBlockType = null;
    sendDisabled = false; var sb = document.getElementById('send-btn'); if (sb) sb.disabled = false;
}

// ====================================================================
// 8. 文件树 & 侧边栏
// ====================================================================

function toggleSummaryBtn(show) {
    var btn = document.getElementById('toggle-summary-btn');
    if (btn) btn.style.display = show ? 'flex' : 'none';
}

function updateSummaryContent(content) {
    summaryContentCache = content || '';
    var contentEl = document.getElementById('summary-content');
    if (contentEl) {
        contentEl.textContent = summaryContentCache || '暂无概括内容';
    }
}

function loadSavedPaths(paths, selectedFilesArr) {
    selectedFiles = new Set(selectedFilesArr || []);
    if (paths && paths.length > 0) {
        if (bridge && bridge.load_cached_folders) {
            bridge.load_cached_folders(JSON.stringify(paths));
        }
    } else {
        clearFileTree();
        var ps = document.getElementById('path-selector');
        if (ps) ps.style.display = 'none';
    }
}

function displayFileTree(tree) {
    var c = document.getElementById('file-tree');
    if (!c) return;
    c.innerHTML = '';

    if (!tree) {
        var emptyMsg = document.createElement('div');
        emptyMsg.textContent = '文件夹为空或无法读取';
        emptyMsg.style.cssText = 'padding: 12px; color: #999; font-size: 13px;';
        c.appendChild(emptyMsg);
        openRightPanel();
        return;
    }

    var rootNode;
    if (Array.isArray(tree)) {
        if (tree.length === 0) {
            var emptyMsg2 = document.createElement('div');
            emptyMsg2.textContent = '该文件夹为空';
            emptyMsg2.style.cssText = 'padding: 12px; color: #999; font-size: 13px;';
            c.appendChild(emptyMsg2);
            openRightPanel();
            return;
        }
        rootNode = {
            type: 'directory',
            name: '根目录',
            children: tree
        };
    } else if (typeof tree === 'object' && tree.type === 'directory') {
        rootNode = tree;
    } else {
        rootNode = { type: 'directory', name: '根目录', children: [tree] };
    }

    var rootUl = document.createElement('ul');
    c.appendChild(rootUl);
    try {
        buildTreeDOM(rootNode, rootUl);
        rootUl.querySelectorAll(':scope > li').forEach(function(li) {
            if (li.querySelector(':scope > ul')) updateParentFolderCheckbox(li);
        });
        openRightPanel();
    } catch (e) {
        console.error('构建文件树异常:', e);
        alert('构建文件树失败: ' + e.message);
        c.innerHTML = '';
    }
}

function updateParentFolderCheckbox(f) {
    var p = f.parentElement ? f.parentElement.closest('li') : null;
    while (p && p.querySelector('ul')) {
        var c = p.querySelector(':scope > .node-content > input[type="checkbox"]');
        if (!c) break;
        var h = p.querySelectorAll('ul li[data-path] input[type="checkbox"]');
        if (h.length > 0) {
            var arr = Array.from(h);
            var checkedCount = arr.filter(function(b) { return b.checked; }).length;
            if (checkedCount === 0) { c.checked = false; c.indeterminate = false; }
            else if (checkedCount === arr.length) { c.checked = true; c.indeterminate = false; }
            else { c.checked = false; c.indeterminate = true; }
        }
        p = p.parentElement ? p.parentElement.closest('li') : null;
    }
}

function buildTreeDOM(n, p) {
    var l = document.createElement('li');
    var d = document.createElement('div'); d.className = 'node-content';
    var t = document.createElement('span'); t.className = 'toggle-icon'; t.innerHTML = n.type === 'directory' ? '▾' : ''; t.style.visibility = n.type === 'directory' ? 'visible' : 'hidden';
    var c = document.createElement('input'); c.type = 'checkbox';
    c.checked = false; c.indeterminate = false;
    var s = document.createElement('span'); s.className = 'node-name'; s.textContent = (n.type === 'directory' ? '📁 ' : '📄 ') + n.name;
    d.appendChild(t); d.appendChild(c); d.appendChild(s);

    if (n.type === 'file') {
        l.setAttribute('data-path', n.path);
        var k = document.createElement('span'); k.className = 'token-info'; k.textContent = (n.token_count || 0) + ' tk';
        d.appendChild(k);
        if (selectedFiles.has(n.path)) c.checked = true;
        c.addEventListener('change', function() {
            if (this.checked) selectedFiles.add(n.path); else selectedFiles.delete(n.path);
            updateParentFolderCheckbox(l);
        });
        l.appendChild(d);
        p.appendChild(l);
    } else {
        var u = document.createElement('ul');
        l.appendChild(d); l.appendChild(u);
        if (n.children) n.children.forEach(function(h) { buildTreeDOM(h, u); });
        var f = function(e) { if (e && e.target === c) return; u.classList.toggle('collapsed'); t.classList.toggle('collapsed'); };
        t.addEventListener('click', function(e) { e.stopPropagation(); f(e); });
        d.addEventListener('click', f);
        c.addEventListener('change', function() {
            var isChecked = this.checked;
            this.indeterminate = false;
            var children = l.querySelectorAll('ul input[type="checkbox"]');
            children.forEach(function(child) {
                child.checked = isChecked;
                child.indeterminate = false;
                var closestNode = child.closest('[data-path]');
                var path = closestNode ? closestNode.getAttribute('data-path') : null;
                if (path) {
                    if (isChecked) selectedFiles.add(path); else selectedFiles.delete(path);
                }
            });
            updateParentFolderCheckbox(l);
        });
        p.appendChild(l);
        updateParentFolderCheckbox(l);
    }
}

function clearFileTree() {
    var c = document.getElementById('file-tree');
    if (c) { c.innerHTML = ''; }
    selectedFiles.clear();
    var ps = document.getElementById('path-selector');
    if (ps) ps.style.display = 'none';
}

function updatePathList(paths, currentPath) {
    var sel = document.getElementById('path-select'), ps = document.getElementById('path-selector');
    if (!sel || !ps) return; sel.innerHTML = '';
    paths.forEach(function(p) {
        var opt = document.createElement('option'); opt.value = p; opt.textContent = p.split('\\').pop().split('/').pop(); opt.title = p;
        if (p === currentPath) opt.selected = true; sel.appendChild(opt);
    });
    ps.style.display = paths.length > 0 ? 'flex' : 'none';
}

function selectAllFiles() {
    document.querySelectorAll('#file-tree input[type="checkbox"]').forEach(function(c) { c.checked = true; c.indeterminate = false; });
    document.querySelectorAll('#file-tree li[data-path]').forEach(function(li) { selectedFiles.add(li.getAttribute('data-path')); });
}
function deselectAllFiles() {
    document.querySelectorAll('#file-tree input[type="checkbox"]').forEach(function(c) { c.checked = false; c.indeterminate = false; });
    document.querySelectorAll('#file-tree li[data-path]').forEach(function(li) { selectedFiles.delete(li.getAttribute('data-path')); });
}

function loadFolder() {
    var i = document.getElementById('folder-path');
    if (!i || !i.value.trim()) {
        alert('请输入文件夹路径');
        return;
    }
    if (!bridge) {
        alert('桥接未就绪');
        return;
    }
    bridge.load_folder(i.value.trim());
}

function openRightPanel() {
    var summaryPanel = document.getElementById('sidebar-summary');
    if (summaryPanel && summaryPanel.classList.contains('open')) {
        return;
    }
    var p = document.getElementById('sidebar-right'), r = document.getElementById('resizer-right');
    if (!p || !r) return;
    p.classList.add('open');
    r.style.display = 'block';
    if (p.offsetWidth === 0) p.style.width = '360px';
}
function closeRightPanel() {
    var p = document.getElementById('sidebar-right'), r = document.getElementById('resizer-right');
    if (p) p.classList.remove('open');
    if (r) r.style.display = 'none';
    if (p) p.style.width = '0';
}

// ====================================================================
// 9. 发送消息 & UI 交互
// ====================================================================
function send() {
    var userInput = document.getElementById('user-input');
    if (!userInput) return;
    var text = userInput.value.trim();
    if (!text) {
        handleEmptySendClick();
        return;
    }
    if (sendDisabled) {
        addError('正在生成中，请稍候...');
        return;
    }
    if (!isBridgeReady()) {
        addError('桥接未就绪，请稍后重试。');
        return;
    }
    try {
        if (bridge && bridge.save_file_selection) {
            bridge.save_file_selection(JSON.stringify(Array.from(selectedFiles)));
        }
    } catch (e) {
        console.warn('保存文件选择失败', e);
    }

    sendDisabled = true;
    document.getElementById('send-btn').disabled = true;
    showStopButton();  // 显示停止按钮
    pendingInputText = text;
    var filesJson = JSON.stringify(Array.from(selectedFiles));
    lastUserMessageElem = addUserMessage(text, filesJson);
    userInput.value = '';
    resetClickCount();

    var cfg = getConvConfig();
    hideConfigPanel();
    try {
        bridge.send_message_with_config(text, filesJson, JSON.stringify(cfg));
    } catch (e) {
        try { bridge.send_message(text, filesJson); } catch (e2) {
            console.error('发送消息异常:', e2);
            addError('发送失败: ' + e2.message);
            enableSendButton();
        }
    }
}

function handleEmptySendClick() {
    if (wallpaperDialogOpen) return;
    if (clickTimer) clearTimeout(clickTimer);
    clickCount++;
    clickTimer = setTimeout(function(){ resetClickCount(); }, 3000);
    if (clickCount >= 5) {
        resetClickCount();
        wallpaperDialogOpen = true;
        if (bridge) bridge.open_wallpaper_settings();
    }
}
function resetClickCount() { clickCount = 0; if (clickTimer) { clearTimeout(clickTimer); clickTimer = null; } }

function fillFileContents(contents) {
    try {
        for (var fpath in contents) {
            document.querySelectorAll('pre[data-path]').forEach(function(pre) {
                if (pre.getAttribute('data-path') === fpath) {
                    var code = pre.querySelector('code');
                    if (code) code.textContent = contents[fpath];
                }
            });
        }
    } catch(e) {
        console.warn('fillFileContents error', e);
    }
}
function enableSendButton() {
    sendDisabled = false;
    var s = document.getElementById('send-btn');
    if (s) s.disabled = false;
    lastUserMessageElem = null;
    pendingInputText = '';
    hideStopButton();  // 隐藏停止按钮
}

// 停止按钮显示/隐藏
function showStopButton() {
    var stopBtn = document.getElementById('stop-btn');
    var sendBtn = document.getElementById('send-btn');
    if (stopBtn) stopBtn.style.display = 'inline-flex';
    if (sendBtn) sendBtn.style.display = 'none';
}
function hideStopButton() {
    var stopBtn = document.getElementById('stop-btn');
    var sendBtn = document.getElementById('send-btn');
    if (stopBtn) stopBtn.style.display = 'none';
    if (sendBtn) sendBtn.style.display = '';
}
function stopGeneration() {
    if (bridge && bridge.stop_generation) {
        bridge.stop_generation();
    }
    hideStopButton();  // 点击后立即隐藏停止按钮
}
function onWallpaperSettingsClosed() { wallpaperDialogOpen = false; }

function toggleLeftSidebar() {
    var sb = document.getElementById('sidebar-left');
    var rl = document.getElementById('resizer-left');
    var btn = document.getElementById('toggle-left-btn');
    if (!sb) return;
    if (sb.classList.contains('collapsed')) {
        sb.classList.remove('collapsed');
        sb.style.width = '240px';
        if (rl) rl.style.display = 'block';
        if (btn) btn.textContent = '☰';
    } else {
        sb.classList.add('collapsed');
        sb.style.width = '';
        if (rl) rl.style.display = 'none';
        if (btn) btn.textContent = '';
    }
}

function openSummaryPanel() {
    var panel = document.getElementById('sidebar-summary');
    if (!panel) return;
    panel.classList.add('open');
    if (bridge && bridge.get_summary_content) {
        var content = bridge.get_summary_content();
        var el = document.getElementById('summary-content');
        if (el) el.textContent = content || '暂无概括内容';
    }
}

function closeSummaryPanel() {
    var panel = document.getElementById('sidebar-summary');
    if (panel) panel.classList.remove('open');
}
function setWallpaper(p, o) {
    var bg = document.getElementById('chat-background');
    if (bg) {
        if (!p || p === '' || p === "''" || p === 'url()') {
            bg.style.backgroundImage = 'none';
            bg.style.opacity = '0';
        } else {
            // 先清除再设置，强制重绘避免缓存
            bg.style.backgroundImage = 'none';
            void bg.offsetHeight;
            bg.style.backgroundImage = 'url(' + p + ')';
            bg.style.opacity = String(o);
        }
    }
    document.documentElement.style.setProperty('--wallpaper-path', (!p || p === '') ? 'none' : 'url(' + p + ')');
    document.documentElement.style.setProperty('--wallpaper-opacity', (!p || p === '') ? '0' : String(o));
}
function showModelTag(model) {
    var bar = document.getElementById('model-bar'); if (!bar) return;
    if (!model) { bar.innerHTML = ''; bar.style.display = 'none'; return; }
    bar.style.display = 'flex';
    bar.innerHTML = '<span class="model-bar-label">🤖 模型:</span> <span class="model-bar-name model-bar-clickable" id="model-bar-click" title="点击更改模型">' + model + ' ✎</span>';
    var modelBarClick = document.getElementById('model-bar-click');
    if (modelBarClick) modelBarClick.addEventListener('click', function() { if (bridge) bridge.open_model_dialog(); });
}
function showSummarizeStatus(text) {
    var bar = document.getElementById('model-bar'); if (!bar) return;
    var statusSpan = bar.querySelector('.summarize-status');
    if (!statusSpan) { statusSpan = document.createElement('span'); statusSpan.className = 'summarize-status'; bar.appendChild(statusSpan); }
    statusSpan.textContent = text || ''; statusSpan.style.display = text ? 'inline' : 'none';
}

// ====================================================================
// 10. 拖拽分隔条 (rAF 节流)
// ====================================================================
function initResizers() {
    var l = document.getElementById('sidebar-left'), r = document.getElementById('sidebar-right'), rl = document.getElementById('resizer-left'), rr = document.getElementById('resizer-right'), ic = document.getElementById('input-container'), ri = document.getElementById('resizer-input');
    if (!l || !r || !rl || !rr || !ic || !ri) return;
    var sx, sw, sy, sh, rafId = null;
    function endDrag() { document.body.style.userSelect = ''; if (rafId) { cancelAnimationFrame(rafId); rafId = null; } }
    
    rl.addEventListener('mousedown', function(e) { sx=e.clientX; sw=l.offsetWidth; document.body.style.userSelect='none'; document.addEventListener('mousemove',doLeftDrag); document.addEventListener('mouseup',endLeftDrag); e.preventDefault(); });
    function doLeftDrag(e) { if(rafId)return; rafId=requestAnimationFrame(function(){rafId=null; l.style.width=Math.min(500,Math.max(150,sw+e.clientX-sx))+'px';}); }
    function endLeftDrag() { endDrag(); document.removeEventListener('mousemove',doLeftDrag); document.removeEventListener('mouseup',endLeftDrag); }

    rr.addEventListener('mousedown', function(e) { sx=e.clientX; sw=r.offsetWidth; document.body.style.userSelect='none'; document.addEventListener('mousemove',doRightDrag); document.addEventListener('mouseup',endRightDrag); e.preventDefault(); });
    function doRightDrag(e) { if(rafId)return; rafId=requestAnimationFrame(function(){rafId=null; r.style.width=Math.min(600,Math.max(200,sw+sx-e.clientX))+'px';}); }
    function endRightDrag() { endDrag(); document.removeEventListener('mousemove',doRightDrag); document.removeEventListener('mouseup',endRightDrag); }

    ri.addEventListener('mousedown', function(e) { sy=e.clientY; sh=ic.offsetHeight; document.body.style.userSelect='none'; document.body.style.cursor='row-resize'; document.addEventListener('mousemove',doInputDrag); document.addEventListener('mouseup',endInputDrag); e.preventDefault(); });
    function doInputDrag(e) { if(rafId)return; rafId=requestAnimationFrame(function(){rafId=null; ic.style.height=Math.min(window.innerHeight*0.6,Math.max(100,sh+sy-e.clientY))+'px';}); }
    function endInputDrag() { document.body.style.cursor=''; endDrag(); document.removeEventListener('mousemove',doInputDrag); document.removeEventListener('mouseup',endInputDrag); }
}

// ====================================================================
// 11. Markdown 渲染
// ====================================================================
function renderMarkdown(text) { return marked.parse(text); }
function renderMarkdownFinal(text) { return marked.parse(text); }

// ====================================================================
// 11.5 对话配置面板 & 思维链模式
// ====================================================================
function populatePlatforms() {
    var sel = document.getElementById('cfg-platform');
    if (!sel) return;
    sel.innerHTML = '';
    PLATFORMS.forEach(function(p) {
        var opt = document.createElement('option');
        opt.value = p; opt.textContent = p;
        sel.appendChild(opt);
    });
}
function showConfigPanel() {
    var overlay = document.getElementById('conv-config-overlay');
    if (overlay) overlay.style.display = 'flex';
    populatePlatforms();
    // 重置表单
    var cb = document.getElementById('cfg-independent-model');
    if (cb) cb.checked = false;
    var cb2 = document.getElementById('cfg-chain-mode');
    if (cb2) cb2.checked = false;
    var detail = document.getElementById('config-model-detail');
    if (detail) detail.style.display = 'none';
    var sp = document.getElementById('cfg-system-prompt');
    if (sp) sp.value = '';
    var mi = document.getElementById('cfg-model');
    if (mi) mi.value = '';
}
function hideConfigPanel() {
    var overlay = document.getElementById('conv-config-overlay');
    if (overlay) overlay.style.display = 'none';
}
function toggleIndependentModel() {
    var cb = document.getElementById('cfg-independent-model');
    var detail = document.getElementById('config-model-detail');
    if (detail) detail.style.display = (cb && cb.checked) ? 'block' : 'none';
}
function toggleChainModeToggle() {
    var cb = document.getElementById('cfg-chain-mode');
    chainModeEnabled = !!(cb && cb.checked);
}
function getConvConfig() {
    var independentModel = false;
    var cb = document.getElementById('cfg-independent-model');
    if (cb) independentModel = cb.checked;
    var platform = '', model = '', memRounds = 50, maxTokens = 65536, temperature = 0.7;
    if (independentModel) {
        var ps = document.getElementById('cfg-platform');
        if (ps) platform = ps.value;
        var mi = document.getElementById('cfg-model');
        if (mi) model = mi.value.trim();
        var mr = document.getElementById('cfg-memory-rounds');
        if (mr) memRounds = parseInt(mr.value) || 50;
        var mt = document.getElementById('cfg-max-tokens');
        if (mt) maxTokens = parseInt(mt.value) || 65536;
        var temp = document.getElementById('cfg-temperature');
        if (temp) temperature = parseFloat(temp.value) || 0.7;
    }
    var systemPrompt = '';
    var sp = document.getElementById('cfg-system-prompt');
    if (sp) systemPrompt = sp.value.trim();
    var modeSelect = document.getElementById('agent-mode-select');
    var agentMode = 'code';
    if (modeSelect) agentMode = modeSelect.value;
    return {
        independentModel: independentModel,
        platform: platform, model: model,
        memRounds: memRounds, maxTokens: maxTokens,
        temperature: temperature,
        chainMode: chainModeEnabled,
        systemPrompt: systemPrompt,
        agentMode: chainModeEnabled ? agentMode : ''
    };
}
function updateChainProgress(status, tasklistJson) {
    var prog = document.getElementById('chain-progress');
    var statusEl = document.getElementById('chain-status');
    var listEl = document.getElementById('chain-tasklist');
    if (!prog || !statusEl || !listEl) return;
    if (!status) { prog.style.display = 'none'; return; }
    prog.style.display = 'block';
    statusEl.textContent = status;
    listEl.innerHTML = '';
    try {
        var tasks = JSON.parse(tasklistJson || '[]');
        tasks.forEach(function(t) {
            var item = document.createElement('div');
            var cls = 'chain-task-item ';
            var icon = '○';
            if (t.status === 'done') { cls += 'task-done'; icon = '✓'; }
            else if (t.status === 'active') { cls += 'task-active'; icon = '▶'; }
            else { cls += 'task-pending'; }
            item.className = cls;
            // 支持缩进（子任务）
            var indent = t.indent || 0;
            var indentStyle = indent > 0 ? 'padding-left:' + (indent * 20 + 8) + 'px;' : '';
            item.style.cssText = indentStyle;
            item.innerHTML = '<span class="task-icon">' + icon + '</span><span>' + t.text + '</span>';
            listEl.appendChild(item);
        });
    } catch(e) {}
}
function setChainMode(active) {
    chainModeEnabled = !!active;
    var btn = document.getElementById('chain-btn');
    if (btn) {
        if (active) btn.classList.add('active');
        else btn.classList.remove('active');
    }
    var cb = document.getElementById('cfg-chain-mode');
    if (cb) cb.checked = !!active;
}
function setConvConfig(indepEnabled, platform, model, memRounds, maxTokens, temperature, chainMode, systemPrompt) {
    var cb = document.getElementById('cfg-independent-model');
    if (cb) cb.checked = !!indepEnabled;
    var ps = document.getElementById('cfg-platform');
    if (ps && platform) ps.value = platform;
    var mi = document.getElementById('cfg-model');
    if (mi) mi.value = model || '';
    var mr = document.getElementById('cfg-memory-rounds');
    if (mr) mr.value = memRounds || 50;
    var mt = document.getElementById('cfg-max-tokens');
    if (mt) mt.value = maxTokens || 65536;
    var temp = document.getElementById('cfg-temperature');
    if (temp) temp.value = temperature || 0.7;
    var spp = document.getElementById('cfg-system-prompt');
    if (spp) spp.value = systemPrompt || '';
    setChainMode(!!chainMode);
    toggleIndependentModel();
}

// ====================================================================
// 12. 初始化
// ====================================================================
function initialize() {
    initResizers();
    var sendBtn = document.getElementById('send-btn');
    if (sendBtn) sendBtn.addEventListener('click', send);
    var stopBtn = document.getElementById('stop-btn');
    if (stopBtn) stopBtn.addEventListener('click', stopGeneration);
    var loadFolderBtn = document.getElementById('load-folder-btn');
    if (loadFolderBtn) loadFolderBtn.addEventListener('click', loadFolder);
    var settingsBtn = document.getElementById('settings-btn');
    if (settingsBtn) settingsBtn.addEventListener('click', function() { if (bridge) bridge.open_settings(); });
    var memoryBtn = document.getElementById('memory-btn');
    if (memoryBtn) memoryBtn.addEventListener('click', function() { if (bridge) bridge.open_memory_settings(); });
    var chainBtn = document.getElementById('chain-btn');
    if (chainBtn) chainBtn.addEventListener('click', function() {
        setChainMode(!chainModeEnabled);
    });
    var newConvBtn = document.getElementById('new-conv-btn');
    if (newConvBtn) newConvBtn.addEventListener('click', newConversation);
    var selectAllBtn = document.getElementById('select-all-btn');
    if (selectAllBtn) selectAllBtn.addEventListener('click', selectAllFiles);
    var deselectAllBtn = document.getElementById('deselect-all-btn');
    if (deselectAllBtn) deselectAllBtn.addEventListener('click', deselectAllFiles);
    var collapseSidebarBtn = document.getElementById('collapse-sidebar-btn');
    if (collapseSidebarBtn) collapseSidebarBtn.addEventListener('click', closeRightPanel);
    var toggleLeftBtn = document.getElementById('toggle-left-btn');
    if (toggleLeftBtn) toggleLeftBtn.addEventListener('click', toggleLeftSidebar);
    var toggleSummaryBtn = document.getElementById('toggle-summary-btn');
    if (toggleSummaryBtn) toggleSummaryBtn.addEventListener('click', openSummaryPanel);
    var summaryCloseBtn = document.getElementById('summary-close-btn');
    if (summaryCloseBtn) summaryCloseBtn.addEventListener('click', closeSummaryPanel);
    var configCloseBtn = document.getElementById('config-dialog-close');
    if (configCloseBtn) configCloseBtn.addEventListener('click', hideConfigPanel);
    var configCancelBtn = document.getElementById('config-cancel-btn');
    if (configCancelBtn) configCancelBtn.addEventListener('click', hideConfigPanel);
    var configConfirmBtn = document.getElementById('config-confirm-btn');
    if (configConfirmBtn) configConfirmBtn.addEventListener('click', confirmNewConvConfig);
    // 点击遮罩关闭
    var configOverlay = document.getElementById('conv-config-overlay');
    if (configOverlay) configOverlay.addEventListener('click', function(e) {
        if (e.target === configOverlay) hideConfigPanel();
    });
    // Escape 关闭模态框
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') {
            var overlay = document.getElementById('conv-config-overlay');
            if (overlay && overlay.style.display === 'flex') hideConfigPanel();
        }
    });
    var cfgIndepModel = document.getElementById('cfg-independent-model');
    if (cfgIndepModel) cfgIndepModel.addEventListener('change', toggleIndependentModel);
    var cfgChainMode = document.getElementById('cfg-chain-mode');
    if (cfgChainMode) cfgChainMode.addEventListener('change', toggleChainModeToggle);
    var pathSelect = document.getElementById('path-select');
    if (pathSelect) pathSelect.addEventListener('change', function() { if (bridge && this.value) bridge.switch_path(this.value); });
    var refreshPathBtn = document.getElementById('refresh-path-btn');
    if (refreshPathBtn) refreshPathBtn.addEventListener('click', function() { if (bridge) bridge.refresh_current_path(); });
    var removePathBtn = document.getElementById('remove-path-btn');
    if (removePathBtn) removePathBtn.addEventListener('click', function() { var sel=document.getElementById('path-select'); if(bridge&&sel&&sel.value) bridge.remove_path(sel.value); });
    var folderPathInput = document.getElementById('folder-path');
    if (folderPathInput) folderPathInput.addEventListener('keydown', function(e) { if (e.key === 'Enter') { e.preventDefault(); loadFolder(); } });
    var userInput = document.getElementById('user-input');
    if (userInput) userInput.addEventListener('keydown', function(e) { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); send(); } });
    // 滚动条修复：区分程序触发的滚动和用户手动滚动
    // programScrolling 为 true 时忽略 scroll 事件，避免自动滚底被误判为用户滚动
    var chatAreaEl = document.getElementById('chat-area');
    if (chatAreaEl) {
        chatAreaEl.addEventListener('scroll', function() {
            if (programScrolling) return;  // 程序触发的滚动，忽略
            // 检查用户是否滚动到底部附近（30px 阈值）
            var isNearBottom = (chatAreaEl.scrollHeight - chatAreaEl.scrollTop - chatAreaEl.clientHeight) < 30;
            if (isNearBottom) {
                // 用户滚动到底部，重置标志，允许自动滚底
                userScrolling = false;
                if (scrollCheckTimer) clearTimeout(scrollCheckTimer);
            } else {
                // 用户不在底部，标记为正在滚动
                userScrolling = true;
                if (scrollCheckTimer) clearTimeout(scrollCheckTimer);
            }
        });
    }
    // 模式选择器：恢复上次选择 + 变更时记忆
    var modeSelect = document.getElementById('agent-mode-select');
    if (modeSelect) {
        try {
            var savedMode = localStorage.getItem('agentMode');
            if (savedMode) modeSelect.value = savedMode;
        } catch(e) {}
        modeSelect.addEventListener('change', function() {
            try { localStorage.setItem('agentMode', this.value); } catch(e) {}
        });
    }
    // 强制重置视口，防止大内容导致整体偏移
    resetViewport();
    setTimeout(resetViewport, 100);
    window.addEventListener('resize', resetViewport);
    
    attemptConnection();
}
function resetViewport() {
    if (document.documentElement) {
        document.documentElement.scrollTop = 0;
        document.documentElement.scrollLeft = 0;
    }
    if (document.body) {
        document.body.scrollTop = 0;
        document.body.scrollLeft = 0;
    }
}
window.addEventListener('load', initialize);
