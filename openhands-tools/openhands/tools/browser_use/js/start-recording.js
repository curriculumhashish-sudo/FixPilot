(function() {
    if (window.__rrweb_stopFn) return {status: 'already_recording'};
    // 检查 rrweb 是否无法从 CDN 加载
    if (window.__rrweb_load_failed) return {status: 'load_failed'};
    // rrweb UMD 模块导出到 window.rrweb （不是 rrwebRecord）
    var recordFn = (typeof rrweb !== 'undefined' && rrweb.record) ||
                   (typeof rrwebRecord !== 'undefined' && rrwebRecord.record);
    if (!recordFn) return {status: 'not_loaded'};
    window.__rrweb_events = [];
    window.__rrweb_should_record = true;
    window.__rrweb_stopFn = recordFn({
        emit: function(event) {
            window.__rrweb_events.push(event);
        }
    });
    return {status: 'started'};
})();
