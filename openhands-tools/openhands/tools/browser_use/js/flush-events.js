(function() {
    var events = window.__rrweb_events || [];
    // 刷新后清除浏览器端事件
    window.__rrweb_events = [];
    return JSON.stringify({events: events});
})();
