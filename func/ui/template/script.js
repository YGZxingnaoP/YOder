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
var currentAssistantMsgDiv = null, currentThinkingBlock = null, currentAssistantBlock = null, currentRawText = "";
var renderTimer = null;
var RENDER_INTERVAL = 80;

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
        renameBtn.className = 'action-btn'; renameBtn.textContent = '\u270E'; renameBtn.title = '\u91CD\u547D\u540D';
        renameBtn.addEventListener('click', function(e) { e.stopPropagation(); renameConv(name); });
        var deleteBtn = document.createElement('button');
        deleteBtn.className = 'action-btn'; deleteBtn.textContent = '\uD83D\uDDD1\uFE0F'; deleteBtn.title = '\u5220\u9664';
        deleteBtn.addEventListener('click', function(e) {
            e.stopPropagation();
            if (confirm('\u786E\u5B9A\u8981\u5220\u9664\u5BF9\u8BDD "' + name + '" \u5417\uFF1F\u6B64\u64CD\u4F5C\u4E0D\u53EF\u6062\u590D\u3002')) { if (bridge) bridge.delete_folder(name); }
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
    if (sendDisabled) { alert('\u6B63\u5728\u751F\u6210\u56DE\u7B54\uFF0C\u8BF7\u7A0D\u540E\u518D\u8BD5'); return; }
    if (!isBridgeReady()) return;
    bridge.switch_conversation(name);
    document.querySelectorAll('#conv-list li').forEach(function(li) { li.classList.remove('active'); });
    if (liElement) liElement.classList.add('active');
}
function renameConv(oldName) {
    if (!isBridgeReady()) return;
    var newName = prompt('\u65B0\u540D\u79F0:', oldName);
    if (newName && newName !== oldName) bridge.rename_folder(oldName, newName);
}
function newConversation() {
    if (sendDisabled) { alert('\u6B63\u5728\u751F\u6210\u56DE\u7B54\uFF0C\u8BF7\u7A0D\u540E\u518D\u8BD5'); return; }
    if (!isBridgeReady()) return;
    bridge.switch_conversation(''); clearMessages();
    document.querySelectorAll('#conv-list li').forEach(function(li) { li.classList.remove('active'); });
}

// ====================================================================
// 4. 消息渲染（流式用纯文本，避免 innerHTML 重排）
// ====================================================================
function addUserMessage(text, filesJson) {
    var chatArea = document.getElementById('chat-area');
    if (!chatArea) return;
    var div = document.createElement('div');
    div.className = 'message user';
    div.dataset.text = text;
    div.dataset.files = filesJson || "[]";
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
                summary.innerHTML = '\uD83D\uDCC4 <strong>' + fileName + '</strong> <span class="file-path">' + fpath + '</span>';
                var pre = document.createElement('pre');
                var code = document.createElement('code');
                pre.setAttribute('data-path', fpath);
                code.textContent = "\u6B63\u5728\u8BFB\u53D6\u6587\u4EF6...";
                pre.appendChild(code);
                details.appendChild(summary);
                details.appendChild(pre);
                contentDiv.appendChild(details);
            });
        } catch(e) {}
    }

    div.innerHTML = '<div class="avatar">\uD83D\uDC64</div>';
    var deleteBtn = document.createElement('button');
    deleteBtn.className = 'msg-delete';
    deleteBtn.textContent = '\u2715';
    deleteBtn.title = '\u5220\u9664\u8FD9\u4E00\u8F6E';
    deleteBtn.style.cssText = 'background:none;border:none;cursor:pointer;font-size:14px;color:rgba(255,255,255,0.5);padding:2px 8px;margin-right:4px;border-radius:4px;order:-1;align-self:center;flex-shrink:0;';
    deleteBtn.onmouseenter = function() { this.style.color = '#ff4444'; this.style.background = 'rgba(255,68,68,0.15)'; };
    deleteBtn.onmouseleave = function() { this.style.color = 'rgba(255,255,255,0.5)'; this.style.background = 'none'; };
    deleteBtn.onclick = function(e) { e.stopPropagation(); deleteTurn(this); };
    div.appendChild(contentDiv);
    div.appendChild(deleteBtn);
    chatArea.appendChild(div);
    chatArea.scrollTop = chatArea.scrollHeight;
    return div;
}

