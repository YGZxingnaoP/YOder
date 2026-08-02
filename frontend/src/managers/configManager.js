/**
 * 配置管理器
 */
export class ConfigManager {
    constructor() {
        this.config = null;
        this.toolsConfig = null;
    }
    
    async loadConfig() {
        try {
            // 从后端API加载配置
            const response = await fetch('/api/config');
            this.config = await response.json();
            // 确保 api_keys 存在
            if (!this.config.api_keys) {
                this.config.api_keys = {};
            }
        } catch (error) {
            console.error('加载配置失败:', error);
            // 使用默认配置
            this.config = this.getDefaultConfig();
        }
    }
    
    getDefaultConfig() {
        return {
            platform: '阿里',
            model: 'qwen-max',
            max_tokens: 65536,
            temperature: 0.7,
            thinking_level: 'high',
            memory_rounds: 50,
            legacy_chain: false,
            tools_enabled: true,
            agent_mode: '',
            api_keys: {}
        };
    }
    
    async saveConfig() {
        try {
            await fetch('/api/config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(this.config)
            });
        } catch (error) {
            console.error('保存配置失败:', error);
        }
    }
    
    /**
     * 获取指定平台的 API Key
     */
    getApiKey(platform) {
        return this.config?.api_keys?.[platform] || '';
    }
    
    /**
     * 设置指定平台的 API Key
     */
    setApiKey(platform, key) {
        if (!this.config.api_keys) {
            this.config.api_keys = {};
        }
        this.config.api_keys[platform] = key;
    }
    
    /**
     * 加载对话级配置覆盖
     */
    async loadChatConfig(chatId) {
        try {
            const response = await fetch(`/api/chats/${chatId}/config`);
            return await response.json();
        } catch (error) {
            console.error('加载对话配置失败:', error);
            return {};
        }
    }
    
    /**
     * 保存对话级配置覆盖
     */
    async saveChatConfig(chatId, config) {
        try {
            await fetch(`/api/chats/${chatId}/config`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(config)
            });
        } catch (error) {
            console.error('保存对话配置失败:', error);
        }
    }
    
    toggleLegacyChain() {
        this.config.legacy_chain = !this.config.legacy_chain;
        this.saveConfig();
    }
    
    get(key) {
        return this.config?.[key];
    }
    
    set(key, value, silent = false) {
        if (this.config) {
            this.config[key] = value;
            if (!silent) {
                this.saveConfig();
            }
        }
    }
}
