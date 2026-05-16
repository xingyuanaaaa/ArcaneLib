/**
 * 软件库系统 - 主JavaScript文件
 * 提供API请求、Toast消息、认证等通用功能
 */

// Android原生桥接
const AndroidBridge = {
    isAvailable() { return typeof AndroidBridge_native !== 'undefined'; },
    getDeviceId() {
        if (this.isAvailable()) return AndroidBridge_native.getDeviceId();
        return '';
    },
    vibrate(duration) {
        if (this.isAvailable()) AndroidBridge_native.vibrate(duration);
    },
    showToast(message) {
        if (this.isAvailable()) AndroidBridge_native.showToast(message);
        else Toast.show(message, 'info', 2000);
    },
    openUrl(url) {
        if (this.isAvailable()) AndroidBridge_native.openUrl(url);
        else window.open(url, '_blank');
    },
    getAppVersion() {
        if (this.isAvailable()) return AndroidBridge_native.getAppVersion();
        return '1.0.0';
    },
    exitApp() {
        if (this.isAvailable()) AndroidBridge_native.exitApp();
    },
    isRooted() {
        if (this.isAvailable()) return AndroidBridge_native.isRooted();
        return false;
    },
    getDeviceInfo() {
        if (this.isAvailable()) return AndroidBridge_native.getDeviceInfo();
        return navigator.userAgent || '';
    }
};

const API = {
    /**
     * 发送API请求
     */
    async request(url, options = {}) {
        const config = {
            headers: {
                'Content-Type': 'application/json',
                'X-CSRF-Token': this.getCSRFToken(),
                'X-Requested-With': 'XMLHttpRequest'
            },
            ...options
        };

        if (config.body && typeof config.body === 'object' && !(config.body instanceof FormData)) {
            config.body = JSON.stringify(config.body);
        }
        if (config.body instanceof FormData) {
            delete config.headers['Content-Type'];
        }

        try {
            const response = await fetch(url, config);
            const data = await response.json();
            if (response.status === 401 && data.message === '请先登录') {
                window.location.href = '/login';
            }
            return data;
        } catch (error) {
            console.error('API请求失败:', error);
            return { success: false, message: '网络错误，请检查连接' };
        }
    },

    get(url) { return this.request(url); },
    post(url, body) { return this.request(url, { method: 'POST', body }); },
    put(url, body) { return this.request(url, { method: 'PUT', body }); },
    delete(url, body) { return this.request(url, { method: 'DELETE', body }); },

    getCSRFToken() {
        const meta = document.querySelector('meta[name="csrf-token"]');
        return meta ? meta.getAttribute('content') : '';
    }
};

/**
 * Toast消息提示
 */
const Toast = {
    show(message, type = 'info', duration = 3000) {
        let container = document.querySelector('.toast-container');
        if (!container) {
            container = document.createElement('div');
            container.className = 'toast-container';
            document.body.appendChild(container);
        }

        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        toast.textContent = message;
        container.appendChild(toast);

        setTimeout(() => {
            toast.style.opacity = '0';
            toast.style.transition = 'opacity 0.3s';
            setTimeout(() => toast.remove(), 300);
        }, duration);
    },
    success(msg) { this.show(msg, 'success'); },
    error(msg) { this.show(msg, 'danger'); },
    warning(msg) { this.show(msg, 'warning'); },
    info(msg) { this.show(msg, 'info'); }
};

/**
 * 模态框
 */
const Modal = {
    show(title, content, buttons = []) {
        const overlay = document.createElement('div');
        overlay.className = 'modal-overlay';
        overlay.innerHTML = `
            <div class="modal-box">
                <h3>${title}</h3>
                <div class="modal-body">${content}</div>
                <div class="modal-actions">
                    ${buttons.map((btn, i) => `
                        <button class="btn ${btn.cls || 'btn-primary'}" data-index="${i}">${btn.text}</button>
                    `).join('')}
                </div>
            </div>`;
        document.body.appendChild(overlay);

        const actions = overlay.querySelectorAll('.modal-actions button');
        actions.forEach(btn => {
            btn.addEventListener('click', () => {
                const idx = parseInt(btn.dataset.index);
                if (buttons[idx] && buttons[idx].callback) {
                    buttons[idx].callback();
                }
                overlay.remove();
            });
        });

        overlay.addEventListener('click', (e) => {
            if (e.target === overlay) overlay.remove();
        });
    },
    confirm(title, message, onConfirm) {
        this.show(title, `<p>${message}</p>`, [
            { text: '取消', cls: 'btn-outline', callback: () => {} },
            { text: '确认', cls: 'btn-danger', callback: onConfirm }
        ]);
    }
};

/**
 * 格式化文件大小
 */
function formatFileSize(bytes) {
    if (!bytes) return '未知';
    const units = ['B', 'KB', 'MB', 'GB'];
    let i = 0;
    let size = bytes;
    while (size >= 1024 && i < units.length - 1) {
        size /= 1024;
        i++;
    }
    return size.toFixed(1) + ' ' + units[i];
}