function deleteTurn(btn) {
    if (sendDisabled || !isBridgeReady()) return;
    var userMsg = btn.closest('.message.user');
    if (!userMsg) return;
    var chatArea = document.getElementById('chat-area');
    if (!chatArea) return;
    // 计算该 user 消息在 current_messages 数组中的索引
    var allMsgs = Array.from(chatArea.querySelectorAll('.message'));
    var userIndex = -1;
    for (var i = 0; i < allMsgs.length; i++) {
        if (allMsgs[i] === userMsg) { userIndex = i; break; }
    }
    if (userIndex < 0) return;
    bridge.delete_turn(String(userIndex));
}

function regenerate(btn) {
    if (sendDisabled || !isBridgeReady()) return;
    var assistantMsg = btn.closest('.message.assistant');
    if (!assistantMsg) return;
    if (renderTimer) { clearTimeout(renderTimer); renderTimer = null; }
    currentAssistantMsgDiv = null; currentThinkingBlock = null; currentAssistantBlock = null; currentRawText = "";
    // 向前查找对应的用户消息
    var userMsg = assistantMsg.previousElementSibling;
    while (userMsg && !userMsg.classList.contains('message') || (userMsg && !userMsg.classList.contains('user'))) {
        userMsg = userMsg ? userMsg.previousElementSibling : null;
    }
    if (!userMsg) return;
    var text = userMsg.dataset.text, filesJson = userMsg.dataset.files;
    // 只移除 AI 回复，保留用户消息
    assistantMsg.remove();
    sendDisabled = true;
    var sendBtn = document.getElementById('send-btn');
    if (sendBtn) sendBtn.disabled = true;
    bridge.regenerate_message(text, filesJson);
}

function addThinking(text) {
    var chatArea = document.getElementById('chat-area');
    if (!chatArea) return;
    if (!currentAssistantMsgDiv) {
        var div = document.createElement('div');
        div.className = 'message assistant';
        div.innerHTML = '<div class="avatar">\uD83E\uDD16</div><div class="content is-streaming"><div class="assistant-output"><div class="thinking-block"><details class="thinking-details open"><summary>\u601D\u8003\u8FC7\u7A0B</summary><div class="thinking-content"></div></details></div><div class="assistant-text" style="display:none;"></div></div></div>';
        currentAssistantMsgDiv = div;
        currentThinkingBlock = div.querySelector('.thinking-content');
        currentAssistantBlock = div.querySelector('.assistant-text');
        chatArea.appendChild(div);
    }
    if (currentThinkingBlock) currentThinkingBlock.textContent += text;
    var nearBottom = chatArea.scrollHeight - chatArea.scrollTop - chatArea.clientHeight < 100;
    if (nearBottom) chatArea.scrollTop = chatArea.scrollHeight;
}

function addContent(chunk) {
    var chatArea = document.getElementById('chat-area');
    if (!chatArea) return;
    if (!currentAssistantMsgDiv) {
        var div = document.createElement('div');
        div.className = 'message assistant';
        div.innerHTML = '<div class="avatar">\uD83E\uDD16<span class="model-tag"></span></div><div class="content is-streaming"><div class="assistant-output"><div class="assistant-text"></div></div></div>';
        currentAssistantMsgDiv = div;
        currentAssistantBlock = div.querySelector('.assistant-text');
        chatArea.appendChild(div);
        currentRawText = "";
    } else if (currentAssistantBlock && currentAssistantBlock.style.display === 'none') {
        currentAssistantBlock.style.display = 'block';
    }
    currentRawText += chunk;
    // 流式阶段：用 textContent 显示纯文本，零 DOM 解析，零重排
    if (!renderTimer) {
        renderTimer = setTimeout(function() {
            renderTimer = null;
            if (currentAssistantBlock) {
                currentAssistantBlock.textContent = currentRawText;
                var nearBottom = chatArea.scrollHeight - chatArea.scrollTop - chatArea.clientHeight < 100;
                if (nearBottom) chatArea.scrollTop = chatArea.scrollHeight;
            }
        }, RENDER_INTERVAL);
    }
}

