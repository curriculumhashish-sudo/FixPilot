(function() {
    if (window.__rrweb_loaded) return;
    window.__rrweb_loaded = true;

    // 初始化事件存储（每页，将刷新到后端）
    window.__rrweb_events = window.__rrweb_events || [];
    // 指示录制是否应在新页面（跨页面）上自动开始的标志这是在显式 start_recording 调用后设置的仅，而不是在初始加载时设置
    //
    window.__rrweb_should_record = window.__rrweb_should_record || false;
    // 标记以跟踪 rrweb 是否加载失败
    window.__rrweb_load_failed = false;

    // 创建一个在 rrweb 加载时解析的 Promise（事件驱动等待）
    var resolveReady;
    window.__rrweb_ready_promise = new Promise(function(resolve) {
        resolveReady = resolve;
    });

    function loadRrweb() {
        var s = document.createElement('script');
        s.src = '{{CDN_URL}}';
        s.onload = function() {
            window.__rrweb_ready = true;
            console.log('[rrweb] Loaded successfully from CDN');
            resolveReady({success: true});
            // 如果设置了标志，则自动开始记录仅（用于跨页连续性） 该标志仅在显式 start_recording 调用后为 True
            //
            if (window.__rrweb_should_record && !window.__rrweb_stopFn) {
                window.startRecordingInternal();
            }
        };
        s.onerror = function() {
            console.error('[rrweb] Failed to load from CDN');
            window.__rrweb_load_failed = true;
            resolveReady({success: false, error: 'load_failed'});
        };
        (document.head || document.documentElement).appendChild(s);
    }

    // 内部开始录音功能（用于导航时自动开始）
    window.startRecordingInternal = function() {
        var recordFn = (typeof rrweb !== 'undefined' && rrweb.record) ||
                       (typeof rrwebRecord !== 'undefined' && rrwebRecord.record);
        if (!recordFn || window.__rrweb_stopFn) return;

        window.__rrweb_events = [];
        window.__rrweb_stopFn = recordFn({
            emit: function(event) {
                window.__rrweb_events.push(event);
            }
        });
        console.log('[rrweb] Auto-started recording on new page');
    };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', loadRrweb);
    } else {
        loadRrweb();
    }
})();
