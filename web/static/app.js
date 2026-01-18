let currentMode = 'spawn';
let activeSessions = []; // list of serials
let codeShares = [];
let profiles = {};
let ws = null;
let allApps = []; // For filtering
let allProcs = []; // For filtering

// Infinite Scroll State
let currentRenderList = [];
let renderOffset = 0;
const BATCH_SIZE = 50;

let cmEditor = null;

const defaultScript = `// ag-frida Simple Test Script
// ใช้ทดสอบว่า Frida ทำงานหรือไม่

Java.perform(function() {
    console.log("[*] Script Loaded successfully!");
    console.log("[*] Frida is working. Ready to hook!");
});
`;

window.addEventListener('load', () => {
    loadDevices();
    loadProfiles();
    connectWS();
    pollStatus();
    loadAIConfig();
    
    // Initialize CodeMirror
    if (typeof CodeMirror !== 'undefined') {
        const ta = document.getElementById('script-manual');
        if (ta) {
            cmEditor = CodeMirror.fromTextArea(ta, {
                mode: "javascript",
                theme: "dracula",
                lineNumbers: true,
                smartIndent: true,
                matchBrackets: true,
                lineWrapping: true
            });
            cmEditor.setSize("100%", "300px"); // Initial height
            
            // Auto-Save Logic
            // ARCHITECT-ZERO: Bumped version to v3 to force load bulletproof script
            const saved = localStorage.getItem('ag_saved_script_v3');
            if (saved) {
                cmEditor.setValue(saved);
            } else {
                 // Force new bulletproof default
                 cmEditor.setValue(defaultScript);
            }

            cmEditor.on('change', () => {
                localStorage.setItem('ag_saved_script_v3', cmEditor.getValue());
            });
        }
    }
    
    // Dismiss Preloader
    setTimeout(() => {
        const p = document.getElementById('preloader');
        if(p) {
            p.style.opacity = '0';
            setTimeout(() => p.remove(), 500);
        }
    }, 800); // Smooth Entry

    initEditorResizer();
});

// --- Panel Management (Drag & Collapse) ---
function togglePanel(id) {
    const el = document.getElementById(id);
    if (!el) return;
    const content = el.querySelector('.panel-content');
    if (content) {
        content.classList.toggle('hidden');
        // Save state
        const state = JSON.parse(localStorage.getItem('ag_panel_states') || '{}');
        state[id] = content.classList.contains('hidden');
        localStorage.setItem('ag_panel_states', JSON.stringify(state));
    }
}

// --- Layout Resizer ---
function initEditorResizer() {
    // Editor Resizer (Height)
    const handleH = document.getElementById('editor-resizer');
    // We resize CodeMirror via its API, not CSS height directly usually
    
    if (handleH && cmEditor) {
        // Restore height
        const savedHeight = localStorage.getItem('ag_editor_height');
        if (savedHeight) cmEditor.setSize("100%", savedHeight);
        
        let isResizingH = false;
        let startY = 0;
        let startHeight = 0;

        handleH.addEventListener('mousedown', (e) => {
            isResizingH = true;
            handleH.classList.add('dragging');
            document.body.style.cursor = 'row-resize';
            document.body.classList.add('select-none');
            
            startY = e.clientY;
            // Get current CM height
            const wrapper = cmEditor.getWrapperElement();
            startHeight = wrapper.offsetHeight;
        });

        document.addEventListener('mousemove', (e) => {
            if (!isResizingH) return;
            const delta = e.clientY - startY;
            const newHeight = startHeight + delta;
            if (newHeight < 100 || newHeight > window.innerHeight - 200) return;
            
            cmEditor.setSize("100%", `${newHeight}px`);
        });

        document.addEventListener('mouseup', () => {
            if (isResizingH) {
                isResizingH = false;
                handleH.classList.remove('dragging');
                document.body.style.cursor = '';
                document.body.classList.remove('select-none');
                
               const wrapper = cmEditor.getWrapperElement();
               localStorage.setItem('ag_editor_height', `${wrapper.offsetHeight}px`);
               cmEditor.refresh();
            }
        });
    }
}

// --- Utils ---
async function debounceAction(btnId, asyncFn) {
    const btn = document.getElementById(btnId);
    if (!btn) {
        await asyncFn();
        return;
    }
    
    if (btn.disabled) return; // Prevent double click

    const ogText = btn.innerHTML;
    const ogClass = btn.className;
    
    btn.disabled = true;
    btn.innerHTML = '<span class="animate-pulse">⏳ Processing...</span>';
    
    try {
        await asyncFn();
    } catch (e) {
        showToast(`Action Failed: ${e}`, 'error');
    } finally {
        setTimeout(() => {
            btn.disabled = false;
            btn.innerHTML = ogText;
        }, 500); // Small delay to prevent rapid-fire
    }
}

function showToast(msg, type = 'info') {
    const c = document.getElementById('toast-container');
    const t = document.createElement('div');
    const colors = {
        'success': 'border-emerald-500/50 bg-emerald-900/80 text-white shadow-emerald-900/40',
        'error': 'border-red-500/50 bg-red-900/80 text-white shadow-red-900/40',
        'info': 'border-blue-500/50 bg-blue-900/80 text-white shadow-blue-900/40',
        'warning': 'border-orange-500/50 bg-orange-900/80 text-white shadow-orange-900/40'
    }[type] || 'border-gray-500/50 bg-gray-900/80 text-white';

    t.className = `toast px-4 py-3 rounded-xl border backdrop-blur-md shadow-lg text-xs font-medium min-w-[250px] flex items-center gap-3 ${colors}`;
    t.innerHTML = `<span>${type === 'success' ? '✅' : type === 'error' ? '❌' : type === 'warning' ? '⚠️' : 'ℹ️'}</span> ${msg}`;
    c.appendChild(t);
    setTimeout(() => {
        t.classList.add('hiding');
        t.addEventListener('animationend', () => t.remove());
    }, 3000);
}