// ====================================================================
// 5. 复制按钮（通过 bridge 调用 Qt 剪贴板）
// ====================================================================
function addCopyButtons(container) {
    container.querySelectorAll('pre').forEach(function(pre) {
        if (pre.querySelector('.code-copy-btn')) return;
        pre.style.position = 'relative';
        var btn = document.createElement('button');
        btn.className = 'code-copy-btn';
        btn.textContent = '\u590D\u5236';
        btn.addEventListener('click', function(e) {
            e.stopPropagation();
            var code = pre.querySelector('code');
            var text = code ? code.textContent : pre.textContent;
            if (bridge && bridge.copy_to_clipboard) {
                bridge.copy_to_clipboard(text);
                btn.textContent = '\u5DF2\u590D\u5236'; btn.classList.add('copied');
                setTimeout(function() { btn.textContent = '\u590D\u5236'; btn.classList.remove('copied'); }, 2000);
            }
        });
        pre.appendChild(btn);
    });
}

// ====================================================================
// 6. 消息完成 & 错误处理
// ====================================================================
function finishMessage(model) {
    if (renderTimer) { clearTimeout(renderTimer); renderTimer = null; }
    if (currentAssistantBlock) {
        // 最终渲染：完整 Markdown + 语法高亮
        currentAssistantBlock.innerHTML = renderMarkdownFinal(currentRawText);
        var contentDiv = currentAssistantMsgDiv && currentAssistantMsgDiv.querySelector('.content');
        if (contentDiv) contentDiv.classList.remove('is-streaming');
        currentAssistantBlock.classList.add('rendered');
        addCopyButtons(currentAssistantBlock);
        var tag = currentAssistantMsgDiv ? currentAssistantMsgDiv.querySelector('.model-tag') : null;
        if (tag) tag.textContent = model;
        var actionsDiv = document.createElement('div');
        actionsDiv.className = 'msg-actions';
        var regenBtn = document.createElement('button');
        regenBtn.className = 'regen-btn';
        regenBtn.textContent = '\uD83D\uDD04 \u91CD\u65B0\u751F\u6210';
        regenBtn.onclick = function(e) { e.stopPropagation(); regenerate(this); };
        actionsDiv.appendChild(regenBtn);
        currentAssistantMsgDiv.appendChild(actionsDiv);
    }
    currentAssistantMsgDiv = null; currentThinkingBlock = null; currentAssistantBlock = null; currentRawText = "";
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
    div.innerHTML = '<div class="avatar">\u26A0\uFE0F</div>';
    div.appendChild(contentDiv);
    chatArea.appendChild(div);
    chatArea.scrollTop = chatArea.scrollHeight;
}

