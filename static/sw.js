/* 软件库系统 - Service Worker */
/* 提供离线缓存和PWA安装支持 */

const CACHE_NAME = 'software-library-v1';
const STATIC_CACHE = [
    '/',
    '/static/css/style.css',
    '/static/js/app.js',
    '/static/manifest.json',
    '/login',
    '/register',
    '/card_redeem',
    '/feedback',
    '/announcements',
    '/user_center'
];

// 安装事件 - 预缓存静态资源
self.addEventListener('install', function(event) {
    event.waitUntil(
        caches.open(CACHE_NAME).then(function(cache) {
            return cache.addAll(STATIC_CACHE);
        })
    );
    self.skipWaiting();
});

// 激活事件 - 清理旧缓存
self.addEventListener('activate', function(event) {
    event.waitUntil(
        caches.keys().then(function(keys) {
            return Promise.all(
                keys.filter(function(key) {
                    return key !== CACHE_NAME;
                }).map(function(key) {
                    return caches.delete(key);
                })
            );
        })
    );
    self.clients.claim();
});

// 请求拦截 - 缓存策略
self.addEventListener('fetch', function(event) {
    // 跳过API请求和动态页面（让它们走网络）
    if (event.request.url.includes('/api/') ||
        event.request.url.includes('/admin') ||
        event.request.url.includes('/search') ||
        event.request.url.includes('/software/') ||
        event.request.url.includes('/category/') ||
        event.request.method !== 'GET') {
        return;
    }

    event.respondWith(
        caches.match(event.request).then(function(cached) {
            if (cached) {
                return cached;
            }
            return fetch(event.request).then(function(response) {
                if (response && response.status === 200) {
                    var clone = response.clone();
                    caches.open(CACHE_NAME).then(function(cache) {
                        cache.put(event.request, clone);
                    });
                }
                return response;
            });
        })
    );
});