function setMode(m) {
    currentMode = m;
    const btnSpawn = document.getElementById('btn-spawn');
    const btnAttach = document.getElementById('btn-attach');
    
    if (m === 'spawn') {
        btnSpawn.className = "flex-1 py-1 text-xs rounded bg-indigo-900/30 text-indigo-400 transition font-medium border border-indigo-900/50";
        btnAttach.className = "flex-1 py-1 text-xs rounded text-gray-500 hover:text-white transition font-medium border border-transparent";
    } else {
        btnSpawn.className = "flex-1 py-1 text-xs rounded text-gray-500 hover:text-white transition font-medium border border-transparent";
        btnAttach.className = "flex-1 py-1 text-xs rounded bg-indigo-900/30 text-indigo-400 transition font-medium border border-indigo-900/50";
    }
}

function clearConsole() {
    document.getElementById('console-output').innerHTML = '';
}

// --- Multi-Device Logic ---
async function loadDevices() {
    const s = document.getElementById('device-select');
    const countEl = document.getElementById('device-count-badge'); // New Element
    s.innerHTML = '<option>Scanning...</option>';
    try {
        const r = await fetch('/api/devices');
        const d = await r.json();
        s.innerHTML = '';
        if (d.devices && d.devices.length > 0) {
            d.devices.forEach(x => {
                const o = document.createElement('option');
                o.value = x[0];
                o.text = `${x[0]} (${x[1]})`;
                s.appendChild(o)
            });
             if (countEl) countEl.innerText = `${d.devices.length} Devices`;
            checkServerStatus(d.devices[0][0]); // Immediate check for first device
        } else {
             s.innerHTML = '<option value="">No Devices Found</option>';
             if (countEl) countEl.innerText = `0 Devices`;
        }
        updateUIState();
    } catch (e) { s.innerHTML = '<option>Error</option>' }
}

async function pollStatus() {
    try {
        const res = await fetch('/api/status');
        const data = await res.json();
        activeSessions = data.running_sessions || [];
        updateUIState();
    } catch (e) { }
    setTimeout(pollStatus, 1000);
}

function updateUIState() {
    const currentObj = document.getElementById('device-select');
    const serial = currentObj ? currentObj.value : null;
    const btn = document.getElementById('main-action');
    const msg = document.getElementById('active-status-msg');
    const count = document.getElementById('active-count');

    if (count) count.innerText = `${activeSessions.length} Sessions`;

    if (!btn) return;

    if (serial && activeSessions.includes(serial)) {
        btn.innerText = "STOP SESSION";
        btn.className = "w-full py-3 rounded-lg font-bold text-sm bg-gradient-to-r from-red-600 to-red-800 text-white hover:from-red-500 hover:to-red-700 transition shadow-lg shadow-red-900/20";
        btn.onclick = () => debounceAction('main-action', toggleSession); // Ensure debounce on stop too
        if (msg) msg.classList.remove('hidden');
    } else if (serial && !isServerRunning) {
        // SERVER STOPPED STATE
        // We change the main button to a "Start Server" CTA to guide the flow.
        btn.innerText = "⛔ SERVER STOPPED (Click to Start)";
        btn.className = "w-full py-3 rounded-lg font-bold text-sm bg-red-900/50 text-red-200 border border-red-700/50 hover:bg-red-900 transition mb-2 shadow-lg shadow-red-900/10";
        btn.onclick = () => manageServer('start'); // Redirect to Server Start
        if (msg) msg.classList.add('hidden');
    } else {
        // SERVER RUNNING -> READY TO SESSION
        btn.innerText = "START SESSION (" + (serial ? serial.substring(0, 8) + "..." : "None") + ")";
        btn.className = "w-full py-3 rounded-lg font-bold text-sm bg-gradient-to-r from-blue-600 to-indigo-600 text-white shadow-lg shadow-indigo-900/30 hover:shadow-indigo-900/50 transition active:scale-95 duration-150";
        btn.onclick = () => debounceAction('main-action', toggleSession);
        if (msg) msg.classList.add('hidden');
    }
}