// ====================================================================
// 7. 历史记录加载
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
            var contentDiv = document.createElement('div');
            contentDiv.className = 'content';
            if (Array.isArray(msg.content)) {
                msg.content.forEach(function(block) {
                    if (block.type === 'text') {
                        var p = document.createElement('p');
                        p.textContent = block.text;
                        p.style.marginBottom = '12px';
                        p.style.lineHeight = '1.75';
                        contentDiv.appendChild(p);
                    } else if (block.type === 'file_content') {
                        var details = document.createElement('details');
                        details.className = 'file-card';
                        var summary = document.createElement('summary');
                        summary.innerHTML = '\uD83D\uDCC4 <strong>' + block.file_name + '</strong> <span class="file-path">' + block.file_path + '</span>';
                        var pre = document.createElement('pre');
                        var code = document.createElement('code');
                        code.textContent = block.text;
                        pre.appendChild(code);
                        details.appendChild(summary);
                        details.appendChild(pre);
                        contentDiv.appendChild(details);
                    } else if (block.type === 'image_url') {
                        var img = document.createElement('img');
                        img.src = block.image_url.url;
                        img.style.cssText = 'max-width:200px;border-radius:8px;display:block;margin-bottom:8px;';
                        contentDiv.appendChild(img);
                    }
                });
            } else { contentDiv.textContent = msg.content; }
            var deleteBtn = document.createElement('button');
            deleteBtn.className = 'msg-delete';
            deleteBtn.textContent = '\u2715';
            deleteBtn.title = '\u5220\u9664\u8FD9\u4E00\u8F6E';
            deleteBtn.style.cssText = 'background:none;border:none;cursor:pointer;font-size:14px;color:rgba(255,255,255,0.5);padding:2px 8px;margin-right:4px;border-radius:4px;order:-1;align-self:center;flex-shrink:0;';
            deleteBtn.onmouseenter = function() { this.style.color = '#ff4444'; this.style.background = 'rgba(255,68,68,0.15)'; };
            deleteBtn.onmouseleave = function() { this.style.color = 'rgba(255,255,255,0.5)'; this.style.background = 'none'; };
            deleteBtn.onclick = function(e) { e.stopPropagation(); deleteTurn(this); };
            div.innerHTML = '<div class="avatar">\uD83D\uDC64</div>';
            div.appendChild(contentDiv);
            div.appendChild(deleteBtn);
            chatArea.appendChild(div);
        } else if (msg.role === 'assistant') {
            var div = document.createElement('div');
            div.className = 'message assistant';
            var contentDiv = document.createElement('div');
            contentDiv.className = 'content rendered';
            var actualDiv = document.createElement('div');
            actualDiv.className = 'assistant-output';
            if (msg.thinking) {
                var thinkDiv = document.createElement('div');
                thinkDiv.className = 'thinking-block';
                thinkDiv.innerHTML = '<details class="thinking-details"><summary>\u601D\u8003\u8FC7\u7A0B</summary><div class="thinking-content">' + msg.thinking + '</div></details>';
                actualDiv.appendChild(thinkDiv);
            }
            var contentHtml = renderMarkdownFinal(msg.content);
            var tempDiv = document.createElement('div');
            tempDiv.innerHTML = contentHtml;
            while (tempDiv.firstChild) actualDiv.appendChild(tempDiv.firstChild);
            addCopyButtons(actualDiv);
            contentDiv.appendChild(actualDiv);
            div.innerHTML = '<div class="avatar">\uD83E\uDD16</div>';
            div.appendChild(contentDiv);
            var actionsDiv = document.createElement('div');
            actionsDiv.className = 'msg-actions';
            var regenBtn = document.createElement('button');
            regenBtn.className = 'regen-btn';
            regenBtn.textContent = '\uD83D\uDD04 \u91CD\u65B0\u751F\u6210';
            regenBtn.onclick = function(e) { e.stopPropagation(); regenerate(this); };
            actionsDiv.appendChild(regenBtn);
            div.appendChild(actionsDiv);
            chatArea.appendChild(div);
        }
    });
    chatArea.scrollTop = chatArea.scrollHeight;
    // 确保加载历史后发送按钮可用
    sendDisabled = false;
    var sendBtn = document.getElementById('send-btn');
    if (sendBtn) sendBtn.disabled = false;
}

function clearMessages() {
    if (renderTimer) { clearTimeout(renderTimer); renderTimer = null; }
    var chatArea = document.getElementById('chat-area');
    if (chatArea) chatArea.innerHTML = '';
    currentAssistantMsgDiv = null; currentThinkingBlock = null; currentAssistantBlock = null; currentRawText = "";
}

