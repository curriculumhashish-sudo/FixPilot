(function() {
    var events = window.__rrweb_events || [];

    // 如果活动则停止录制
    if (window.__rrweb_stopFn) {
        window.__rrweb_stopFn();
        window.__rrweb_stopFn = null;
    }

    // 清除标志
    window.__rrweb_should_record = false;
    window.__rrweb_events = [];

    return JSON.stringify({events: events});
})();