async function toggleSession() {
    const serial = document.getElementById('device-select').value;
    if (!serial) {
        showToast("Select device first!", 'error');
        return;
    }

    if (activeSessions.includes(serial)) {
        await fetch(`/api/session/stop?serial=${serial}`, { method: 'POST' });
        showToast("Session Stopped", 'info');
    } else {
        const payload = {
            serial: serial,
            target: document.getElementById('target-input').value,
            mode: currentMode,
            mode: currentMode,
            scripts: [cmEditor ? cmEditor.getValue() : document.getElementById('script-manual').value].filter(x => x),
            codeshare: codeShares,
            auto_restart: document.getElementById('auto-restart-toggle')?.checked ?? true
        };
        if (!payload.target) {
             showToast("Enter target!", 'error');
             return;
        }

        const res = await fetch('/api/session/start', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const j = await res.json();
        if (j.status !== 'ok') throw j.message || 'Failed';
        showToast("Session Started", 'success');
    }
}

// --- Profiles ---
async function loadProfiles() {
    try {
        const res = await fetch('/api/profiles');
        const data = await res.json();
        profiles = data.profiles || {};

        const s = document.getElementById('profile-select');
        if (s) {
            s.innerHTML = '<option value="">Load Profile...</option>';
            Object.keys(profiles).forEach(k => {
                const opt = document.createElement('option');
                opt.value = k; opt.text = k;
                s.appendChild(opt);
            });
        }
    } catch (e) { }
}

function loadProfile() {
    const name = document.getElementById('profile-select').value;
    if (!name || !profiles[name]) return;
    const p = profiles[name];
    if (p.target) document.getElementById('target-input').value = p.target;
    if (p.script) {
        if (cmEditor) cmEditor.setValue(p.script);
        else document.getElementById('script-manual').value = p.script;
    }
    if (p.mode) setMode(p.mode);
}

// --- AI Utils ---
const AI_ROLES = {
    "security_bypass": { icon: "🔓", system: "You are an expert at bypassing Android SSL Pinning and Root Detection." },
    "security_analysis": { icon: "🛡️", system: "You are a Security Auditor. Analyze this code for vulnerabilities." },
    "decryption_analysis": { icon: "🔓", system: "You are a Cryptography Expert. Focus on finding AES/RSA keys and IVs." },
    "reverse_engineering_analysis": { icon: "🧩", system: "You represent a Reverse Engineer explaining obfuscated logic." },
    "tools": { icon: "🛠️", system: "You are a Frida/Objection Tool Expert. Suggest scripts." },
    "conversion": { icon: "🔄", system: "Convert this Java/Smali code to a Frida TypeScript hook." }
};

function updateSubRoles() {
    // Logic for sub roles if implemented
}

// --- AI Logic (Persistence) ---

let globalAIConfig = {
    active_provider: 'openai',
    providers: {}
};

async function loadAIConfig() {
    try {
        const res = await fetch('/api/ai/config');
        const data = await res.json();
        
        if (data.error) throw data.error;

        // Populate Global State
        globalAIConfig.active_provider = data.active_provider || 'openai';
        globalAIConfig.providers = data.providers || {};
        
        // Initialize UI
        const provSelect = document.getElementById('ai-provider');
        if (provSelect) {
            provSelect.value = globalAIConfig.active_provider;
            updateAIForm(globalAIConfig.active_provider);
        }

    } catch (e) {
        console.warn("AI Config Load Failed:", e);
        // Fallback to local storage if API fails
         const conf = JSON.parse(localStorage.getItem('ag_ai_config') || '{}');
         if(conf.provider) globalAIConfig.active_provider = conf.provider;
    }
}

function checkProvider() {
    // Called when dropdown changes
    const prov = document.getElementById('ai-provider').value;
    updateAIForm(prov);
}

function updateAIForm(providerKey) {
    // 1. Get cached config for this provider
    const conf = globalAIConfig.providers[providerKey] || {};
    
    // 2. Populate Fields (Smart Defaults)
    const defaults = {
        'openai': { model: 'gpt-4o', base: '' },
        'anthropic': { model: 'claude-3-5-sonnet-20240620', base: '' },
        'gemini': { model: 'gemini-1.5-pro', base: '' },
        'ollama': { model: 'llama3:latest', base: 'http://localhost:11434' },
        'xai': { model: 'grok-beta', base: 'https://api.x.ai/v1' },
        'deepseek': { model: 'deepseek-coder', base: 'https://api.deepseek.com' }
    };

    const def = defaults[providerKey] || { model: '', base: '' };

    document.getElementById('ai-model').value = conf.model || def.model;
    document.getElementById('ai-key').value = conf.api_key || ''; // Will be masked ******* from API
    document.getElementById('ai-base').value = conf.api_base || conf.base_url || def.base;
    
    // Visual Feedback
    document.getElementById('ai-key').placeholder = conf.api_key ? "******** (Saved)" : "sk-...";
}

async function saveAI() {
    const prov = document.getElementById('ai-provider').value;
    const model = document.getElementById('ai-model').value;
    let key = document.getElementById('ai-key').value;
    const base = document.getElementById('ai-base').value;

    // Check if key is masked (********) - if so, DO NOT send it to overwrite!
    // Or API should handle ignoring it. But cleaner if we don't send valid key if unchanged?
    // Actually, simple logic: If user typed new key, it won't start with **** usually.
    // But verify.
    
    const payload = {
        active_provider: prov,
        provider_config: {
            model: model,
            // key note: core/config.py should Handle saving.
            // frontend sends what it has.
            api_key: key.startsWith('****') ? undefined : key, // Don't send mask
            base_url: base
        }
    };
    
    // Clean up undefined
    if (!payload.provider_config.api_key) delete payload.provider_config.api_key;
    
    // Update Local State immediately for UI responsiveness
    if (!globalAIConfig.providers[prov]) globalAIConfig.providers[prov] = {};
    globalAIConfig.providers[prov].model = model;
    globalAIConfig.providers[prov].base_url = base;
    if (payload.provider_config.api_key) globalAIConfig.providers[prov].api_key = payload.provider_config.api_key;
    globalAIConfig.active_provider = prov;

    try {
        const res = await fetch('/api/ai/config', {
            method: 'POST', 
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const d = await res.json();
        if (d.status === 'saved') {
             showToast(`AI Config (${prov}) Saved!`, 'success');
             toggleAIConfig();
             // Reload to get properly masked keys back if needed, or trust local state
             loadAIConfig(); 
        } else {
            throw d.message;
        }
    } catch(e) {
        showToast("Save Failed: " + e, 'error');
    }
}

async function testAI() {
    // Basic test
    showToast("Testing connection...", 'info');
    // Implement actual test call if needed
    setTimeout(() => showToast("Test Simulated: OK", 'success'), 1000);
}

// Exposed wrapper for the button
function triggerGenerateHook() {
    debounceAction('btn-generate-ai', generateHook);
}

async function generateHook() {
    const prompt = document.getElementById('ai-prompt').value;
    const serial = document.getElementById('device-select').value;
    const roleCat = document.getElementById('ai-role-category').value;
    const roleDef = AI_ROLES[roleCat] || AI_ROLES['tools'];

    if (!prompt) {
        showToast("Enter a prompt!", 'warning');
        return;
    }

    const fullPrompt = `[ROLE: ${roleDef.system}]\n${prompt}`;
    
    // Config from local storage
    const conf = JSON.parse(localStorage.getItem('ag_ai_config') || '{}');
    if (!conf.key) {
        showToast("Configure AI Key first!", 'error');
        toggleAIConfig();
        return;
    }

    // Call API (Proxied or Direct)
    // Here we use our backend proxy to keep keys safe or manage providers
    const res = await fetch('/api/ai/generate', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            prompt: fullPrompt,
            device_serial: serial,
            provider_config: conf
        })
    });
    
    const data = await res.json();
    if (data.status !== 'ok') throw data.message;
    
    if (data.status !== 'ok') throw data.message;
    
    if (cmEditor) cmEditor.setValue(data.script);
    else document.getElementById('script-manual').value = data.script;
    showToast("Script Generated!", 'success');
}

