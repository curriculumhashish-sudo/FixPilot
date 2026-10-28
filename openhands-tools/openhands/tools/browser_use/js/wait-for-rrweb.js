(function() {
    // 如果 Promise 不存在，则脚本尚未注入
    if (!window.__rrweb_ready_promise) {
        return Promise.resolve({success: false, error: 'not_injected'});
    }
    // 如果已经加载，则立即返回
    if (window.__rrweb_ready) {
        return Promise.resolve({success: true});
    }
    // 如果已经失败，立即返回
    if (window.__rrweb_load_failed) {
        return Promise.resolve({success: false, error: 'load_failed'});
    }
    // 等待 Promise 解决
    return window.__rrweb_ready_promise;
})();