// ====================================================================
// 8. 文件树 & 侧边栏
// ====================================================================
function displayFileTree(tree) { var c=document.getElementById('file-tree');if(!c)return;c.innerHTML='';selectedFiles.clear();var r=document.createElement('ul');buildTreeDOM(tree,r);c.appendChild(r);selectAllFiles();openRightPanel(); }
function buildTreeDOM(n,p){var l=document.createElement('li'),d=document.createElement('div');d.className='node-content';var t=document.createElement('span');t.className='toggle-icon';t.innerHTML=n.type==='directory'?'\u25BE':'';t.style.visibility=n.type==='directory'?'visible':'hidden';var c=document.createElement('input');c.type='checkbox';c.checked=true;var s=document.createElement('span');s.className='node-name';s.textContent=(n.type==='directory'?'\uD83D\uDCC1 ':'\uD83D\uDCC4 ')+n.name;d.appendChild(t);d.appendChild(c);d.appendChild(s);if(n.type==='file'){l.setAttribute('data-path',n.path);var k=document.createElement('span');k.className='token-info';k.textContent=(n.token_count||0)+' tk';d.appendChild(k);c.addEventListener('change',function(){if(this.checked)selectedFiles.add(n.path);else selectedFiles.delete(n.path);updateParentFolderCheckbox(l);});l.appendChild(d);p.appendChild(l);}else{var u=document.createElement('ul');l.appendChild(d);l.appendChild(u);if(n.children)n.children.forEach(function(h){buildTreeDOM(h,u);});var f=function(e){if(e&&e.target===c)return;u.classList.toggle('collapsed');t.classList.toggle('collapsed');};t.addEventListener('click',function(e){e.stopPropagation();f(e);});d.addEventListener('click',f);c.addEventListener('change',function(){var a=l.querySelectorAll('ul input[type="checkbox"]');a.forEach(function(b){b.checked=this.checked;var v=b.closest('[data-path]')?.getAttribute('data-path');if(v){if(this.checked)selectedFiles.add(v);else selectedFiles.delete(v);}});});p.appendChild(l);}}
function updateParentFolderCheckbox(f){var p=f.parentElement?.closest('li');while(p&&p.querySelector('ul')){var c=p.querySelector(':scope > .node-content > input[type="checkbox"]');if(!c)break;var h=p.querySelectorAll('ul li[data-path] input[type="checkbox"]');if(h.length>0)c.checked=Array.from(h).every(function(b){return b.checked;});p=p.parentElement?.closest('li');}}
function selectAllFiles(){document.querySelectorAll('#file-tree input[type="checkbox"]').forEach(function(c){c.checked=true;});rebuildSelectedFilesFromDOM();}
function deselectAllFiles(){document.querySelectorAll('#file-tree input[type="checkbox"]').forEach(function(c){c.checked=false;});rebuildSelectedFilesFromDOM();}
function rebuildSelectedFilesFromDOM(){selectedFiles.clear();document.querySelectorAll('#file-tree li[data-path] input[type="checkbox"]:checked').forEach(function(c){var p=c.closest('[data-path]').getAttribute('data-path');if(p)selectedFiles.add(p);});}
function loadFolder(){var i=document.getElementById('folder-path');if(!i)return;var p=i.value.trim();if(p&&bridge)bridge.load_folder(p);}
function openRightPanel(){var p=document.getElementById('sidebar-right'),r=document.getElementById('resizer-right');if(!p||!r)return;p.classList.add('open');r.style.display='block';if(p.offsetWidth===0)p.style.width='360px';}
function closeRightPanel(){var p=document.getElementById('sidebar-right'),r=document.getElementById('resizer-right');if(p)p.classList.remove('open');if(r)r.style.display='none';if(p)p.style.width='0';selectedFiles.clear();}

// ====================================================================
// 9. 发送消息
// ====================================================================
function send() {
    var userInput = document.getElementById('user-input');
    if (!userInput) return;
    var text = userInput.value.trim();
    if (!text) { handleEmptySendClick(); return; }
    if (sendDisabled) { alert('\u6B63\u5728\u7B49\u5F85\u4E0A\u4E00\u8F6E\u56DE\u590D\u7ED3\u675F\uFF0C\u8BF7\u7A0D\u540E\u518D\u8BD5'); return; }
    if (!isBridgeReady()) return;
    sendDisabled = true;
    var sendBtn = document.getElementById('send-btn');
    if (sendBtn) sendBtn.disabled = true;
    var filesArray = Array.from(selectedFiles);
    var filesJson = JSON.stringify(filesArray);
    bridge.send_message(text, filesJson);
    pendingInputText = text;
    lastUserMessageElem = addUserMessage(text, filesJson);
    userInput.value = '';
    resetClickCount();
}
function handleEmptySendClick(){if(wallpaperDialogOpen)return;if(clickTimer)clearTimeout(clickTimer);clickCount++;clickTimer=setTimeout(function(){resetClickCount();},3000);if(clickCount>=5){resetClickCount();wallpaperDialogOpen=true;if(bridge)bridge.open_wallpaper_settings();}}
function resetClickCount(){clickCount=0;if(clickTimer){clearTimeout(clickTimer);clickTimer=null;}}
function fillFileContents(contentsJson) {
    try {
        var contents = JSON.parse(contentsJson);
        for (var fpath in contents) {
            var pres = document.querySelectorAll('pre[data-path]');
            for (var i = 0; i < pres.length; i++) {
                if (pres[i].getAttribute('data-path') === fpath) {
                    var codeElem = pres[i].querySelector('code');
                    if (codeElem) codeElem.textContent = contents[fpath];
                }
            }
        }
    } catch(e) {}
}

function enableSendButton(){sendDisabled=false;var s=document.getElementById('send-btn');if(s)s.disabled=false;lastUserMessageElem=null;pendingInputText='';}
function onWallpaperSettingsClosed(){wallpaperDialogOpen=false;}
function setWallpaper(p,o){document.documentElement.style.setProperty('--wallpaper-path','url('+p+')');document.documentElement.style.setProperty('--wallpaper-opacity',o);}

