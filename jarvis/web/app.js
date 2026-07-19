/* ══════════════════════════════════════════════════════════════════
   JARVIS AI v2.0 — Application Logic (Live Backend)
   Connects to FastAPI server for Groq LLM, Whisper STT, and TTS
   ══════════════════════════════════════════════════════════════════ */

(function () {
  const API_BASE = (window.location.protocol === 'file:' || window.location.origin === 'null') 
    ? 'http://127.0.0.1:8000' 
    : window.location.origin;

  const GROQ_LLM_MODEL = 'llama-3.3-70b-versatile';

  // ── DOM refs ───────────────────────────────────────────────────
  const chatLog        = document.getElementById('chatLog');
  const commandInput   = document.getElementById('commandInput');
  const sendBtn        = document.getElementById('sendBtn');
  const stopBtn        = document.getElementById('stopBtn');
  const micBtn         = document.getElementById('micBtn');
  const clearBtn = document.getElementById('clearBtn');
  const transcriptText = document.getElementById('transcriptText');

  let currentMsgElement = null;
  let sentenceBuffer = "";

  // WebSocket Connection for Proactive and Reactive Streaming
  let ws = null;
  
  function connectWebSocket() {
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    ws = new WebSocket(`${wsProtocol}//${window.location.host}/api/ws`);
    
    ws.onopen = () => {
      console.log('WebSocket connected to Jarvis Core.');
    };
    
    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        
        // Iteration 58: Swarm WebSockets
        if (data.type === 'swarm') {
            const swarmList = document.getElementById('swarmList');
            if (swarmList) swarmList.innerHTML = `[${data.agent}] ${data.status}`;
            showToast(`Swarm Agent ${data.agent}: ${data.status}`);
        }
        
        // Iteration 63: Sentiment Color Mapping
        if (data.type === 'transcript' || data.type === 'chunk') {
            if (data.sentiment === 'positive') {
                document.documentElement.style.setProperty('--orb-hue', '120deg'); // Green
            } else if (data.sentiment === 'negative') {
                document.documentElement.style.setProperty('--orb-hue', '0deg'); // Red
            }
        }

        if (data.type === 'proactive') {
          showToast(data.text);

        // Iteration 86: Voice Auth UI
        if (data.type === 'proactive' && data.text.includes("Voice verified")) {
            const auth = document.getElementById('authStatus');
            if(auth) { auth.innerText = 'VERIFIED'; auth.style.color = '#0f0'; }
        }

          // Handle a spontaneous message from Jarvis
          addMessage('jarvis', data.text);
          if (data.audio) {
            // If backend generates TTS and sends base64 audio
            const byteCharacters = atob(data.audio);
            const byteNumbers = new Array(byteCharacters.length);
            for (let i = 0; i < byteCharacters.length; i++) {
                byteNumbers[i] = byteCharacters.charCodeAt(i);
            }
            const byteArray = new Uint8Array(byteNumbers);
            playAudioChunk(byteArray.buffer);
          } else {
            // fallback to client-side fetching TTS
            ttsQueue.push(data.text);
            processTTSQueue();
          }
          setOrbMode('speaking');
        } else if (data.type === 'transcript') {
          // Handle the completed transcript from the audio stream
          if (data.text) {
            updateLiveTranscript(data.text);
            if (data.is_final) {
              setOrbMode('processing');
              isProcessing = true;
            }
          }
        } else if (data.type === 'system_stats_update') {
          if (hudCpu) hudCpu.textContent = `CPU: ${data.cpu}%`;
          if (hudRam) hudRam.textContent = `RAM: ${data.ram}%`;
        } else if (data.type === 'chunk') {
          // Handle streaming chunk from a command
          if (currentMsgElement) {
            currentMsgElement.textContent += data.chunk;
            transcriptText.textContent = currentMsgElement.textContent;
            chatLog.scrollTop = chatLog.scrollHeight;
            
            sentenceBuffer += data.chunk;
            if (sentenceBuffer.match(/[.!?\n]\s/)) {
              ttsQueue.push(sentenceBuffer);
              sentenceBuffer = "";
              processTTSQueue();
            }
          }
        } else if (data.type === 'done') {
          if (data.model) metricModel.textContent = data.model;
          if (sentenceBuffer.trim()) {
            ttsQueue.push(sentenceBuffer);
            processTTSQueue();
          }
          isProcessing = false;
        } else if (data.type === 'wakeup') {
          // Triggered by global hotkey
          if (!isRecording) {
            micBtn.click();
          }
        }
      } catch(e) {
        console.error('WS parse error:', e);
      }
    };
    
    ws.onclose = () => {
      console.log('WebSocket disconnected. Reconnecting in 5s...');
      setTimeout(connectWebSocket, 5000);
    };
  }
  
  // Initialize WS
  connectWebSocket();

  // ══════════════════════════════════════════════════════════════
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
    ttsQueue = []; // Clear pending TTS sentences
    
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
            // Start recording with a timeslice of 250ms to stream chunks
            mediaRecorder.start(250);
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

      
      // Iteration 11: True Audio Visualizer
      analyser = audioContext.createAnalyser();
      analyser.fftSize = 256;
      source.connect(analyser);
      
      const bufferLength = analyser.frequencyBinCount;
      const dataArray = new Uint8Array(bufferLength);
      
      function drawVisualizer() {
          if (!isRecording) return;
          analyser.getByteFrequencyData(dataArray);
          let sum = 0;
          for (let i = 0; i < bufferLength; i++) {
              sum += dataArray[i];
          }
          let avg = sum / bufferLength;
          let scale = 1 + (avg / 256) * 0.5;
          let glow = 20 + (avg / 256) * 40;
          document.documentElement.style.setProperty('--orb-scale', scale);
          document.documentElement.style.setProperty('--orb-glow', glow + 'px');
          // Iteration 34: Chromatic Audio Reactivity
          let hue = 180 + (avg / 256) * 60;
          document.documentElement.style.setProperty('--orb-hue', hue + 'deg');

        // Iteration 87: 3D Audio Spectrum EQ Ring Mock
        let eqSize = 50 + (avg / 256) * 100;
        document.documentElement.style.setProperty('--orb-glow', `${glow}px ${glow}px ${eqSize}px rgba(0,255,255,0.5)`);

          document.querySelector('.orb').style.filter = `hue-rotate(${hue}deg)`;
          requestAnimationFrame(drawVisualizer);
      }
      drawVisualizer();

      mediaRecorder = new MediaRecorder(stream, {
        mimeType: MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
          ? 'audio/webm;codecs=opus'
          : 'audio/webm'
      });
      audioChunks = [];

      mediaRecorder.ondataavailable = async (e) => {
        if (e.data.size > 0) {
          audioChunks.push(e.data);
        }
      };

      mediaRecorder.onstop = async () => {
        isRecording = false;
        if (audioChunks.length === 0) return;
        
        const audioBlob = new Blob(audioChunks, { type: mediaRecorder.mimeType || 'audio/webm' });
        audioChunks = [];

        isSpeaking = false;
        
        if (audioBlob.size < 4000) {
            console.log("Audio blob too small, ignoring to prevent Groq API error.");
            setOrbMode('idle');
            transcriptText.textContent = 'Say something or type a command...';
            transcriptText.classList.remove('active');
            return;
        }

        setOrbMode('thinking');
        transcriptText.textContent = 'Transcribing stream...';
        transcriptText.classList.add('active');

        // Notify backend that stream is complete
        if (ws && ws.readyState === WebSocket.OPEN) {
            const arrayBuffer = await audioBlob.arrayBuffer();
            ws.send(arrayBuffer);
            ws.send(JSON.stringify({ type: "stream_end" }));
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
    if (stopBtn) stopBtn.style.display = 'inline-flex';
    
    while (ttsQueue.length > 0) {
      const sentence = ttsQueue.shift();
      if (!sentence.trim()) continue;
      
      try {
        const ttsResp = await fetch(`${API_BASE}/api/tts`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ text: sentence, provider: prefs.voice }),
          signal: currentAbortController?.signal
        });
        
        if (ttsResp.ok) {
          const wavBuffer = await ttsResp.arrayBuffer();
          await playAudioChunk(wavBuffer);
        }
      } catch (e) {
        console.error('Error in TTS queue processing:', e);
      }
    }
    
    isPlayingAudio = false;
    if (stopBtn) stopBtn.style.display = 'none';
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
    
    currentMsgElement = addMessage('jarvis', '');

    try {
      currentAbortController = new AbortController();
      const currentPrefs = JSON.parse(localStorage.getItem('jarvis_prefs') || '{"model": "llama-3.3-70b-versatile", "voice": "sapi5"}');
      const resp = await fetch(`${API_BASE}/api/command`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          text: clean,
          model: currentPrefs.model,
          voice: currentPrefs.voice
        }),
        signal: currentAbortController.signal
      });
      
      const reader = resp.body.getReader();
      const decoder = new TextDecoder('utf-8');
      let done = false;
      sentenceBuffer = "";
      
      hideTypingIndicator();
      setOrbMode('speaking');

      let fullMessage = "";
      let inCodeBlock = false;
      let codeBuffer = "";
      
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
                  fullMessage += data.chunk;
                  
                  // Render markdown
                  if (window.marked && window.hljs) {
                      marked.setOptions({
                          highlight: function(code, lang) {
                              const language = hljs.getLanguage(lang) ? lang : 'plaintext';
                              return hljs.highlight(code, { language }).value;
                          }
                      });
                      currentMsgElement.innerHTML = marked.parse(fullMessage);
                  } else {
                      currentMsgElement.textContent = fullMessage;
                  }
                  
                  transcriptText.textContent = fullMessage.replace(/<[^>]*>?/gm, ''); // stripped HTML for transcript
                  chatLog.scrollTop = chatLog.scrollHeight;
                  
                  // Code block detection for TTS filtering
                  const tickCount = (data.chunk.match(/```/g) || []).length;
                  if (tickCount % 2 !== 0) {
                      inCodeBlock = !inCodeBlock;
                  }
                  
                  if (!inCodeBlock && !data.chunk.includes('```')) {
                      sentenceBuffer += data.chunk;
                      // Extremely simple sentence boundary detection
                      if (sentenceBuffer.match(/[.!?\n]\s/)) {
                        ttsQueue.push(sentenceBuffer);
                        sentenceBuffer = "";
                        processTTSQueue(); // fire and forget
                      }
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
      if (sentenceBuffer.trim() && !inCodeBlock) {
        ttsQueue.push(sentenceBuffer);
        processTTSQueue();
      }

    } catch (e) {
      if (e.name === 'AbortError') {
        console.log('Command aborted.');
      } else {
        console.error('API Error:', e);
        if (currentMsgElement) currentMsgElement.textContent = 'Connection to Jarvis backend failed.';
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
  // ══════════════════════════════════════════════════════════════  // Bind manual send button
  sendBtn.addEventListener('click', () => processCommand(commandInput.value));
  
  if (stopBtn) {
      stopBtn.addEventListener('click', () => {
          stopAudio();
          ttsQueue = [];
          isPlayingAudio = false;
          stopBtn.style.display = 'none';
          appendMessage('JARVIS', 'Playback interrupted by user.');
          if (!isProcessing) {
              setOrbMode(isMicActive ? 'listening' : 'standby');
          }
      });
  }

  // Handle enter key in input
  commandInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      processCommand(commandInput.value);
    }
  });

  // ══════════════════════════════════════════════════════════════
  //  HUD & Ticker Logic
  // ══════════════════════════════════════════════════════════════
  const hudCpu = document.getElementById('hudCpu');
  const hudRam = document.getElementById('hudRam');
  const tickerText = document.getElementById('tickerText');
  
  const hints = [
      "Tip: Say 'Identify my displays' to manage monitors.",
      "Tip: Say 'Toggle WiFi off' to disable internet.",
      "Tip: Say 'Read my emails' to check your inbox.",
      "Tip: Say 'Add task: buy groceries' to manage your todo list.",
      "Tip: Try interrupting me while I'm speaking.",
      "System: Jarvis MK II operational.",
      "Network: Secure connection established.",
  ];
  let hintIndex = 0;
  setInterval(() => {
      tickerText.textContent = hints[hintIndex];
      hintIndex = (hintIndex + 1) % hints.length;
  }, 10000); // cycle every 10 seconds

  // Request system stats every 5 seconds
  setInterval(() => {
      if (ws && ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ type: 'get_system_stats' }));
      }
  }, 5000);

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
          body: JSON.stringify({ text: greeting, provider: prefs.voice }),
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

  // ── Settings Modal Logic ───────────────────────────────────────
  const settingsModal = document.getElementById('settingsModal');
  const settingsBtn = document.getElementById('settingsBtn');
  const closeSettingsBtn = document.getElementById('closeSettingsBtn');
  const saveSettingsBtn = document.getElementById('saveSettingsBtn');
  const modelSelect = document.getElementById('modelSelect');
  const voiceSelect = document.getElementById('voiceSelect');
  const themeSelect = document.getElementById('themeSelect');

  // Load preferences
  const prefs = JSON.parse(localStorage.getItem('jarvis_prefs') || '{"model": "llama-3.3-70b-versatile", "voice": "sapi5", "theme": "iron-man"}');
  modelSelect.value = prefs.model || 'llama-3.3-70b-versatile';
  voiceSelect.value = prefs.voice || 'sapi5';
  themeSelect.value = prefs.theme || 'iron-man';
  applyTheme(themeSelect.value);

  settingsBtn.addEventListener('click', () => settingsModal.classList.add('active'));
  closeSettingsBtn.addEventListener('click', () => settingsModal.classList.remove('active'));
  
  
  // Iteration 14: Wake Word Toggle
  const wakeWordToggle = document.getElementById('wakeWordToggle');
  if (wakeWordToggle) {
    wakeWordToggle.checked = localStorage.getItem('jarvis_wakeword') === 'true';
    wakeWordToggle.addEventListener('change', (e) => {
        localStorage.setItem('jarvis_wakeword', e.target.checked);
        if (e.target.checked && !isRecording) {
            startRecording();
        } else if (!e.target.checked && isRecording) {
            stopRecording();
        }
    });
  }

  saveSettingsBtn.addEventListener('click', () => {
    prefs.model = modelSelect.value;
    prefs.voice = voiceSelect.value;
    prefs.theme = themeSelect.value;
    localStorage.setItem('jarvis_prefs', JSON.stringify(prefs));
    applyTheme(prefs.theme);
    metricModel.textContent = modelSelect.options[modelSelect.selectedIndex].text;
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'update_settings', settings: prefs }));
    }
    settingsModal.classList.remove('active');
  });

  function applyTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
  }

  // ── History Sidebar Logic ──────────────────────────────────────
  const historyBtn = document.getElementById('historyBtn');
  const closeHistoryBtn = document.getElementById('closeHistoryBtn');
  const historySidebar = document.getElementById('historyModal');
  const historyList = document.getElementById('historyList');

  if (historyBtn) {
    historyBtn.addEventListener('click', () => {
      historyModal.classList.add('active');
      loadHistory();
    });
  }
  if (closeHistoryBtn) {
    closeHistoryBtn.addEventListener('click', () => historyModal.classList.remove('active'));
  }

  async function loadHistory() {
    historyList.innerHTML = '<div style="color:var(--muted); font-size:0.8rem; text-align:center;">Loading...</div>';
    try {
      const resp = await fetch(`${API_BASE}/api/history`);
      if (resp.ok) {
        const sessions = await resp.json();
        if (sessions.length === 0) {
          historyList.innerHTML = '<div style="color:var(--muted); font-size:0.8rem; text-align:center;">No past sessions found.</div>';
          return;
        }
        historyList.innerHTML = '';
        sessions.forEach(session => {
          const item = document.createElement('div');
          item.className = 'history-item';
          item.innerHTML = `<div class="history-item-date">${session.date}</div><div>${session.preview}</div>`;
          item.addEventListener('click', () => {
            loadSession(session.id);
            historyModal.classList.remove('active');
          });
          historyList.appendChild(item);
        });
      }
    } catch(e) {
      historyList.innerHTML = '<div style="color:var(--muted); font-size:0.8rem; text-align:center;">Failed to load history.</div>';
    }
  }

  async function loadSession(id) {
    // Minimal impl: restore a saved session transcript from localStorage if present.
    try {
      const sessions = JSON.parse(localStorage.getItem('jarvis_sessions') || '{}');
      const session = sessions[id];
      chatLog.innerHTML = '';
      if (session && Array.isArray(session.messages)) {
        session.messages.forEach((m) => {
          if (m && m.role && typeof m.content === 'string') {
            addMessage(m.role === 'user' ? 'user' : 'jarvis', m.content);
          }
        });
      } else {
        addMessage('jarvis', `Loaded session ${id}.`);
      }
    } catch (e) {
      chatLog.innerHTML = '';
      addMessage('jarvis', `Loaded session ${id}.`);
    }
  }

  // ── Play greeting audio and stream the text into the message element ──
  async function playAudioAndStreamText(wavBuffer, text, msgElement, transcriptEl) {
    try {
      if (msgElement) msgElement.textContent = text;
      if (transcriptEl) {
        transcriptEl.textContent = text;
        transcriptEl.classList.add('active');
      }
      await playAudioChunk(wavBuffer);
    } catch (e) {
      console.warn('playAudioAndStreamText failed:', e);
      if (msgElement) msgElement.textContent = text || '';
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


// Iteration 33: Toast Notification System
function showToast(message) {
    const container = document.getElementById('toastContainer');
    if (!container) return;
    const toast = document.createElement('div');
    toast.className = 'toast';
    toast.textContent = message;
    container.appendChild(toast);
    setTimeout(() => {
        toast.style.opacity = '0';
        setTimeout(() => toast.remove(), 300);
    }, 5000);
}


// Iteration 64: Hacker Terminal Overlay
const terminalOverlay = document.getElementById('terminalOverlay');
const terminalInput = document.getElementById('terminalInput');
const terminalOutput = document.getElementById('terminalOutput');

document.addEventListener('keydown', (e) => {
    if (e.key === '`') {
        terminalOverlay.style.display = terminalOverlay.style.display === 'none' ? 'block' : 'none';
        if (terminalOverlay.style.display === 'block') {
            setTimeout(() => terminalInput.focus(), 50);
        }
    }
    if (e.key === 'Escape' && terminalOverlay.style.display === 'block') {
        terminalOverlay.style.display = 'none';
    }
});

if (terminalInput) {
    terminalInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            const val = terminalInput.value;
            terminalInput.value = '';
            terminalOutput.innerHTML += `\nadmin@jarvis:~$ ${val}\n> command executed in background.\n`;
        }
    });
}