function resetScript() {
    const defaultScript = `// ag-frida Default Starter Script
// Use this to test connectivity and basic hooking.

if (typeof Java !== 'undefined') {
    Java.perform(function() {
        console.log("[*] Script Loaded successfully!");

        // 1. Diagnostics: Print System Info
        const Build = Java.use("android.os.Build");
        console.log("[i] Device: " + Build.MANUFACTURER.value + " " + Build.MODEL.value);
        console.log("[i] Android: " + Build.VERSION.RELEASE.value);

        // 2. Example: Hook all Activity onCreates to see what opens
        const Activity = Java.use("android.app.Activity");
        Activity.onCreate.overload("android.os.Bundle").implementation = function(bundle) {
            console.log("[+] Activity Started: " + this.getClass().getName());
            this.onCreate(bundle);
        };

        // 3. Simple SSL Unpinning Stub (Just a test, use AI for full wipe)
        try {
            const TrustManagerImpl = Java.use('com.android.org.conscrypt.TrustManagerImpl');
            TrustManagerImpl.checkTrustedRecursive.implementation = function(a, b, c, d, e, f) {
                // console.log("[!] Bypassing TrustManagerImpl (SSL)");
                return new java.util.ArrayList();
            };
        } catch(e) { /* Ignore if class not found */ }
    });
} else {
    console.log("[!] Warning: Java runtime not available (Native-only process?)");
}
`;
    if (cmEditor) cmEditor.setValue(defaultScript);
    else document.getElementById('script-manual').value = defaultScript;
    // Don't auto-save default overwrite immediately unless user edits
}

function addCodeShare() {
    const slug = document.getElementById('codeshare-input').value;
    if (slug) {
        codeShares.push(slug);
        renderTags();
        document.getElementById('codeshare-input').value = '';
    }
}

function renderTags() {
    const c = document.getElementById('active-tags');
    c.innerHTML = '';
    codeShares.forEach(slug => {
         const t = document.createElement('span');
         t.className = "text-[10px] bg-indigo-900 text-indigo-200 px-1 rounded border border-indigo-700 flex items-center gap-1";
         t.innerHTML = `${slug} <button onclick="removeShare('${slug}')" class="hover:text-white">x</button>`;
         c.appendChild(t);
    });
}
function removeShare(slug) {
    codeShares = codeShares.filter(x => x !== slug);
    renderTags();
}

// --- Modals ---
function toggleRootModal() {
    const m = document.getElementById('root-modal');
    m.classList.toggle('hidden');
    if (!m.classList.contains('hidden')) checkWizardStatus();
}
function toggleMagisk() {
    const m = document.getElementById('magisk-modal');
    m.classList.toggle('hidden');
    // Logic to check magisk status could go here
    document.getElementById('magisk-status-badge').innerText = "Checking...";
}
function toggleAIConfig() { document.getElementById('ai-config-modal').classList.toggle('hidden'); }
function toggleAppModal() { document.getElementById('app-list-modal').classList.toggle('hidden'); }

// --- Server Manager Logic (V6) ---
let isServerRunning = false; // Global State

// Polling for Server Status
setInterval(() => {
    const s = document.getElementById('device-select');
    if (s && s.value) {
        checkServerStatus(s.value);
    }
}, 3000); // Faster polling for responsiveness

async function checkServerStatus(serial) {
    try {
        const res = await fetch(`/api/server/${serial}/status`);
        const data = await res.json();
        
        const badge = document.getElementById('serverStatusBadge');
        const ver = document.getElementById('serverVersion');
        const inst = document.getElementById('serverInstalled');
        const root = document.getElementById('serverRooted');
        
        isServerRunning = data.running; // Update State
        updateUIState(); // Trigger UI Refresh

        if (!badge) return; // Not on page?

        if (data.running) {
            badge.className = "bg-green-900 text-green-300 px-2 py-1 rounded text-xs";
            badge.textContent = "RUNNING";
        } else {
            badge.className = "bg-red-900 text-red-300 px-2 py-1 rounded text-xs";
            badge.textContent = "STOPPED";
        }
        
        ver.textContent = data.version || "N/A";
        inst.textContent = data.installed ? "Yes" : "No";
        
        if (root) {
            root.textContent = data.rooted ? "Yes" : "No";
            root.className = data.rooted ? "text-green-400" : "text-red-400";
        }
        
        if (data.version && !data.compatible) {
             ver.innerHTML += " <span class='text-red-400'>(Mismatch)</span>";
        }
        
    } catch(e) {
        // console.error("Server Check Error:", e);
    }
}

async function manageServer(action) {
    const s = document.getElementById('device-select');
    if (!s || !s.value) return showToast("Select a device first!", 'error');
    const serial = s.value;
    
    // show loading
    const btn = event.currentTarget || document.activeElement; 
    // Fallback if event is missing (rare)
    
    const originalText = btn.innerHTML;
    btn.innerHTML = `<i data-lucide="loader-2" class="animate-spin"></i> ...`;
    btn.disabled = true;
    
    try {
        const res = await fetch(`/api/server/${serial}/action?action=${action}`, { method: 'POST' });
        const data = await res.json();
        
        if (data.status === "ok") {
            showToast("Server Action: " + action + " Success", "success");
            // Immediate check
            checkServerStatus(serial);
            setTimeout(() => checkServerStatus(serial), 2000); // Double check
        } else {
            showToast("Error: " + data.message, "error");
        }
    } catch(e) {
        showToast("Network Error", "error");
    } finally {
        if(btn) {
            btn.innerHTML = originalText;
            btn.disabled = false;
        }
        if(window.lucide) lucide.createIcons();
    }
}