/**
 * 格式化日期
 */
function formatDate(dateStr) {
    if (!dateStr) return '';
    const d = new Date(dateStr);
    const now = new Date();
    const diff = now - d;
    if (diff < 60000) return '刚刚';
    if (diff < 3600000) return Math.floor(diff / 60000) + '分钟前';
    if (diff < 86400000) return Math.floor(diff / 3600000) + '小时前';
    if (diff < 604800000) return Math.floor(diff / 86400000) + '天前';
    return d.getFullYear() + '-' +
           String(d.getMonth() + 1).padStart(2, '0') + '-' +
           String(d.getDate()).padStart(2, '0');
}

/**
 * URL参数解析
 */
function getUrlParam(name) {
    const params = new URLSearchParams(window.location.search);
    return params.get(name);
}

/**
 * 防抖函数
 */
function debounce(fn, delay = 300) {
    let timer;
    return function(...args) {
        clearTimeout(timer);
        timer = setTimeout(() => fn.apply(this, args), delay);
    };
}

/**
 * 获取机器码（从客户端采集）
 */
async function getMachineCode() {
    try {
        const canvas = document.createElement('canvas');
        const gl = canvas.getContext('webgl');
        const debugInfo = gl.getExtension('WEBGL_debug_renderer_info');
        let gpu = debugInfo ? gl.getParameter(debugInfo.UNMASKED_RENDERER_WEBGL) : '';

        const components = [
            navigator.hardwareConcurrency || '',
            navigator.deviceMemory || '',
            navigator.platform || '',
            screen.colorDepth + 'x' + screen.width + 'x' + screen.height,
            new Date().getTimezoneOffset(),
            gpu,
            navigator.language
        ];

        const fingerprint = components.join('|');
        const encoder = new TextEncoder();
        const data = encoder.encode(fingerprint);
        const hashBuffer = await crypto.subtle.digest('SHA-256', data);
        const hashArray = Array.from(new Uint8Array(hashBuffer));
        const hashHex = hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
        return hashHex.substring(0, 32).toUpperCase();
    } catch (e) {
        return 'UNKNOWN_MACHINE_CODE';
    }
}

(function() {
    'use strict';

    // 仅通过 debugger 延迟检测来识别开发者工具
    // VPN/梯子 不会影响 debugger 执行速度，不会被误判
    var _checkDevTools = function() {
        var start = performance.now();
        debugger;
        var end = performance.now();
        // debugger > 200ms = 开发者工具打开（抓包/调试）
        // debugger < 5ms = VPN/梯子/正常，正常运行
        if (end - start > 200) {
            _triggerProtection();
        }
    };

    setInterval(_checkDevTools, 10000);

    // F12 / Ctrl+Shift+I / Ctrl+U 快捷键防护
    document.addEventListener('keydown', function(e) {
        if (e.key === 'F12' ||
            (e.ctrlKey && e.shiftKey && (e.key === 'I' || e.key === 'J' || e.key === 'C')) ||
            (e.ctrlKey && e.key === 'U')) {
            e.preventDefault();
            return false;
        }
    });

    // 右键菜单禁用
    document.addEventListener('contextmenu', function(e) {
        e.preventDefault();
        return false;
    });

    // WebDriver 保护
    Object.defineProperty(navigator, 'webdriver', {
        get: function() { return false; }
    });

    // 温和触发保护 - 不销毁页面，只提示
    function _triggerProtection() {
        var banner = document.createElement('div');
        banner.id = '_devWarning';
        banner.style.cssText = 'position:fixed;top:0;left:0;right:0;z-index:99999;background:#b04a4a;color:#fff;text-align:center;padding:10px 16px;font-size:0.85rem;font-family:sans-serif;display:flex;align-items:center;justify-content:center;gap:12px';
        banner.innerHTML = '<span>⚠ 检测到开发者工具已打开，请关闭以保证正常使用</span><button onclick="this.parentElement.remove()" style="background:rgba(255,255,255,0.2);border:none;color:#fff;padding:4px 12px;border-radius:4px;cursor:pointer;font-size:0.8rem">知道了</button>';
        document.body.appendChild(banner);
    }
})();

// 页面加载完成
document.addEventListener('DOMContentLoaded', () => {
    // 自动设置当前导航激活状态
    const currentPath = window.location.pathname;
    document.querySelectorAll('.bottom-nav a').forEach(link => {
        const href = link.getAttribute('href');
        if (href === currentPath || (href !== '/' && currentPath.startsWith(href))) {
            link.classList.add('active');
        }
    });

    // 自动设置分类标签激活
    const categoryId = getUrlParam('category_id');
    if (categoryId) {
        document.querySelectorAll('.category-tab').forEach(tab => {
            if (tab.dataset.categoryId === categoryId) {
                tab.classList.add('active');
            }
        });
    }
});