# 🌌 Python Code Visualizer Pro

> **See your codebase. Don't just read it.**

A professional desktop tool for visualizing, analyzing and understanding Python codebases — with 5 powerful views including a real-time solar system visualization powered by pygame.

![Python](https://img.shields.io/badge/Python-3.8+-blue?style=flat-square&logo=python)
![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)
![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey?style=flat-square)
![Status](https://img.shields.io/badge/Status-Active-brightgreen?style=flat-square)

---

## ✨ Overview

Python Code Visualizer Pro parses any Python file or directory and renders it across 5 distinct visualization modes — from a classic tree view to a living, animated solar system where complexity is visible at a glance.

Load a codebase. The most complex classes emerge instantly as giant red planets drowning in orbiting moons. No metrics dashboard needed. You just *see* it.

---

## 🖥️ Views

### 🌳 Tree View
- Lazy-loaded collapsible hierarchy
- Every module, class, method, function and import
- Single-click expand, search, filter
- Jump to definition
- Complexity indicators per node

### 🧠 Mind Map
- Radial and hierarchical layout modes
- Structural relationships at a glance
- Zoom, pan, fit-to-view
- Inheritance and call edges

### 🔗 Network Graph
- Force-directed dependency map
- Cross-module call relationships
- Hierarchical, tree, force and circular layouts
- Shows who calls who across the entire codebase

### 📊 UML Class Diagram
- Auto-generated class diagrams
- Inheritance chains, attributes, methods
- Auto, grid and hierarchical layout
- Export to PostScript/EPS

### 🌌 Code Cosmos *(flagship)*
- Real-time solar system visualization via pygame + PIL
- **Planet** = class (size = lines of code)
- **Planet color** = cyclomatic complexity (blue → red)
- **Orbiting moons** = methods (animated)
- **Saturn rings** = attributes
- **Yellow arcs** = inheritance relationships
- **Pulsing cyan arcs** = function calls
- **Asteroid dots** = standalone functions
- Pan, zoom, hover tooltips, click to select
- Runs at 30fps embedded inside the tkinter UI

---

## ⚡ Features

| Feature | Description |
|---|---|
| 🔍 Syntax-highlighted code preview | Full file viewer with line numbers, font size control |
| 📈 Complexity metrics | Cyclomatic complexity per function and class |
| 📊 Statistics panel | Modules, classes, functions, total lines, avg complexity |
| 🔎 Duplicate detection | Find duplicate code blocks across modules |
| 🗑 Unused code finder | Detect dead classes and functions |
| 🎨 Multiple themes | Dark and light color variants |
| 💾 Session save & restore | Remembers last opened files |
| ⚙️ Preferences dialog | Font sizes, performance tuning, cache control |
| 🚀 Background threading | Non-blocking analysis for large codebases |
| 📦 Lazy loading | Fast startup even for 20k+ line projects |
| 📤 Export diagrams | PostScript/EPS export from UML and graph views |

---

## 🛠️ Installation

```bash
# Clone the repository
git clone https://github.com/shuvrobasu/python-code-visualizer.git
cd python-code-visualizer

# Install dependencies
pip install -r requirements.txt

# Run
python PY_Code_Visualizer.py
```

### Requirements

```txt
pygame>=2.0.0
Pillow>=9.0.0
pygments>=2.0.0
psutil>=5.0.0
```

> Python 3.8+ required. All other dependencies are standard library.

---

## 🚀 Usage

### Open a file
```
File → Open File   (Ctrl+O)
```

### Open a directory
```
File → Open Directory   (Ctrl+D)
```

### Switch views
Click any tab: `🌳 Tree View` | `🧠 Mind Map` | `🔗 Network` | `📊 Classes` | `🌌 Cosmos`

### Code Cosmos controls
| Action | Control |
|---|---|
| Pan | Right-click drag |
| Zoom | Scroll wheel |
| Select class | Left-click planet |
| Hover tooltip | Mouse over planet or moon |
| Class name | Hover planet |
| Method name | Hover moon |

---

## 📁 Project Structure

```
python-code-visualizer/
├── PY_Code_Visualizer.py      # Main application
├── code_visualizer.ini        # Auto-generated config
├── requirements.txt
└── README.md
```

---

## 🧠 How It Works

The analyzer uses Python's built-in `ast` module to parse source files without executing them. It extracts:

- Module structure and imports
- Class definitions, bases, decorators
- Method signatures, arguments, return types
- Function calls (cross-module resolution)
- Cyclomatic complexity (enhanced formula)
- Attributes, docstrings, async indicators

All data is passed to each visualization view on demand via lazy loading.

---

## 🌌 Code Cosmos — Technical Notes

Code Cosmos runs a pygame render loop inside a tkinter frame using PIL as the bridge:

```
pygame.Surface → pygame.image.tostring → PIL.Image → PIL.ImageTk.PhotoImage → tk.Canvas
```

The loop runs at 30fps when the Cosmos tab is active and drops to a 500ms idle poll when hidden — keeping CPU usage minimal while other views are in use.

---

## 📸 Screenshots

> *Load your own codebase to see it come alive.*

---

## 🗺️ Roadmap

- [ ] Multi-file diff view
- [ ] Git blame integration
- [ ] Export Cosmos as animated GIF
- [ ] Plugin system for custom analyzers
- [ ] Dark/light theme for Cosmos
- [ ] Search within Cosmos view

---

## 🤝 Contributing

Pull requests welcome. For major changes please open an issue first.

---

## 📄 License

MIT License — see [LICENSE](LICENSE) for details.

---

## 🔗 Related Posts

- [Why you should own your AI, not rent it](https://www.linkedin.com/feed/update/urn:li:activity:7433173454688006144/)
- [Automating code dataset curation for AI training](https://www.linkedin.com/feed/update/urn:li:activity:7433887597317222400/)
---

*Built with Python, pygame, PIL, tkinter. Zero JS. Zero web frameworks. Pure desktop.*
