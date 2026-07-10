/* ══════════════════════════════════════════════════════════════════
   JARVIS AI v2.0 — Application Logic (Live Backend)
   Connects to FastAPI server for Groq LLM, Whisper STT, and TTS
   ══════════════════════════════════════════════════════════════════ */

(function () {
  const API_BASE = (window.location.protocol === 'file:' || window.location.origin === 'null') 
    ? 'http://127.0.0.1:8000' 
    : window.location.origin;

  // ── DOM refs ───────────────────────────────────────────────────
  const chatLog        = document.getElementById('chatLog');
  const commandInput   = document.getElementById('commandInput');
  const sendBtn        = document.getElementById('sendBtn');
  const micBtn         = document.getElementById('micBtn');
  const clearBtn       = document.getElementById('clearBtn');
  const transcriptText = document.getElementById('transcriptText');
  const orbLabel       = document.getElementById('orbLabel');
  const modeText       = document.getElementById('modeText');
  const metricLatency  = document.getElementById('metricLatency');
  const metricModel    = document.getElementById('metricModel');
  const metricUptime   = document.getElementById('metricUptime');
  const metricTokens   = document.getElementById('metricTokens');
  const pillMode       = document.getElementById('pillMode');
  const pillBrain      = document.getElementById('pillBrain');
  const suggestions    = document.getElementById('suggestions');

  // ── State ──────────────────────────────────────────────────────
  let isProcessing = false;
  let isMicActive = false;
  let isRecording = false;
  let mediaRecorder = null;
  let audioChunks = [];
  let currentAudioSource = null;
  let currentAbortController = null;
  let silenceTimer = null;
  let isSpeaking = false;
  const startTime = Date.now();
  const commandHistory = [];
  let historyIndex = -1;
  let typingIndicatorEl = null;

  // ── Uptime counter ─────────────────────────────────────────────
  setInterval(() => {
    const elapsed = Math.floor((Date.now() - startTime) / 1000);
    const m = Math.floor(elapsed / 60);
    const s = elapsed % 60;
    metricUptime.textContent = `${m}:${s.toString().padStart(2, '0')}`;
  }, 1000);

  // ── Orb state management ───────────────────────────────────────
  function setOrbMode(mode) {
    if (window.orbState) window.orbState.mode = mode;
    orbLabel.textContent = mode.toUpperCase();
    modeText.textContent = mode.charAt(0).toUpperCase() + mode.slice(1);

    const dot = pillMode.querySelector('.dot');
    pillMode.classList.remove('online');
    if (mode === 'listening') {
      dot.style.background = '#00e5ff';
      dot.style.boxShadow = '0 0 6px #00e5ff';
    } else if (mode === 'thinking') {
      dot.style.background = '#7c4dff';
      dot.style.boxShadow = '0 0 6px #7c4dff';
    } else if (mode === 'speaking') {
      dot.style.background = '#69f0ae';
      dot.style.boxShadow = '0 0 6px #69f0ae';
    } else {
      dot.style.background = '';
      dot.style.boxShadow = '';
    }
  }

  function setAudioLevel(level) {
    if (window.orbState) window.orbState.audioLevel = Math.min(1, Math.max(0, level));
  }

  // ── Add chat message ───────────────────────────────────────────
  function addMessage(role, text) {
    const msg = document.createElement('div');
    msg.className = `message ${role}`;

    const avatar = document.createElement('div');
    avatar.className = 'message-avatar';
    avatar.textContent = role === 'jarvis' ? 'J' : 'Y';

    const body = document.createElement('div');
    body.className = 'message-body';

    const name = document.createElement('div');
    name.className = 'message-name';
    name.textContent = role === 'jarvis' ? 'JARVIS' : 'YOU';

    const content = document.createElement('div');
    content.className = 'message-text';
    content.textContent = text;

    const time = document.createElement('div');
    time.className = 'message-time';
    const now = new Date();
    time.textContent = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

    body.appendChild(name);
    body.appendChild(content);
    body.appendChild(time);
    msg.appendChild(avatar);
    msg.appendChild(body);
    chatLog.appendChild(msg);
    chatLog.scrollTop = chatLog.scrollHeight;
    
    return content; // Return the text container so we can stream into it
  }

  // ── Typing indicator ────────────────────────────────────────────
  function showTypingIndicator() {
    if (typingIndicatorEl) return;
    const msg = document.createElement('div');
    msg.className = 'message jarvis';
    const avatar = document.createElement('div');
    avatar.className = 'message-avatar';
    avatar.textContent = 'J';
    const body = document.createElement('div');
    body.className = 'message-body';
    const indicator = document.createElement('div');
    indicator.className = 'typing-indicator';
    indicator.innerHTML = '<div class="dot"></div><div class="dot"></div><div class="dot"></div>';
    body.appendChild(indicator);
    msg.appendChild(avatar);
    msg.appendChild(body);
    chatLog.appendChild(msg);
    chatLog.scrollTop = chatLog.scrollHeight;
    typingIndicatorEl = msg;
  }

  function hideTypingIndicator() {
    if (typingIndicatorEl) {
      typingIndicatorEl.remove();
      typingIndicatorEl = null;
    }
  }

  // ══════════════════════════════════════════════════════════════
  //  Audio playback with orb reactivity
  // ══════════════════════════════════════════════════════════════
  let audioContext = null;
  let analyser = null;

  function getAudioContext() {
    if (!audioContext) {
      audioContext = new (window.AudioContext || window.webkitAudioContext)();
      analyser = audioContext.createAnalyser();
      analyser.fftSize = 256;
      analyser.connect(audioContext.destination);
    }
    if (audioContext.state === 'suspended') {
      audioContext.resume();
    }
    return { ctx: audioContext, analyser };
  }

  function monitorAudioLevel() {
    if (!analyser) return;
    const data = new Uint8Array(analyser.frequencyBinCount);
    analyser.getByteFrequencyData(data);
    let sum = 0;
    for (let i = 0; i < data.length; i++) sum += data[i];
    const avg = sum / data.length / 255;
    setAudioLevel(avg * 2.5); // Amplify for visual effect
    if (window.orbState && window.orbState.mode === 'speaking') {
      requestAnimationFrame(monitorAudioLevel);
    }
  }

  async function playAudioChunk(wavBytes) {
    return new Promise(async (resolve) => {
      try {
        const { ctx, analyser: an } = getAudioContext();
        const buffer = await ctx.decodeAudioData(wavBytes.slice(0)); 
        
        currentAudioSource = ctx.createBufferSource();
        currentAudioSource.buffer = buffer;
        currentAudioSource.connect(an);
        currentAudioSource.onended = () => {
          setAudioLevel(0);
          currentAudioSource = null;
          resolve();
        };
        currentAudioSource.start();
        monitorAudioLevel();
      } catch (e) {
        console.warn('Audio playback failed, using fallback:', e);
        const blob = new Blob([wavBytes], { type: 'audio/mpeg' });
        const url = URL.createObjectURL(blob);
        const audio = new Audio(url);
        audio.crossOrigin = 'anonymous';
        
        try {
          const { ctx, analyser: an } = getAudioContext();
          const source = ctx.createMediaElementSource(audio);
          source.connect(an);
          monitorAudioLevel();
        } catch(err) {}
        
        currentAudioSource = { stop: () => { audio.pause(); audio.currentTime = 0; } };
        audio.onended = () => { 
          URL.revokeObjectURL(url); 
          currentAudioSource = null; 
          setAudioLevel(0); 
          resolve(); 
        };
        audio.onerror = () => { 
          URL.revokeObjectURL(url); 
          currentAudioSource = null; 
          setAudioLevel(0); 
          resolve(); 
        };
        audio.play().catch(() => resolve());
      }
    });
  }

  function interruptJarvis() {
    if (currentAudioSource) {
      try { currentAudioSource.stop(); } catch(e) {}
      currentAudioSource = null;
    }
    if (currentAbortController) {
      currentAbortController.abort();
      currentAbortController = null;
    }
    if (window.speechSynthesis) window.speechSynthesis.cancel();
    
    if (isProcessing) {
      isProcessing = false;
      addMessage('jarvis', '[Interrupted]');
    }
  }

  // ══════════════════════════════════════════════════════════════
  //  Microphone recording (sends to Groq Whisper via backend)
  // ══════════════════════════════════════════════════════════════
  let micAnalyser = null;
  let micSource = null;

  function monitorMicLevel() {
    if (!micAnalyser || !isMicActive) return;
    const data = new Uint8Array(micAnalyser.frequencyBinCount);
    micAnalyser.getByteFrequencyData(data);
    let sum = 0;
    for (let i = 0; i < data.length; i++) sum += data[i];
    const avg = sum / data.length / 255;
    
    // Only animate orb with mic if we aren't thinking/speaking
    if (window.orbState && (window.orbState.mode === 'idle' || window.orbState.mode === 'listening')) {
        setAudioLevel(avg * 3);
    }

    // Continuous VAD logic
    if (avg > 0.015) {
      // User is speaking!
      if (!isSpeaking) {
        isSpeaking = true;
        
        // Barge-in: interrupt Jarvis immediately if he's talking
        if (window.orbState.mode === 'speaking' || isProcessing) {
            interruptJarvis();
        }
        
        setOrbMode('listening');
        transcriptText.textContent = 'Listening...';
        transcriptText.classList.add('active');
        
        if (!isRecording && mediaRecorder && mediaRecorder.state === 'inactive') {
            audioChunks = [];
            mediaRecorder.start();
            isRecording = true;
        }
      }
      
      // Reset silence timer because user is still speaking
      if (silenceTimer) {
        clearTimeout(silenceTimer);
        silenceTimer = null;
      }
    } else {
      // Silence detected
      if (isSpeaking && !silenceTimer) {
        // Wait 2.5 seconds of silence before assuming user is done
        silenceTimer = setTimeout(() => {
          isSpeaking = false;
          silenceTimer = null;
          if (isRecording && mediaRecorder.state === 'recording') {
            mediaRecorder.stop(); // This triggers onstop to send the audio
          }
        }, 2500);
      }
    }
    
    if (isMicActive) requestAnimationFrame(monitorMicLevel);
  }

  async function startMicContext() {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const { ctx } = getAudioContext();
      micSource = ctx.createMediaStreamSource(stream);
      micAnalyser = ctx.createAnalyser();
      micAnalyser.fftSize = 256;
      micSource.connect(micAnalyser);

      mediaRecorder = new MediaRecorder(stream, {
        mimeType: MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
          ? 'audio/webm;codecs=opus'
          : 'audio/webm'
      });
      audioChunks = [];

      mediaRecorder.ondataavailable = (e) => {
        if (e.data.size > 0) audioChunks.push(e.data);
      };

      mediaRecorder.onstop = async () => {
        isRecording = false;
        if (audioChunks.length === 0 || !isMicActive) return;
        const blob = new Blob(audioChunks, { type: 'audio/webm' });
        audioChunks = [];

        // Don't send if we were just interrupted
        if (isSpeaking) return; 

        setOrbMode('thinking');
        transcriptText.textContent = 'Transcribing...';
        transcriptText.classList.add('active');

        const formData = new FormData();
        formData.append('audio', blob, 'recording.webm');

        try {
          const resp = await fetch(`${API_BASE}/api/transcribe`, {
            method: 'POST',
            body: formData,
          });
          const data = await resp.json();
          if (data.text) {
            processCommand(data.text, true);
          } else {
            transcriptText.textContent = 'Say something or type a command...';
            setOrbMode('listening');
          }
        } catch (e) {
          transcriptText.textContent = 'Transcription failed. Check server.';
          setOrbMode('listening');
        }
      };

      isMicActive = true;
      micBtn.classList.add('active');
      setOrbMode('listening');
      monitorMicLevel();
    } catch (e) {
      console.error('Mic access denied:', e);
      transcriptText.textContent = 'Microphone access denied. Check browser permissions.';
      isMicActive = false;
      micBtn.classList.remove('active');
      setOrbMode('idle');
    }
  }

  function stopMicContext() {
    isMicActive = false;
    isSpeaking = false;
    isRecording = false;
    setAudioLevel(0);
    if (silenceTimer) clearTimeout(silenceTimer);
    if (mediaRecorder && mediaRecorder.state !== 'inactive') {
      mediaRecorder.stop();
    }
    if (micSource) {
      micSource.mediaStream.getTracks().forEach(t => t.stop());
      micSource.disconnect();
      micSource = null;
    }
    micAnalyser = null;
  }

  // ══════════════════════════════════════════════════════════════
  //  Process command (text → Groq LLM → TTS → play)
  // ══════════════════════════════════════════════════════════════
  let ttsQueue = [];
  let isPlayingAudio = false;

  async function processTTSQueue() {
    if (isPlayingAudio || ttsQueue.length === 0) return;
    isPlayingAudio = true;
    
    while (ttsQueue.length > 0) {
      const sentence = ttsQueue.shift();
      if (!sentence.trim()) continue;
      
      try {
        const ttsResp = await fetch(`${API_BASE}/api/tts`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ text: sentence }),
          signal: currentAbortController?.signal
        });
        
        if (ttsResp.ok) {
          const wavBuffer = await ttsResp.arrayBuffer();
          await playAudioChunk(wavBuffer);
        }
      } catch (e) {
        console.warn("TTS failed for sentence", e);
      }
    }
    
    isPlayingAudio = false;
    if (!isProcessing) {
      if (isMicActive) {
        setOrbMode('listening');
      } else {
        setOrbMode('idle');
        transcriptText.textContent = 'Say something or type a command...';
      }
    }
  }

  let ttsQueue = [];
  let isPlayingAudio = false;

  async function processTTSQueue() {
    if (isPlayingAudio || ttsQueue.length === 0) return;
    isPlayingAudio = true;
    
    while (ttsQueue.length > 0) {
      const sentence = ttsQueue.shift();
      if (!sentence.trim()) continue;
      
      try {
        const ttsResp = await fetch(`${API_BASE}/api/tts`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ text: sentence }),
          signal: currentAbortController?.signal
        });
        
        if (ttsResp.ok) {
          const wavBuffer = await ttsResp.arrayBuffer();
          await playAudioChunk(wavBuffer);
        }
      } catch (e) {
        console.warn("TTS failed for sentence", e);
      }
    }
    
    isPlayingAudio = false;
    if (!isProcessing) {
      if (isMicActive) {
        setOrbMode('listening');
      } else {
        setOrbMode('idle');
        transcriptText.textContent = 'Say something or type a command...';
      }
    }
  }

  async function processCommand(text, fromVoice = false) {
    const clean = text.trim();
    if (!clean || isProcessing) return;
    isProcessing = true;

    addMessage('user', clean);
    if (!fromVoice) { commandInput.value = ''; autoResize(); }

    commandHistory.push(clean);
    historyIndex = commandHistory.length;

    setOrbMode('thinking');
    transcriptText.textContent = 'Processing...';
    showTypingIndicator();
    transcriptText.classList.add('active');
    
    const msgElement = addMessage('jarvis', '');

    try {
      currentAbortController = new AbortController();
      const resp = await fetch(`${API_BASE}/api/command`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: clean }),
        signal: currentAbortController.signal
      });
      
      const reader = resp.body.getReader();
      const decoder = new TextDecoder('utf-8');
      let done = false;
      let sentenceBuffer = "";
      
      hideTypingIndicator();
      setOrbMode('speaking');

      while (!done) {
        const { value, done: readerDone } = await reader.read();
        done = readerDone;
        if (value) {
          const chunkStr = decoder.decode(value, { stream: true });
          const lines = chunkStr.split('\n');
          
          for (const line of lines) {
            if (line.startsWith('data: ')) {
              const dataStr = line.substring(6);
              if (dataStr === '[DONE]') continue;
              
              try {
                const data = JSON.parse(dataStr);
                if (data.chunk) {
                  msgElement.textContent += data.chunk;
                  transcriptText.textContent = msgElement.textContent;
                  chatLog.scrollTop = chatLog.scrollHeight;
                  
                  sentenceBuffer += data.chunk;
                  // Extremely simple sentence boundary detection
                  if (sentenceBuffer.match(/[.!?\n]\s/)) {
                    ttsQueue.push(sentenceBuffer);
                    sentenceBuffer = "";
                    processTTSQueue(); // fire and forget
                  }
                }
                if (data.done) {
                  if (data.model) metricModel.textContent = data.model;
                }
              } catch(e) {}
            }
          }
        }
      }
      
      // Push any remaining text
      if (sentenceBuffer.trim()) {
        ttsQueue.push(sentenceBuffer);
        processTTSQueue();
      }

    } catch (e) {
      if (e.name === 'AbortError') {
        console.log('Command aborted.');
      } else {
        console.error('API Error:', e);
        msgElement.textContent = 'Connection to Jarvis backend failed.';
      }
    } finally {
      isProcessing = false;
      // The final state change to idle/listening will be handled by processTTSQueue 
      // once it finishes playing the last audio chunk.
      if (!isPlayingAudio && ttsQueue.length === 0) {
        if (isMicActive) setOrbMode('listening');
        else {
          setOrbMode('idle');
          transcriptText.textContent = 'Say something or type a command...';
        }
      }
      currentAbortController = null;
    }
  }

  // ── Browser speech synthesis fallback ──────────────────────────
  function browserSpeak(text) {
    return new Promise((resolve) => {
      if (!('speechSynthesis' in window)) { resolve(); return; }
      window.speechSynthesis.cancel();
      const utterance = new SpeechSynthesisUtterance(text);
      utterance.rate = 0.95;
      utterance.onend = resolve;
      utterance.onerror = resolve;
      window.speechSynthesis.speak(utterance);

      // Simulate audio levels for orb
      const interval = setInterval(() => {
        if (!window.speechSynthesis.speaking) { clearInterval(interval); setAudioLevel(0); return; }
        setAudioLevel(0.3 + Math.random() * 0.5);
      }, 80);
    });
  }

  // ── Auto-resize textarea ───────────────────────────────────────
  function autoResize() {
    commandInput.style.height = 'auto';
    commandInput.style.height = Math.min(commandInput.scrollHeight, 120) + 'px';
  }
  commandInput.addEventListener('input', autoResize);

  // ══════════════════════════════════════════════════════════════
  //  Event listeners
  // ══════════════════════════════════════════════════════════════
  sendBtn.addEventListener('click', () => processCommand(commandInput.value));

  commandInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      processCommand(commandInput.value);
    } else if (e.key === 'ArrowUp' && commandHistory.length > 0) {
      e.preventDefault();
      if (historyIndex > 0) historyIndex--;
      commandInput.value = commandHistory[historyIndex] || '';
      autoResize();
    } else if (e.key === 'ArrowDown' && commandHistory.length > 0) {
      e.preventDefault();
      if (historyIndex < commandHistory.length - 1) {
        historyIndex++;
        commandInput.value = commandHistory[historyIndex] || '';
      } else {
        historyIndex = commandHistory.length;
        commandInput.value = '';
      }
      autoResize();
    }
  });

  // ── Global keyboard shortcuts ──────────────────────────────────
  document.addEventListener('keydown', (e) => {
    // Escape to interrupt Jarvis
    if (e.key === 'Escape') {
      interruptJarvis();
      if (isMicActive) {
        stopMicContext();
        micBtn.classList.remove('active');
        setOrbMode('idle');
        transcriptText.textContent = 'Say something or type a command...';
      }
      return;
    }
    // Space to toggle mic (only when not typing in input)
    if (e.code === 'Space' && document.activeElement !== commandInput) {
      e.preventDefault();
      micBtn.click();
    }
  });

  micBtn.addEventListener('click', () => {
    if (isMicActive) {
      stopMicContext();
      micBtn.classList.remove('active');
      setOrbMode('idle');
      transcriptText.textContent = 'Say something or type a command...';
      transcriptText.classList.remove('active');
    } else {
      startMicContext();
    }
  });

  clearBtn.addEventListener('click', () => {
    chatLog.innerHTML = '';
    addMessage('jarvis', 'Conversation cleared. Ready for new commands.');
  });

  suggestions.addEventListener('click', (e) => {
    const chip = e.target.closest('.suggestion-chip');
    if (chip) {
      commandInput.value = chip.textContent;
      commandInput.focus();
      autoResize();
    }
  });

  // ── Idle breathing ─────────────────────────────────────────────
  function idleBreathing() {
    if (window.orbState && window.orbState.mode === 'idle') {
      setAudioLevel(0.05 + Math.sin(Date.now() * 0.002) * 0.05);
    }
    requestAnimationFrame(idleBreathing);
  }
  idleBreathing();

  // ── Boot: check backend health ─────────────────────────────────
  async function boot() {
    try {
      const resp = await fetch(`${API_BASE}/api/state`);
      const data = await resp.json();

      if (data.brain?.available) {
        pillBrain.classList.add('online');
        pillBrain.innerHTML = '<span class="dot"></span> Brain Online';
        metricModel.textContent = data.brain.model || GROQ_LLM_MODEL;
      }

      const greeting = 'Systems online, sir.';
      const msgElement = addMessage('jarvis', '');
      
      setOrbMode('speaking');
      try {
        const ttsResp = await fetch(`${API_BASE}/api/tts`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ text: greeting }),
        });
        if (ttsResp.ok) {
          const wavBuffer = await ttsResp.arrayBuffer();
          isProcessing = true;
          await playAudioAndStreamText(wavBuffer, greeting, msgElement, transcriptText);
          isProcessing = false;
        } else {
          msgElement.textContent = greeting;
        }
      } catch (e) {
        msgElement.textContent = greeting;
      }
      setOrbMode('idle');
      transcriptText.textContent = 'Say something or type a command...';

    } catch (e) {
      pillBrain.innerHTML = '<span class="dot"></span> Offline';
      addMessage('jarvis', 'Backend server not detected. Start it with: uvicorn server:app --reload');
    }
  }

  // ── Initialization Overlay ───────────────────────────────────────
  const initOverlay = document.createElement('div');
  initOverlay.style.cssText = "position:fixed; inset:0; z-index:9999; background:rgba(0,0,0,0.85); display:flex; flex-direction:column; justify-content:center; align-items:center; color:var(--blue-core); font-family:var(--font-display); cursor:pointer; backdrop-filter: blur(10px); transition: opacity 0.5s;";
  initOverlay.innerHTML = '<div style="font-size:1.5rem; letter-spacing:0.2em; margin-bottom: 20px;">[ INITIALIZE SYSTEM ]</div><div style="font-size:0.7rem; color:var(--muted); font-family:var(--font-body);">Tap anywhere to begin audio context</div>';
  document.body.appendChild(initOverlay);
  
  initOverlay.addEventListener('click', () => {
    getAudioContext().ctx.resume();
    initOverlay.style.opacity = '0';
    setTimeout(() => {
       initOverlay.remove();
       boot();
    }, 500);
  });

})();