// --- App Browser Logic ---
async function loadApps() {
    setupModal('apps');
    const serial = document.getElementById('device-select').value;
    if (!serial) return showToast("Select device!", 'error');
    
    try {
        const res = await fetch(`/api/apps/${serial}`);
        const data = await res.json();
        
        // Normalize Data (Backend returns strings, Frontend needs objects with type)
        const rawApps = data.apps || [];
        allApps = rawApps.map(app => {
            if (typeof app === 'string') {
                // Heuristic: Auto-classify based on package name
                const isSystem = app.startsWith('com.android.') || 
                               app.startsWith('android.') || 
                               app.startsWith('com.google.android.') ||
                               app.startsWith('com.sec.android.'); // Samsung
                return { id: app, type: isSystem ? 'system' : 'user' };
            }
            return app; // Already object (future proof)
        });

        allProcs = []; // Clear procs to avoid confusion
        
        document.getElementById('app-filter-type').value = 'user'; // Default
        filterApps('apps');
    } catch (e) {
        document.getElementById('app-list-container').innerHTML = `<div class="text-red-500 p-4">Error: ${e}</div>`;
    }
}

async function loadProcesses() {
    setupModal('procs');
    const serial = document.getElementById('device-select').value;
    if (!serial) return showToast("Select device!", 'error');

    try {
        const res = await fetch(`/api/processes/${serial}`);
        const data = await res.json();
        
        // Backend now returns [[name, pid], ...]
        const raw = data.processes || [];
        allProcs = raw.map(p => {
             if (Array.isArray(p) && p.length >= 2) return p; 
             if (typeof p === 'string') return [p, '?']; // Fallback
             return ['Unknown', '?'];
        });

        allApps = []; 
        
        document.getElementById('app-filter-type').value = 'running';
        filterApps('procs'); 
    } catch (e) {
        document.getElementById('app-list-container').innerHTML = `<div class="text-red-500 p-4">Error: ${e}</div>`;
    }
}

function setupModal(mode) {
    document.getElementById('app-list-modal').classList.remove('hidden');
    document.getElementById('app-list-container').innerHTML = '<div class="text-white p-4 animate-pulse">Loading data...</div>';
    
    const title = document.getElementById('app-modal-title');
    const icon = document.getElementById('app-modal-icon');
    const desc = document.getElementById('app-modal-desc');
    const select = document.getElementById('app-filter-type');

    if (mode === 'apps') {
        title.innerText = "Installed Packages";
        icon.innerText = "📦";
        desc.innerText = "Select a package to SPAWN";
        
        // Enable Package Filters
        select.innerHTML = `
            <option value="user" selected>User Apps</option>
            <option value="system">System Apps</option>
            <option value="all">All Packages</option>
        `;
        select.disabled = false;
    } else {
        title.innerText = "Running Processes";
        icon.innerText = "⚙️";
        desc.innerText = "Select a PID to ATTACH";
        
        // Lock to Processes
        select.innerHTML = `<option value="running" selected>Running PIDs</option>`;
        select.disabled = true; // No filtering needed for raw PID list usually
    }
}

function filterApps(forcedMode = null) {
    const filter = document.getElementById('app-search').value.toLowerCase();
    const type = document.getElementById('app-filter-type').value;
    const container = document.getElementById('app-list-container');
    const countEl = document.getElementById('app-total-count');
    
    // Reset Scroll
    container.innerHTML = '';
    renderOffset = 0;
    
    let items = [];

    // Determine Source
    if (type === 'running' || forcedMode === 'procs') {
            items = allProcs.filter(p => {
                if (!p) return false;
                const name = p[0] || '';
                const pid = String(p[1] || '');
                return name.toLowerCase().includes(filter) || pid.includes(filter);
            }).map(p => ({
                type: 'proc',
                name: p[0] || 'Unknown',
                id: p[1] || '?', // PID
                badge: 'proc'
            }));
    } else {
        items = allApps.filter(a => {
            if (!a || !a.id) return false; // Guard
            if (type !== 'all' && a.type !== type) return false;
            return a.id.toLowerCase().includes(filter);
        }).map(a => ({
            type: 'app',
            name: a.id,
            id: a.id,
            badge: a.type
        }));
    }

    if (countEl) countEl.innerText = items.length;

    if (items.length === 0) {
        container.innerHTML = '<div class="text-gray-500 p-4 text-center italic">No matches found.</div>';
        return;
    }

    currentRenderList = items;
    renderBatch(); 
    
    // Attach Scroll Listener 
    container.onscroll = () => {
        if (container.scrollTop + container.clientHeight >= container.scrollHeight - 50) {
            renderBatch();
        }
    };
}

function renderBatch() {
    const container = document.getElementById('app-list-container');
    const nextBatch = currentRenderList.slice(renderOffset, renderOffset + BATCH_SIZE);
    
    if (nextBatch.length === 0) return;

    const serial = document.getElementById('device-select').value;
    const fragment = document.createDocumentFragment();

    nextBatch.forEach(item => {
        const div = document.createElement('div');
        div.className = "flex items-center gap-3 p-2 hover:bg-white/5 border-b border-gray-800/50 cursor-pointer group transition";
        div.onclick = () => selectApp(item.id);

        let badgeHtml = '';
        if (item.badge === 'user') badgeHtml = `<span class="text-[10px] bg-indigo-900/50 text-indigo-300 px-1 rounded border border-indigo-500/20">User</span>`;
        if (item.badge === 'system') badgeHtml = `<span class="text-[10px] bg-gray-800 text-gray-400 px-1 rounded border border-gray-600/20">Sys</span>`;
        if (item.badge === 'proc') badgeHtml = `<span class="text-[10px] bg-emerald-900/50 text-emerald-300 px-1 rounded border border-emerald-500/20">PID ${item.id}</span>`;

        div.innerHTML = `
            <div class="flex-1 min-w-0">
                <div class="text-sm text-gray-200 truncate font-mono">${item.name}</div>
                <div class="flex gap-2 items-center mt-0.5">
                    ${badgeHtml}
                </div>
            </div>
            <div class="opacity-0 group-hover:opacity-100 flex gap-2">
                    <button onclick="event.stopPropagation(); analyzeJadx('${item.id}')" 
                    class="text-[10px] bg-orange-900/30 text-orange-400 border border-orange-500/30 px-2 py-1 rounded hover:bg-orange-900/50">⚡ Jadx</button>
            </div>
        `;
        fragment.appendChild(div);
    });

    container.appendChild(fragment);
    renderOffset += BATCH_SIZE;
}



