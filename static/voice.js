/* ============================================================
   AUX — pływający dyktafon (opcja B).
   Nagrywanie w przeglądarce (MediaRecorder — Chrome/Edge/Firefox),
   transkrypcja na serwerze: POST /voice/transcribe.
   - Kopiuj: schowek.
   - Wstaw do pola: wkleja w pozycji kursora do ostatnio używanego
     pola (kompatybilne z Alpine x-model przez natywny setter + input).
   ============================================================ */
(function () {
  var fab = document.getElementById('voice-fab');
  var panel = document.getElementById('voice-panel');
  var btnClose = document.getElementById('voice-close');
  var btnRec = document.getElementById('voice-rec');
  var btnCopy = document.getElementById('voice-copy');
  var btnInsert = document.getElementById('voice-insert');
  var statusEl = document.getElementById('voice-status');
  var ta = document.getElementById('voice-text');
  var hintEl = document.getElementById('voice-hint');

  if (!fab || !panel) return;

  var MAX_MS = 10 * 60 * 1000; // auto-stop po 10 minutach
  var mediaRec = null;
  var stream = null;
  var chunks = [];
  var recording = false;
  var busy = false; // wysyłanie / transkrypcja w toku
  var timerId = null;
  var maxTimerId = null;
  var startTs = 0;
  var lastField = null;

  function setStatus(msg, cls) {
    statusEl.textContent = msg;
    statusEl.classList.remove('rec', 'ok');
    if (cls) statusEl.classList.add(cls);
  }

  function syncButtons() {
    var has = ta.value.trim().length > 0;
    btnCopy.disabled = !has;
    btnInsert.disabled = !has;
  }

  function fmtTime(ms) {
    var s = Math.floor(ms / 1000);
    var m = Math.floor(s / 60);
    s = s % 60;
    return m + ':' + (s < 10 ? '0' : '') + s;
  }

  /* ---- Śledzenie ostatnio używanego pola (poza panelem dyktafonu) ---- */
  document.addEventListener('focusin', function (e) {
    var t = e.target;
    if (!t || panel.contains(t)) return;
    if (t.isContentEditable) { lastField = t; return; }
    if (t.tagName === 'TEXTAREA') { lastField = t; return; }
    if (t.tagName === 'INPUT') {
      var type = (t.type || 'text').toLowerCase();
      if (['text', 'search', 'password', 'url', 'email', 'tel', 'number'].indexOf(type) !== -1) {
        lastField = t;
      }
    }
  });

  /* ---- Panel ---- */
  fab.addEventListener('click', function () {
    panel.classList.toggle('hidden');
  });
  btnClose.addEventListener('click', function () {
    if (recording) stopRecording();
    panel.classList.add('hidden');
  });
  ta.addEventListener('input', syncButtons);

  /* ---- Status silnika (jednorazowo, do podpowiedzi) ---- */
  fetch('/voice/status')
    .then(function (r) { return r.json(); })
    .then(function (d) {
      if (d.status === 'ok') {
        hintEl.textContent = 'Mowa: polski · silnik: gateway' +
          (d.local_whisper ? ' (+ lokalny Whisper)' : '') +
          (d.has_key ? '' : ' · UWAGA: brak klucza API') + '.';
      }
    })
    .catch(function () { /* zostaje domyślna podpowiedź */ });

  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia || !window.MediaRecorder) {
    btnRec.disabled = true;
    hintEl.textContent = 'Twoja przeglądarka nie wspiera nagrywania dźwięku.';
    setStatus('Brak wsparcia MediaRecorder w tej przeglądarce.');
    return;
  }

  function pickMime() {
    var cands = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4'];
    for (var i = 0; i < cands.length; i++) {
      try {
        if (window.MediaRecorder.isTypeSupported(cands[i])) return cands[i];
      } catch (e) { /* sprawdzaj dalej */ }
    }
    return '';
  }

  /* ---- Nagrywanie ---- */
  function startRecording() {
    if (busy) return;
    setStatus('Prośba o dostęp do mikrofonu…');
    navigator.mediaDevices.getUserMedia({ audio: true }).then(function (s) {
      stream = s;
      chunks = [];
      var mime = pickMime();
      try {
        mediaRec = mime ? new MediaRecorder(stream, { mimeType: mime }) : new MediaRecorder(stream);
      } catch (e) {
        stopTracks();
        setStatus('Nie udało się uruchomić nagrywania.');
        return;
      }
      mediaRec.ondataavailable = function (e) {
        if (e.data && e.data.size) chunks.push(e.data);
      };
      mediaRec.onstop = onStopped;
      try {
        mediaRec.start(250);
      } catch (e) {
        stopTracks();
        setStatus('Nie udało się uruchomić nagrywania.');
        return;
      }
      recording = true;
      startTs = Date.now();
      btnRec.innerHTML = '⏹ STOP';
      fab.classList.add('recording');
      setStatus('Nagrywanie… 0:00', 'rec');
      timerId = setInterval(function () {
        setStatus('Nagrywanie… ' + fmtTime(Date.now() - startTs), 'rec');
      }, 500);
      maxTimerId = setTimeout(function () {
        if (recording) {
          stopRecording();
          setStatus('Osiągnięto limit 10 minut — przetwarzam nagranie…');
        }
      }, MAX_MS);
    }).catch(function () {
      setStatus('Brak dostępu do mikrofonu — zezwól w przeglądarce.');
    });
  }

  function stopTracks() {
    try {
      if (stream) stream.getTracks().forEach(function (t) { t.stop(); });
    } catch (e) { /* ignoruj */ }
    stream = null;
  }

  function stopRecording() {
    if (!recording || !mediaRec) return;
    recording = false;
    if (timerId) { clearInterval(timerId); timerId = null; }
    if (maxTimerId) { clearTimeout(maxTimerId); maxTimerId = null; }
    btnRec.disabled = true;
    try {
      mediaRec.stop();
    } catch (e) {
      onStopped();
    }
    stopTracks();
  }

  function onStopped() {
    btnRec.innerHTML = '🔴 REC';
    var blob = new Blob(chunks, { type: (mediaRec && mediaRec.mimeType) || 'audio/webm' });
    chunks = [];
    if (!blob.size) {
      btnRec.disabled = false;
      fab.classList.remove('recording');
      setStatus('Brak dźwięku — nic nie nagrano.');
      return;
    }
    busy = true;
    setStatus('Przetwarzanie (transkrypcja)…', 'rec');
    var ext = blob.type.indexOf('mp4') !== -1 ? 'm4a' : 'webm';
    var fd = new FormData();
    fd.append('audio', blob, 'nagranie.' + ext);
    fd.append('language', 'pl');
    fetch('/voice/transcribe', { method: 'POST', body: fd })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        busy = false;
        btnRec.disabled = false;
        fab.classList.remove('recording');
        if (d.status === 'ok') {
          ta.value = d.text || '';
          syncButtons();
          setStatus('Gotowe ✓ (silnik: ' + (d.engine || '?') + ') — skopiuj lub wstaw tekst.', 'ok');
        } else {
          setStatus('Błąd: ' + (d.error || '?'));
        }
      })
      .catch(function (e) {
        busy = false;
        btnRec.disabled = false;
        fab.classList.remove('recording');
        setStatus('Błąd połączenia z serwerem: ' + e);
      });
  }

  btnRec.addEventListener('click', function () {
    if (busy) return;
    if (recording) stopRecording();
    else startRecording();
  });

  /* ---- Kopiuj ---- */
  btnCopy.addEventListener('click', function () {
    var text = ta.value;
    if (!text.trim()) return;
    function done() { setStatus('Skopiowano do schowka ✓', 'ok'); }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(done, function () { fallbackCopy(); done(); });
    } else {
      fallbackCopy();
      done();
    }
  });

  function fallbackCopy() {
    ta.select();
    try { document.execCommand('copy'); } catch (err) { /* brak wsparcia */ }
    window.getSelection().removeAllRanges();
  }

  /* ---- Wstaw do ostatnio używanego pola ---- */
  btnInsert.addEventListener('click', function () {
    var text = ta.value;
    if (!text.trim()) return;
    if (!lastField || !document.contains(lastField)) {
      setStatus('Kliknij najpierw w pole tekstowe, do którego wstawić tekst.');
      return;
    }
    try {
      if (lastField.isContentEditable) {
        lastField.focus();
        document.execCommand('insertText', false, text);
      } else {
        lastField.focus();
        var start = lastField.selectionStart;
        var end = lastField.selectionEnd;
        if (start === null || start === undefined) {
          start = end = (lastField.value || '').length;
        }
        var v = lastField.value || '';
        var next = v.slice(0, start) + text + v.slice(end);
        // Natywny setter + zdarzenie input — wymagane, żeby Alpine x-model
        // (Playground, Optymalizator) zauważył programową zmianę.
        var proto = lastField.tagName === 'TEXTAREA'
          ? HTMLTextAreaElement.prototype
          : HTMLInputElement.prototype;
        var setter = Object.getOwnPropertyDescriptor(proto, 'value').set;
        setter.call(lastField, next);
        lastField.dispatchEvent(new Event('input', { bubbles: true }));
        var pos = start + text.length;
        try { lastField.setSelectionRange(pos, pos); } catch (err) { /* np. number */ }
      }
      setStatus('Wstawiono do pola ✓', 'ok');
    } catch (err) {
      setStatus('Nie udało się wstawić: ' + err);
    }
  });

  syncButtons();
})();
