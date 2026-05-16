/**
 * 班级投屏 - 手机端客户端
 * Supports: screen share (Android), document camera (all), photo upload (all), URL push (all)
 */
(function() {
  'use strict';

  // ---- Shared WebSocket ----
  let ws = null;
  let isCasting = false;
  let reconnectAttempts = 0;
  const MAX_RECONNECT = 3;

  function getWsUrl() {
    var loc = window.location;
    return (loc.protocol === 'https:' ? 'wss:' : 'ws:') + '//' + loc.host + '/ws';
  }

  function connectWs() {
    return new Promise(function(resolve, reject) {
      try { ws = new WebSocket(getWsUrl()); }
      catch(e) { reject(e); return; }
      ws.onopen = function() { reconnectAttempts = 0; resolve(); };
      ws.onmessage = function(e) {
        if (e.data === 'CLIENT_DISCONNECT') {
          // Big screen disconnected us
          if (isCasting) {
            stopCast();
            var st = document.getElementById('statusScreen');
            setStatus(st, '大屏端已断开连接', 'error');
          }
          if (cameraStream) {
            stopCamera();
            var st2 = document.getElementById('statusCamera');
            setStatus(st2, '大屏端已断开连接', 'error');
          }
        }
      };
      ws.onclose = function() {
        ws = null;
        if (isCasting && reconnectAttempts < MAX_RECONNECT) {
          reconnectAttempts++;
          setTimeout(function() { if (isCasting) connectWs().catch(function(){}); }, 2000);
        }
      };
      ws.onerror = function() {
        if (!ws || ws.readyState === WebSocket.CLOSED) reject(new Error('WS fail'));
      };
    });
  }

  function wsSend(data) {
    if (ws && ws.readyState === WebSocket.OPEN) {
      try { ws.send(data); } catch(e) {}
    }
  }

  function base64ToArrayBuffer(b64) {
    var bin = atob(b64), buf = new Uint8Array(bin.length);
    for (var i = 0; i < bin.length; i++) buf[i] = bin.charCodeAt(i);
    return buf.buffer;
  }

  function setStatus(el, msg, type) {
    el.textContent = msg;
    el.className = 'status';
    if (type) el.classList.add('status-' + type);
  }

  function show(el) { if (el) el.classList.remove('hidden'); }
  function hide(el) { if (el) el.classList.add('hidden'); }

  // =========================================================
  // 1. SCREEN SHARE (Android only)
  // =========================================================
  var mediaStream = null, videoEl = null, animId = null;

  window.startCast = async function() {
    if (isCasting) return;
    var btn = document.getElementById('btnStart');
    var st  = document.getElementById('statusScreen');

    if (!navigator.mediaDevices || !navigator.mediaDevices.getDisplayMedia) {
      setStatus(st, 'iOS 不支持屏幕共享，请使用"实物展台"或"拍照上传"', 'error');
      return;
    }
    if (!window.isSecureContext) {
      setStatus(st, '需要 HTTPS 连接', 'error');
      return;
    }

    try {
      setStatus(st, '请求屏幕权限...', 'connecting');
      mediaStream = await navigator.mediaDevices.getDisplayMedia({
        video: { width: { ideal: 1280 }, height: { ideal: 720 }, frameRate: { ideal: 20 } },
        audio: false
      });
      if (!mediaStream) { setStatus(st, '已取消', 'error'); return; }

      mediaStream.getVideoTracks()[0].addEventListener('ended', function() { stopCast(); });

      await connectWs();
      isCasting = true;
      hide(btn); show(document.getElementById('btnStop'));
      setStatus(st, '正在投屏...', 'connected');
      wsSend('CAST_START');

      // Canvas capture
      videoEl = document.createElement('video');
      videoEl.srcObject = mediaStream;
      videoEl.muted = true; videoEl.playsInline = true; videoEl.play();
      var canvas = document.createElement('canvas');
      var ctx = canvas.getContext('2d');

      videoEl.onloadedmetadata = function() {
        canvas.width = Math.min(videoEl.videoWidth || 640, 1280);
        canvas.height = Math.round(canvas.width * ((videoEl.videoHeight || 480) / (videoEl.videoWidth || 640)));
        var preview = document.getElementById('previewScreen');
        preview.style.display = 'block';
        var lastCap = 0;
        function frame(ts) {
          if (!isCasting) return;
          if (ts - lastCap >= 80) { // ~12fps
            lastCap = ts - ((ts - lastCap) % 80);
            ctx.drawImage(videoEl, 0, 0, canvas.width, canvas.height);
            var dataUrl = canvas.toDataURL('image/jpeg', 0.55);
            wsSend(base64ToArrayBuffer(dataUrl.split(',')[1]));
            preview.src = dataUrl;
          }
          animId = requestAnimationFrame(frame);
        }
        animId = requestAnimationFrame(frame);
      };
    } catch(e) {
      console.error(e);
      setStatus(st, '启动失败: ' + (e.message || e), 'error');
      cleanupCast();
    }
  };

  window.stopCast = function() {
    isCasting = false;
    wsSend('CAST_STOP');
    cleanupCast();
    show(document.getElementById('btnStart'));
    hide(document.getElementById('btnStop'));
    setStatus(document.getElementById('statusScreen'), '投屏已停止', 'idle');
    var p = document.getElementById('previewScreen');
    if (p) p.style.display = 'none';
  };

  function cleanupCast() {
    if (animId) { cancelAnimationFrame(animId); animId = null; }
    if (mediaStream) { try { mediaStream.getTracks().forEach(function(t){t.stop();}); } catch(e){} mediaStream = null; }
    if (videoEl) { videoEl.pause(); videoEl.srcObject = null; videoEl = null; }
    if (ws) { try { ws.close(); } catch(e){} ws = null; }
    isCasting = false;
  }

  // =========================================================
  // 2. DOCUMENT CAMERA - iOS handles orientation natively
  // =========================================================
  var cameraStream = null, cameraAnimId = null, cameraVideo = null;
  var cameraCanvas = null, cameraCtx = null;

  window.startCamera = async function() {
    if (cameraStream) return;
    var btn = document.getElementById('btnCameraStart');
    var st  = document.getElementById('statusCamera');

    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      setStatus(st, '设备不支持摄像头', 'error');
      return;
    }

    try {
      setStatus(st, '请求摄像头权限...', 'connecting');
      cameraStream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: 'environment', width: { ideal: 1280 }, height: { ideal: 720 } },
        audio: false
      });

      await connectWs();
      isCasting = true;
      hide(btn); show(document.getElementById('cameraControls'));
      setStatus(st, '实物展台已开启', 'connected');
      wsSend('CAST_START');

      cameraVideo = document.getElementById('cameraFeed');
      cameraVideo.srcObject = cameraStream;
      cameraVideo.classList.remove('hidden');
      cameraVideo.setAttribute('playsinline', '');
      cameraVideo.play();

      cameraCanvas = document.createElement('canvas');
      cameraCtx = cameraCanvas.getContext('2d');

      cameraVideo.onloadedmetadata = function() {
        var vw = cameraVideo.videoWidth || 1280;
        var vh = cameraVideo.videoHeight || 720;

        function orientCanvas() {
          // Detect orientation by comparing viewport dimensions (always reliable)
          var portrait = window.innerHeight > window.innerWidth;
          if (portrait) {
            cameraCanvas.height = Math.min(Math.max(vw, vh), 960);
            cameraCanvas.width = Math.round(cameraCanvas.height * Math.min(vw, vh) / Math.max(vw, vh));
          } else {
            cameraCanvas.width = Math.min(Math.max(vw, vh), 1280);
            cameraCanvas.height = Math.round(cameraCanvas.width * Math.min(vw, vh) / Math.max(vw, vh));
          }
        }

        orientCanvas();

        // React to orientation changes — use multiple listeners for reliability
        window.addEventListener('resize', orientCanvas);
        if (screen.orientation) {
          screen.orientation.addEventListener('change', orientCanvas);
        }

        var lastCap = 0;
        function frame(ts) {
          if (!isCasting) return;
          if (ts - lastCap >= 100) {
            // Re-check orientation before each capture (negligible cost)
            orientCanvas();
            lastCap = ts - ((ts - lastCap) % 100);
            cameraCtx.drawImage(cameraVideo, 0, 0, cameraCanvas.width, cameraCanvas.height);
            wsSend(base64ToArrayBuffer(
              cameraCanvas.toDataURL('image/jpeg', 0.55).split(',')[1]
            ));
          }
          cameraAnimId = requestAnimationFrame(frame);
        }
        cameraAnimId = requestAnimationFrame(frame);
      };
    } catch(e) {
      console.error(e);
      if (e.name === 'NotAllowedError')
        setStatus(st, '摄像头权限被拒绝', 'error');
      else
        setStatus(st, '启动失败: ' + (e.message || e), 'error');
      stopCamera();
    }
  };

  window.captureSnapshot = async function() {
    if (!cameraCanvas || !isCasting) return;
    var st = document.getElementById('statusCamera');
    try {
      // Capture the current canvas as JPEG blob
      var blob = await new Promise(function(resolve) {
        cameraCanvas.toBlob(function(b) { resolve(b); }, 'image/jpeg', 0.85);
      });
      if (!blob) { setStatus(st, '截图失败', 'error'); return; }

      // Stop live camera streaming so the photo stays on screen
      isCasting = false;
      wsSend('CAST_STOP');
      if (cameraAnimId) { cancelAnimationFrame(cameraAnimId); cameraAnimId = null; }
      if (cameraStream) {
        try { cameraStream.getTracks().forEach(function(t){t.stop();}); } catch(e){}
      }
      cameraStream = null;

      // Send via upload API so it appears in the photo gallery
      var formData = new FormData();
      formData.append('photo', blob, 'snapshot_' + Date.now() + '.jpg');
      var resp = await fetch('/api/upload', { method: 'POST', body: formData });
      var data = await resp.json();

      // Reset UI buttons regardless of upload result
      hide(document.getElementById('cameraControls'));
      show(document.getElementById('btnCameraStart'));

      if (data.ok) {
        setStatus(st, '✅ 截图已发送', 'connected');
        var feed = document.getElementById('cameraFeed');
        feed.style.filter = 'brightness(1.5)';
        setTimeout(function() { feed.style.filter = ''; }, 150);
      } else {
        setStatus(st, '截图发送失败', 'error');
      }
    } catch(e) {
      setStatus(st, '截图失败: ' + e.message, 'error');
    }
  };

  window.stopCamera = function() {
    isCasting = false;
    if (cameraAnimId) { cancelAnimationFrame(cameraAnimId); cameraAnimId = null; }
    if (cameraStream) { try { cameraStream.getTracks().forEach(function(t){t.stop();}); } catch(e){} cameraStream = null; }
    if (cameraVideo) { cameraVideo.classList.add('hidden'); cameraVideo.srcObject = null; cameraVideo = null; }
    wsSend('CAST_STOP');
    hide(document.getElementById('cameraControls'));
    show(document.getElementById('btnCameraStart'));
    setStatus(document.getElementById('statusCamera'), '摄像头已关闭', 'idle');
  };

  // =========================================================
  // 3. PHOTO UPLOAD (multiple)
  // =========================================================
  var selectedFiles = [];
  var totalSent = 0;

  // Read file as data URL
  function readFile(file) {
    return new Promise(function(resolve) {
      var r = new FileReader();
      r.onload = function(e) { resolve(e.target.result); };
      r.readAsDataURL(file);
    });
  }

  // Render preview thumbnails
  async function renderPhotoPreviews(files) {
    var container = document.getElementById('photoPreviewList');
    container.innerHTML = '';
    for (var i = 0; i < files.length; i++) {
      var dataUrl = await readFile(files[i]);
      var div = document.createElement('div');
      div.style.position = 'relative';
      div.style.width = '80px';
      div.style.height = '80px';
      div.style.borderRadius = '8px';
      div.style.overflow = 'hidden';
      div.style.border = '2px solid #30363d';
      div.innerHTML = '<img src="' + dataUrl + '" style="width:100%;height:100%;object-fit:cover;">' +
        '<div style="position:absolute;bottom:0;right:0;background:#238636;color:#fff;font-size:11px;padding:1px 5px;border-radius:4px 0 0 0;">' + (i+1) + '</div>';
      container.appendChild(div);
    }
  }

  document.getElementById('photoInput').addEventListener('change', function(e) {
    if (e.target.files && e.target.files.length > 0) {
      // Append new files to existing selection
      for (var i = 0; i < e.target.files.length; i++) {
        selectedFiles.push(e.target.files[i]);
      }
      renderPhotoPreviews(selectedFiles);
      document.getElementById('btnPhotoSend').textContent = '发送 ' + selectedFiles.length + ' 张照片';
      show(document.getElementById('photoPreview'));
      hide(document.getElementById('photoSentList'));
      setStatus(document.getElementById('statusPhoto'), '已选择 ' + selectedFiles.length + ' 张照片', 'connecting');
      // Clear input so re-selecting same file / re-taking photo works
      e.target.value = '';
    }
  });

  window.sendPhotos = async function() {
    if (selectedFiles.length === 0) return;
    var st = document.getElementById('statusPhoto');
    var btn = document.getElementById('btnPhotoSend');
    btn.disabled = true;
    btn.textContent = '发送中 0/' + selectedFiles.length + '...';

    var successCount = 0;
    for (var i = 0; i < selectedFiles.length; i++) {
      btn.textContent = '发送中 ' + (i+1) + '/' + selectedFiles.length + '...';
      try {
        var formData = new FormData();
        formData.append('photo', selectedFiles[i]);
        var resp = await fetch('/api/upload', { method: 'POST', body: formData });
        var data = await resp.json();
        if (data.ok) successCount++;
      } catch(e) {
        console.error('Upload failed:', e);
      }
    }

    totalSent += successCount;

    // Hide preview, show sent confirmation
    hide(document.getElementById('photoPreview'));
    show(document.getElementById('photoSentList'));
    document.getElementById('photoSentCount').textContent = '✅ 已发送 ' + totalSent + ' 张照片';
    setStatus(st, successCount === selectedFiles.length ? '全部发送成功' : successCount + '/' + selectedFiles.length + ' 发送成功', 'connected');

    selectedFiles = [];
    btn.disabled = false;
  };

  window.resetPhotoUpload = function() {
    hide(document.getElementById('photoSentList'));
    document.getElementById('photoInput').value = '';
    setStatus(document.getElementById('statusPhoto'), '', 'idle');
  };

  // =========================================================
  // 4. URL PUSH
  // =========================================================
  window.pushUrl = async function() {
    var input = document.getElementById('urlInput');
    var st = document.getElementById('statusUrl');
    var url = input.value.trim();
    if (!url) { setStatus(st, '请输入网址', 'error'); return; }
    if (!url.startsWith('http://') && !url.startsWith('https://')) {
      url = 'https://' + url;
      input.value = url;
    }

    try {
      var resp = await fetch('/api/pushurl', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: url })
      });
      var data = await resp.json();
      if (data.ok) {
        setStatus(st, '✅ 网址已推送到大屏', 'connected');
      } else {
        setStatus(st, '推送失败: ' + (data.error || 'unknown'), 'error');
      }
    } catch(e) {
      setStatus(st, '推送失败: ' + e.message, 'error');
    }
  };

  // =========================================================
  // Init
  // =========================================================
  (function init() {
    fetch('/api/info').then(function(r){return r.json();}).then(function(d){
      document.getElementById('serverInfo').textContent = '服务器: ' + (d.ip || '未知');
    }).catch(function(){});
  })();

  console.log('[Cast] Client loaded');
})();
