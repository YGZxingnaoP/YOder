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
marked.use({ extensions: [blockMathExtension, inlineMathExtension] });
marked.setOptions({ breaks: true, gfm: true });

// ====================================================================
// 2. 全局变量 & 核心连接
// ====================================================================
var bridge = null, selectedFiles = new Set(), clickCount = 0, clickTimer = null, wallpaperDialogOpen = false;
var sendDisabled = false, lastUserMessageElem = null, pendingInputText = '';
var currentAssistantMsgDiv = null, currentRawText = "";
var renderTimer = null;
var RENDER_INTERVAL = 80;
var summaryContentCache = '';
var chainModeEnabled = false;
var PLATFORMS = ['阿里', 'DeepSeek', '智谱', 'Kimi'];
// 多块追踪：支持思考/内容交错显示在同一个气泡
var msgBlocks = [];          // [{type, text, rawText, element, contentElement}, ...]
var currentBlockIndex = -1;
var currentBlockType = null;  // "thinking" | "content" | null
var blockIdCounter = 0;

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
function updateConversationList(convs) {
    if (!bridge) return;
    var convList = document.getElementById('conv-list');
    if (!convList) return;
    convList.innerHTML = '';
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
        li.addEventListener('mouseenter', function() { btnGroup.style.opacity = '1'; });
        li.addEventListener('mouseleave', function() { btnGroup.style.opacity = '0'; });
        li.addEventListener('click', function(e) { switchConv(name, e.currentTarget); });
        convList.appendChild(li);
    });
}

function switchConv(name, liElement) {
    if (sendDisabled) { alert('正在生成回答，请稍后再试'); return; }
    if (!isBridgeReady()) return;
    selectedFiles.clear();
    hideConfigPanel();
    setChainMode(false);
    if (bridge && bridge.save_file_selection) {
        bridge.save_file_selection(JSON.stringify(Array.from(selectedFiles)));
    }
    bridge.switch_conversation(name);
    document.querySelectorAll('#conv-list li').forEach(function(li) { li.classList.remove('active'); });
    if (liElement) liElement.classList.add('active');
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
    bridge.switch_conversation(''); clearMessages(); clearFileTree();
    setChainMode(false);
    showConfigPanel();
    document.querySelectorAll('#conv-list li').forEach(function(li) { li.classList.remove('active'); });
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
    chatArea.scrollTop = chatArea.scrollHeight;
    return div;
}
function deleteTurn(btn) {
    if (sendDisabled || !isBridgeReady()) return;
    var userMsg = btn.closest('.message.user');
    if (!userMsg) return;
    var allMsgs = Array.from(document.getElementById('chat-area').querySelectorAll('.message'));
    var userIndex = allMsgs.indexOf(userMsg);
    if (userIndex >= 0) bridge.delete_turn(String(userIndex));
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
    assistantMsg.remove();
    sendDisabled = true;
    document.getElementById('send-btn').disabled = true;
    bridge.regenerate_message(userMsg.dataset.text, userMsg.dataset.files, JSON.stringify({chainMode: userMsg.dataset.chainMode === '1'}));
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
                    block.contentElement.textContent = block.rawText;
                    if (chatArea.scrollHeight - chatArea.scrollTop - chatArea.clientHeight < 100) chatArea.scrollTop = chatArea.scrollHeight;
                }
            }, RENDER_INTERVAL);
        }
    } else {
        if (block.contentElement) {
            block.contentElement.textContent += text;
            if (chatArea.scrollHeight - chatArea.scrollTop - chatArea.clientHeight < 100) chatArea.scrollTop = chatArea.scrollHeight;
        }
    }
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
    var chatArea = document.getElementById('chat-area');
    if (chatArea && chatArea.scrollHeight - chatArea.scrollTop - chatArea.clientHeight < 100) chatArea.scrollTop = chatArea.scrollHeight;
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
                block.contentElement.textContent = block.rawText;
                var chatArea = document.getElementById('chat-area');
                if (chatArea && chatArea.scrollHeight - chatArea.scrollTop - chatArea.clientHeight < 100) chatArea.scrollTop = chatArea.scrollHeight;
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

function finishMessage(model) {
    if (renderTimer) { clearTimeout(renderTimer); renderTimer = null; }

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
            contentDiv.appendChild(actionsDiv);
        }
    }

    currentAssistantMsgDiv = null;
    msgBlocks = [];
    currentBlockIndex = -1;
    currentBlockType = null;
    currentRawText = "";

    var chatArea = document.getElementById('chat-area');
    if (chatArea) chatArea.scrollTop = chatArea.scrollHeight;
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
    chatArea.scrollTop = chatArea.scrollHeight;
}

// ====================================================================
// 7. 历史记录加载 - 支持多块格式
// ====================================================================
function loadHistory(messages) {
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
            contentDiv.appendChild(actionsDiv); chatArea.appendChild(div);
        }
    });
    chatArea.scrollTop = chatArea.scrollHeight;
    sendDisabled = false; document.getElementById('send-btn').disabled = false;
}

function clearMessages() {
    if (renderTimer) { clearTimeout(renderTimer); renderTimer = null; }
    var chatArea = document.getElementById('chat-area');
    if (chatArea) chatArea.innerHTML = '';
    currentAssistantMsgDiv = null; currentRawText = "";
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
    document.documentElement.style.setProperty('--wallpaper-path', 'url(' + p + ')');
    document.documentElement.style.setProperty('--wallpaper-opacity', o);
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
function renderMarkdownFinal(text) { var html=marked.parse(text); var tmp=document.createElement('div'); tmp.innerHTML=html; tmp.querySelectorAll('pre code').forEach(function(b){hljs.highlightElement(b)}); return tmp.innerHTML; }

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
    var panel = document.getElementById('conv-config-panel');
    if (panel) panel.style.display = 'block';
    populatePlatforms();
}
function hideConfigPanel() {
    var panel = document.getElementById('conv-config-panel');
    if (panel) panel.style.display = 'none';
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
    var platform = '', model = '', memRounds = 50, maxTokens = 65536;
    if (independentModel) {
        var ps = document.getElementById('cfg-platform');
        if (ps) platform = ps.value;
        var mi = document.getElementById('cfg-model');
        if (mi) model = mi.value.trim();
        var mr = document.getElementById('cfg-memory-rounds');
        if (mr) memRounds = parseInt(mr.value) || 50;
        var mt = document.getElementById('cfg-max-tokens');
        if (mt) maxTokens = parseInt(mt.value) || 65536;
    }
    return {
        independentModel: independentModel,
        platform: platform, model: model,
        memRounds: memRounds, maxTokens: maxTokens,
        chainMode: chainModeEnabled
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

// ====================================================================
// 12. 初始化
// ====================================================================
function initialize() {
    initResizers();
    var sendBtn = document.getElementById('send-btn');
    if (sendBtn) sendBtn.addEventListener('click', send);
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
    var configCollapseBtn = document.getElementById('config-collapse-btn');
    if (configCollapseBtn) configCollapseBtn.addEventListener('click', hideConfigPanel);
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
    attemptConnection();
}
window.addEventListener('load', initialize);
