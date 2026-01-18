# 🔧 ag-frida v2.1.0

> **Production-Grade Frida Automation Tool**  
> Zero-Dependency • Web Dashboard • AI-Powered • Multi-Device Support

[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://www.python.org/)
[![Frida](https://img.shields.io/badge/Frida-17.5.2-green.svg)](https://frida.re/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## ✨ Features

### 🎯 Core Capabilities
- **Zero-Dependency Setup** — Auto-downloads ADB, frida-server, and JADX
- **Multi-Device Support** — USB, WiFi ADB, and Emulator (LDPlayer, Nox, etc.)
- **Stealth Mode** — Dynamic server naming to bypass anti-frida detection
- **Auto-Restart** — Session recovery on crash with configurable toggle

### 🌐 Web Dashboard
- **Modern UI** — Dark theme with premium design
- **Real-time Logs** — WebSocket-based live log streaming
- **Script Editor** — CodeMirror with syntax highlighting
- **CodeShare Integration** — Browse and fetch community scripts

### 🤖 AI Assistant
- **Multi-Provider** — OpenAI, Google Gemini, OpenRouter
- **Role-Based Generation** — Security bypass, analysis, reverse engineering
- **Context-Aware** — Uses device and package info for better scripts

### 🔓 Root Assistant
- **Boot Image Dump** — Extract boot.img with A/B slot support
- **Magisk Manager** — Install APK, manage DenyList
- **Partition Detection** — Smart boot partition finder (Android 9-14+)

### 📦 Analysis Tools
- **JADX Integration** — Pull APK and launch decompiler
- **Process Browser** — View running processes and PIDs
- **Package Manager** — List installed apps with filtering

---

## 📋 Requirements

| Requirement | Version |
|-------------|---------|
| Python | 3.8+ |
| Frida | 17.5.2 (auto-matched) |
| Android Device | Rooted or Debuggable |
| ADB | Auto-installed |

---

## 🚀 Quick Start

### 1. Clone Repository
```bash
git clone https://github.com/yourusername/ag-frida.git
cd ag-frida
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Run
```bash
# Interactive CLI Mode
python main.py

# Web Dashboard Mode (Recommended)
python main.py --web
```

### 4. Open Browser
Navigate to: **http://127.0.0.1:8000**

---

## 📖 Usage

### CLI Mode
```bash
# Start with specific device
python main.py --serial emulator-5554

# Connect via WiFi ADB
python main.py --connect 192.168.1.100:5555

# Spawn mode with package
python main.py --target com.example.app --mode spawn
```

### Web Dashboard

1. **Select Device** — Choose from connected devices dropdown
2. **Enter Target** — Package name (e.g., `com.example.app`)
3. **Choose Mode** — Spawn (fresh start) or Attach (running app)
4. **Edit Script** — Write or paste your Frida script
5. **Start Session** — Click the green Start button

### AI Script Generation

1. Open **AI Assistant** panel
2. Enter prompt (e.g., "bypass SSL pinning for OkHttp")
3. Select role category (Auto-Detect, Security Bypass, etc.)
4. Click **Generate** — Script appears in editor

---

## ⚙️ Configuration

### AI Providers (`ag-frida.yaml`)
```yaml
ai:
  active_provider: openai
  providers:
    openai:
      api_key: sk-your-key-here
      model: gpt-4o-mini
    gemini:
      api_key: your-gemini-key
      model: gemini-1.5-flash
    openrouter:
      api_key: your-openrouter-key
      model: anthropic/claude-3-haiku
```

### Profiles
Save and load session configurations:
- Device serial
- Target package
- Scripts
- CodeShare slugs

---

## 📁 Project Structure

```
ag-frida/
├── main.py              # CLI entry point
├── requirements.txt     # Python dependencies
├── ag-frida.yaml        # Configuration file
│
├── core/                # Core modules
│   ├── adb.py           # ADB wrapper
│   ├── adb_installer.py # Auto-install ADB
│   ├── ai.py            # AI assistant
│   ├── cli_bridge.py    # Frida CLI subprocess
│   ├── codeshare.py     # CodeShare fetcher
│   ├── config.py        # Config manager
│   ├── device.py        # Device info
│   ├── jadx.py          # JADX launcher
│   ├── magisk.py        # Magisk manager
│   ├── root.py          # Root automation
│   ├── server.py        # Frida server manager
│   ├── session.py       # Session manager
│   └── tools_installer.py
│
├── web/                 # Web dashboard
│   ├── server.py        # FastAPI backend
│   ├── bridge.py        # Session pool
│   ├── static/          # CSS, JS
│   └── templates/       # HTML
│
├── bin/                 # Auto-downloaded tools
├── logs/                # Session logs
└── scripts/             # User scripts
```

---

## 🔧 Troubleshooting

### Common Issues

| Issue | Solution |
|-------|----------|
| `frida-server not found` | Click "Start Server" in web UI or use `--server start` |
| `spawn timed out` | Enable Auto-Restart, will retry automatically |
| `adb not found` | ADB auto-downloads on first run |
| `device offline` | Reconnect USB or restart ADB server |

### Emulator Support
| Emulator | Status | Notes |
|----------|--------|-------|
| Android Studio | ✅ | Full support |
| LDPlayer | ✅ | Use WiFi ADB mode |
| Nox | ✅ | Enable root in settings |
| BlueStacks | ⚠️ | Limited, use adb connect |

---

## 🛡️ Security Notice

> ⚠️ **This tool is for educational and authorized security testing only.**

- Do NOT use on devices/apps without permission
- API keys are stored locally in `ag-frida.yaml`
- Web dashboard has no authentication (local use only)

---

## 📄 License

MIT License — See [LICENSE](LICENSE) for details.

---

## 🙏 Credits

- [Frida](https://frida.re/) — Dynamic instrumentation toolkit
- [CodeShare](https://codeshare.frida.re/) — Community scripts
- [JADX](https://github.com/skylot/jadx) — APK decompiler
- [FastAPI](https://fastapi.tiangolo.com/) — Web framework
- [Rich](https://rich.readthedocs.io/) — Terminal UI

---

<div align="center">

**Made with ❤️ for the security research community**

</div>