// --- Editor Tools ---
function clearScript() {
    if (confirm("Clear editor content?")) {
        if (cmEditor) cmEditor.setValue("");
        localStorage.removeItem('ag_saved_script');
    }
}

function downloadScript() {
    const content = cmEditor ? cmEditor.getValue() : "";
    if (!content) return showToast("Editor is empty", "error");
    
    const blob = new Blob([content], { type: "text/javascript" });
    const defaultScript = `// ag-frida Default Starter Script
// Use this to test connectivity and basic hooking.

function waitForJava() {
    if (typeof Java !== 'undefined' && Java.available) {
        console.log("[*] Java Runtime Detected! Initializing hooks...");
        runJavaHooks();
    } else {
        console.log("[-] Waiting for Java Runtime...");
        setTimeout(waitForJava, 500); // Retry every 500ms
    }
}

function runJavaHooks() {
    Java.perform(function() {
        console.log("[*] Script Loaded successfully!");

        // 1. Diagnostics: Print System Info
        const Build = Java.use("android.os.Build");
        console.log("[i] Device: " + Build.MANUFACTURER.value + " " + Build.MODEL.value);
        console.log("[i] Android: " + Build.VERSION.RELEASE.value);

        // 2. Example: Hook Activity.onCreate
        try {
            const Activity = Java.use("android.app.Activity");
            Activity.onCreate.overload("android.os.Bundle").implementation = function(bundle) {
                console.log("[+] Activity Started: " + this.getClass().getName());
                this.onCreate(bundle);
            };
        } catch(e) { console.error(e); }

        // 3. Simple SSL Unpinning Stub
        try {
            const TrustManagerImpl = Java.use('com.android.org.conscrypt.TrustManagerImpl');
            TrustManagerImpl.checkTrustedRecursive.implementation = function(a, b, c, d, e, f) {
                return new java.util.ArrayList();
            };
        } catch(e) { /* Ignore */ }
    });
}

// Start waiting
waitForJava();
`;

    if (cmEditor) cmEditor.setValue(defaultScript);
    else document.getElementById('script-manual').value = defaultScript;
}

function selectApp(val) {
    // Check if it's a PID (digits) or Package
    const isPid = /^\d+$/.test(val);
    
    document.getElementById('target-input').value = val;
    
    if (isPid) {
        setMode('attach');
        showToast(`Selected PID ${val} (Attach Mode)`, 'info');
    } else {
        setMode('spawn');
        showToast(`Selected Package ${val} (Spawn Mode)`, 'info');
    }
    
    document.getElementById('app-list-modal').classList.add('hidden');
}

async function analyzeJadx(pkg) {
    const serial = document.getElementById('device-select').value;
    showToast(`Analyzing ${pkg}...`, 'info');
    try {
        const res = await fetch(`/api/tools/jadx/${serial}?package=${pkg}`, { method: 'POST' });
        const data = await res.json();
        if (data.status === 'launched') showToast("Jadx Launched!", 'success');
        else if (data.status === 'pulled_only') showToast(`Pulled to ${data.path}`, 'warning');
        else throw data.message || "Unknown error";
    } catch (e) { showToast(`Jadx Error: ${e}`, 'error'); }
}

// --- WebSocket ---
function connectWS() {
    const proto = window.location.protocol === 'https:' ? 'wss' : 'ws';
    ws = new WebSocket(`${proto}://${window.location.host}/ws/logs`);
    
    ws.onmessage = (event) => {
        const activeSerial = document.getElementById('device-select') ? document.getElementById('device-select').value : null;
        const lines = event.data.split('\n');
        const fragment = document.createDocumentFragment();
        
        lines.forEach(line => {
            // Filter Logic:
            // 1. If line strictly matches [serial], show it.
            // 2. If line has NO [serial] pattern (e.g. System log), show it.
            // 3. If line has [other_serial], hide it.
            
            const serialMatch = line.match(/\[([a-zA-Z0-9]+)\]/); // Simple regex for serial inside brackets
            let shouldShow = true;
            
            if (activeSerial && serialMatch) {
                const logSerial = serialMatch[1];
                // Ignore timestamp like [10:00:00] - heuristic check length/format if needed
                // But usually serials are mixed with timestamps.
                // Our Logger usually formats: [SERIAL] [TIME] Level Message
                if (logSerial !== activeSerial && logSerial.length > 8 && !line.includes(`[${activeSerial}]`)) {
                    // It's likely another device's log
                    shouldShow = false;
                }
            }

            if (shouldShow) {
                const displayLine = activeSerial ? line.replace(`[${activeSerial}]`, '').trim() : line;
                const div = document.createElement('div');
                div.style.whiteSpace = "pre-wrap"; // Preserve formatting
                
                if (displayLine.includes('[SCRIPT]')) div.className = "text-emerald-400 border-l-2 border-emerald-500/30 pl-2";
                else if (displayLine.includes('[ERROR]') || displayLine.includes('Error:') || displayLine.includes('Crash Report:')) div.className = "text-red-400 bg-red-900/10 border-l-2 border-red-500 pl-2";
                else if (displayLine.includes('WARNING') || displayLine.includes('Warning')) div.className = "text-orange-300";
                else if (displayLine.includes('INFO')) div.className = "text-blue-300/80";
                else div.className = "text-gray-400";
                
                div.innerText = displayLine;
                fragment.appendChild(div);
            }
        });
        
        const c = document.getElementById('console-output');
        if(c) {
            c.appendChild(fragment);
            if (c.scrollHeight - c.scrollTop - c.clientHeight < 100) {
                    c.scrollTop = c.scrollHeight;
            }
        }
    };
    
    ws.onclose = () => setTimeout(connectWS, 1000);
}