// ====================================================================
// 10. 拖拽分隔条（rAF 节流）
// ====================================================================
function initResizers() {
    var l = document.getElementById('sidebar-left');
    var r = document.getElementById('sidebar-right');
    var rl = document.getElementById('resizer-left');
    var rr = document.getElementById('resizer-right');
    var ic = document.getElementById('input-container');
    var ri = document.getElementById('resizer-input');
    if (!l || !r || !rl || !rr || !ic || !ri) return;

    var sx, sw, sy, sh, rafId = null;

    function endDrag() {
        document.body.style.userSelect = '';
        if (rafId) { cancelAnimationFrame(rafId); rafId = null; }
    }

    // 左侧边栏
    rl.addEventListener('mousedown', function(e) {
        sx = e.clientX; sw = l.offsetWidth;
        document.body.style.userSelect = 'none';
        document.addEventListener('mousemove', doLeftDrag);
        document.addEventListener('mouseup', endLeftDrag);
        e.preventDefault();
    });
    function doLeftDrag(e) {
        if (rafId) return;
        rafId = requestAnimationFrame(function() {
            rafId = null;
            l.style.width = Math.min(500, Math.max(150, sw + e.clientX - sx)) + 'px';
        });
    }
    function endLeftDrag() {
        endDrag();
        document.removeEventListener('mousemove', doLeftDrag);
        document.removeEventListener('mouseup', endLeftDrag);
    }

    // 右侧边栏
    rr.addEventListener('mousedown', function(e) {
        sx = e.clientX; sw = r.offsetWidth;
        document.body.style.userSelect = 'none';
        document.addEventListener('mousemove', doRightDrag);
        document.addEventListener('mouseup', endRightDrag);
        e.preventDefault();
    });
    function doRightDrag(e) {
        if (rafId) return;
        rafId = requestAnimationFrame(function() {
            rafId = null;
            r.style.width = Math.min(600, Math.max(200, sw + sx - e.clientX)) + 'px';
        });
    }
    function endRightDrag() {
        endDrag();
        document.removeEventListener('mousemove', doRightDrag);
        document.removeEventListener('mouseup', endRightDrag);
    }

    // 输入区域高度
    ri.addEventListener('mousedown', function(e) {
        sy = e.clientY; sh = ic.offsetHeight;
        document.body.style.userSelect = 'none';
        document.body.style.cursor = 'row-resize';
        document.addEventListener('mousemove', doInputDrag);
        document.addEventListener('mouseup', endInputDrag);
        e.preventDefault();
    });
    function doInputDrag(e) {
        if (rafId) return;
        rafId = requestAnimationFrame(function() {
            rafId = null;
            ic.style.height = Math.min(window.innerHeight * 0.6, Math.max(100, sh + sy - e.clientY)) + 'px';
        });
    }
    function endInputDrag() {
        document.body.style.cursor = '';
        endDrag();
        document.removeEventListener('mousemove', doInputDrag);
        document.removeEventListener('mouseup', endInputDrag);
    }
}

// ====================================================================
// 11. Markdown 渲染
// ====================================================================
function renderMarkdown(text) { return marked.parse(text); }

function renderMarkdownFinal(text) {
    var html = marked.parse(text);
    var tmp = document.createElement('div');
    tmp.innerHTML = html;
    tmp.querySelectorAll('pre code').forEach(function(block) { hljs.highlightElement(block); });
    return tmp.innerHTML;
}

// ====================================================================
// 12. 初始化
// ====================================================================
function initialize() {
    initResizers();
    document.getElementById('send-btn')?.addEventListener('click', send);
    document.getElementById('load-folder-btn')?.addEventListener('click', loadFolder);
    document.getElementById('settings-btn')?.addEventListener('click', function() { if (bridge) bridge.open_settings(); });
    document.getElementById('new-conv-btn')?.addEventListener('click', newConversation);
    document.getElementById('select-all-btn')?.addEventListener('click', selectAllFiles);
    document.getElementById('deselect-all-btn')?.addEventListener('click', deselectAllFiles);
    document.getElementById('folder-path')?.addEventListener('keydown', function(e) { if (e.key === 'Enter') { e.preventDefault(); loadFolder(); } });

    document.getElementById('user-input')?.addEventListener('keydown', function(e) {
        if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
            e.preventDefault();
            send();
        }
    });
    attemptConnection();
}
window.addEventListener('load', initialize);