// --- Magisk Logic ---
async function checkMagiskStatus() {
    const serial = document.getElementById('device-select').value;
    if (!serial) return;
    
    document.getElementById('magisk-status-badge').innerText = "Checking...";
    document.getElementById('magisk-detail-text').innerText = "Querying Zygisk...";
    
    try {
        const res = await fetch(`/api/magisk/${serial}/status`);
        const data = await res.json();
        
        const badge = document.getElementById('magisk-status-badge');
        const detail = document.getElementById('magisk-detail-text');
        const btn = document.getElementById('btn-magisk-action');
        const chk = document.getElementById('chk-denylist');
        
        if (data.installed) {
            badge.innerText = "INSTALLED";
            badge.className = "text-[10px] uppercase font-bold px-2 py-0.5 rounded bg-emerald-900 text-emerald-300 border border-emerald-500/50";
            
            if (data.zygisk) {
                detail.innerText = `Zygisk: Active (${data.ver})`;
                btn.classList.add('hidden');
            } else {
                detail.innerText = "Zygisk: Inactive (Reboot needed?)";
                btn.innerText = "Reboot Device";
                btn.onclick = () => rebootDevice();
                btn.classList.remove('hidden');
            }
            
            if (data.denylist) chk.checked = true;
            
        } else {
            badge.innerText = "NOT FOUND";
            badge.className = "text-[10px] uppercase font-bold px-2 py-0.5 rounded bg-red-900 text-red-300 border border-red-500/50";
            detail.innerText = "Magisk app not found.";
            btn.innerText = "Install Magisk";
            btn.onclick = () => installMagiskApp();
            btn.classList.remove('hidden');
        }
    } catch (e) {
        document.getElementById('magisk-detail-text').innerText = "Error checking status";
    }
}

async function toggleDenyList(chk) {
    const serial = document.getElementById('device-select').value;
    const enable = chk.checked;
    try {
        await fetch(`/api/magisk/${serial}/denylist?enable=${enable}`, { method: 'POST' });
        showToast(`DenyList ${enable ? 'Enabled' : 'Disabled'}`, 'success');
    } catch (e) {
        chk.checked = !enable; // revert
        showToast("Failed to toggle DenyList", 'error');
    }
}

async function addToDenyList() {
    const serial = document.getElementById('device-select').value;
    const pkg = document.getElementById('magisk-add-pkg').value;
    if (!pkg) return;
    
    try {
        const res = await fetch(`/api/magisk/${serial}/add?package=${pkg}`, { method: 'POST' });
        const d = await res.json();
        if (d.status === 'ok') {
            showToast(`Added ${pkg} to DenyList`, 'success');
            document.getElementById('magisk-add-pkg').value = '';
        } else throw d.message;
    } catch (e) { showToast(`Error: ${e}`, 'error'); }
}

async function installMagiskApp() {
    const serial = document.getElementById('device-select').value;
    showToast("Installing Magisk...", 'info');
    try {
        const res = await fetch(`/api/magisk/${serial}/install`, { method: 'POST' });
        const d = await res.json();
        if (d.status === 'ok') {
            showToast("Magisk Installed! Please open app to setup.", 'success');
            checkMagiskStatus();
        } else throw d.message;
    } catch (e) { showToast(`Install Failed: ${e}`, 'error'); }
}

async function rebootDevice() {
    // Basic adb reboot wrapper if needed, or manual
    showToast("Please reboot device manually to apply Zygisk.", 'warning');
}

// Override toggle to also check status
const originalToggleMagisk = toggleMagisk;
toggleMagisk = function() {
    originalToggleMagisk();
    const m = document.getElementById('magisk-modal');
    if (!m.classList.contains('hidden')) {
        checkMagiskStatus();
    }
}


// --- Root Wizard Logic ---
async function checkWizardStatus() {
    const serial = document.getElementById('device-select').value;
    if (!serial) return;
    
    document.getElementById('wiz-model').innerText = "Checking...";
    document.getElementById('wiz-root').innerText = "...";
    
    try {
        const res = await fetch(`/api/root/${serial}/info`);
        const info = await res.json();
        
        document.getElementById('wiz-model').innerText = info.model || "Unknown";
        document.getElementById('wiz-android').innerText = `Android ${info.android_version || '?'} (SDK ${info.sdk_level || '?'})`;
        
        // root_access can be: 'adb_root', 'su', or 'none'
        if (info.root_access && info.root_access !== 'none') {
             document.getElementById('wiz-root').innerText = info.root_access.toUpperCase();
             document.getElementById('wiz-root').className = "text-emerald-400 font-bold font-mono truncate";
        } else {
             document.getElementById('wiz-root').innerText = "NONE";
             document.getElementById('wiz-root').className = "text-red-400 font-bold font-mono truncate";
        }
        
    } catch (e) {
        console.error("Root info fetch failed:", e);
        document.getElementById('wiz-model').innerText = "Error";
    }
    
    // Check partition (separate try-catch to avoid breaking info display)
    try {
        const pRes = await fetch(`/api/root/${serial}/partition`);
        const pInfo = await pRes.json();
        const partEl = document.getElementById('wiz-partition');
        if (partEl) partEl.innerText = pInfo.path || "Not Found";
        
        refreshArtifacts();
    } catch (e) {
        console.error("Partition fetch failed:", e);
    }
}

async function dumpBoot() {
    const serial = document.getElementById('device-select').value;
    logWizard("Starting Boot Dump...");
    debounceAction('btn-dump', async () => {
        const res = await fetch(`/api/root/${serial}/dump`, { method: 'POST' });
        const data = await res.json();
        if (data.status === 'ok') {
            logWizard(`SUCCESS: Dumped to ${data.path}`);
            showToast("Boot Image Dumped!", 'success');
            refreshArtifacts();
        } else {
            logWizard(`ERROR: ${data.message}`);
            showToast("Dump Failed", 'error');
        }
    });
}

async function flashBoot() {
    const serial = document.getElementById('device-select').value;
    const file = document.getElementById('flash-file-select').value;
    if (!file) return showToast("Select a file first!", 'error');
    
    if (!confirm("WARNING: Flashing boot image risks bricking. Ensure you have the correct file. Continue?")) return;
    
    logWizard(`Flashing ${file}...`);
    debounceAction('btn-flash', async () => {
        const res = await fetch(`/api/root/${serial}/flash?filename=${file}`, { method: 'POST' });
        const data = await res.json();
        if (data.status === 'ok') {
            logWizard("SUCCESS: Flash Complete. Rebooting...");
            showToast("Flashed & Rebooting", 'success');
        } else {
            logWizard(`ERROR: ${data.message}`);
        }
    });
}

async function refreshArtifacts() {
    const s = document.getElementById('flash-file-select');
    s.innerHTML = '<option value="">Loading...</option>';
    try {
        const res = await fetch('/api/root/artifacts');
        const data = await res.json();
        s.innerHTML = '<option value="">Select Artifact...</option>';
        if (data.files) {
            data.files.forEach(f => {
                const opt = document.createElement('option');
                opt.value = f;
                opt.text = f;
                s.appendChild(opt);
            });
        }
    } catch (e) {}
}

async function installMagiskAppRoot() {
    const serial = document.getElementById('device-select').value;
    logWizard("Installing Magisk App...");
    try {
        const res = await fetch(`/api/root/${serial}/install-magisk`, { method: 'POST' });
        const d = await res.json();
        if (d.status === 'ok') logWizard("Magisk App Installed.");
        else logWizard("Install Failed.");
    } catch (e) { logWizard("Error installing app."); }
}

async function launchMagiskApp() {
    const serial = document.getElementById('device-select').value;
    await fetch(`/api/root/${serial}/launch-magisk`, { method: 'POST' });
}

function logWizard(msg) {
    const c = document.getElementById('wiz-console');
    const d = document.createElement('div');
    d.innerText = `> ${msg}`;
    c.scrollTop = c.scrollHeight;
}

// --- CodeShare Logic ---
function toggleCodeShareModal() {
    const m = document.getElementById('codeshare-modal');
    m.classList.toggle('hidden');
    if (!m.classList.contains('hidden')) {
        loadRecommendedScripts();
    }
}

async function loadRecommendedScripts() {
    const list = document.getElementById('codeshare-list');
    list.innerHTML = '<div class="text-gray-500 text-xs text-center">Loading...</div>';
    
    try {
        const res = await fetch('/api/codeshare/recommended');
        const data = await res.json();
        
        if (data.error) throw data.error;
        const scripts = data.recommended || [];
        
        list.innerHTML = '';
        scripts.forEach(s => {
            const item = document.createElement('div');
            item.className = "p-3 bg-white/5 border border-gray-800 rounded hover:bg-white/10 transition cursor-pointer flex justify-between items-center group";
            item.onclick = () => selectCodeShare(s.slug);
            
            item.innerHTML = `
                <div>
                    <div class="text-sm font-bold text-indigo-300 group-hover:text-white transition">${s.name}</div>
                    <div class="text-[10px] text-gray-500">${s.description}</div>
                </div>
                <div class="text-right">
                    <div class="text-[10px] text-gray-600 font-mono">${s.slug}</div>
                    <span class="text-[10px] bg-gray-800 text-gray-400 px-1 rounded">${s.category}</span>
                </div>
            `;
            list.appendChild(item);
        });
        
    } catch (e) {
        list.innerHTML = `<div class="text-red-500 text-xs text-center">Error: ${e}</div>`;
    }
}

function selectCodeShare(slug) {
    document.getElementById('codeshare-input').value = slug;
    toggleCodeShareModal();
    showToast(`Added ${slug}`, 'success');
}

// --- Full Screen Editor Modal (Separate) ---
let cmModal = null;

function initModalEditor() {
    if (cmModal) return;
    const ta = document.getElementById('script-modal-area');
    if (ta && typeof CodeMirror !== 'undefined') {
        cmModal = CodeMirror.fromTextArea(ta, {
            mode: "javascript",
            theme: "dracula",
            lineNumbers: true,
            smartIndent: true,
            matchBrackets: true,
            lineWrapping: true,
            // Extra features for Big Editor
            foldGutter: true,
            gutters: ["CodeMirror-linenumbers", "CodeMirror-foldgutter"]
        });
        cmModal.setSize("100%", "100%");
    }
}

function toggleMaximizeEditor() {
    initModalEditor(); // Ensure init
    const m = document.getElementById('editor-modal');
    
    // Sync Content: Sidebar -> Modal
    if (cmEditor && cmModal) {
        cmModal.setValue(cmEditor.getValue());
    }
    
    m.classList.remove('hidden');
    setTimeout(() => cmModal.refresh(), 100);
}

function closeEditorModal() {
    const m = document.getElementById('editor-modal');
    m.classList.add('hidden');
    
    // Auto-Sync: Modal -> Sidebar
    if (cmEditor && cmModal) {
        cmEditor.setValue(cmModal.getValue());
    }
}

function saveFromModal() {
    closeEditorModal();
    showToast("Script Synced & Saved", "success");
}

// Escape key to close
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        const m = document.getElementById('editor-modal');
        if (m && !m.classList.contains('hidden')) {
            closeEditorModal();
        }
    }
});
