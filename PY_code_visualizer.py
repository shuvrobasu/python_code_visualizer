"""
Professional Python Code Visualizer with Performance Optimization
==================================================================
Handles 10K+ LOC efficiently with threading, lazy loading, and caching
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import ast
import os
import math
import json
import re
import threading
import configparser
from dataclasses import dataclass, field
from typing import Dict, List, Set, Optional, Tuple, Any
from collections import defaultdict
from pathlib import Path
import queue
import time
import random
import pygame
import PIL.Image
import PIL.ImageTk
# from theme_manager import ThemeManager

# Try to import Pygments for better syntax highlighting
try:
    from pygments import lex
    from pygments.lexers import PythonLexer
    from pygments.token import Token
    HAS_PYGMENTS = True
except ImportError:
    HAS_PYGMENTS = False
    print("Warning: Pygments not installed. Using basic syntax highlighting.")

# ============================================================================
# DATA STRUCTURES
# ============================================================================

@dataclass
class FunctionInfo:
    """Stores information about a function/method"""
    name: str
    lineno: int
    end_lineno: int
    args: List[str]
    decorators: List[str]
    docstring: Optional[str]
    calls: List[str] = field(default_factory=list)
    is_method: bool = False
    is_async: bool = False
    complexity: int = 1
    parent_class: Optional[str] = None
    return_type: Optional[str] = None


@dataclass
class ClassInfo:
    """Stores information about a class"""
    name: str
    lineno: int
    end_lineno: int
    bases: List[str]
    decorators: List[str]
    docstring: Optional[str]
    methods: List[FunctionInfo] = field(default_factory=list)
    attributes: List[str] = field(default_factory=list)
    is_abstract: bool = False


@dataclass
class ModuleInfo:
    """Stores information about a module"""
    name: str
    path: str
    imports: List[str] = field(default_factory=list)
    from_imports: Dict[str, List[str]] = field(default_factory=dict)
    functions: List[FunctionInfo] = field(default_factory=list)
    classes: List[ClassInfo] = field(default_factory=list)
    global_vars: List[str] = field(default_factory=list)
    has_main: bool = False
    line_count: int = 0


# ============================================================================
# CONFIGURATION MANAGER
# ============================================================================

class ConfigManager:
    """Manage application configuration using INI file"""

    def __init__(self, config_file='code_visualizer.ini'):
        self.config_file = config_file
        self.config = configparser.ConfigParser()
        self.load_config()

    def load_config(self):
        """Load configuration from INI file with error handling"""
        if os.path.exists(self.config_file):
            try:
                # Try reading with UTF-8-SIG to handle BOM
                with open(self.config_file, 'r', encoding='utf-8-sig') as f:
                    self.config.read_file(f)

                # Validate that we have sections
                if len(self.config.sections()) == 0:
                    raise ValueError("Config file has no sections")

            except Exception as e:
                print(f"Warning: Config file corrupted ({e}). Creating new one.")
                # Backup corrupted file
                try:
                    backup_name = f"{self.config_file}.backup"
                    if os.path.exists(self.config_file):
                        os.rename(self.config_file, backup_name)
                        print(f"Old config backed up to {backup_name}")
                except:
                    pass

                # Create fresh config
                self.set_defaults()
                self.save_config()
        else:
            # Create default config
            self.set_defaults()
            self.save_config()

    def set_defaults(self):
        """Set default configuration values"""
        self.config.clear()  # Clear any existing data

        self.config['General'] = {
            'last_path': os.path.expanduser('~'),
            'window_geometry': '1400x900+50+50',
            'theme': 'dark',
            'last_tab': '0',
            'recent_files': '[]'
        }

        self.config['Features'] = {
            'analyze_dirs': 'yes',
            'show_calls': 'yes',
            'show_inheritance': 'yes',
            'code_preview': 'yes',
            'export_png': 'yes',
            'dark_mode': 'yes',
            'track_imports': 'yes',
            'show_complexity': 'yes',
            'auto_detect_main': 'yes'
        }

        self.config['Performance'] = {
            'lazy_loading': 'yes',
            'use_threading': 'yes',
            'max_initial_nodes': '200',
            'cache_files': 'yes',
            'cache_size_mb': '50',
            'analysis_timeout': '30'
        }

        self.config['Display'] = {
            'tree_font_size': '9',
            'code_font_size': '10',
            'diagram_font_size': '8',
            'min_zoom': '10',
            'max_zoom': '5000',
            'default_zoom': '100'
        }

        self.config['Session'] = {
            'modules': '[]'
        }

    def save_config(self):
        """Save configuration to INI file"""
        try:
            # Write with UTF-8 encoding (no BOM)
            with open(self.config_file, 'w', encoding='utf-8') as f:
                self.config.write(f)
        except Exception as e:
            print(f"Error saving config: {e}")

    def get(self, section: str, key: str, fallback=None):
        """Get configuration value"""
        try:
            return self.config.get(section, key)
        except (configparser.NoSectionError, configparser.NoOptionError):
            return fallback

    def set(self, section: str, key: str, value: str):
        """Set configuration value"""
        if section not in self.config:
            self.config[section] = {}
        self.config[section][key] = str(value)

    def get_bool(self, section: str, key: str, fallback=False) -> bool:
        """Get boolean configuration value"""
        value = self.get(section, key, str(fallback))
        return str(value).lower() in ('yes', 'true', '1', 'on')

    def get_int(self, section: str, key: str, fallback=0) -> int:
        """Get integer configuration value"""
        try:
            return int(self.get(section, key, str(fallback)))
        except (ValueError, TypeError):
            return fallback

    def get_float(self, section: str, key: str, fallback=0.0) -> float:
        """Get float configuration value"""
        try:
            return float(self.get(section, key, str(fallback)))
        except (ValueError, TypeError):
            return fallback


# ============================================================================
# THREAD POOL FOR BACKGROUND TASKS
# ============================================================================

class ThreadPool:
    """Simple thread pool for background tasks"""

    def __init__(self, max_workers=4):
        self.max_workers = max_workers
        self.queue = queue.Queue()
        self.workers = []
        self.running = True
        self._start_workers()

    def _start_workers(self):
        """Start worker threads"""
        for i in range(self.max_workers):
            worker = threading.Thread(target=self._worker, daemon=True)
            worker.start()
            self.workers.append(worker)

    def _worker(self):
        """Worker thread main loop"""
        while self.running:
            try:
                func, args, kwargs, callback = self.queue.get(timeout=1)
                try:
                    result = func(*args, **kwargs)
                    if callback:
                        callback(result)
                except Exception as e:
                    print(f"Worker error: {e}")
                finally:
                    self.queue.task_done()
            except queue.Empty:
                continue

    def submit(self, func, *args, callback=None, **kwargs):
        """Submit task to thread pool"""
        self.queue.put((func, args, kwargs, callback))

    def shutdown(self):
        """Shutdown thread pool"""
        self.running = False
        for worker in self.workers:
            worker.join(timeout=1)


# ============================================================================
# CACHE MANAGER
# ============================================================================

class CacheManager:
    """Manage file and analysis caching"""

    def __init__(self, max_size_mb=50):
        self.max_size_bytes = max_size_mb * 1024 * 1024
        self.file_cache = {}  # filepath -> (content, lines, timestamp)
        self.analysis_cache = {}  # filepath -> ModuleInfo
        self.syntax_cache = {}  # filepath -> highlighting data
        self.current_size = 0
        self.lock = threading.Lock()

    def get_file(self, filepath: str) -> Optional[Tuple[str, List[str]]]:
        """Get cached file content"""
        with self.lock:
            if filepath in self.file_cache:
                content, lines, timestamp = self.file_cache[filepath]
                # Check if file has been modified
                if os.path.getmtime(filepath) <= timestamp:
                    return content, lines
                else:
                    # File modified, remove from cache
                    self._remove_from_cache(filepath)
        return None

    def cache_file(self, filepath: str, content: str, lines: List[str]):
        """Cache file content"""
        with self.lock:
            size = len(content.encode('utf-8'))

            # Check size limit
            while self.current_size + size > self.max_size_bytes and self.file_cache:
                # Remove oldest entry
                oldest = min(self.file_cache.items(), key=lambda x: x[1][2])
                self._remove_from_cache(oldest[0])

            self.file_cache[filepath] = (content, lines, time.time())
            self.current_size += size

    def _remove_from_cache(self, filepath: str):
        """Remove file from all caches"""
        if filepath in self.file_cache:
            content = self.file_cache[filepath][0]
            self.current_size -= len(content.encode('utf-8'))
            del self.file_cache[filepath]

        if filepath in self.analysis_cache:
            del self.analysis_cache[filepath]

        if filepath in self.syntax_cache:
            del self.syntax_cache[filepath]

    def get_analysis(self, filepath: str) -> Optional[ModuleInfo]:
        """Get cached analysis"""
        with self.lock:
            return self.analysis_cache.get(filepath)

    def cache_analysis(self, filepath: str, module: ModuleInfo):
        """Cache analysis result"""
        with self.lock:
            self.analysis_cache[filepath] = module

    def clear(self):
        """Clear all caches"""
        with self.lock:
            self.file_cache.clear()
            self.analysis_cache.clear()
            self.syntax_cache.clear()
            self.current_size = 0


# ============================================================================
# ANALYSIS PROGRESS DIALOG
# ============================================================================

class AnalysisProgressDialog(tk.Toplevel):
    """Show progress during directory analysis"""

    def __init__(self, parent):
        super().__init__(parent)

        self.title("Analyzing Files...")
        self.geometry("600x400")
        self.resizable(False, False)
        self.transient(parent)

        # Center window
        self.update_idletasks()
        x = (self.winfo_screenwidth() - 600) // 2
        y = (self.winfo_screenheight() - 400) // 2
        self.geometry(f"+{x}+{y}")

        # Statistics
        self.total_files = 0
        self.processed_files = 0
        self.successful = 0
        self.failed = 0
        self.errors = []

        self._create_widgets()

    def _create_widgets(self):
        """Create progress widgets"""
        # Title
        title = ttk.Label(self, text="Analyzing Python Files",
                          font=('Segoe UI', 12, 'bold'))
        title.pack(pady=10)

        # Progress bar
        self.progress = ttk.Progressbar(self, length=550, mode='determinate')
        self.progress.pack(padx=20, pady=10)

        # Status label
        self.status_label = ttk.Label(self, text="Preparing...",
                                      font=('Segoe UI', 10))
        self.status_label.pack(pady=5)

        # Stats frame
        stats_frame = ttk.LabelFrame(self, text="Statistics", padding=10)
        stats_frame.pack(fill=tk.X, padx=20, pady=10)

        self.stats_labels = {}

        stats = [
            ('total', 'Total Files:', '0'),
            ('processed', 'Processed:', '0'),
            ('success', 'Successful:', '0'),
            ('failed', 'Failed:', '0')
        ]

        for i, (key, label, value) in enumerate(stats):
            frame = ttk.Frame(stats_frame)
            frame.grid(row=i, column=0, sticky='ew', pady=2)

            ttk.Label(frame, text=label, width=15).pack(side=tk.LEFT)
            value_label = ttk.Label(frame, text=value, font=('Segoe UI', 9, 'bold'))
            value_label.pack(side=tk.LEFT)
            self.stats_labels[key] = value_label

        # Error log
        log_frame = ttk.LabelFrame(self, text="Error Log", padding=5)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)

        self.error_text = tk.Text(log_frame, height=8, wrap=tk.WORD,
                                  font=('Consolas', 9),
                                  bg='#2B2B2B', fg='#FF6B6B')
        scrollbar = ttk.Scrollbar(log_frame, command=self.error_text.yview)
        self.error_text.configure(yscrollcommand=scrollbar.set)

        self.error_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Cancel button
        self.cancel_btn = ttk.Button(self, text="Cancel", command=self._cancel)
        self.cancel_btn.pack(pady=10)

        self.cancelled = False

    def set_total(self, total: int):
        """Set total number of files"""
        self.total_files = total
        self.progress['maximum'] = total
        self.stats_labels['total'].configure(text=str(total))

    def update_progress(self, current: int, filename: str):
        """Update progress"""
        self.processed_files = current
        self.progress['value'] = current
        self.status_label.configure(text=f"Analyzing: {filename}")
        self.stats_labels['processed'].configure(text=str(current))

        # Calculate percentage
        if self.total_files > 0:
            percent = int((current / self.total_files) * 100)
            self.title(f"Analyzing Files... {percent}%")

        self.update()

    def add_success(self, filename: str):
        """Record successful analysis"""
        self.successful += 1
        self.stats_labels['success'].configure(text=str(self.successful))

    def add_error(self, filename: str, error: str):
        """Record error"""
        self.failed += 1
        self.stats_labels['failed'].configure(text=str(self.failed))

        # Add to error log
        error_msg = f"❌ {filename}: {error}\n"
        self.errors.append((filename, error))
        self.error_text.insert(tk.END, error_msg)
        self.error_text.see(tk.END)

    def _cancel(self):
        """Cancel analysis"""
        self.cancelled = True
        self.cancel_btn.configure(state='disabled', text="Cancelling...")

    def finish(self):
        """Finish analysis"""
        self.status_label.configure(text="Analysis Complete!")
        self.cancel_btn.configure(text="Close", command=self.destroy)

        if self.failed > 0:
            messagebox.showwarning(
                "Analysis Complete with Errors",
                f"Completed with {self.failed} error(s).\nCheck the error log for details."
            )

# ============================================================================
# CODE ANALYZER
# ============================================================================

class PythonCodeAnalyzer(ast.NodeVisitor):
    """Analyzes Python source code using AST with performance optimization"""

    def __init__(self, cache_manager: Optional[CacheManager] = None):
        self.current_class: Optional[str] = None
        self.module_info: Optional[ModuleInfo] = None
        self.all_names: Set[str] = set()
        self.source_lines: List[str] = []
        self.cache_manager = cache_manager
        self.function_calls: Dict[str, Set[str]] = defaultdict(set)

    def analyze_file(self, filepath: str, use_cache: bool = True) -> ModuleInfo:
        """Analyze a single Python file with caching"""
        # Check cache first
        if use_cache and self.cache_manager:
            cached_module = self.cache_manager.get_analysis(filepath)
            if cached_module:
                return cached_module

        # Read file content
        file_content = None
        if use_cache and self.cache_manager:
            cached_content = self.cache_manager.get_file(filepath)
            if cached_content:
                content, lines = cached_content
                file_content = content
                self.source_lines = lines

        if file_content is None:
            try:
                with open(filepath, 'r', encoding='utf-8-sig', errors='ignore') as f:
                    file_content = f.read()
                self.source_lines = file_content.split('\n')

                # Cache file content
                if use_cache and self.cache_manager:
                    self.cache_manager.cache_file(filepath, file_content, self.source_lines)

            except Exception as e:
                raise ValueError(f"Cannot read file {filepath}: {e}")

        # Parse AST
        # try:
        #     tree = ast.parse(file_content, filepath)
        # except SyntaxError as e:
        #     raise ValueError(f"Syntax error in {filepath} at line {e.lineno}: {e.msg}")
        try:
            tree = ast.parse(file_content, filepath)
        except SyntaxError as e:
            # Re-raise with better error message
            raise SyntaxError(f"{e.msg}", (filepath, e.lineno, e.offset, e.text))
        except Exception as e:
            raise ValueError(f"Parse error: {e}")

        # Initialize module info
        module_name = Path(filepath).stem
        self.module_info = ModuleInfo(
            name=module_name,
            path=filepath,
            line_count=len(self.source_lines)
        )

        # Check for main block
        if 'if __name__ == "__main__"' in file_content or \
                'if __name__ == \'__main__\'' in file_content:
            self.module_info.has_main = True

        # First pass: collect all defined names for call resolution
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self.all_names.add(node.name)
            elif isinstance(node, ast.ClassDef):
                self.all_names.add(node.name)
                # Also add method names with class prefix
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        self.all_names.add(f"{node.name}.{item.name}")

        # Second pass: detailed analysis
        self.visit(tree)

        # Resolve function calls
        self._resolve_calls()

        # Cache analysis result
        if use_cache and self.cache_manager:
            self.cache_manager.cache_analysis(filepath, self.module_info)

        return self.module_info

    def analyze_directory(self, dirpath: str, progress_callback=None) -> List[ModuleInfo]:
        """Analyze all Python files in directory with progress reporting"""
        modules = []
        py_files = []

        # Collect all Python files
        for root, dirs, files in os.walk(dirpath):
            # Skip hidden directories and common non-source directories
            dirs[:] = [d for d in dirs if not d.startswith('.') and
                       d not in ('__pycache__', 'venv', 'env', 'node_modules')]

            for file in files:
                if file.endswith('.py') and not file.startswith('.'):
                    py_files.append(os.path.join(root, file))

        total_files = len(py_files)

        # Analyze each file
        for i, filepath in enumerate(py_files):
            if progress_callback:
                progress_callback(i, total_files, os.path.basename(filepath))

            try:
                module = self.analyze_file(filepath)
                modules.append(module)
            except Exception as e:
                print(f"Error analyzing {filepath}: {e}")
                # Continue with other files

        if progress_callback:
            progress_callback(total_files, total_files, "Complete")

        return modules

    def visit_Import(self, node: ast.Import):
        """Handle import statements"""
        for alias in node.names:
            import_name = alias.name
            self.module_info.imports.append(import_name)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        """Handle from ... import statements"""
        module = node.module or ''
        names = []
        for alias in node.names:
            name = alias.name
            names.append(name)
            # Track imported names for call resolution
            if name != '*':
                self.all_names.add(name)

        if module in self.module_info.from_imports:
            self.module_info.from_imports[module].extend(names)
        else:
            self.module_info.from_imports[module] = names

        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef):
        """Handle class definitions"""
        # Extract base classes
        bases = []
        for base in node.bases:
            if isinstance(base, ast.Name):
                bases.append(base.id)
            elif isinstance(base, ast.Attribute):
                bases.append(self._get_full_name(base))
            elif isinstance(base, ast.Subscript):
                # Handle generic types like List[int]
                if isinstance(base.value, ast.Name):
                    bases.append(base.value.id)

        # Extract decorators
        decorators = [self._get_decorator_name(d) for d in node.decorator_list]

        # Check if abstract class
        is_abstract = any('abstract' in d.lower() for d in decorators) or \
                      'ABC' in bases or 'ABCMeta' in str(node.bases)

        # Get docstring
        docstring = ast.get_docstring(node)

        # Create class info
        class_info = ClassInfo(
            name=node.name,
            lineno=node.lineno,
            end_lineno=getattr(node, 'end_lineno', node.lineno),
            bases=bases,
            decorators=decorators,
            docstring=docstring,
            is_abstract=is_abstract
        )

        # Analyze class body
        old_class = self.current_class
        self.current_class = node.name

        for item in node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                method_info = self._analyze_function(item, is_method=True)
                method_info.parent_class = node.name
                class_info.methods.append(method_info)

            elif isinstance(item, ast.Assign):
                # Class attributes
                for target in item.targets:
                    if isinstance(target, ast.Name):
                        class_info.attributes.append(target.id)
                    elif isinstance(target, ast.Tuple):
                        for elt in target.elts:
                            if isinstance(elt, ast.Name):
                                class_info.attributes.append(elt.id)

            elif isinstance(item, ast.AnnAssign):
                # Type-annotated class attributes
                if isinstance(item.target, ast.Name):
                    attr_name = item.target.id
                    if item.annotation:
                        # Could extract type annotation here
                        pass
                    class_info.attributes.append(attr_name)

        self.current_class = old_class
        self.module_info.classes.append(class_info)

        # Continue visiting
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef):
        """Handle function definitions"""
        if self.current_class is None:
            func_info = self._analyze_function(node, is_method=False)
            self.module_info.functions.append(func_info)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        """Handle async function definitions"""
        if self.current_class is None:
            func_info = self._analyze_function(node, is_method=False, is_async=True)
            self.module_info.functions.append(func_info)
        self.generic_visit(node)

    def _analyze_function(self, node, is_method: bool, is_async: bool = False) -> FunctionInfo:
        """Analyze a function or method in detail"""
        # Extract arguments
        args = []
        defaults = []

        for arg in node.args.args:
            args.append(arg.arg)

        # Get default values (for future use)
        for default in node.args.defaults:
            if isinstance(default, ast.Constant):
                defaults.append(default.value)
            else:
                defaults.append(None)

        # Handle *args and **kwargs
        if node.args.vararg:
            args.append(f"*{node.args.vararg.arg}")
        if node.args.kwarg:
            args.append(f"**{node.args.kwarg.arg}")

        # Extract decorators
        decorators = [self._get_decorator_name(d) for d in node.decorator_list]

        # Get docstring
        docstring = ast.get_docstring(node)

        # Extract return type if annotated
        return_type = None
        if node.returns:
            return_type = self._get_annotation_string(node.returns)

        # Calculate cyclomatic complexity
        complexity = self._calculate_complexity(node)

        # Track function calls within this function
        func_name = node.name
        if self.current_class:
            func_name = f"{self.current_class}.{node.name}"

        # Find all function calls
        calls = self._extract_calls(node, func_name)

        return FunctionInfo(
            name=node.name,
            lineno=node.lineno,
            end_lineno=getattr(node, 'end_lineno', node.lineno),
            args=args,
            decorators=decorators,
            docstring=docstring,
            calls=list(calls),
            is_method=is_method,
            is_async=is_async or isinstance(node, ast.AsyncFunctionDef),
            complexity=complexity,
            return_type=return_type
        )

    def _extract_calls(self, node, caller_name: str) -> Set[str]:
        calls = set()
        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                call_name = None
                if isinstance(child.func, ast.Name):
                    call_name = child.func.id
                elif isinstance(child.func, ast.Attribute):
                    if isinstance(child.func.value, ast.Name):
                        obj_name = child.func.value.id
                        method_name = child.func.attr
                        if obj_name in ('self', 'cls'):
                            call_name = f"{self.current_class}.{method_name}" if self.current_class else method_name
                        else:
                            call_name = f"{obj_name}.{method_name}"
                    else:
                        call_name = child.func.attr
                if call_name:
                    calls.add(call_name)
                    self.function_calls[caller_name].add(call_name)

        filtered_calls = set()
        for call in calls:
            if call in self.all_names:
                filtered_calls.add(call)
            elif '.' in call:
                parts = call.split('.')
                if len(parts) == 2:
                    if parts[1] in self.all_names:
                        filtered_calls.add(call)
                    else:
                        # External module call - prefix with EXT:
                        root_mod = parts[0]
                        if root_mod not in ('self', 'cls', 'super') and root_mod[0].islower():
                            filtered_calls.add(f"EXT:{root_mod}")
        return filtered_calls

    def _calculate_complexity(self, node) -> int:
        """Calculate enhanced complexity: (LOC% * vars * external_calls * cyclomatic) / total_LOC"""
        try:
            # Get function lines
            func_lines = getattr(node, 'end_lineno', node.lineno) - node.lineno + 1

            # Count variables
            var_count = 0
            for child in ast.walk(node):
                if isinstance(child, ast.Assign):
                    var_count += len(child.targets)

            # Count external calls
            calls = self._extract_calls(node, node.name if hasattr(node, 'name') else '')
            external_calls = len(calls)

            # Calculate cyclomatic complexity
            cyclomatic = 1  # Base complexity

            for child in ast.walk(node):
                # Decision points
                if isinstance(child, (ast.If, ast.While, ast.For)):
                    cyclomatic += 1
                elif isinstance(child, ast.ExceptHandler):
                    cyclomatic += 1
                elif isinstance(child, (ast.With, ast.AsyncWith)):
                    cyclomatic += 1
                elif isinstance(child, ast.Assert):
                    cyclomatic += 1
                elif isinstance(child, ast.BoolOp):
                    # Each 'and'/'or' adds a branch
                    cyclomatic += len(child.values) - 1
                elif isinstance(child, ast.comprehension):
                    cyclomatic += 1

            # Enhanced complexity formula
            total_lines = len(self.source_lines) if self.source_lines else 1
            loc_percentage = (func_lines / total_lines) * 100 if total_lines > 0 else 1

            var_factor = max(var_count, 1)  # At least 1
            call_factor = max(external_calls, 1)  # At least 1

            # Final complexity: (LOC% * vars * calls * cyclomatic) / total_lines
            enhanced_complexity = (loc_percentage * var_factor * call_factor * cyclomatic) / total_lines

            return max(int(enhanced_complexity), 1)  # At least 1

        except Exception as e:
            print(f"Complexity calculation error: {e}")
            return 1  # Default to 1 on error

    def _resolve_calls(self):
        """Resolve function calls to actual functions"""
        # This method can be expanded to resolve cross-module calls
        pass

    def _get_decorator_name(self, node) -> str:
        """Get decorator name as string"""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            return self._get_full_name(node)
        elif isinstance(node, ast.Call):
            return self._get_decorator_name(node.func)
        return "unknown"

    def _get_full_name(self, node) -> str:
        """Get full name from attribute node"""
        parts = []
        current = node

        while isinstance(current, ast.Attribute):
            parts.append(current.attr)
            current = current.value

        if isinstance(current, ast.Name):
            parts.append(current.id)

        return '.'.join(reversed(parts))

    def _get_annotation_string(self, node) -> str:
        """Convert annotation node to string"""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Constant):
            return str(node.value)
        elif isinstance(node, ast.Attribute):
            return self._get_full_name(node)
        elif isinstance(node, ast.Subscript):
            if isinstance(node.value, ast.Name):
                return f"{node.value.id}[...]"
        return "Any"

# ============================================================================
# BASE CANVAS WITH ZOOM AND PAN
# ============================================================================

class ZoomableCanvas(tk.Canvas):
    """Canvas with zoom, pan, and performance optimizations"""

    def __init__(self, parent, **kwargs):
        # Set defaults for better performance
        kwargs.setdefault('highlightthickness', 0)
        kwargs.setdefault('borderwidth', 0)
        super().__init__(parent, **kwargs)

        self.scale_factor = 1.0
        self.min_scale = 0.1
        self.max_scale = 50.0
        self.pan_start_x = 0
        self.pan_start_y = 0

        # Performance: track visible area
        self.visible_bbox = None
        self._update_visible_area()

        # Bind events
        self._bind_events()

    def _bind_events(self):
        """Bind mouse and keyboard events"""
        # Mouse wheel for zoom
        self.bind('<MouseWheel>', self._on_mousewheel)  # Windows
        self.bind('<Button-4>', self._on_mousewheel)  # Linux scroll up
        self.bind('<Button-5>', self._on_mousewheel)  # Linux scroll down

        # Middle mouse or right mouse for pan
        self.bind('<ButtonPress-2>', self._start_pan)  # Middle mouse
        self.bind('<B2-Motion>', self._do_pan)
        self.bind('<ButtonRelease-2>', self._end_pan)

        self.bind('<ButtonPress-3>', self._start_pan)  # Right mouse
        self.bind('<B3-Motion>', self._do_pan)
        self.bind('<ButtonRelease-3>', self._end_pan)

        # Configure for resize
        self.bind('<Configure>', self._on_resize)

        # Keyboard shortcuts
        self.bind('<Control-0>', lambda e: self.reset_zoom())
        self.bind('<Control-equal>', lambda e: self.zoom_in())
        self.bind('<Control-minus>', lambda e: self.zoom_out())

    def _on_mousewheel(self, event):
        """Handle mouse wheel for zooming"""
        # Get mouse position in canvas coordinates
        x = self.canvasx(event.x)
        y = self.canvasy(event.y)

        # Determine zoom direction and scale
        if event.num == 5 or (hasattr(event, 'delta') and event.delta < 0):
            scale = 0.9  # Zoom out
        else:
            scale = 1.1  # Zoom in

        # Check limits
        new_scale = self.scale_factor * scale
        if new_scale < self.min_scale or new_scale > self.max_scale:
            return

        # Apply scale
        self.scale_factor = new_scale
        self.scale('all', x, y, scale, scale)

        # Update scroll region
        self._update_scroll_region()
        self._update_visible_area()

    def _start_pan(self, event):
        """Start panning operation"""
        self.scan_mark(event.x, event.y)
        self.pan_start_x = event.x
        self.pan_start_y = event.y
        # Change cursor
        self.configure(cursor="fleur")

    def _do_pan(self, event):
        """Perform panning"""
        self.scan_dragto(event.x, event.y, gain=1)
        self._update_visible_area()

    def _end_pan(self, event):
        """End panning operation"""
        self.configure(cursor="")

    def _on_resize(self, event):
        """Handle canvas resize"""
        self._update_visible_area()

    def _update_visible_area(self):
        """Update the visible bounding box for optimization"""
        try:
            x1 = self.canvasx(0)
            y1 = self.canvasy(0)
            x2 = self.canvasx(self.winfo_width())
            y2 = self.canvasy(self.winfo_height())
            self.visible_bbox = (x1, y1, x2, y2)
        except:
            self.visible_bbox = None

    def _update_scroll_region(self):
        """Update scroll region after scaling"""
        bbox = self.bbox('all')
        if bbox:
            # Add padding
            padding = 50
            self.configure(scrollregion=(
                bbox[0] - padding,
                bbox[1] - padding,
                bbox[2] + padding,
                bbox[3] + padding
            ))

    def is_visible(self, bbox) -> bool:
        """Check if item is in visible area"""
        if not self.visible_bbox or not bbox:
            return True

        x1, y1, x2, y2 = self.visible_bbox
        ix1, iy1, ix2, iy2 = bbox

        # Check for intersection
        return not (ix2 < x1 or ix1 > x2 or iy2 < y1 or iy1 > y2)

    def zoom_in(self):
        """Zoom in by fixed amount"""
        cx = self.winfo_width() / 2
        cy = self.winfo_height() / 2
        x = self.canvasx(cx)
        y = self.canvasy(cy)

        scale = 1.2
        if self.scale_factor * scale <= self.max_scale:
            self.scale_factor *= scale
            self.scale('all', x, y, scale, scale)
            self._update_scroll_region()

    def zoom_out(self):
        """Zoom out by fixed amount"""
        cx = self.winfo_width() / 2
        cy = self.winfo_height() / 2
        x = self.canvasx(cx)
        y = self.canvasy(cy)

        scale = 0.8
        if self.scale_factor * scale >= self.min_scale:
            self.scale_factor *= scale
            self.scale('all', x, y, scale, scale)
            self._update_scroll_region()

    def reset_zoom(self):
        """Reset zoom to 1.0"""
        if self.scale_factor != 1.0:
            scale = 1.0 / self.scale_factor
            cx = self.winfo_width() / 2
            cy = self.winfo_height() / 2
            x = self.canvasx(cx)
            y = self.canvasy(cy)

            self.scale('all', x, y, scale, scale)
            self.scale_factor = 1.0
            self._update_scroll_region()

    def fit_to_view(self):
        """Fit all content in view"""
        bbox = self.bbox('all')
        if not bbox:
            return

        # Get canvas dimensions
        canvas_width = self.winfo_width()
        canvas_height = self.winfo_height()

        if canvas_width <= 1 or canvas_height <= 1:
            return

        # Calculate content dimensions
        content_width = bbox[2] - bbox[0]
        content_height = bbox[3] - bbox[1]

        if content_width <= 0 or content_height <= 0:
            return

        # Calculate scale to fit
        scale_x = canvas_width / content_width * 0.9
        scale_y = canvas_height / content_height * 0.9
        scale = min(scale_x, scale_y, 1.0)

        # Reset and apply new scale
        self.reset_zoom()

        if scale != 1.0:
            cx = (bbox[0] + bbox[2]) / 2
            cy = (bbox[1] + bbox[3]) / 2
            self.scale('all', cx, cy, scale, scale)
            self.scale_factor = scale

        # Center content
        self._center_content()

    def _center_content(self):
        """Center content in canvas"""
        self.update_idletasks()
        bbox = self.bbox('all')
        if not bbox:
            return

        canvas_width = self.winfo_width()
        canvas_height = self.winfo_height()

        content_width = bbox[2] - bbox[0]
        content_height = bbox[3] - bbox[1]

        # Calculate offsets to center
        x_offset = (canvas_width - content_width) / 2 - bbox[0]
        y_offset = (canvas_height - content_height) / 2 - bbox[1]

        # Move all items
        self.move('all', x_offset, y_offset)
        self._update_scroll_region()


# ============================================================================
# OPTIMIZED TREE VIEW WITH LAZY LOADING
# ============================================================================

class OptimizedTreeView(ttk.Frame):
    """Tree view with lazy loading and single-click expand"""

    def __init__(self, parent, on_select_callback=None):
        super().__init__(parent)

        self.on_select_callback = on_select_callback
        self.item_data = {}  # item_id -> (type, data)
        self.lazy_items = {}  # item_id -> lazy load info
        self.expanded_items = set()  # Track expanded state
        self.is_loaded = False

        # Create UI
        self._create_widgets()
        self._create_context_menu()
        self._bind_events()

        # Configure tags for styling
        self._configure_tags()

    def _create_widgets(self):
        """Create tree and scrollbars"""
        # Container frame
        container = ttk.Frame(self)
        container.pack(fill=tk.BOTH, expand=True)

        # Create treeview
        self.tree = ttk.Treeview(
            container,
            show='tree headings',
            selectmode='browse'
        )

        # Define columns
        self.tree['columns'] = ('type', 'lines', 'complexity')

        # Configure columns
        self.tree.heading('#0', text='Name', anchor='w')
        self.tree.heading('type', text='Type', anchor='w')
        self.tree.heading('lines', text='Lines', anchor='w')
        self.tree.heading('complexity', text='Complex', anchor='w')

        self.tree.column('#0', width=400, minwidth=200, stretch=True)
        self.tree.column('type', width=80, minwidth=60, stretch=False)
        self.tree.column('lines', width=80, minwidth=60, stretch=False)
        self.tree.column('complexity', width=60, minwidth=40, stretch=False)

        # Scrollbars
        vsb = ttk.Scrollbar(container, orient='vertical', command=self.tree.yview)
        hsb = ttk.Scrollbar(container, orient='horizontal', command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        # Grid layout
        self.tree.grid(row=0, column=0, sticky='nsew')
        vsb.grid(row=0, column=1, sticky='ns')
        hsb.grid(row=1, column=0, sticky='ew')

        container.grid_rowconfigure(0, weight=1)
        container.grid_columnconfigure(0, weight=1)

        # Search frame
        search_frame = ttk.Frame(self)
        search_frame.pack(fill=tk.X, padx=5, pady=2)

        ttk.Label(search_frame, text="🔍").pack(side=tk.LEFT)
        self.search_var = tk.StringVar()
        self.search_entry = ttk.Entry(search_frame, textvariable=self.search_var)
        self.search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        self.search_entry.bind('<Return>', lambda e: self.search())
        self.search_entry.bind('<KeyRelease>', self._on_search_key)

        ttk.Button(search_frame, text="Clear",
                   command=self.clear_search).pack(side=tk.LEFT)

    def _configure_tags(self):
        config = ConfigManager()
        font_size = config.get_int('Display', 'tree_font_size', 9)
        self.tree.tag_configure('module', font=('Segoe UI', font_size, 'bold'))
        self.tree.tag_configure('class', font=('Segoe UI', font_size, 'bold'))
        self.tree.tag_configure('function', font=('Segoe UI', font_size))
        self.tree.tag_configure('method', font=('Segoe UI', font_size))
        self.tree.tag_configure('high_complexity', background='#4A1010')
        self.tree.tag_configure('search_match', background='#5A5A00', foreground='#FFFFFF')
        self.tree.tag_configure('import', font=('Segoe UI', font_size - 1, 'italic'))

    def _reconfigure_tags(self, t: dict):
        is_dark = t['bg'] < '#888888'
        fg_color = t['fg']
        self.tree.tag_configure('module', foreground=fg_color)
        self.tree.tag_configure('class', foreground=fg_color)
        self.tree.tag_configure('function', foreground=fg_color)
        self.tree.tag_configure('method', foreground=fg_color)
        self.tree.tag_configure('import', foreground=fg_color)
        if is_dark:
            self.tree.tag_configure('search_match', background='#5A5A00', foreground='#FFFFFF')
            self.tree.tag_configure('high_complexity', background='#4A1010')
        else:
            self.tree.tag_configure('search_match', background='#FFFF00', foreground='#000000')
            self.tree.tag_configure('high_complexity', background='#FFCCCC')
        try:
            self.tree.configure(style='Treeview')
            style = ttk.Style()
            style.configure('Treeview', background=t['entry_bg'], foreground=t['entry_fg'],
                            fieldbackground=t['entry_bg'])
            style.map('Treeview', background=[('selected', t['select'])],
                      foreground=[('selected', t['entry_fg'])])
        except:
            pass


    def _create_context_menu(self):
        """Create right-click context menu"""
        self.context_menu = tk.Menu(self.tree, tearoff=0)
        self.context_menu.add_command(label="📋 Copy Name",
                                      command=self._copy_name,
                                      accelerator="Ctrl+C")
        self.context_menu.add_command(label="📁 Copy Path",
                                      command=self._copy_path)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="📍 Go to Definition",
                                      command=self._goto_definition,
                                      accelerator="Enter")
        self.context_menu.add_separator()
        self.context_menu.add_command(label="➕ Expand All Children",
                                      command=self._expand_all_children)
        self.context_menu.add_command(label="➖ Collapse All Children",
                                      command=self._collapse_all_children)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="📊 Show Info",
                                      command=self._show_info)

    def _bind_events(self):
        """Bind tree events"""
        # Single click for expand/collapse
        self.tree.bind('<Button-1>', self._on_single_click)

        # Selection change
        self.tree.bind('<<TreeviewSelect>>', self._on_select)

        # Double click for goto
        self.tree.bind('<Double-Button-1>', self._on_double_click)

        # Right click for context menu
        self.tree.bind('<Button-3>', self._on_right_click)

        # Keyboard shortcuts
        self.tree.bind('<Return>', lambda e: self._goto_definition())
        self.tree.bind('<Control-c>', lambda e: self._copy_name())
        self.tree.bind('<space>', self._on_space_key)

        # Track item expansion
        self.tree.bind('<<TreeviewOpen>>', self._on_item_open)
        self.tree.bind('<<TreeviewClose>>', self._on_item_close)

    def _on_single_click(self, event):
        """Handle single click for expand/collapse"""
        region = self.tree.identify_region(event.x, event.y)
        if region == 'tree':
            item = self.tree.identify_row(event.y)
            if item:
                # Toggle expand/collapse
                if self.tree.item(item, 'open'):
                    self.tree.item(item, open=False)
                else:
                    # Check for lazy loading
                    if item in self.lazy_items and not self.lazy_items[item]['loaded']:
                        self._load_lazy_item(item)
                    self.tree.item(item, open=True)
                return 'break'  # Prevent default behavior

    def _on_select(self, event):
        """Handle selection change"""
        selected = self.tree.selection()
        if selected and self.on_select_callback:
            item_id = selected[0]
            if item_id in self.item_data:
                # Call callback with item data
                self.on_select_callback(self.item_data[item_id])

    def _on_double_click(self, event):
        """Handle double click"""
        self._goto_definition()

    def _on_right_click(self, event):
        """Show context menu"""
        item = self.tree.identify_row(event.y)
        if item:
            self.tree.selection_set(item)
            self.tree.focus(item)
            try:
                self.context_menu.post(event.x_root, event.y_root)
            finally:
                self.context_menu.grab_release()

    def _on_space_key(self, event):
        """Toggle expand/collapse with spacebar"""
        selected = self.tree.selection()
        if selected:
            item = selected[0]
            if self.tree.item(item, 'open'):
                self.tree.item(item, open=False)
            else:
                if item in self.lazy_items and not self.lazy_items[item]['loaded']:
                    self._load_lazy_item(item)
                self.tree.item(item, open=True)

    def _on_item_open(self, event):
        """Track item expansion"""
        selected = self.tree.selection()
        if selected:
            self.expanded_items.add(selected[0])

    def _on_item_close(self, event):
        """Track item collapse"""
        selected = self.tree.selection()
        if selected:
            self.expanded_items.discard(selected[0])

    def _on_search_key(self, event):
        """Live search as user types"""
        if len(self.search_var.get()) >= 2:
            self.search()

    def _copy_name(self):
        """Copy item name to clipboard"""
        selected = self.tree.selection()
        if selected:
            item_text = self.tree.item(selected[0], 'text')
            # Remove icon prefix
            name = re.sub(r'^[^\w]*', '', item_text).strip()
            self.clipboard_clear()
            self.clipboard_append(name)

    def _copy_path(self):
        """Copy file path to clipboard"""
        selected = self.tree.selection()
        if selected and selected[0] in self.item_data:
            item_type, data = self.item_data[selected[0]]
            path = None

            if item_type == 'module' and hasattr(data, 'path'):
                path = data.path
            elif hasattr(data, 'parent_module'):
                path = data.parent_module.path

            if path:
                self.clipboard_clear()
                self.clipboard_append(path)

    def _goto_definition(self):
        """Go to selected item definition"""
        if self.on_select_callback:
            selected = self.tree.selection()
            if selected and selected[0] in self.item_data:
                self.on_select_callback(self.item_data[selected[0]])

    def _expand_all_children(self):
        """Expand all children of selected item"""
        selected = self.tree.selection()
        if selected:
            self._expand_recursive(selected[0])

    def _collapse_all_children(self):
        """Collapse all children of selected item"""
        selected = self.tree.selection()
        if selected:
            self._collapse_recursive(selected[0])

    def _expand_recursive(self, item):
        """Recursively expand item and children"""
        # Load lazy items first
        if item in self.lazy_items and not self.lazy_items[item]['loaded']:
            self._load_lazy_item(item)

        self.tree.item(item, open=True)
        for child in self.tree.get_children(item):
            self._expand_recursive(child)

    def _collapse_recursive(self, item):
        """Recursively collapse item and children"""
        for child in self.tree.get_children(item):
            self._collapse_recursive(child)
        self.tree.item(item, open=False)

    def _show_info(self):
        """Show detailed info about selected item"""
        selected = self.tree.selection()
        if selected and selected[0] in self.item_data:
            item_type, data = self.item_data[selected[0]]

            info_lines = [f"Type: {item_type.title()}"]

            if hasattr(data, 'name'):
                info_lines.append(f"Name: {data.name}")
            if hasattr(data, 'lineno'):
                info_lines.append(f"Line: {data.lineno}-{data.end_lineno}")
            if hasattr(data, 'complexity'):
                info_lines.append(f"Complexity: {data.complexity}")
            if hasattr(data, 'docstring') and data.docstring:
                doc = data.docstring[:100]
                if len(data.docstring) > 100:
                    doc += "..."
                info_lines.append(f"Doc: {doc}")

            messagebox.showinfo("Item Info", "\n".join(info_lines))

    # ============================================================================
    # TREE VIEW METHODS (Continuation)
    # ============================================================================

    def load_modules(self, modules: List[ModuleInfo], lazy: bool = True):
        """Load modules into tree with optional lazy loading"""
        # Clear existing items
        self.tree.delete(*self.tree.get_children())
        self.item_data.clear()
        self.lazy_items.clear()
        self.expanded_items.clear()
        self.is_loaded = True

        if not modules:
            self.tree.insert('', 'end', text='No modules loaded', tags=('info',))
            return

        # Sort modules by name
        sorted_modules = sorted(modules, key=lambda m: m.name.lower())

        # Add modules to tree
        for module in sorted_modules:
            if lazy:
                self._add_module_lazy(module)
            else:
                self._add_module_full(module)

    def _add_module_lazy(self, module: ModuleInfo):
        module_id = self.tree.insert(
            '', 'end',
            text=f"📁 {module.name}",
            values=('Module', str(module.line_count), ''),
            tags=('module',),
            open=False
        )
        self.item_data[module_id] = ('module', module)
        placeholder_id = self.tree.insert(module_id, 'end', text='Loading...')
        self.lazy_items[module_id] = {
            'loaded': False,
            'placeholder': placeholder_id,
            'module': module
        }

    def _add_module_full(self, module: ModuleInfo):
        module_id = self.tree.insert(
            '', 'end',
            text=f"📁 {module.name}",
            values=('Module', str(module.line_count), ''),
            tags=('module',),
            open=False
        )
        self.item_data[module_id] = ('module', module)
        self._add_module_contents(module_id, module)

    def _load_lazy_item(self, item_id: str):
        """Load children for a lazy item"""
        if item_id not in self.lazy_items:
            return

        lazy_info = self.lazy_items[item_id]
        if lazy_info['loaded']:
            return

        # Remove placeholder
        try:
            self.tree.delete(lazy_info['placeholder'])
        except:
            pass

        # Load actual children
        module = lazy_info['module']
        self._add_module_contents(item_id, module)

        # Mark as loaded
        lazy_info['loaded'] = True

    def _add_module_contents(self, parent_id: str, module: ModuleInfo):
        """Add module contents to tree"""
        # Add imports (collapsed by default)
        if module.imports or module.from_imports:
            imports_id = self.tree.insert(
                parent_id, 'end',
                text=f"📥 Imports ({len(module.imports) + sum(len(v) for v in module.from_imports.values())})",
                values=('', '', ''),
                tags=('import',)
            )

            # Add individual imports
            for imp in module.imports[:10]:  # Limit display
                self.tree.insert(
                    imports_id, 'end',
                    text=f"  import {imp}",
                    values=('import', '', ''),
                    tags=('import',)
                )

            for from_mod, names in list(module.from_imports.items())[:10]:
                for name in names[:5]:
                    self.tree.insert(
                        imports_id, 'end',
                        text=f"  from {from_mod} import {name}",
                        values=('from', '', ''),
                        tags=('import',)
                    )

        # Add classes
        for cls in module.classes:
            self._add_class(parent_id, cls, module)

        # Add functions
        for func in module.functions:
            self._add_function(parent_id, func, module, is_method=False)

    def _add_class(self, parent_id: str, cls: ClassInfo, module: ModuleInfo):
        """Add class to tree with lazy loading for methods"""
        # Build class text
        bases_str = f" ({', '.join(cls.bases)})" if cls.bases else ""
        class_text = f"🔷 {cls.name}{bases_str}"

        # Add decorators indicator
        if cls.decorators:
            class_text = f"@ {class_text}"

        # Add abstract indicator
        if cls.is_abstract:
            class_text = f"[A] {class_text}"

        lines = f"{cls.lineno}-{cls.end_lineno}"

        # Create class node - FIX: Convert tags to tuple properly
        tags_list = ['class']

        # Create class node
        class_id = self.tree.insert(
            parent_id, 'end',
            text=class_text,
            values=('Class', lines, ''),
            tags=tuple(tags_list)  # Must be tuple, not list
        )

        # Store data with module reference
        cls.parent_module = module
        self.item_data[class_id] = ('class', cls)

        # Add attributes if present
        if cls.attributes:
            attrs_id = self.tree.insert(
                class_id, 'end',
                text=f"📋 Attributes ({len(cls.attributes)})",
                values=('', '', ''),
                tags=('attributes',)
            )

            for attr in cls.attributes[:20]:
                self.tree.insert(
                    attrs_id, 'end',
                    text=f"  {attr}",
                    values=('attr', '', ''),
                    tags=('attribute',)
                )

        # Add methods - DON'T use lazy loading for methods to avoid recursion
        for method in cls.methods:
            self._add_function(class_id, method, module, is_method=True)

    def _add_function(self, parent_id: str, func: FunctionInfo,
                      module: ModuleInfo, is_method: bool = False):
        """Add function/method to tree"""
        # Choose icon based on type
        if func.is_async:
            icon = "⚡"
        elif is_method:
            if func.name.startswith('_'):
                icon = "🔒"  # Private method
            else:
                icon = "🔸"
        else:
            icon = "🔹"

        # Build function signature
        args_str = self._build_args_string(func.args)
        func_text = f"{icon} {func.name}({args_str})"

        # Add decorators indicator
        if func.decorators:
            func_text = f"@ {func_text}"

        # Add return type if available
        if func.return_type:
            func_text += f" -> {func.return_type}"

        lines = f"{func.lineno}-{func.end_lineno}"

        # Determine tags
        tags = ['method' if is_method else 'function']
        if func.complexity > 10:
            tags.append('high_complexity')

        # Create function node
        func_id = self.tree.insert(
            parent_id, 'end', text=func_text,
            values=('Method' if is_method else 'Function',
                    lines,
                    str(func.complexity)),
            tags=tuple(tags)
        )

        # Add complexity tooltip on hover (will implement in bind event)

        # Store data with module reference
        func_data = func
        func_data.parent_module = module
        self.item_data[func_id] = ('function', func_data)

        # Add calls if present
        if func.calls:
            calls_id = self.tree.insert(
                func_id, 'end',
                text=f"📞 Calls ({len(func.calls)})",
                values=('', '', ''),
                tags=('calls',)
            )

            for call in func.calls[:10]:  # Limit display
                # self.tree.insert(
                #     calls_id, 'end',
                #     text=f"  → {call}",
                #     values=('call', '', ''),
                #     tags=('call',)
                # )
                self.tree.insert(calls_id, 'end', text=f"  → {module.name}:{call}",
                                 values=('call', '', ''))

            if len(func.calls) > 10:
                self.tree.insert(
                    calls_id, 'end',
                    text=f"  ... and {len(func.calls) - 10} more",
                    values=('', '', ''),
                    tags=('info',)
                )

    def _build_args_string(self, args: List[str]) -> str:
        """Build formatted argument string"""
        if not args:
            return ""

        # Filter out 'self' and 'cls' for methods
        filtered_args = [a for a in args if a not in ('self', 'cls')]

        if len(filtered_args) <= 3:
            return ', '.join(filtered_args)
        else:
            return f"{', '.join(filtered_args[:2])}, ..."

    def _show_complexity_tooltip(self, event):
        """Show complexity calculation details on hover"""
        item = self.tree.identify_row(event.y)
        if item and item in self.item_data:
            item_type, data = self.item_data[item]
            if hasattr(data, 'complexity'):
                tooltip_text = (
                    f"Complexity: {data.complexity}\n"
                    f"Formula: (LOC% × vars × calls × decisions) ÷ total_lines\n"
                    f"Lines: {data.end_lineno - data.lineno}\n"
                    f"Calls: {len(data.calls)}"
                )
                # Create tooltip (simplified - add to existing tooltip system)

    def search(self, query: str = None):
        """Search and highlight matching items"""
        if query is None:
            query = self.search_var.get()

        if not query:
            self.clear_search()
            return

        query_lower = query.lower()
        matches = []

        # Remove previous search highlights
        for item in self._get_all_items():
            tags = list(self.tree.item(item, 'tags'))
            if 'search_match' in tags:
                tags.remove('search_match')
                self.tree.item(item, tags=tags)

        # Search all items
        for item in self._get_all_items():
            item_text = self.tree.item(item, 'text').lower()
            if query_lower in item_text:
                # Highlight match
                tags = list(self.tree.item(item, 'tags'))
                tags.append('search_match')
                self.tree.item(item, tags=tags)
                matches.append(item)

                # Ensure item is visible
                self._make_visible(item)

        # Select first match
        if matches:
            self.tree.selection_set(matches[0])
            self.tree.focus(matches[0])
            self.tree.see(matches[0])

        # Update status
        self.search_entry.configure(style='Found.TEntry' if matches else 'NotFound.TEntry')

    def clear_search(self):
        """Clear search highlighting"""
        self.search_var.set('')

        for item in self._get_all_items():
            tags = list(self.tree.item(item, 'tags'))
            if 'search_match' in tags:
                tags.remove('search_match')
                self.tree.item(item, tags=tags)

        self.search_entry.configure(style='TEntry')

    def _get_all_items(self, item=''):
        """Get all tree items recursively"""
        items = []
        children = self.tree.get_children(item)
        for child in children:
            items.append(child)
            items.extend(self._get_all_items(child))
        return items

    def _make_visible(self, item):
        """Ensure item is visible by expanding parents"""
        parent = self.tree.parent(item)
        if parent:
            self._make_visible(parent)
            self.tree.item(parent, open=True)


# ============================================================================
# OPTIMIZED MIND MAP VISUALIZATION
# ============================================================================

# ============================================================================
# OPTIMIZED MIND MAP VISUALIZATION
# ============================================================================

class OptimizedMindMap(ttk.Frame):
    """Mind map with hierarchical layout and call relationships"""

    def __init__(self, parent, on_select_callback=None):
        super().__init__(parent)

        self.on_select_callback = on_select_callback
        self.nodes = {}  # node_id -> node_info
        self.edges = []  # (source, target, edge_type)
        self.node_positions = {}  # node_id -> (x, y)
        self.selected_node = None
        self.is_loaded = False
        self._tooltip_win = None
        self._tooltip_node_id = None

        # Visual settings
        self.node_colors = {
            'project': '#2E86AB',
            'module': '#3498DB',
            'class': '#9B59B6',
            'function': '#F39C12',
            'method': '#E74C3C',
            'main': '#27AE60',
            'external': '#7F8C8D'
        }

        self._create_widgets()
        self._bind_events()

    def _create_widgets(self):
        """Create canvas and controls"""
        # Control panel
        controls = ttk.Frame(self)
        controls.pack(side=tk.TOP, fill=tk.X, padx=5, pady=2)

        # Zoom controls
        ttk.Label(controls, text="Zoom:").pack(side=tk.LEFT, padx=5)

        self.zoom_var = tk.IntVar(value=100)
        self.zoom_slider = ttk.Scale(
            controls,
            from_=10, to=200,
            orient=tk.HORIZONTAL,
            variable=self.zoom_var,
            command=self._on_zoom_change,
            length=150
        )
        self.zoom_slider.pack(side=tk.LEFT)

        self.zoom_label = ttk.Label(controls, text="100%")
        self.zoom_label.pack(side=tk.LEFT, padx=5)

        ttk.Button(controls, text="Fit", command=self._fit_to_view).pack(side=tk.LEFT, padx=5)
        ttk.Button(controls, text="Reset", command=self._reset_view).pack(side=tk.LEFT)

        ttk.Separator(controls, orient='vertical').pack(side=tk.LEFT, fill='y', padx=10)

        # Layout options
        ttk.Label(controls, text="Layout:").pack(side=tk.LEFT, padx=5)

        self.layout_var = tk.StringVar(value='hierarchical')
        ttk.Radiobutton(controls, text="Hierarchical",
                        variable=self.layout_var, value='hierarchical',
                        command=self._relayout).pack(side=tk.LEFT)
        ttk.Radiobutton(controls, text="Radial",
                        variable=self.layout_var, value='radial',
                        command=self._relayout).pack(side=tk.LEFT)

        ttk.Separator(controls, orient='vertical').pack(side=tk.LEFT, fill='y', padx=10)

        # Show options
        self.show_calls_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(controls, text="Show Calls",
                        variable=self.show_calls_var,
                        command=self._update_display).pack(side=tk.LEFT, padx=5)

        # Canvas
        self.canvas = ZoomableCanvas(
            self,
            bg='#1E1E1E',
            highlightthickness=0
        )
        self.canvas.pack(fill=tk.BOTH, expand=True)

        # Tooltip
        self.tooltip = None

    def _bind_events(self):
        self.canvas.bind('<Button-1>', self._on_click)
        self.canvas.bind('<Motion>', self._on_motion)
        self.canvas.bind('<Leave>', self._hide_node_tooltip)

    def _on_zoom_change(self, value):
        """Handle zoom slider change"""
        zoom = float(value)
        self.zoom_label.configure(text=f"{int(zoom)}%")

        # Calculate scale factor
        current_scale = getattr(self.canvas, 'scale_factor', 1.0)
        new_scale = zoom / 100

        if current_scale != 0:
            scale_change = new_scale / current_scale
        else:
            scale_change = new_scale

        if abs(scale_change - 1.0) > 0.01:  # Only scale if significant change
            # Apply scaling
            try:
                cx = self.canvas.winfo_width() / 2
                cy = self.canvas.winfo_height() / 2

                if cx > 0 and cy > 0:
                    canvas_x = self.canvas.canvasx(cx)
                    canvas_y = self.canvas.canvasy(cy)

                    self.canvas.scale('all', canvas_x, canvas_y, scale_change, scale_change)
                    self.canvas.scale_factor = new_scale

                    # Update scroll region
                    self.canvas._update_scroll_region()
            except:
                pass

    def _fit_to_view(self):
        """Fit graph to canvas view"""
        try:
            if hasattr(self.canvas, 'fit_to_view'):
                self.canvas.fit_to_view()
                # Update zoom slider
                self.zoom_var.set(int(self.canvas.scale_factor * 100))
                self.zoom_label.configure(text=f"{int(self.canvas.scale_factor * 100)}%")
        except:
            pass

    def _reset_view(self):
        """Reset to default view"""
        try:
            if hasattr(self.canvas, 'reset_zoom'):
                self.canvas.reset_zoom()
            self.zoom_var.set(100)
            self.zoom_label.configure(text="100%")

            # Re-center
            if hasattr(self.canvas, '_center_content'):
                self.canvas._center_content()
        except:
            pass

    def _relayout(self):
        """Re-layout graph with selected algorithm"""
        if not self.nodes:
            return

        # Clear positions
        self.node_positions.clear()

        # Apply selected layout
        if self.layout_var.get() == 'hierarchical':
            self._hierarchical_layout()
        else:
            self._radial_layout()

        # Redraw
        self._draw_graph()

        # Fit to view
        self.after(100, self._fit_to_view)

    def _update_display(self):
        """Update display based on show options"""
        if self.nodes:
            self._draw_graph()

    def load_modules(self, modules: List[ModuleInfo]):
        """Load modules and create mind map"""
        if not modules:
            return

        self.is_loaded = True
        self.nodes.clear()
        self.edges.clear()
        self.node_positions.clear()

        # Build graph structure
        self._build_graph(modules)

        # Calculate layout
        if self.layout_var.get() == 'hierarchical':
            self._hierarchical_layout()
        else:
            self._radial_layout()

        # Draw graph
        self._draw_graph()

        # Fit to view
        self.after(100, self._fit_to_view)

    def _build_graph(self, modules: List[ModuleInfo]):
        main_modules = [m.name for m in modules if m.has_main]
        self.nodes['__root__'] = {'type': 'project', 'label': 'Project', 'data': None, 'size': 40}

        external_nodes_added = set()

        for module in modules:
            module_id = f"module_{module.name}"
            node_type = 'main' if module.name in main_modules else 'module'
            self.nodes[module_id] = {'type': node_type, 'label': module.name, 'data': module, 'size': 35 if node_type == 'main' else 30}
            self.edges.append(('__root__', module_id, 'contains'))

            for cls in module.classes[:20]:
                class_id = f"class_{module.name}_{cls.name}"
                self.nodes[class_id] = {'type': 'class', 'label': cls.name, 'data': cls, 'size': 25}
                self.edges.append((module_id, class_id, 'contains'))

                important_methods = [m for m in cls.methods if not m.name.startswith('_') or m.name in ('__init__', '__str__')][:10]
                for method in important_methods:
                    method_id = f"method_{module.name}_{cls.name}_{method.name}"
                    self.nodes[method_id] = {'type': 'method', 'label': f"{module.name}:{cls.name}:{method.name}", 'data': method, 'size': 15}
                    self.edges.append((class_id, method_id, 'contains'))
                    for call in method.calls:
                        if call.startswith('EXT:'):
                            ext_name = call[4:]
                            ext_id = f"ext_{ext_name}"
                            if ext_id not in external_nodes_added:
                                self.nodes[ext_id] = {'type': 'external', 'label': ext_name, 'data': None, 'size': 18}
                                external_nodes_added.add(ext_id)
                            self.edges.append((method_id, ext_id, 'calls'))
                        else:
                            call_id = self._resolve_call_id(call, module.name)
                            if call_id and call_id in self.nodes:
                                self.edges.append((method_id, call_id, 'calls'))

            for func in module.functions[:15]:
                func_id = f"func_{module.name}_{func.name}"
                self.nodes[func_id] = {'type': 'function', 'label': f"{module.name}:{func.name}", 'data': func, 'size': 20}
                self.edges.append((module_id, func_id, 'contains'))
                for call in func.calls:
                    if call.startswith('EXT:'):
                        ext_name = call[4:]
                        ext_id = f"ext_{ext_name}"
                        if ext_id not in external_nodes_added:
                            self.nodes[ext_id] = {'type': 'external', 'label': ext_name, 'data': None, 'size': 18}
                            external_nodes_added.add(ext_id)
                        self.edges.append((func_id, ext_id, 'calls'))
                    else:
                        call_id = self._resolve_call_id(call, module.name)
                        if call_id and call_id in self.nodes:
                            self.edges.append((func_id, call_id, 'calls'))

    def _resolve_call_id(self, call_name: str, current_module: str) -> Optional[str]:
        """Resolve a call name to a node ID"""
        # Try direct function name
        func_id = f"func_{current_module}_{call_name}"
        if func_id in self.nodes:
            return func_id

        # Try class.method format
        if '.' in call_name:
            parts = call_name.split('.')
            if len(parts) == 2:
                class_name, method_name = parts
                method_id = f"method_{current_module}_{class_name}_{method_name}"
                if method_id in self.nodes:
                    return method_id

        return None

    def _hierarchical_layout(self):
        """Calculate hierarchical top-to-bottom layout"""
        if not self.nodes:
            return

        # Parameters
        level_height = 120
        min_node_spacing = 80

        # Build adjacency lists
        children = defaultdict(list)
        parents = defaultdict(list)

        for source, target, edge_type in self.edges:
            if edge_type == 'contains':
                children[source].append(target)
                parents[target].append(source)

        # Find root nodes
        roots = []
        for node_id in self.nodes:
            if node_id not in parents or not parents[node_id]:
                roots.append(node_id)

        if not roots:
            roots = ['__root__'] if '__root__' in self.nodes else [list(self.nodes.keys())[0]]

        # Calculate levels using BFS
        levels = []
        visited = set()
        current_level = roots

        while current_level:
            levels.append(current_level)
            visited.update(current_level)

            next_level = []
            for node_id in current_level:
                for child in children.get(node_id, []):
                    if child not in visited:
                        next_level.append(child)

            current_level = next_level

        # Add any unvisited nodes
        unvisited = set(self.nodes.keys()) - visited
        if unvisited:
            levels.append(list(unvisited))

        # Position nodes level by level
        y_offset = 50

        for level_idx, level_nodes in enumerate(levels):
            y = y_offset + level_idx * level_height

            # Calculate width needed for this level
            level_width = len(level_nodes) * min_node_spacing

            # Position nodes horizontally
            x_start = 600 - level_width / 2  # Center around x=600

            for i, node_id in enumerate(level_nodes):
                x = x_start + i * min_node_spacing + min_node_spacing / 2
                self.node_positions[node_id] = [x, y]

    def _radial_layout(self):
        """Calculate radial layout with root at center"""
        if not self.nodes:
            return

        # Center position
        center_x, center_y = 600, 400

        # Build tree structure
        children = defaultdict(list)
        for source, target, edge_type in self.edges:
            if edge_type == 'contains':
                children[source].append(target)

        # Find root
        root = '__root__' if '__root__' in self.nodes else list(self.nodes.keys())[0]

        # Position root at center
        self.node_positions[root] = [center_x, center_y]

        # Position nodes in rings
        visited = {root}
        current_ring = [root]
        ring_radius = 100

        while current_ring:
            next_ring = []

            for node_id in current_ring:
                for child in children.get(node_id, []):
                    if child not in visited:
                        next_ring.append(child)
                        visited.add(child)

            if next_ring:
                # Calculate positions for this ring
                angle_step = 2 * math.pi / len(next_ring)

                for i, node_id in enumerate(next_ring):
                    angle = i * angle_step
                    x = center_x + ring_radius * math.cos(angle)
                    y = center_y + ring_radius * math.sin(angle)
                    self.node_positions[node_id] = [x, y]

                ring_radius += 120
                current_ring = next_ring
            else:
                break

    def _draw_graph(self):
        """Draw the mind map"""
        self.canvas.delete('all')

        if not self.nodes:
            return

        # Draw edges first
        if self.show_calls_var.get():
            self._draw_edges()
        else:
            self._draw_edges(edge_types=['contains'])

        # Draw nodes
        self._draw_nodes()

    def _draw_edges(self, edge_types=None):
        """Draw edges between nodes"""
        for source, target, edge_type in self.edges:
            if edge_types and edge_type not in edge_types:
                continue

            if source not in self.node_positions or target not in self.node_positions:
                continue

            x1, y1 = self.node_positions[source]
            x2, y2 = self.node_positions[target]

            # Edge styling
            if edge_type == 'contains':
                color = '#555555'
                width = 2
                dash = None
                arrow = None
            elif edge_type == 'calls':
                color = '#FF6B6B'
                width = 1
                dash = (3, 2)
                arrow = tk.LAST
            else:
                color = '#444444'
                width = 1
                dash = None
                arrow = None

            # Draw edge
            if edge_type == 'calls':
                # Curved line
                mid_x = (x1 + x2) / 2
                mid_y = (y1 + y2) / 2 - 20

                self.canvas.create_line(
                    x1, y1, mid_x, mid_y, x2, y2,
                    fill=color, width=width, smooth=True,
                    dash=dash, arrow=arrow,
                    tags=('edge', f'edge_{edge_type}', f'{source}_to_{target}')
                )
            else:
                # Straight line
                self.canvas.create_line(
                    x1, y1, x2, y2,
                    fill=color, width=width,
                    dash=dash, arrow=arrow,
                    tags=('edge', f'edge_{edge_type}', f'{source}_to_{target}')
                )

    def _draw_nodes(self):
        """Draw all nodes"""
        for node_id, node_info in self.nodes.items():
            if node_id not in self.node_positions:
                continue

            x, y = self.node_positions[node_id]
            node_type = node_info['type']
            label = node_info['label']
            size = node_info.get('size', 20)

            # Get color
            color = self.node_colors.get(node_type, '#888888')

            # Draw node
            self.canvas.create_oval(
                x - size, y - size,
                x + size, y + size,
                fill=color, outline='white', width=2,
                tags=('node', f'node_{node_type}', node_id)
            )

            # Draw label
            if len(label) <= 8:
                self.canvas.create_text(
                    x, y,
                    text=label,
                    fill='white',
                    font=('Segoe UI', 9, 'bold'),
                    tags=('node_label', node_id)
                )
            else:
                display_label = label[:6] + '..'
                self.canvas.create_text(
                    x, y,
                    text=display_label,
                    fill='white',
                    font=('Segoe UI', 8),
                    tags=('node_label', node_id)
                )

            # Full label for important nodes
            if node_type in ('project', 'module', 'main', 'class'):
                self.canvas.create_text(
                    x, y + size + 12,
                    text=label,
                    fill='#CCCCCC',
                    font=('Segoe UI', 8),
                    tags=('label', node_id)
                )

    def _on_click(self, event):
        """Handle click on node"""
        x = self.canvas.canvasx(event.x)
        y = self.canvas.canvasy(event.y)

        items = self.canvas.find_overlapping(x - 2, y - 2, x + 2, y + 2)

        for item in items:
            tags = self.canvas.gettags(item)
            if 'node' in tags:
                for tag in tags:
                    if tag in self.nodes:
                        self._select_node(tag)
                        return

    def _select_node(self, node_id: str):
        """Select a node"""
        # Clear previous
        if self.selected_node:
            items = self.canvas.find_withtag(self.selected_node)
            for item in items:
                if 'node' in self.canvas.gettags(item):
                    self.canvas.itemconfig(item, outline='white', width=2)

        # Highlight new
        items = self.canvas.find_withtag(node_id)
        for item in items:
            if 'node' in self.canvas.gettags(item):
                self.canvas.itemconfig(item, outline='#FFD700', width=3)
                self.selected_node = node_id
                break

        # Callback
        if self.on_select_callback and node_id in self.nodes:
            node_info = self.nodes[node_id]
            if node_info['data']:
                self.on_select_callback((node_info['type'], node_info['data']))

    def _on_motion(self, event):
        x = self.canvas.canvasx(event.x)
        y = self.canvas.canvasy(event.y)
        items = self.canvas.find_overlapping(x - 2, y - 2, x + 2, y + 2)
        node_found = False
        for item in items:
            tags = self.canvas.gettags(item)
            if 'node' in tags:
                for tag in tags:
                    if tag in self.nodes:
                        self._show_node_tooltip(event, tag)
                        node_found = True
                        break
                break
        if not node_found:
            self._hide_node_tooltip()

    def _show_node_tooltip(self, event, node_id: str):
        if self._tooltip_node_id == node_id:
            return
        self._hide_node_tooltip()
        self._tooltip_node_id = node_id
        node_info = self.nodes[node_id]
        data = node_info.get('data')
        lines = [f"{node_info['type'].title()}: {node_info['label']}"]
        if data:
            if hasattr(data, 'lineno'):
                lines.append(f"Lines: {data.lineno}-{data.end_lineno}")
            if hasattr(data, 'complexity'):
                lines.append(f"Complexity: {data.complexity}")
            if hasattr(data, 'docstring') and data.docstring:
                doc = data.docstring[:80]
                if len(data.docstring) > 80:
                    doc += '...'
                lines.append(f"Doc: {doc}")
            if hasattr(data, 'bases') and data.bases:
                lines.append(f"Bases: {', '.join(data.bases)}")
            if hasattr(data, 'args') and data.args:
                filtered = [a for a in data.args if a not in ('self', 'cls')]
                if filtered:
                    lines.append(f"Args: {', '.join(filtered[:5])}")
            if hasattr(data, 'calls') and data.calls:
                ext_calls = [c[4:] for c in data.calls if c.startswith('EXT:')]
                int_calls = [c for c in data.calls if not c.startswith('EXT:')]
                if int_calls:
                    lines.append(f"Calls: {', '.join(int_calls[:3])}")
                if ext_calls:
                    lines.append(f"External: {', '.join(ext_calls[:3])}")
        self._tooltip_win = tk.Toplevel(self)
        self._tooltip_win.wm_overrideredirect(True)
        self._tooltip_win.wm_geometry(f"+{event.x_root + 15}+{event.y_root + 10}")
        lbl = tk.Label(self._tooltip_win, text='\n'.join(lines),
                       justify=tk.LEFT, background='#1A1A2E', foreground='#E0E0E0',
                       font=('Segoe UI', 9), padx=8, pady=5,
                       relief='solid', borderwidth=1)
        lbl.pack()

    def _hide_node_tooltip(self, event=None):
        self._tooltip_node_id = None
        if hasattr(self, '_tooltip_win') and self._tooltip_win:
            try:
                self._tooltip_win.destroy()
            except:
                pass
            self._tooltip_win = None


# ============================================================================
# HIERARCHICAL NETWORK GRAPH VISUALIZATION
# ============================================================================

class HierarchicalNetworkGraph(ttk.Frame):
    """Network graph with hierarchical layout showing relationships"""

    def __init__(self, parent, on_select_callback=None):
        super().__init__(parent)

        self.on_select_callback = on_select_callback
        self.nodes = {}  # node_id -> node_info
        self.edges = []  # (source, target, edge_type)
        self.node_positions = {}  # node_id -> [x, y]
        self.selected_node = None
        self.is_loaded = False
        self._tooltip_win = None
        self._tooltip_node = None

        # Graph layout parameters
        self.layout_params = {
            'level_height': 100,
            'node_spacing': 120,
            'group_spacing': 200,
            'margin': 50
        }

        # Visual settings
        self.node_styles = {
            'module': {'radius': 30, 'color': '#2196F3', 'shape': 'rectangle'},
            'class': {'radius': 25, 'color': '#9C27B0', 'shape': 'circle'},
            'function': {'radius': 20, 'color': '#FF9800', 'shape': 'circle'},
            'method': {'radius': 18, 'color': '#F44336', 'shape': 'circle'},
            'import': {'radius': 15, 'color': '#607D8B', 'shape': 'diamond'},
            'external': {'radius': 16, 'color': '#607D8B', 'shape': 'diamond'}
        }

        self.edge_styles = {
            'inherits': {'color': '#E91E63', 'width': 2, 'arrow': 'triangle'},
            'calls': {'color': '#4CAF50', 'width': 1, 'arrow': 'arrow', 'dash': (4, 2)},
            'imports': {'color': '#00BCD4', 'width': 1, 'arrow': 'arrow', 'dash': (2, 2)},
            'contains': {'color': '#757575', 'width': 1, 'arrow': None}
        }

        self._create_widgets()
        self._bind_events()

    def _create_widgets(self):
        """Create canvas and control panel"""
        # Control panel
        controls = ttk.Frame(self)
        controls.pack(side=tk.TOP, fill=tk.X, padx=5, pady=2)

        # Layout selector
        ttk.Label(controls, text="Layout:").pack(side=tk.LEFT, padx=5)

        self.layout_type = tk.StringVar(value='hierarchy')
        layout_options = [
            ('Hierarchy', 'hierarchy'),
            ('Tree', 'tree'),
            ('Force', 'force'),
            ('Circular', 'circular')
        ]

        for text, value in layout_options:
            ttk.Radiobutton(controls, text=text, variable=self.layout_type,
                            value=value, command=self._relayout).pack(side=tk.LEFT)

        ttk.Separator(controls, orient='vertical').pack(side=tk.LEFT, fill='y', padx=10)

        # View options
        ttk.Label(controls, text="Show:").pack(side=tk.LEFT, padx=5)

        self.show_inheritance = tk.BooleanVar(value=True)
        self.show_calls = tk.BooleanVar(value=True)
        self.show_imports = tk.BooleanVar(value=False)

        ttk.Checkbutton(controls, text="Inheritance",
                        variable=self.show_inheritance,
                        command=self._update_edges).pack(side=tk.LEFT)
        ttk.Checkbutton(controls, text="Calls",
                        variable=self.show_calls,
                        command=self._update_edges).pack(side=tk.LEFT)
        ttk.Checkbutton(controls, text="Imports",
                        variable=self.show_imports,
                        command=self._update_edges).pack(side=tk.LEFT)

        ttk.Separator(controls, orient='vertical').pack(side=tk.LEFT, fill='y', padx=10)

        # Actions
        ttk.Button(controls, text="Fit View",
                   command=self._fit_view).pack(side=tk.LEFT, padx=2)
        ttk.Button(controls, text="Reset",
                   command=self._reset_layout).pack(side=tk.LEFT, padx=2)

        # Filter
        ttk.Label(controls, text="Filter:").pack(side=tk.LEFT, padx=5)
        self.filter_var = tk.StringVar()
        filter_entry = ttk.Entry(controls, textvariable=self.filter_var, width=15)
        filter_entry.pack(side=tk.LEFT)
        filter_entry.bind('<Return>', lambda e: self._apply_filter())

        # Canvas with scrollbars
        canvas_frame = ttk.Frame(self)
        canvas_frame.pack(fill=tk.BOTH, expand=True)

        self.canvas = ZoomableCanvas(
            canvas_frame,
            bg='#0D1117',
            highlightthickness=0
        )

        # Scrollbars
        v_scrollbar = ttk.Scrollbar(canvas_frame, orient='vertical',
                                    command=self.canvas.yview)
        h_scrollbar = ttk.Scrollbar(canvas_frame, orient='horizontal',
                                    command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=v_scrollbar.set,
                              xscrollcommand=h_scrollbar.set)

        # Grid layout
        self.canvas.grid(row=0, column=0, sticky='nsew')
        v_scrollbar.grid(row=0, column=1, sticky='ns')
        h_scrollbar.grid(row=1, column=0, sticky='ew')

        canvas_frame.grid_rowconfigure(0, weight=1)
        canvas_frame.grid_columnconfigure(0, weight=1)

        # Info panel
        self.info_label = ttk.Label(self, text="", font=('Segoe UI', 9))
        self.info_label.pack(side=tk.BOTTOM, fill=tk.X, padx=5, pady=2)

    def _bind_events(self):
        """Bind canvas events"""
        self.canvas.bind('<Button-1>', self._on_click)
        self.canvas.bind('<Double-Button-1>', self._on_double_click)
        self.canvas.bind('<Motion>', self._on_hover)
        self.canvas.bind('<Leave>', lambda e: self._update_info(""))
        self.canvas.bind('<Leave>', lambda e: self._hide_node_tooltip())

    def load_modules(self, modules: List[ModuleInfo]):
        """Load modules and build network graph"""
        if not modules:
            self.canvas.delete('all')
            self.canvas.create_text(
                400, 300,
                text="No modules loaded. Please open a file or directory.",
                fill='#CCCCCC',
                font=('Segoe UI', 12)
            )
            return

        self.is_loaded = True
        self.nodes.clear()
        self.edges.clear()
        self.node_positions.clear()

        # Build graph structure
        self._build_graph(modules)

        # Check if we have nodes
        if not self.nodes:
            self.canvas.delete('all')
            self.canvas.create_text(
                400, 300,
                text="No classes or functions found to visualize",
                fill='#CCCCCC',
                font=('Segoe UI', 12)
            )
            return

        # Apply initial layout
        self._apply_layout()

        # Draw graph
        self._draw_graph()

        # Fit to view
        self.after(100, self._fit_view)

        # Update info
        self._update_info(f"Loaded {len(self.nodes)} nodes, {len(self.edges)} edges")

    def _build_graph(self, modules: List[ModuleInfo]):
        all_classes = {}
        all_functions = {}
        external_nodes_added = set()

        for module in modules:
            module_id = f"mod_{module.name}"
            self.nodes[module_id] = {'type': 'module', 'label': module.name, 'data': module, 'group': module.name}

            for cls in module.classes[:30]:
                class_id = f"cls_{module.name}_{cls.name}"
                self.nodes[class_id] = {'type': 'class', 'label': cls.name, 'data': cls, 'group': module.name}
                all_classes[cls.name] = (module.name, cls)
                self.edges.append((module_id, class_id, 'contains'))

                public_methods = [m for m in cls.methods if not m.name.startswith('_') or m.name == '__init__']
                for method in public_methods[:10]:
                    method_id = f"mth_{module.name}_{cls.name}_{method.name}"
                    self.nodes[method_id] = {'type': 'method', 'label': f"{module.name}:{cls.name}:{method.name}", 'data': method, 'group': module.name}
                    self.edges.append((class_id, method_id, 'contains'))
                    all_functions[f"{cls.name}.{method.name}"] = (module.name, method)

                    # External calls
                    for call in method.calls:
                        if call.startswith('EXT:'):
                            ext_name = call[4:]
                            ext_id = f"ext_{ext_name}"
                            if ext_id not in external_nodes_added:
                                self.nodes[ext_id] = {'type': 'external', 'label': ext_name, 'data': None, 'group': 'external'}
                                external_nodes_added.add(ext_id)
                            self.edges.append((method_id, ext_id, 'calls'))

            for func in module.functions[:20]:
                func_id = f"fn_{module.name}_{func.name}"
                self.nodes[func_id] = {'type': 'function', 'label': f"{module.name}:{func.name}", 'data': func, 'group': module.name}
                all_functions[func.name] = (module.name, func)
                self.edges.append((module_id, func_id, 'contains'))

                for call in func.calls:
                    if call.startswith('EXT:'):
                        ext_name = call[4:]
                        ext_id = f"ext_{ext_name}"
                        if ext_id not in external_nodes_added:
                            self.nodes[ext_id] = {'type': 'external', 'label': ext_name, 'data': None, 'group': 'external'}
                            external_nodes_added.add(ext_id)
                        self.edges.append((func_id, ext_id, 'calls'))

        if self.show_inheritance.get():
            self._create_inheritance_edges(modules, all_classes)
        if self.show_calls.get():
            self._create_call_edges(modules, all_functions)
        if self.show_imports.get():
            self._create_import_edges(modules)

    def _create_inheritance_edges(self, modules, all_classes):
        """Create inheritance relationship edges"""
        for module in modules:
            for cls in module.classes:
                class_id = f"cls_{module.name}_{cls.name}"

                if class_id not in self.nodes:
                    continue

                for base in cls.bases:
                    # Try to find base class
                    if base in all_classes:
                        base_module, base_cls = all_classes[base]
                        base_id = f"cls_{base_module}_{base}"

                        if base_id in self.nodes:
                            self.edges.append((base_id, class_id, 'inherits'))

    def _create_call_edges(self, modules, all_functions):
        """Create function call edges"""
        for module in modules:
            # Process class methods
            for cls in module.classes:
                for method in cls.methods:
                    caller_id = f"mth_{module.name}_{cls.name}_{method.name}"

                    if caller_id not in self.nodes:
                        continue

                    for call in method.calls[:5]:  # Limit call edges
                        callee_id = self._resolve_call(call, module.name, all_functions)
                        if callee_id and callee_id in self.nodes:
                            self.edges.append((caller_id, callee_id, 'calls'))

            # Process functions
            for func in module.functions:
                caller_id = f"fn_{module.name}_{func.name}"

                if caller_id not in self.nodes:
                    continue

                for call in func.calls[:5]:  # Limit call edges
                    callee_id = self._resolve_call(call, module.name, all_functions)
                    if callee_id and callee_id in self.nodes:
                        self.edges.append((caller_id, callee_id, 'calls'))

    def _resolve_call(self, call_name: str, current_module: str,
                      all_functions: dict) -> Optional[str]:
        """Resolve a function call to a node ID"""
        # Try direct lookup
        if call_name in all_functions:
            target_module, target_func = all_functions[call_name]

            if '.' in call_name:  # Method call
                parts = call_name.split('.')
                if len(parts) == 2:
                    return f"mth_{target_module}_{parts[0]}_{parts[1]}"
            else:  # Function call
                return f"fn_{target_module}_{call_name}"

        # Try in same module
        func_id = f"fn_{current_module}_{call_name}"
        if func_id in self.nodes:
            return func_id

        return None

    def _create_import_edges(self, modules):
        """Create import relationship edges"""
        module_map = {m.name: m for m in modules}

        for module in modules:
            module_id = f"mod_{module.name}"

            if module_id not in self.nodes:
                continue

            # Process imports
            for imp in module.imports[:5]:  # Limit import edges
                # Extract module name from import
                imp_parts = imp.split('.')
                imported_module = imp_parts[0]

                if imported_module in module_map:
                    target_id = f"mod_{imported_module}"
                    if target_id in self.nodes:
                        self.edges.append((module_id, target_id, 'imports'))

    def _apply_layout(self):
        """Apply selected layout algorithm"""
        layout_type = self.layout_type.get()

        if layout_type == 'hierarchy':
            self._hierarchical_layout()
        elif layout_type == 'tree':
            self._tree_layout()
        elif layout_type == 'force':
            self._force_directed_layout()
        elif layout_type == 'circular':
            self._circular_layout()

    def _hierarchical_layout(self):
        """Apply hierarchical top-to-bottom layout"""
        if not self.nodes:
            return

        # Separate nodes by type
        modules = [nid for nid, n in self.nodes.items() if n['type'] == 'module']
        classes = [nid for nid, n in self.nodes.items() if n['type'] == 'class']
        functions = [nid for nid, n in self.nodes.items() if n['type'] == 'function']
        methods = [nid for nid, n in self.nodes.items() if n['type'] == 'method']

        # Build containment hierarchy
        children = defaultdict(list)
        for source, target, edge_type in self.edges:
            if edge_type == 'contains':
                children[source].append(target)

        # Position modules
        y_offset = self.layout_params['margin']
        x_offset = self.layout_params['margin']

        # Level 1: Modules
        module_spacing = self.layout_params['group_spacing']
        for i, module_id in enumerate(modules):
            x = x_offset + i * module_spacing
            y = y_offset
            self.node_positions[module_id] = [x, y]

            # Position module's children
            module_children = children.get(module_id, [])

            # Separate classes and functions
            module_classes = [c for c in module_children if self.nodes[c]['type'] == 'class']
            module_functions = [f for f in module_children if self.nodes[f]['type'] == 'function']

            # Level 2: Classes
            class_y = y + self.layout_params['level_height']
            for j, class_id in enumerate(module_classes):
                class_x = x + j * self.layout_params['node_spacing']
                self.node_positions[class_id] = [class_x, class_y]

                # Level 3: Methods
                class_methods = children.get(class_id, [])
                method_y = class_y + self.layout_params['level_height']
                for k, method_id in enumerate(class_methods):
                    method_x = class_x + (k - len(class_methods) / 2) * 60
                    self.node_positions[method_id] = [method_x, method_y]

            # Functions at same level as classes but offset
            func_x_start = x + len(module_classes) * self.layout_params['node_spacing'] + 50
            for j, func_id in enumerate(module_functions):
                func_x = func_x_start + j * 80
                self.node_positions[func_id] = [func_x, class_y]

    def _tree_layout(self):
        """Apply tree layout using module hierarchy"""
        if not self.nodes:
            return

        # Find root modules (those not imported by others)
        imported = set()
        for source, target, edge_type in self.edges:
            if edge_type == 'imports':
                imported.add(target)

        roots = [nid for nid, n in self.nodes.items()
                 if n['type'] == 'module' and nid not in imported]

        if not roots:
            roots = [nid for nid, n in self.nodes.items() if n['type'] == 'module'][:1]

        # Build tree structure
        children = defaultdict(list)
        for source, target, edge_type in self.edges:
            if edge_type in ('contains', 'imports'):
                children[source].append(target)

        # Position nodes recursively
        x_offset = self.layout_params['margin']
        y_offset = self.layout_params['margin']
        x_pos = [x_offset]  # Use list for mutable reference

        for root_id in roots:
            self._position_tree_recursive(root_id, x_pos, y_offset, children, set())

    def _position_tree_recursive(self, node_id, x_pos, y, children, visited):
        """Recursively position nodes in tree layout"""
        if node_id in visited:
            return

        visited.add(node_id)

        # Position this node
        self.node_positions[node_id] = [x_pos[0], y]

        # Position children
        node_children = children.get(node_id, [])
        if node_children:
            child_y = y + self.layout_params['level_height']

            for child_id in node_children:
                if child_id not in visited:
                    self._position_tree_recursive(child_id, x_pos, child_y,
                                                  children, visited)
                    x_pos[0] += self.layout_params['node_spacing']

    def _force_directed_layout(self):
        """Apply force-directed layout for optimal spacing"""
        if not self.nodes:
            return

        import random

        # Initialize random positions
        width = max(800, len(self.nodes) * 20)
        height = max(600, len(self.nodes) * 15)

        for node_id in self.nodes:
            self.node_positions[node_id] = [
                random.uniform(100, width),
                random.uniform(100, height)
            ]

        # Simulation parameters
        k = math.sqrt((width * height) / max(len(self.nodes), 1))
        temperature = width / 10
        cooling_rate = 0.95

        # Run simulation
        for iteration in range(50):
            forces = {node_id: [0, 0] for node_id in self.nodes}

            # Calculate repulsive forces between all nodes
            node_list = list(self.nodes.keys())
            for i, node1 in enumerate(node_list):
                for node2 in node_list[i + 1:]:
                    dx = self.node_positions[node1][0] - self.node_positions[node2][0]
                    dy = self.node_positions[node1][1] - self.node_positions[node2][1]
                    dist = max(math.sqrt(dx * dx + dy * dy), 0.1)

                    # Repulsive force
                    force = (k * k) / dist
                    fx = (dx / dist) * force
                    fy = (dy / dist) * force

                    forces[node1][0] += fx
                    forces[node1][1] += fy
                    forces[node2][0] -= fx
                    forces[node2][1] -= fy

            # Calculate attractive forces for edges
            for source, target, _ in self.edges:
                if source in self.node_positions and target in self.node_positions:
                    dx = self.node_positions[source][0] - self.node_positions[target][0]
                    dy = self.node_positions[source][1] - self.node_positions[target][1]
                    dist = max(math.sqrt(dx * dx + dy * dy), 0.1)

                    # Attractive force
                    force = (dist * dist) / k
                    fx = (dx / dist) * force
                    fy = (dy / dist) * force

                    forces[source][0] -= fx * 0.1
                    forces[source][1] -= fy * 0.1
                    forces[target][0] += fx * 0.1
                    forces[target][1] += fy * 0.1

            # Apply forces with temperature
            for node_id in self.nodes:
                fx = forces[node_id][0]
                fy = forces[node_id][1]

                # Limit displacement by temperature
                displacement = math.sqrt(fx * fx + fy * fy)
                if displacement > 0:
                    limited_displacement = min(displacement, temperature)
                    fx = (fx / displacement) * limited_displacement
                    fy = (fy / displacement) * limited_displacement

                self.node_positions[node_id][0] += fx
                self.node_positions[node_id][1] += fy

                # Keep within bounds
                self.node_positions[node_id][0] = max(50, min(width - 50,
                                                              self.node_positions[node_id][0]))
                self.node_positions[node_id][1] = max(50, min(height - 50,
                                                              self.node_positions[node_id][1]))

            # Cool down
            temperature *= cooling_rate

    def _circular_layout(self):
        """Apply circular layout with modules on outer ring"""
        if not self.nodes:
            return

        center_x = 400
        center_y = 300

        # Separate by type
        modules = [nid for nid, n in self.nodes.items() if n['type'] == 'module']
        others = [nid for nid, n in self.nodes.items() if n['type'] != 'module']

        # Position modules in outer circle
        radius = 200
        for i, module_id in enumerate(modules):
            angle = (2 * math.pi * i) / max(len(modules), 1)
            x = center_x + radius * math.cos(angle)
            y = center_y + radius * math.sin(angle)
            self.node_positions[module_id] = [x, y]

        # Position other nodes in inner circles by group
        groups = defaultdict(list)
        for node_id in others:
            group = self.nodes[node_id].get('group', 'default')
            groups[group].append(node_id)

        inner_radius = 100
        for group_name, group_nodes in groups.items():
            # Find module position for this group
            module_id = f"mod_{group_name}"
            if module_id in self.node_positions:
                module_x, module_y = self.node_positions[module_id]

                # Position group nodes around module
                for i, node_id in enumerate(group_nodes):
                    angle = (2 * math.pi * i) / max(len(group_nodes), 1)
                    x = module_x + inner_radius * math.cos(angle) * 0.5
                    y = module_y + inner_radius * math.sin(angle) * 0.5
                    self.node_positions[node_id] = [x, y]

    # ============================================================================
    # NETWORK GRAPH DRAWING (Continuation)
    # ============================================================================

    def _draw_graph(self):
        """Draw the complete network graph"""
        self.canvas.delete('all')

        if not self.nodes:
            self.canvas.create_text(
                400, 300,
                text="No data to display",
                fill='#666666',
                font=('Segoe UI', 12)
            )
            return

        # Draw edges first (behind nodes)
        self._draw_edges()

        # Draw nodes
        self._draw_nodes()

        # Update scroll region
        self.canvas._update_scroll_region()

    def _draw_edges(self):
        """Draw all edges based on visibility settings"""
        for source, target, edge_type in self.edges:
            # Check visibility settings
            if edge_type == 'inherits' and not self.show_inheritance.get():
                continue
            if edge_type == 'calls' and not self.show_calls.get():
                continue
            if edge_type == 'imports' and not self.show_imports.get():
                continue

            # Skip if nodes not positioned
            if source not in self.node_positions or target not in self.node_positions:
                continue

            x1, y1 = self.node_positions[source]
            x2, y2 = self.node_positions[target]

            # Get edge style
            style = self.edge_styles.get(edge_type, {})
            color = style.get('color', '#666666')
            width = style.get('width', 1)
            dash = style.get('dash', None)
            arrow_type = style.get('arrow', None)

            # Calculate arrow shape based on type
            if arrow_type == 'triangle':
                arrow = tk.LAST
                arrowshape = (12, 15, 5)
            elif arrow_type == 'arrow':
                arrow = tk.LAST
                arrowshape = (8, 10, 3)
            else:
                arrow = None
                arrowshape = None

            # Draw edge
            if edge_type in ('calls', 'imports'):
                # Draw curved edge for better visibility
                mid_x = (x1 + x2) / 2
                mid_y = (y1 + y2) / 2

                # Offset curve based on edge direction
                if x1 < x2:
                    mid_y -= 20
                else:
                    mid_y += 20

                edge_id = self.canvas.create_line(
                    x1, y1, mid_x, mid_y, x2, y2,
                    fill=color,
                    width=width,
                    dash=dash,
                    smooth=True,
                    arrow=arrow,
                    arrowshape=arrowshape,
                    tags=('edge', f'edge_{edge_type}', f'{source}_{target}')
                )
            else:
                # Straight edge for containment and inheritance
                edge_id = self.canvas.create_line(
                    x1, y1, x2, y2,
                    fill=color,
                    width=width,
                    dash=dash,
                    arrow=arrow,
                    arrowshape=arrowshape,
                    tags=('edge', f'edge_{edge_type}', f'{source}_{target}')
                )

    def _draw_nodes(self):
        """Draw all nodes"""
        for node_id, node_info in self.nodes.items():
            if node_id not in self.node_positions:
                continue

            x, y = self.node_positions[node_id]
            node_type = node_info['type']
            label = node_info['label']

            # Get node style
            style = self.node_styles.get(node_type, {})
            radius = style.get('radius', 20)
            color = style.get('color', '#888888')
            shape = style.get('shape', 'circle')

            # Apply filter if set
            if self.filter_var.get():
                if self.filter_var.get().lower() not in label.lower():
                    color = '#333333'  # Dim filtered nodes

            # Draw node shape
            if shape == 'rectangle':
                # Rectangle for modules
                width = max(len(label) * 7, radius * 2)
                height = radius * 1.5
                node_item = self.canvas.create_rectangle(
                    x - width / 2, y - height / 2,
                    x + width / 2, y + height / 2,
                    fill=color,
                    outline='white',
                    width=2,
                    tags=('node', f'node_{node_type}', node_id)
                )
            elif shape == 'diamond':
                # Diamond for imports
                points = [
                    x, y - radius,  # Top
                       x + radius, y,  # Right
                    x, y + radius,  # Bottom
                       x - radius, y  # Left
                ]
                node_item = self.canvas.create_polygon(
                    points,
                    fill=color,
                    outline='white',
                    width=2,
                    tags=('node', f'node_{node_type}', node_id)
                )
            else:
                # Circle for classes, functions, methods
                node_item = self.canvas.create_oval(
                    x - radius, y - radius,
                    x + radius, y + radius,
                    fill=color,
                    outline='white',
                    width=2,
                    tags=('node', f'node_{node_type}', node_id)
                )

            # Draw label
            # Truncate long labels
            display_label = label
            max_chars = 15
            if len(label) > max_chars:
                display_label = label[:max_chars - 2] + '..'

            # Label inside for large nodes, below for small
            if radius >= 20:
                self.canvas.create_text(
                    x, y,
                    text=display_label,
                    fill='white',
                    font=('Segoe UI', 8, 'bold'),
                    tags=('node_label', node_id)
                )
            else:
                self.canvas.create_text(
                    x, y + radius + 8,
                    text=display_label,
                    fill='#CCCCCC',
                    font=('Segoe UI', 7),
                    tags=('node_label', node_id)
                )

    def _on_click(self, event):
        """Handle click on node"""
        x = self.canvas.canvasx(event.x)
        y = self.canvas.canvasy(event.y)

        # Find clicked item
        items = self.canvas.find_overlapping(x - 2, y - 2, x + 2, y + 2)

        for item in items:
            tags = self.canvas.gettags(item)
            if 'node' in tags:
                for tag in tags:
                    if tag in self.nodes:
                        self._select_node(tag)
                        return

    def _on_double_click(self, event):
        """Handle double click - center on node"""
        x = self.canvas.canvasx(event.x)
        y = self.canvas.canvasy(event.y)

        items = self.canvas.find_overlapping(x - 2, y - 2, x + 2, y + 2)

        for item in items:
            tags = self.canvas.gettags(item)
            if 'node' in tags:
                for tag in tags:
                    if tag in self.node_positions:
                        # Center view on node
                        node_x, node_y = self.node_positions[tag]
                        self._center_on_point(node_x, node_y)
                        return

    def _center_on_point(self, x, y):
        """Center canvas view on a specific point"""
        canvas_width = self.canvas.winfo_width()
        canvas_height = self.canvas.winfo_height()

        # Calculate scroll positions
        bbox = self.canvas.bbox('all')
        if bbox:
            total_width = bbox[2] - bbox[0]
            total_height = bbox[3] - bbox[1]

            # Calculate relative position
            rel_x = (x - bbox[0]) / total_width
            rel_y = (y - bbox[1]) / total_height

            # Scroll to center
            self.canvas.xview_moveto(rel_x - 0.5)
            self.canvas.yview_moveto(rel_y - 0.5)

    def _select_node(self, node_id: str):
        """Select and highlight a node"""
        # Clear previous selection
        if self.selected_node:
            # Reset previous node appearance
            items = self.canvas.find_withtag(self.selected_node)
            for item in items:
                if 'node' in self.canvas.gettags(item):
                    self.canvas.itemconfig(item, outline='white', width=2)

        # Highlight new selection
        items = self.canvas.find_withtag(node_id)
        for item in items:
            if 'node' in self.canvas.gettags(item):
                self.canvas.itemconfig(item, outline='#FFD700', width=3)
                self.selected_node = node_id

                # Highlight connected edges
                self._highlight_connections(node_id)
                break

        # Callback
        if self.on_select_callback and node_id in self.nodes:
            node_info = self.nodes[node_id]
            if node_info.get('data'):
                self.on_select_callback((node_info['type'], node_info['data']))

    def _highlight_connections(self, node_id: str):
        """Highlight edges connected to selected node"""
        # Reset all edges
        for item in self.canvas.find_withtag('edge'):
            edge_tags = self.canvas.gettags(item)

            # Determine original color based on type
            color = '#666666'
            for tag in edge_tags:
                if tag.startswith('edge_'):
                    edge_type = tag[5:]
                    if edge_type in self.edge_styles:
                        color = self.edge_styles[edge_type].get('color', '#666666')
                    break

            self.canvas.itemconfig(item, width=1, fill=color)

        # Highlight connected edges
        for item in self.canvas.find_withtag('edge'):
            edge_tags = self.canvas.gettags(item)

            for tag in edge_tags:
                if '_' in tag and (tag.startswith(node_id) or tag.endswith(node_id)):
                    self.canvas.itemconfig(item, width=2, fill='#FFD700')
                    break

    def _on_hover(self, event):
        x = self.canvas.canvasx(event.x)
        y = self.canvas.canvasy(event.y)
        items = self.canvas.find_overlapping(x - 2, y - 2, x + 2, y + 2)
        for item in items:
            tags = self.canvas.gettags(item)
            if 'node' in tags:
                for tag in tags:
                    if tag in self.nodes:
                        node_info = self.nodes[tag]
                        self._update_info(f"{node_info['type'].title()}: {node_info['label']}")
                        self._show_node_tooltip(event, tag, node_info)
                        return
        self._update_info("")
        self._hide_node_tooltip()

    def _show_node_tooltip(self, event, node_id: str, node_info: dict):
        if self._tooltip_node == node_id:
            return
        self._hide_node_tooltip()
        self._tooltip_node = node_id
        data = node_info.get('data')
        lines = [f"{node_info['type'].title()}: {node_info['label']}"]
        if data:
            if hasattr(data, 'lineno'):
                lines.append(f"Lines: {data.lineno}-{data.end_lineno}")
            if hasattr(data, 'complexity'):
                lines.append(f"Complexity: {data.complexity}")
            if hasattr(data, 'docstring') and data.docstring:
                doc = data.docstring[:80]
                if len(data.docstring) > 80:
                    doc += '...'
                lines.append(f"Doc: {doc}")
            if hasattr(data, 'bases') and data.bases:
                lines.append(f"Bases: {', '.join(data.bases)}")
            if hasattr(data, 'args') and data.args:
                filtered = [a for a in data.args if a not in ('self', 'cls')]
                if filtered:
                    lines.append(f"Args: {', '.join(filtered[:5])}")
            if hasattr(data, 'calls') and data.calls:
                ext_calls = [c[4:] for c in data.calls if c.startswith('EXT:')]
                int_calls = [c for c in data.calls if not c.startswith('EXT:')]
                if int_calls:
                    lines.append(f"Calls: {', '.join(int_calls[:3])}")
                if ext_calls:
                    lines.append(f"External: {', '.join(ext_calls[:3])}")
        self._tooltip_win = tk.Toplevel(self)
        self._tooltip_win.wm_overrideredirect(True)
        self._tooltip_win.wm_geometry(f"+{event.x_root + 15}+{event.y_root + 10}")
        lbl = tk.Label(self._tooltip_win, text='\n'.join(lines),
                       justify=tk.LEFT, background='#1A1A2E', foreground='#E0E0E0',
                       font=('Segoe UI', 9), padx=8, pady=5,
                       relief='solid', borderwidth=1)
        lbl.pack()

    def _hide_node_tooltip(self, event=None):
        self._tooltip_node = None
        if self._tooltip_win:
            try:
                self._tooltip_win.destroy()
            except:
                pass
            self._tooltip_win = None

    def _update_info(self, text: str):
        """Update info label"""
        self.info_label.configure(text=text)

    def _update_edges(self):
        """Update edge visibility based on checkboxes"""
        if self.nodes:
            self._draw_graph()

    def _apply_filter(self):
        """Apply filter to highlight matching nodes"""
        if self.nodes:
            self._draw_graph()

    def _fit_view(self):
        """Fit graph to canvas view"""
        self.canvas.fit_to_view()

    def _reset_layout(self):
        """Reset to default layout"""
        if self.nodes:
            self._apply_layout()
            self._draw_graph()
            self._fit_view()

    def _relayout(self):
        """Re-layout graph with selected algorithm"""
        if self.nodes:
            self._apply_layout()
            self._draw_graph()



# ============================================================================
# OPTIMIZED CLASS DIAGRAM VISUALIZATION
# ============================================================================

class OptimizedClassDiagram(ttk.Frame):
    """UML-style class diagram with auto-sizing boxes"""

    def __init__(self, parent, on_select_callback=None):
        super().__init__(parent)

        self.on_select_callback = on_select_callback
        self.class_boxes = {}  # class_name -> box_info
        self.selected_class = None
        self.is_loaded = False
        self._tooltip_win = None
        self._tooltip_node_id = None
        self._tooltip_win = None
        self._tooltip_class = None

        # Visual settings
        self.colors = {
            'header': '#4A90E2',
            'body': '#FFFFFF',
            'border': '#2C5282',
            'text': '#1A202C',
            'method_public': '#38A169',
            'method_private': '#E53E3E',
            'method_protected': '#ED8936',
            'attribute': '#805AD5',
            'selected': '#FFD700',
            'inheritance_arrow': '#E91E63',
            'composition_arrow': '#FF9800'
        }

        self._create_widgets()
        self._bind_events()

    def _create_widgets(self):
        """Create canvas and control panel"""
        # Control panel
        controls = ttk.Frame(self)
        controls.pack(side=tk.TOP, fill=tk.X, padx=5, pady=2)

        # View options
        ttk.Label(controls, text="Show:").pack(side=tk.LEFT, padx=5)

        self.show_attributes = tk.BooleanVar(value=True)
        self.show_methods = tk.BooleanVar(value=True)
        self.show_private = tk.BooleanVar(value=False)
        self.show_inheritance = tk.BooleanVar(value=True)

        ttk.Checkbutton(controls, text="Attributes",
                        variable=self.show_attributes,
                        command=self._update_display).pack(side=tk.LEFT)
        ttk.Checkbutton(controls, text="Methods",
                        variable=self.show_methods,
                        command=self._update_display).pack(side=tk.LEFT)
        ttk.Checkbutton(controls, text="Private Members",
                        variable=self.show_private,
                        command=self._update_display).pack(side=tk.LEFT)
        ttk.Checkbutton(controls, text="Inheritance",
                        variable=self.show_inheritance,
                        command=self._update_display).pack(side=tk.LEFT)

        ttk.Separator(controls, orient='vertical').pack(side=tk.LEFT, fill='y', padx=10)

        # Layout options
        ttk.Label(controls, text="Layout:").pack(side=tk.LEFT, padx=5)

        self.layout_type = tk.StringVar(value='auto')
        ttk.Radiobutton(controls, text="Auto",
                        variable=self.layout_type, value='auto',
                        command=self._relayout).pack(side=tk.LEFT)
        ttk.Radiobutton(controls, text="Grid",
                        variable=self.layout_type, value='grid',
                        command=self._relayout).pack(side=tk.LEFT)
        ttk.Radiobutton(controls, text="Hierarchical",
                        variable=self.layout_type, value='hierarchical',
                        command=self._relayout).pack(side=tk.LEFT)

        ttk.Separator(controls, orient='vertical').pack(side=tk.LEFT, fill='y', padx=10)

        ttk.Button(controls, text="Fit View",
                   command=self._fit_view).pack(side=tk.LEFT, padx=2)
        ttk.Button(controls, text="Export",
                   command=self._export_diagram).pack(side=tk.LEFT, padx=2)

        # Canvas with scrollbars
        canvas_frame = ttk.Frame(self)
        canvas_frame.pack(fill=tk.BOTH, expand=True)

        self.canvas = ZoomableCanvas(
            canvas_frame,
            bg='#F5F5F5',
            highlightthickness=0
        )

        # Scrollbars
        v_scrollbar = ttk.Scrollbar(canvas_frame, orient='vertical',
                                    command=self.canvas.yview)
        h_scrollbar = ttk.Scrollbar(canvas_frame, orient='horizontal',
                                    command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=v_scrollbar.set,
                              xscrollcommand=h_scrollbar.set)

        # Grid layout
        self.canvas.grid(row=0, column=0, sticky='nsew')
        v_scrollbar.grid(row=0, column=1, sticky='ns')
        h_scrollbar.grid(row=1, column=0, sticky='ew')

        canvas_frame.grid_rowconfigure(0, weight=1)
        canvas_frame.grid_columnconfigure(0, weight=1)

    def _bind_events(self):
        self.canvas.bind('<Button-1>', self._on_click)
        self.canvas.bind('<Double-Button-1>', self._on_double_click)
        self.canvas.bind('<Motion>', self._on_hover)
        self.canvas.bind('<Leave>', self._hide_class_tooltip)

    def _on_hover(self, event):
        x = self.canvas.canvasx(event.x)
        y = self.canvas.canvasy(event.y)
        items = self.canvas.find_overlapping(x - 2, y - 2, x + 2, y + 2)
        for item in items:
            tags = self.canvas.gettags(item)
            for tag in tags:
                if tag in self.class_boxes:
                    self._show_class_tooltip(event, tag)
                    return
        self._hide_class_tooltip()

    def _show_class_tooltip(self, event, class_name: str):
        if self._tooltip_class == class_name:
            return
        self._hide_class_tooltip()
        self._tooltip_class = class_name
        box = self.class_boxes[class_name]
        cls = box['class']
        lines = [f"Class: {cls.name}"]
        if cls.bases:
            lines.append(f"Bases: {', '.join(cls.bases)}")
        lines.append(f"Methods: {len(cls.methods)} | Attrs: {len(cls.attributes)}")
        if cls.lineno:
            lines.append(f"Lines: {cls.lineno}-{cls.end_lineno}")
        if cls.docstring:
            doc = cls.docstring[:80]
            if len(cls.docstring) > 80:
                doc += '...'
            lines.append(f"Doc: {doc}")
        # Show external calls from methods
        ext_calls = set()
        for m in cls.methods:
            for c in m.calls:
                if c.startswith('EXT:'):
                    ext_calls.add(c[4:])
        if ext_calls:
            lines.append(f"External: {', '.join(list(ext_calls)[:4])}")
        self._tooltip_win = tk.Toplevel(self)
        self._tooltip_win.wm_overrideredirect(True)
        self._tooltip_win.wm_geometry(f"+{event.x_root + 15}+{event.y_root + 10}")
        lbl = tk.Label(self._tooltip_win, text='\n'.join(lines),
                       justify=tk.LEFT, background='#1A1A2E', foreground='#E0E0E0',
                       font=('Segoe UI', 9), padx=8, pady=5,
                       relief='solid', borderwidth=1)
        lbl.pack()

    def _hide_class_tooltip(self, event=None):
        self._tooltip_class = None
        if self._tooltip_win:
            try:
                self._tooltip_win.destroy()
            except:
                pass
            self._tooltip_win = None

    def load_modules(self, modules: List[ModuleInfo]):
        """Load modules and create class diagram"""
        if not modules:
            return

        self.is_loaded = True
        self.class_boxes.clear()

        # Collect all classes
        all_classes = []
        for module in modules:
            for cls in module.classes:
                # Store with module reference
                cls.parent_module = module
                all_classes.append((module.name, cls))

        if not all_classes:
            self.canvas.delete('all')
            self.canvas.create_text(
                400, 300,
                text="No classes found in modules",
                fill='#666666',
                font=('Segoe UI', 12)
            )
            return

        # Calculate layout
        self._calculate_layout(all_classes)

        # Draw diagram
        self._draw_diagram(all_classes)

        # Fit to view
        self.after(100, self._fit_view)

    def _calculate_layout(self, classes: List[Tuple[str, ClassInfo]]):
        """Calculate positions for class boxes"""
        layout_type = self.layout_type.get()

        if layout_type == 'grid':
            self._grid_layout(classes)
        elif layout_type == 'hierarchical':
            self._hierarchical_layout(classes)
        else:
            self._auto_layout(classes)

    def _auto_layout(self, classes: List[Tuple[str, ClassInfo]]):
        """Automatic layout using size-based packing"""
        # Calculate box sizes first
        for module_name, cls in classes:
            width, height = self._calculate_box_size(cls)

            self.class_boxes[cls.name] = {
                'module': module_name,
                'class': cls,
                'width': width,
                'height': height,
                'x': 0,
                'y': 0
            }

        # Sort by size for better packing
        sorted_classes = sorted(self.class_boxes.items(),
                                key=lambda x: x[1]['width'] * x[1]['height'],
                                reverse=True)

        # Pack boxes
        canvas_width = 1400
        padding = 30
        x = padding
        y = padding
        row_height = 0

        for class_name, box_info in sorted_classes:
            width = box_info['width']
            height = box_info['height']

            # Check if fits in current row
            if x + width > canvas_width - padding:
                # New row
                x = padding
                y += row_height + padding
                row_height = 0

            # Position box
            box_info['x'] = x
            box_info['y'] = y

            x += width + padding
            row_height = max(row_height, height)

    def _grid_layout(self, classes: List[Tuple[str, ClassInfo]]):
        """Simple grid layout"""
        cols = max(3, int(math.sqrt(len(classes))))
        padding = 30

        # Calculate maximum box size
        max_width = 0
        max_height = 0

        for module_name, cls in classes:
            width, height = self._calculate_box_size(cls)
            max_width = max(max_width, width)
            max_height = max(max_height, height)

            self.class_boxes[cls.name] = {
                'module': module_name,
                'class': cls,
                'width': width,
                'height': height,
                'x': 0,
                'y': 0
            }

        # Position in grid
        for i, (module_name, cls) in enumerate(classes):
            row = i // cols
            col = i % cols

            box_info = self.class_boxes[cls.name]
            box_info['x'] = padding + col * (max_width + padding)
            box_info['y'] = padding + row * (max_height + padding)

    def _hierarchical_layout(self, classes: List[Tuple[str, ClassInfo]]):
        """Layout based on inheritance hierarchy"""
        # Build inheritance tree
        parent_map = {}  # child -> parent
        children_map = defaultdict(list)  # parent -> [children]
        roots = []

        for module_name, cls in classes:
            width, height = self._calculate_box_size(cls)

            self.class_boxes[cls.name] = {
                'module': module_name,
                'class': cls,
                'width': width,
                'height': height,
                'x': 0,
                'y': 0
            }

            # Find parent
            parent_found = False
            for base in cls.bases:
                # Check if base is in our classes
                if base in self.class_boxes:
                    parent_map[cls.name] = base
                    children_map[base].append(cls.name)
                    parent_found = True
                    break

            if not parent_found:
                roots.append(cls.name)

        # Position hierarchically
        level_height = 200
        y = 50

        # Position roots
        x = 50
        for root in roots:
            self._position_hierarchy(root, x, y, children_map)
            x += self.class_boxes[root]['width'] + 100

    def _position_hierarchy(self, class_name: str, x: int, y: int,
                            children_map: dict):
        """Recursively position class and its children"""
        if class_name not in self.class_boxes:
            return

        box_info = self.class_boxes[class_name]
        box_info['x'] = x
        box_info['y'] = y

        # Position children
        children = children_map.get(class_name, [])
        if children:
            child_x = x
            child_y = y + box_info['height'] + 50

            for child in children:
                self._position_hierarchy(child, child_x, child_y, children_map)
                if child in self.class_boxes:
                    child_x += self.class_boxes[child]['width'] + 50

    def _calculate_box_size(self, cls: ClassInfo) -> Tuple[int, int]:
        """Calculate required size for a class box"""
        # Base measurements
        padding = 10
        char_width = 7
        line_height = 18
        header_height = 35

        # Calculate width
        min_width = 150
        max_width = len(cls.name) * 10 + padding * 2

        # Check attributes
        if self.show_attributes.get():
            for attr in cls.attributes:
                if not self.show_private.get() and attr.startswith('_'):
                    continue
                attr_width = (len(attr) + 3) * char_width + padding * 2
                max_width = max(max_width, attr_width)

        # Check methods
        if self.show_methods.get():
            for method in cls.methods:
                if not self.show_private.get() and method.name.startswith('_'):
                    continue

                # Build method signature
                args = [a for a in method.args if a not in ('self', 'cls')]
                args_str = ', '.join(args[:2])
                if len(args) > 2:
                    args_str += ', ...'

                method_text = f"{method.name}({args_str})"
                if method.return_type:
                    method_text += f" -> {method.return_type}"

                method_width = (len(method_text) + 3) * char_width + padding * 2
                max_width = max(max_width, method_width)

        width = max(min_width, min(max_width, 300))

        # Calculate height
        height = header_height

        if self.show_attributes.get():
            visible_attrs = [a for a in cls.attributes
                             if self.show_private.get() or not a.startswith('_')]
            height += len(visible_attrs) * line_height + 25

        if self.show_methods.get():
            visible_methods = [m for m in cls.methods
                               if self.show_private.get() or not m.name.startswith('_')]
            height += len(visible_methods) * line_height + 25

        return width, height

    # ============================================================================
    # CLASS DIAGRAM DRAWING (Continuation)
    # ============================================================================

    def _draw_diagram(self, classes: List[Tuple[str, ClassInfo]]):
        """Draw the complete class diagram"""
        self.canvas.delete('all')

        # Draw relationships first (behind boxes)
        if self.show_inheritance.get():
            self._draw_relationships()

        # Draw class boxes
        for module_name, cls in classes:
            if cls.name in self.class_boxes:
                self._draw_class_box(self.class_boxes[cls.name])

        # Update scroll region
        self.canvas._update_scroll_region()

    def _draw_class_box(self, box_info: dict):
        """Draw a single class box"""
        x = box_info['x']
        y = box_info['y']
        width = box_info['width']
        height = box_info['height']
        cls = box_info['class']

        # Draw main rectangle
        box_id = self.canvas.create_rectangle(
            x, y, x + width, y + height,
            fill=self.colors['body'],
            outline=self.colors['border'],
            width=2,
            tags=('class_box', cls.name)
        )

        # Draw header
        header_height = 35
        header_id = self.canvas.create_rectangle(
            x, y, x + width, y + header_height,
            fill=self.colors['header'],
            outline=self.colors['border'],
            width=2,
            tags=('class_header', cls.name)
        )

        # Draw class name
        # Add stereotypes if applicable
        stereotypes = []
        if cls.is_abstract:
            stereotypes.append('«abstract»')
        if 'dataclass' in [d.lower() for d in cls.decorators]:
            stereotypes.append('«dataclass»')

        name_text = cls.name
        if stereotypes:
            name_text = ' '.join(stereotypes) + '\n' + name_text

        self.canvas.create_text(
            x + width / 2, y + header_height / 2,
            text=name_text,
            fill='white',
            font=('Segoe UI', 10, 'bold'),
            tags=('class_name', cls.name)
        )

        current_y = y + header_height

        # Draw attributes section
        if self.show_attributes.get() and cls.attributes:
            # Section divider
            current_y += 5
            self.canvas.create_line(
                x, current_y, x + width, current_y,
                fill=self.colors['border'],
                tags=('divider', cls.name)
            )
            current_y += 5

            # Draw attributes
            visible_attrs = []
            for attr in cls.attributes:
                if self.show_private.get() or not attr.startswith('_'):
                    visible_attrs.append(attr)

            for attr in visible_attrs[:15]:  # Limit display
                # Determine visibility symbol
                if attr.startswith('__'):
                    symbol = '-'  # Private
                elif attr.startswith('_'):
                    symbol = '#'  # Protected
                else:
                    symbol = '+'  # Public

                attr_text = f"{symbol} {attr}"

                self.canvas.create_text(
                    x + 10, current_y + 9,
                    text=attr_text,
                    fill=self.colors['attribute'],
                    font=('Consolas', 9),
                    anchor='w',
                    tags=('attribute', cls.name)
                )
                current_y += 18

            if len(visible_attrs) > 15:
                self.canvas.create_text(
                    x + 10, current_y + 9,
                    text=f"... +{len(visible_attrs) - 15} more",
                    fill='#999999',
                    font=('Consolas', 8, 'italic'),
                    anchor='w',
                    tags=('more_attrs', cls.name)
                )
                current_y += 18

        # Draw methods section
        if self.show_methods.get() and cls.methods:
            # Section divider
            current_y += 5
            self.canvas.create_line(
                x, current_y, x + width, current_y,
                fill=self.colors['border'],
                tags=('divider', cls.name)
            )
            current_y += 5

            # Group methods by type
            constructors = []
            properties = []
            regular_methods = []
            static_methods = []

            for method in cls.methods:
                if not self.show_private.get() and method.name.startswith('_'):
                    if method.name not in ('__init__', '__str__', '__repr__'):
                        continue

                if method.name == '__init__':
                    constructors.append(method)
                elif 'property' in method.decorators:
                    properties.append(method)
                elif 'staticmethod' in method.decorators or 'classmethod' in method.decorators:
                    static_methods.append(method)
                else:
                    regular_methods.append(method)

            # Draw methods by group
            all_methods = constructors + properties + static_methods + regular_methods

            for i, method in enumerate(all_methods[:20]):  # Limit display
                # Determine visibility symbol
                if method.name.startswith('__'):
                    symbol = '-'
                    color = self.colors['method_private']
                elif method.name.startswith('_'):
                    symbol = '#'
                    color = self.colors['method_protected']
                else:
                    symbol = '+'
                    color = self.colors['method_public']

                # Build method signature
                args = [a for a in method.args if a not in ('self', 'cls')]
                args_str = ', '.join(args[:2])
                if len(args) > 2:
                    args_str += ', ...'

                method_text = f"{symbol} {method.name}({args_str})"

                # Add return type if available
                if method.return_type:
                    method_text += f": {method.return_type}"

                # Add modifiers
                if 'staticmethod' in method.decorators:
                    method_text = f"{{static}} {method_text}"
                elif 'classmethod' in method.decorators:
                    method_text = f"{{class}} {method_text}"
                elif 'property' in method.decorators:
                    method_text = f"{{property}} {method_text}"
                elif method.is_async:
                    method_text = f"{{async}} {method_text}"

                # Truncate if too long
                max_chars = int(width / 7) - 2
                if len(method_text) > max_chars:
                    method_text = method_text[:max_chars - 2] + '..'

                self.canvas.create_text(
                    x + 10, current_y + 9,
                    text=method_text,
                    fill=color,
                    font=('Consolas', 9),
                    anchor='w',
                    tags=('method', cls.name)
                )
                current_y += 18

            if len(all_methods) > 20:
                self.canvas.create_text(
                    x + 10, current_y + 9,
                    text=f"... +{len(all_methods) - 20} more methods",
                    fill='#999999',
                    font=('Consolas', 8, 'italic'),
                    anchor='w',
                    tags=('more_methods', cls.name)
                )

    def _draw_relationships(self):
        """Draw inheritance and other relationships"""
        # Build parent-child relationships
        for class_name, box_info in self.class_boxes.items():
            cls = box_info['class']

            for base in cls.bases:
                if base in self.class_boxes:
                    # Draw inheritance arrow from parent to child
                    self._draw_inheritance_arrow(base, class_name)

    def _draw_inheritance_arrow(self, parent_name: str, child_name: str):
        """Draw inheritance arrow from parent to child"""
        parent_box = self.class_boxes.get(parent_name)
        child_box = self.class_boxes.get(child_name)

        if not parent_box or not child_box:
            return

        # Calculate connection points
        # Parent bottom center
        parent_x = parent_box['x'] + parent_box['width'] / 2
        parent_y = parent_box['y'] + parent_box['height']

        # Child top center
        child_x = child_box['x'] + child_box['width'] / 2
        child_y = child_box['y']

        # Draw line with arrow
        if abs(parent_x - child_x) < 20:
            # Straight vertical line
            self.canvas.create_line(
                parent_x, parent_y,
                child_x, child_y,
                fill=self.colors['inheritance_arrow'],
                width=2,
                arrow=tk.LAST,
                arrowshape=(12, 15, 5),
                tags=('inheritance', f'{parent_name}_to_{child_name}')
            )
        else:
            # L-shaped line for better visibility
            mid_y = (parent_y + child_y) / 2

            self.canvas.create_line(
                parent_x, parent_y,
                parent_x, mid_y,
                child_x, mid_y,
                child_x, child_y,
                fill=self.colors['inheritance_arrow'],
                width=2,
                smooth=False,
                arrow=tk.LAST,
                arrowshape=(12, 15, 5),
                tags=('inheritance', f'{parent_name}_to_{child_name}')
            )

        # Draw hollow triangle at parent end (UML style)
        triangle_size = 10
        triangle = self.canvas.create_polygon(
            parent_x, parent_y,
            parent_x - triangle_size / 2, parent_y + triangle_size,
            parent_x + triangle_size / 2, parent_y + triangle_size,
            fill='white',
            outline=self.colors['inheritance_arrow'],
            width=2,
            tags=('inheritance_triangle', parent_name)
        )

    def _on_click(self, event):
        """Handle click on class box"""
        x = self.canvas.canvasx(event.x)
        y = self.canvas.canvasy(event.y)

        # Find clicked item
        items = self.canvas.find_overlapping(x - 2, y - 2, x + 2, y + 2)

        for item in items:
            tags = self.canvas.gettags(item)

            # Find class name in tags
            for tag in tags:
                if tag in self.class_boxes:
                    self._select_class(tag)
                    return

    def _on_double_click(self, event):
        """Handle double click - center on class"""
        x = self.canvas.canvasx(event.x)
        y = self.canvas.canvasy(event.y)

        items = self.canvas.find_overlapping(x - 2, y - 2, x + 2, y + 2)

        for item in items:
            tags = self.canvas.gettags(item)

            for tag in tags:
                if tag in self.class_boxes:
                    box = self.class_boxes[tag]
                    center_x = box['x'] + box['width'] / 2
                    center_y = box['y'] + box['height'] / 2
                    self._center_on_point(center_x, center_y)
                    return

    def _center_on_point(self, x, y):
        """Center view on a point"""
        canvas_width = self.canvas.winfo_width()
        canvas_height = self.canvas.winfo_height()

        # Move to center
        self.canvas.xview_moveto(0)
        self.canvas.yview_moveto(0)

        # Calculate offset to center the point
        current_x = self.canvas.canvasx(canvas_width / 2)
        current_y = self.canvas.canvasy(canvas_height / 2)

        offset_x = x - current_x
        offset_y = y - current_y

        self.canvas.scan_mark(0, 0)
        self.canvas.scan_dragto(int(-offset_x), int(-offset_y), gain=1)

    def _select_class(self, class_name: str):
        """Select and highlight a class"""
        # Clear previous selection
        if self.selected_class:
            items = self.canvas.find_withtag(self.selected_class)
            for item in items:
                if 'class_box' in self.canvas.gettags(item):
                    self.canvas.itemconfig(item, outline=self.colors['border'], width=2)

        # Highlight new selection
        items = self.canvas.find_withtag(class_name)
        for item in items:
            if 'class_box' in self.canvas.gettags(item):
                self.canvas.itemconfig(item, outline=self.colors['selected'], width=3)
                self.selected_class = class_name
                break

        # Callback
        if self.on_select_callback and class_name in self.class_boxes:
            cls = self.class_boxes[class_name]['class']
            self.on_select_callback(('class', cls))

    def _update_display(self):
        """Update display based on view options"""
        if self.class_boxes:
            # Recalculate layout if needed
            all_classes = [(box['module'], box['class'])
                           for box in self.class_boxes.values()]
            self._calculate_layout(all_classes)
            self._draw_diagram(all_classes)

    def _relayout(self):
        """Re-layout diagram with selected algorithm"""
        if self.class_boxes:
            all_classes = [(box['module'], box['class'])
                           for box in self.class_boxes.values()]
            self._calculate_layout(all_classes)
            self._draw_diagram(all_classes)

    def _fit_view(self):
        """Fit diagram to view"""
        self.canvas.fit_to_view()

    def _export_diagram(self):
        """Export diagram as image"""
        from tkinter import filedialog

        filepath = filedialog.asksaveasfilename(
            defaultextension='.ps',
            filetypes=[
                ('PostScript', '*.ps'),
                ('Encapsulated PostScript', '*.eps')
            ]
        )

        if filepath:
            # Export as PostScript
            self.canvas.postscript(file=filepath)
            messagebox.showinfo("Export Complete", f"Diagram exported to {filepath}")



class OptimizedCodePreview(ttk.Frame):
    """Code preview panel with enhanced syntax highlighting"""

    HIGHLIGHT_COLOR = '#FFFF00'
    CURRENT_MATCH_COLOR = '#FF6600'

    COLORS = {
        'keyword': '#569CD6',
        'builtin': '#4EC9B0',
        'string': '#CE9178',
        'comment': '#6A9955',
        'number': '#B5CEA8',
        'operator': '#D4D4D4',
        'decorator': '#DCDCAA',
        'function': '#DCDCAA',
        'class': '#4EC9B0',
        'self': '#569CD6',
        'default': '#D4D4D4',
    }

    def __init__(self, parent):
        super().__init__(parent)

        self.current_file = None
        self.cache_manager = None
        self.file_cache = {}
        self.search_matches = []
        self.current_match_index = -1
        self.hidden_lines = []  # Track hidden comment blocks
        self.original_content = ""  # Store original content

        self._create_widgets()
        self._setup_syntax_tags()

    def reconfigure_colors(self, theme_dict: dict):
        """Update code preview colors based on the theme dictionary"""
        is_dark = theme_dict.get('name', 'dark') == 'dark'
        
        # Override specific text area background to strict neutral to ensure pure syntax highlighting
        editor_bg = '#1E1E1E' if is_dark else '#FAFAFA'

        self.text.configure(bg=editor_bg, fg=theme_dict['fg'], 
                            selectbackground=theme_dict['select'],
                            selectforeground=theme_dict['fg'],
                            insertbackground=theme_dict['fg'])
        self.line_numbers.configure(bg=theme_dict['select'], fg=theme_dict['fg'])
        
        if is_dark:
            self.HIGHLIGHT_LINE_BG = '#264F78' if theme_dict['bg'] != '#000000' else '#003300'
            colors = {
                'keyword': '#569CD6', 'builtin': '#4EC9B0', 'string': '#CE9178',
                'comment': '#6A9955', 'number': '#B5CEA8', 'operator': '#D4D4D4',
                'decorator': '#DCDCAA', 'function': '#DCDCAA', 'class': '#4EC9B0',
                'self': '#569CD6', 'default': '#D4D4D4'
            }
        else:
            self.HIGHLIGHT_LINE_BG = '#E8F2FF' if theme_dict['bg'] == '#FFFFFF' else '#C8E6C9'
            colors = {
                'keyword': '#0000FF', 'builtin': '#006699', 'string': '#A31515',
                'comment': '#008000', 'number': '#098658', 'operator': '#000000',
                'decorator': '#000000', 'function': '#795E26', 'class': '#267F99',
                'self': '#0000FF', 'default': '#000000'
            }
        
        self.COLORS = colors
        self._setup_syntax_tags()
        # Trigger re-highlight if file is already loaded
        if self.original_content:
            text = self.text.get('1.0', 'end-1c')
            self._highlight_code(text)

    def _create_widgets(self):
        """Create preview widgets"""
        # Header
        header_frame = ttk.Frame(self)
        header_frame.pack(fill=tk.X, padx=5, pady=2)

        self.file_label = ttk.Label(
            header_frame,
            text="No file loaded",
            font=('Segoe UI', 10, 'bold')
        )
        self.file_label.pack(side=tk.LEFT)

        self.position_label = ttk.Label(
            header_frame,
            text="",
            font=('Segoe UI', 9)
        )
        self.position_label.pack(side=tk.RIGHT)

        # Toolbar
        toolbar = ttk.Frame(self)
        toolbar.pack(fill=tk.X, padx=5)

        ttk.Button(toolbar, text="Copy", command=self._copy_selection,
                   width=8).pack(side=tk.LEFT, padx=2)
        ttk.Button(toolbar, text="Find", command=self._show_find,
                   width=8).pack(side=tk.LEFT, padx=2)

        ttk.Separator(toolbar, orient='vertical').pack(side=tk.LEFT, fill='y', padx=5)

        # Font size control
        ttk.Label(toolbar, text="Font:").pack(side=tk.LEFT, padx=2)

        self.font_size = tk.IntVar(value=10)
        font_spin = ttk.Spinbox(
            toolbar,
            from_=8, to=16,
            textvariable=self.font_size,
            width=5,
            command=self._update_font
        )
        font_spin.pack(side=tk.LEFT)

        # Line numbers checkbox
        self.show_line_numbers = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            toolbar,
            text="Line Numbers",
            variable=self.show_line_numbers,
            command=self._toggle_line_numbers
        ).pack(side=tk.LEFT, padx=10)

        # Hide comments checkbox
        self.hide_comments = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            toolbar,
            text="Hide Comment Blocks",
            variable=self.hide_comments,
            command=self._toggle_hide_comments
        ).pack(side=tk.LEFT, padx=10)

        # Text frame with line numbers
        text_frame = ttk.Frame(self)
        text_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Line numbers text widget
        self.line_numbers = tk.Text(
            text_frame,
            width=6,
            padx=5,
            pady=5,
            wrap=tk.NONE,
            bg='#2B2B2B',
            fg='#808080',
            state='disabled',
            font=('Consolas', 10),
            takefocus=0
        )

        # Main text widget with syntax highlighting
        self.text = tk.Text(
            text_frame,
            wrap=tk.NONE,
            padx=5,
            pady=5,
            bg='#1E1E1E',
            fg='#D4D4D4',
            insertbackground='white',
            selectbackground='#264F78',
            selectforeground='white',
            font=('Consolas', 10),
            undo=False
        )

        # Scrollbars
        v_scrollbar = ttk.Scrollbar(text_frame, orient='vertical')
        h_scrollbar = ttk.Scrollbar(text_frame, orient='horizontal')

        # Configure scrolling
        def on_v_scroll(*args):
            self.text.yview(*args)
            self.line_numbers.yview(*args)

        def on_text_scroll(*args):
            v_scrollbar.set(*args)
            self.line_numbers.yview_moveto(args[0])

        v_scrollbar.configure(command=on_v_scroll)
        h_scrollbar.configure(command=self.text.xview)
        self.text.configure(
            yscrollcommand=on_text_scroll,
            xscrollcommand=h_scrollbar.set
        )

        # Grid layout
        self.line_numbers.grid(row=0, column=0, sticky='ns')
        self.text.grid(row=0, column=1, sticky='nsew')
        v_scrollbar.grid(row=0, column=2, sticky='ns')
        h_scrollbar.grid(row=1, column=0, columnspan=2, sticky='ew')

        text_frame.grid_rowconfigure(0, weight=1)
        text_frame.grid_columnconfigure(1, weight=1)

        # Find frame (hidden initially)
        self.find_frame = ttk.Frame(self)

        ttk.Label(self.find_frame, text="Find:").pack(side=tk.LEFT, padx=5)

        self.find_var = tk.StringVar()
        self.find_entry = ttk.Entry(self.find_frame, textvariable=self.find_var, width=30)
        self.find_entry.pack(side=tk.LEFT, padx=5)
        self.find_entry.bind('<Return>', lambda e: self._find_next())
        self.find_entry.bind('<Escape>', lambda e: self._hide_find())

        self.case_sensitive_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(self.find_frame, text="Case",
                        variable=self.case_sensitive_var).pack(side=tk.LEFT, padx=2)

        ttk.Button(self.find_frame, text="Next", command=self._find_next,
                   width=8).pack(side=tk.LEFT, padx=2)
        ttk.Button(self.find_frame, text="Previous", command=self._find_previous,
                   width=8).pack(side=tk.LEFT, padx=2)

        self.match_label = ttk.Label(self.find_frame, text="")
        self.match_label.pack(side=tk.LEFT, padx=5)

        ttk.Button(self.find_frame, text="Close", command=self._hide_find,
                   width=8).pack(side=tk.LEFT, padx=2)

        # Status bar
        self.status_label = ttk.Label(self, text="", font=('Segoe UI', 9))
        self.status_label.pack(side=tk.BOTTOM, fill=tk.X, padx=5, pady=2)

        # Bindings
        self.text.bind('<Control-f>', lambda e: self._show_find())
        self.text.bind('<F3>', lambda e: self._find_next())
        self.text.bind('<Shift-F3>', lambda e: self._find_previous())

    def _setup_syntax_tags(self):
        """Configure syntax highlighting tags"""
        for tag_name, color in self.COLORS.items():
            self.text.tag_configure(tag_name, foreground=color)

        # Special highlighting
        hl_bg = getattr(self, 'HIGHLIGHT_LINE_BG', '#264F78')
        self.text.tag_configure('highlight_line', background=hl_bg)
        self.text.tag_configure('search_highlight',
                                background=self.HIGHLIGHT_COLOR,
                                foreground='#000000')
        self.text.tag_configure('current_match',
                                background=self.CURRENT_MATCH_COLOR,
                                foreground='#000000')

        # Raise search tags above syntax tags
        self.text.tag_raise('search_highlight')
        self.text.tag_raise('current_match')
        self.text.tag_raise('highlight_line')

    def load_file(self, filepath: str, line_start: int = None, line_end: int = None):
        """Load and display a file with syntax highlighting"""
        if filepath == self.current_file and filepath in self.file_cache:
            if line_start and line_end:
                self.highlight_lines(line_start, line_end)
            return

        self.current_file = filepath
        self.file_label.configure(text=os.path.basename(filepath))

        # Check cache
        if filepath in self.file_cache:
            content = self.file_cache[filepath]
        else:
            try:
                with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                self.file_cache[filepath] = content
            except Exception as e:
                self.text.delete('1.0', tk.END)
                self.text.insert('1.0', f"Error loading file: {e}")
                self.status_label.configure(text=f"Error: {e}")
                return



        # Display and highlight
        # self._highlight_code(content)
        # Store original content
        self.original_content = content

        # Apply hiding if enabled
        if self.hide_comments.get():
            content = self._hide_comment_blocks(content)

        # Display and highlight
        self._highlight_code(content)


        # Update line numbers
        lines = content.split('\n')
        self._update_line_numbers(len(lines))

        # Highlight specific lines if requested
        if line_start and line_end:
            self.highlight_lines(line_start, line_end)

        # Update status
        file_size = len(content)
        self.status_label.configure(
            text=f"Lines: {len(lines)} | Size: {file_size:,} bytes | {filepath}"
        )

    def _highlight_code(self, code: str):
        """Apply syntax highlighting using Pygments or fallback"""
        self.text.delete('1.0', tk.END)
        self.text.insert('1.0', code)

        if HAS_PYGMENTS:
            self._pygments_highlight(code)
        else:
            self._basic_highlight()

        # Mark collapsed comment lines if any
        if self.hide_comments.get():
            self._mark_collapsed_comments()  # ADD THIS LINE

    def _pygments_highlight(self, code: str):
        """Use Pygments for advanced syntax highlighting"""
        # Remove old tags
        for tag in self.COLORS.keys():
            self.text.tag_remove(tag, '1.0', tk.END)

        lexer = PythonLexer()
        tokens = lex(code, lexer)

        line = 1
        col = 0

        for token_type, token_value in tokens:
            start = f"{line}.{col}"

            newlines = token_value.count('\n')
            if newlines:
                last_newline = token_value.rfind('\n')
                end_line = line + newlines
                end_col = len(token_value) - last_newline - 1
            else:
                end_line = line
                end_col = col + len(token_value)

            end = f"{end_line}.{end_col}"

            tag = self._get_tag_for_token(token_type)
            if tag:
                self.text.tag_add(tag, start, end)

            line = end_line
            col = end_col

    def _get_tag_for_token(self, token_type):
        """Map Pygments token to tag name"""
        if token_type in Token.Keyword:
            return 'keyword'
        elif token_type in Token.Name.Builtin:
            return 'builtin'
        elif token_type in Token.String:
            return 'string'
        elif token_type in Token.Comment:
            return 'comment'
        elif token_type in Token.Number:
            return 'number'
        elif token_type in Token.Operator:
            return 'operator'
        elif token_type in Token.Name.Decorator:
            return 'decorator'
        elif token_type in Token.Name.Function:
            return 'function'
        elif token_type in Token.Name.Class:
            return 'class'
        return None

    def _basic_highlight(self):
        """Fallback basic highlighting using regex"""
        content = self.text.get('1.0', tk.END)

        # Keywords
        keywords = ['def', 'class', 'import', 'from', 'return', 'if', 'else',
                    'elif', 'for', 'while', 'try', 'except', 'finally', 'with',
                    'as', 'yield', 'raise', 'pass', 'break', 'continue', 'in',
                    'not', 'and', 'or', 'is', 'None', 'True', 'False', 'lambda']

        for keyword in keywords:
            self._highlight_pattern(f'\\b{keyword}\\b', 'keyword')

        # Strings
        self._highlight_pattern(r'"""[\s\S]*?"""', 'string')
        self._highlight_pattern(r"'''[\s\S]*?'''", 'string')
        self._highlight_pattern(r'"(?:[^"\\]|\\.)*"', 'string')
        self._highlight_pattern(r"'(?:[^'\\]|\\.)*'", 'string')

        # Comments
        self._highlight_pattern(r'#[^\n]*', 'comment')

        # Numbers
        self._highlight_pattern(r'\b\d+\.?\d*\b', 'number')

        # Decorators
        self._highlight_pattern(r'@\w+', 'decorator')

        # Functions
        self._highlight_pattern(r'(?<=def\s)\w+', 'function')

        # Classes
        self._highlight_pattern(r'(?<=class\s)\w+', 'class')

    def _highlight_pattern(self, pattern: str, tag: str):
        """Highlight regex pattern"""
        content = self.text.get('1.0', tk.END)
        for match in re.finditer(pattern, content, re.MULTILINE):
            start = f"1.0+{match.start()}c"
            end = f"1.0+{match.end()}c"
            self.text.tag_add(tag, start, end)

    def highlight_lines(self, line_start: int, line_end: int):
        """Highlight specific lines"""
        self.text.tag_remove('highlight_line', '1.0', tk.END)
        self.text.tag_add('highlight_line', f'{line_start}.0', f'{line_end + 1}.0')
        self.text.see(f'{line_start}.0')
        self.position_label.configure(text=f"Lines {line_start}-{line_end}")

    def _show_find(self):
        """Show find toolbar"""
        self.find_frame.pack(fill=tk.X, padx=5, pady=2, before=self.status_label)
        self.find_entry.focus()
        self.find_entry.select_range(0, tk.END)

    def _hide_find(self):
        """Hide find toolbar"""
        self.find_frame.pack_forget()
        self._clear_search_highlights()

    def _find_next(self):
        """Find next match"""
        query = self.find_var.get()
        if not query:
            return

        # First search
        if not self.search_matches:
            count = self._search_and_highlight(query)
            if count > 0:
                self._update_match_label()
            else:
                self.match_label.configure(text="No matches")
        else:
            # Navigate to next
            self._next_match()
            self._update_match_label()

    def _find_previous(self):
        """Find previous match"""
        if self.search_matches:
            self._prev_match()
            self._update_match_label()

    def _search_and_highlight(self, query: str) -> int:
        """Search and highlight all matches"""
        self._clear_search_highlights()
        self.search_matches = []
        self.current_match_index = -1

        start_pos = '1.0'
        count_var = tk.IntVar()
        case_sensitive = self.case_sensitive_var.get()

        while True:
            if case_sensitive:
                pos = self.text.search(query, start_pos, stopindex=tk.END, count=count_var)
            else:
                pos = self.text.search(query, start_pos, stopindex=tk.END,
                                       count=count_var, nocase=True)

            if not pos:
                break

            end_pos = f"{pos}+{count_var.get()}c"
            self.search_matches.append((pos, end_pos))
            self.text.tag_add('search_highlight', pos, end_pos)
            start_pos = end_pos

        if self.search_matches:
            self.current_match_index = 0
            self._highlight_current_match()

        return len(self.search_matches)

    def _highlight_current_match(self):
        """Highlight current match"""
        self.text.tag_remove('current_match', '1.0', tk.END)
        if 0 <= self.current_match_index < len(self.search_matches):
            start, end = self.search_matches[self.current_match_index]
            self.text.tag_add('current_match', start, end)
            self.text.see(start)
            self.text.mark_set(tk.INSERT, start)

    def _next_match(self):
        """Navigate to next match"""
        if self.search_matches:
            self.current_match_index = (self.current_match_index + 1) % len(self.search_matches)
            self._highlight_current_match()

    def _prev_match(self):
        """Navigate to previous match"""
        if self.search_matches:
            self.current_match_index = (self.current_match_index - 1) % len(self.search_matches)
            self._highlight_current_match()

    def _clear_search_highlights(self):
        """Clear all search highlights"""
        self.text.tag_remove('search_highlight', '1.0', tk.END)
        self.text.tag_remove('current_match', '1.0', tk.END)
        self.search_matches = []
        self.current_match_index = -1

    def _update_match_label(self):
        """Update match counter label"""
        if self.search_matches:
            self.match_label.configure(
                text=f"{self.current_match_index + 1} of {len(self.search_matches)}"
            )
        else:
            self.match_label.configure(text="")



    def _update_line_numbers(self, line_count: int):
        """Update line numbers display"""
        self.line_numbers.configure(state='normal')
        self.line_numbers.delete('1.0', tk.END)

        if self.show_line_numbers.get():
            line_numbers_text = '\n'.join(str(i) for i in range(1, line_count + 1))
            self.line_numbers.insert('1.0', line_numbers_text)

        self.line_numbers.configure(state='disabled')

    def _make_line_numbers_clickable(self):
        """Make collapse/expand icons in line numbers clickable"""
        # Enable temporarily to add tags
        self.line_numbers.configure(state='normal')

        # Find and tag collapse/expand indicators
        content = self.line_numbers.get('1.0', tk.END)
        lines = content.split('\n')

        for i, line in enumerate(lines, 1):
            start = f"{i}.0"
            end = f"{i}.end"

            if line.strip().startswith('▶'):
                # Collapsed block - clickable
                self.line_numbers.tag_add('collapse_icon', start, end)
            elif line.strip().startswith('▼'):
                # Expanded block header - clickable
                self.line_numbers.tag_add('expand_icon', start, end)
            elif '💬' in line:
                # Expanded comment line - not clickable, just styled
                self.line_numbers.tag_add('comment_icon', start, end)

        # Configure tags
        self.line_numbers.tag_configure('collapse_icon',
                                        foreground='#4EC9B0',
                                        font=('Consolas', 10, 'bold'))
        self.line_numbers.tag_configure('expand_icon',
                                        foreground='#FFD700',
                                        font=('Consolas', 10, 'bold'))
        self.line_numbers.tag_configure('comment_icon',
                                        foreground='#6A9955')

        # Bind click events
        self.line_numbers.tag_bind('collapse_icon', '<Button-1>', self._on_line_number_click)
        self.line_numbers.tag_bind('expand_icon', '<Button-1>', self._on_line_number_click)

        # Change cursor on hover
        for tag in ['collapse_icon', 'expand_icon']:
            self.line_numbers.tag_bind(tag, '<Enter>',
                                       lambda e: self.line_numbers.configure(cursor='hand2'))
            self.line_numbers.tag_bind(tag, '<Leave>',
                                       lambda e: self.line_numbers.configure(cursor=''))

        self.line_numbers.configure(state='disabled')

    def _on_line_number_click(self, event):
        """Handle click on collapse/expand icon in line numbers"""
        # Get clicked line in line_numbers widget
        index = self.line_numbers.index(f"@{event.x},{event.y}")
        clicked_visual_line = int(index.split('.')[0])

        # Get the text of clicked line
        line_text = self.line_numbers.get(f"{clicked_visual_line}.0", f"{clicked_visual_line}.end")

        if '▶' in line_text:
            # Expand the block
            self._expand_block_by_visual_line(clicked_visual_line)
        elif '▼' in line_text:
            # Collapse the block
            self._collapse_block_by_visual_line(clicked_visual_line)

    def _toggle_line_numbers(self):
        """Toggle line numbers visibility"""
        if self.show_line_numbers.get():
            self.line_numbers.grid()
            if self.current_file:
                lines = self.text.get('1.0', tk.END).count('\n')
                self._update_line_numbers(lines)
        else:
            self.line_numbers.grid_remove()

    def _update_font(self):
        """Update text font size"""
        font_size = self.font_size.get()
        self.text.configure(font=('Consolas', font_size))
        self.line_numbers.configure(font=('Consolas', font_size))

    def _copy_selection(self):
        """Copy selected text to clipboard"""
        try:
            selection = self.text.get(tk.SEL_FIRST, tk.SEL_LAST)
            self.clipboard_clear()
            self.clipboard_append(selection)
            self.status_label.configure(text=f"Copied {len(selection)} characters")
        except tk.TclError:
            self.status_label.configure(text="No selection")

    def _toggle_hide_comments(self):
        """Toggle hiding of comment blocks - SIMPLE VERSION"""
        if not self.original_content:
            return

        content = self.original_content

        if self.hide_comments.get():
            # Hide comment blocks by filtering lines
            lines = content.split('\n')
            filtered_lines = []
            i = 0
            blocks_hidden = 0

            while i < len(lines):
                line = lines[i]

                # Check if comment line
                if line.lstrip().startswith('#'):
                    # Count consecutive comments
                    start = i
                    count = 0
                    while i < len(lines) and lines[i].lstrip().startswith('#'):
                        count += 1
                        i += 1

                    # If 3+ comments, replace with placeholder
                    if count >= 3:
                        indent = len(line) - len(line.lstrip())
                        filtered_lines.append(' ' * indent + f'# ... {count} comment lines hidden ...')
                        blocks_hidden += 1
                    else:
                        # Keep small blocks
                        filtered_lines.extend(lines[start:i])
                else:
                    filtered_lines.append(line)
                    i += 1

            content = '\n'.join(filtered_lines)
            self.status_label.configure(text=f"Hidden {blocks_hidden} comment block(s)")
        else:
            self.status_label.configure(text="")

        # Redisplay
        self._highlight_code(content)
        lines = content.split('\n')
        self._update_line_numbers(len(lines))

    def _hide_comment_blocks(self, content: str) -> str:
        """Hide consecutive comment lines (3+ lines starting with #) - DON'T modify text"""
        lines = content.split('\n')
        self.hidden_lines = []

        i = 0
        block_id = 0

        while i < len(lines):
            line = lines[i]
            stripped = line.lstrip()

            # Check if this is start of a comment block
            if stripped.startswith('#'):
                # Count consecutive comment lines
                block_start = i
                block_lines = []

                while i < len(lines) and lines[i].lstrip().startswith('#'):
                    block_lines.append(i)  # Store line numbers
                    i += 1

                # If 3 or more consecutive comment lines, mark for hiding
                if len(block_lines) >= 3:
                    self.hidden_lines.append({
                        'id': block_id,
                        'start_line': block_start + 1,  # 1-indexed
                        'end_line': block_start + len(block_lines),
                        'line_numbers': block_lines,
                        'count': len(block_lines),
                        'expanded': False
                    })
                    block_id += 1
            else:
                i += 1

        # Return ORIGINAL content unchanged
        return content

    def _setup_comment_expand_bindings(self):
        """Setup click binding to expand/collapse hidden comment blocks"""
        self.text.tag_configure('collapsed_comment',
                                foreground='#4EC9B0',
                                background='#2A2A2A',
                                font=('Consolas', 10, 'bold'))

        self.text.tag_configure('expanded_comment',
                                foreground='#6A9955',
                                background='#1E1E1E')

        self.text.tag_configure('collapse_button',
                                foreground='#FFD700',
                                background='#2A2A2A',
                                font=('Consolas', 10, 'bold'))

        self.text.tag_bind('collapsed_comment', '<Button-1>', self._toggle_comment_block)
        self.text.tag_bind('collapse_button', '<Button-1>', self._toggle_comment_block)
        self.text.tag_bind('collapsed_comment', '<Enter>',
                           lambda e: self.text.configure(cursor='hand2'))
        self.text.tag_bind('collapsed_comment', '<Leave>',
                           lambda e: self.text.configure(cursor=''))
        self.text.tag_bind('collapse_button', '<Enter>',
                           lambda e: self.text.configure(cursor='hand2'))
        self.text.tag_bind('collapse_button', '<Leave>',
                           lambda e: self.text.configure(cursor=''))

    def _mark_collapsed_comments(self):
        """Mark collapsed/expanded comment lines for clicking"""
        content = self.text.get('1.0', tk.END)
        lines = content.split('\n')

        for i, line in enumerate(lines, 1):
            start = f"{i}.0"
            end = f"{i}.end"

            # Mark collapsed indicators
            if '▶' in line and 'comment lines hidden' in line:
                self.text.tag_add('collapsed_comment', start, end)

            # Mark expanded comment lines with collapse button
            elif '▼' in line and 'comment lines' in line:
                self.text.tag_add('collapse_button', start, end)

            # Mark individual comment lines with icon
            elif line.strip().startswith('💬'):
                self.text.tag_add('expanded_comment', start, end)

    def _toggle_comment_block(self, event):
        """Toggle expand/collapse of a comment block on click"""
        # Get clicked line
        index = self.text.index(f"@{event.x},{event.y}")
        line_num = int(index.split('.')[0])

        # Get the line content
        line_content = self.text.get(f"{line_num}.0", f"{line_num}.end")

        # Check if it's a collapsed block (expand it)
        if '▶' in line_content and 'hidden' in line_content:
            self._expand_block_at_line(line_num)

        # Check if it's an expanded block (collapse it)
        elif '▼' in line_content:
            self._collapse_block_at_line(line_num)

    def _expand_block_by_visual_line(self, visual_line: int):
        """Expand block at visual line number"""
        # Map visual line to actual block
        current_visual = 1

        for block in self.hidden_lines:
            if not block['expanded']:
                if current_visual == visual_line:
                    # Expand this block
                    block['expanded'] = True

                    # Refresh display
                    self._refresh_display()
                    return
                current_visual += 1
            else:
                # Skip past expanded block lines
                current_visual += block['count']

    def _collapse_block_by_visual_line(self, visual_line: int):
        """Collapse block at visual line number"""
        # Map visual line to block
        current_visual = 1

        for block in self.hidden_lines:
            if block['expanded']:
                # Check if this visual line is within this expanded block
                if current_visual <= visual_line <= current_visual + block['count'] - 1:
                    # Collapse this block
                    block['expanded'] = False

                    # Refresh display
                    self._refresh_display()
                    return
                current_visual += block['count']
            else:
                current_visual += 1

    def _refresh_display(self):
        """Refresh the code display after expand/collapse"""
        if not self.original_content:
            return

        # Get original content
        content = self.original_content

        # Re-highlight (content doesn't change, just visibility)
        self._highlight_code(content)

        # Update line numbers with new state
        lines = content.split('\n')
        self._update_line_numbers(len(lines))

        # Update status
        collapsed_count = sum(1 for b in self.hidden_lines if not b['expanded'])
        if collapsed_count > 0:
            self.status_label.configure(
                text=f"Hidden {collapsed_count} comment block(s) - Click ▶ to expand"
            )
        else:
            self.status_label.configure(text="All blocks visible - Uncheck to auto-hide")

    def _expand_block_at_line(self, line_num: int):
        """Expand a collapsed comment block"""
        # Get current content
        content = self.text.get('1.0', tk.END)
        lines = content.split('\n')

        # Find which block this is
        for block in self.hidden_lines:
            if not block['expanded']:
                # Count visible lines up to this point
                visible_line = self._get_visible_line_for_block(block)

                if visible_line + 1 == line_num:
                    # Expand this block
                    block['expanded'] = True

                    # Replace collapse indicator with expand indicator + comments
                    indent = ' ' * block['indent']
                    header = f"{indent}▼ {block['count']} comment lines (click to collapse)"

                    # Add comment icon to each line
                    expanded_lines = [header]
                    for comment_line in block['lines']:
                        stripped = comment_line.lstrip()
                        indent_len = len(comment_line) - len(stripped)
                        expanded_lines.append(' ' * indent_len + '💬 ' + stripped)

                    # Replace the line
                    lines[line_num - 1:line_num] = expanded_lines

                    # Redisplay
                    new_content = '\n'.join(lines)
                    self._highlight_code(new_content)
                    self._mark_collapsed_comments()

                    # Update status
                    collapsed_count = sum(1 for b in self.hidden_lines if not b['expanded'])
                    if collapsed_count > 0:
                        self.status_label.configure(
                            text=f"{collapsed_count} block(s) hidden - Click ▶ to expand, ▼ to collapse"
                        )
                    else:
                        self.status_label.configure(text="All blocks expanded - Click ▼ to collapse")

                    break

    def _collapse_block_at_line(self, line_num: int):
        """Collapse an expanded comment block"""
        # Get current content
        content = self.text.get('1.0', tk.END)
        lines = content.split('\n')

        # Find which block this is (the header line with ▼)
        for block in self.hidden_lines:
            if block['expanded']:
                # This block is expanded, check if clicked line is its header
                visible_line = self._get_visible_line_for_block(block)

                if visible_line + 1 == line_num:
                    # Collapse this block
                    block['expanded'] = False

                    # Replace expanded lines with collapse indicator
                    indent = ' ' * block['indent']
                    collapse_line = f"{indent}▶ {block['count']} comment lines hidden (click to expand)"

                    # Remove the header + all comment lines
                    num_lines_to_remove = block['count'] + 1  # +1 for header
                    lines[line_num - 1:line_num - 1 + num_lines_to_remove] = [collapse_line]

                    # Redisplay
                    new_content = '\n'.join(lines)
                    self._highlight_code(new_content)
                    self._mark_collapsed_comments()

                    # Update status
                    collapsed_count = sum(1 for b in self.hidden_lines if not b['expanded'])
                    self.status_label.configure(
                        text=f"{collapsed_count} block(s) hidden - Click ▶ to expand"
                    )

                    break

    def _get_visible_line_for_block(self, block) -> int:
        """Calculate which visible line number a block appears at"""
        visible_line = 0

        for b in self.hidden_lines:
            if b['id'] == block['id']:
                return visible_line

            if b['expanded']:
                visible_line += b['count'] + 1  # +1 for header
            else:
                visible_line += 1  # Just the collapse line

        return visible_line



    def _expand_block(self, block, line_num: int):
        """Expand a specific comment block"""
        # Get current content
        content = self.text.get('1.0', tk.END)
        lines = content.split('\n')

        # Replace the collapse line with original lines
        lines[line_num - 1:line_num] = block['lines']

        # Redisplay
        new_content = '\n'.join(lines)
        self._highlight_code(new_content)

        # Remove this block from hidden list
        self.hidden_lines.remove(block)

        # Update status
        if self.hidden_lines:
            self.status_label.configure(
                text=f"Hidden {len(self.hidden_lines)} comment block(s)"
            )
        else:
            self.status_label.configure(text="All blocks expanded")

# ============================================================================
# MAIN APPLICATION WINDOW
# ============================================================================

class PythonCodeVisualizerApp(tk.Tk):
    """Main application window"""

    def __init__(self):
        super().__init__()

        # Initialize components
        self.config_manager = ConfigManager()
        self.recent_files_manager = RecentFilesManager(self.config_manager)
        self.cache_manager = CacheManager(
            max_size_mb=self.config_manager.get_int('Performance', 'cache_size_mb', 50)
        )
        self.thread_pool = ThreadPool(max_workers=4)
        self.analyzer = PythonCodeAnalyzer(cache_manager=self.cache_manager)

        # Data
        self.modules = []
        self.current_file = None

        # Setup window
        self._setup_window()
        self._setup_styles()

        # Create UI components
        self._create_menu()
        self._create_toolbar()
        self._create_main_layout()
        self._create_statusbar()

        # Bind events
        self._bind_events()

        # Load last session if configured
        self._restore_session()

    def _setup_window(self):
        """Setup main window properties"""
        self.title("🐍 Python Code Visualizer Pro")

        # Load window geometry from config
        geometry = self.config_manager.get('General', 'window_geometry', '1400x900+50+50')
        self.geometry(geometry)

        # Set minimum size
        self.minsize(800, 600)

        # Set window icon if available
        try:
            icon_path = os.path.join(os.path.dirname(__file__), 'icon.ico')
            if os.path.exists(icon_path):
                self.iconbitmap(icon_path)
        except:
            pass

        # Configure grid
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)


    def _setup_styles(self):
        """Setup ttk styles"""
        style = ttk.Style()

        # Try to use a modern theme
        available_themes = style.theme_names()
        if 'clam' in available_themes:
            style.theme_use('clam')
        elif 'vista' in available_themes and os.name == 'nt':
            style.theme_use('vista')

        theme = self.config_manager.get('General', 'theme', 'dark')
        self._apply_theme_colors(theme)

    def _apply_theme_colors(self, theme_name: str):
        style = ttk.Style()
        themes = {
            'dark':   {'name': 'dark', 'bg': '#2B2B2B', 'fg': '#FFFFFF', 'select': '#404040', 'entry_bg': '#3C3C3C', 'entry_fg': '#FFFFFF'},
            'yellow': {'name': 'dark', 'bg': '#2B2B2B', 'fg': '#FFD700', 'select': '#404040', 'entry_bg': '#3C3C3C', 'entry_fg': '#FFD700'},
            'red':    {'name': 'dark', 'bg': '#2B1B1B', 'fg': '#FF4444', 'select': '#3D1F1F', 'entry_bg': '#3C2C2C', 'entry_fg': '#FFFFFF'},
            'green':  {'name': 'light', 'bg': '#F0FFF0', 'fg': '#2E7D32', 'select': '#C8E6C9', 'entry_bg': '#FFFFFF', 'entry_fg': '#000000'},
            'blue':   {'name': 'light', 'bg': '#F0F4FF', 'fg': '#1565C0', 'select': '#BBDEFB', 'entry_bg': '#FFFFFF', 'entry_fg': '#000000'},
        }
        # Fallback to dark if unknown literal is passed
        t = themes.get(theme_name, themes.get('dark')) 
        if t is None: t = themes['dark']

        style.configure('TFrame', background=t['bg'])
        style.configure('TLabel', background=t['bg'], foreground=t['fg'])
        style.configure('TLabelframe', background=t['bg'], foreground=t['fg'])
        style.configure('TLabelframe.Label', background=t['bg'], foreground=t['fg'])
        style.configure('TButton', background=t['bg'], foreground=t['fg'])
        style.map('TButton', background=[('active', t['select'])], foreground=[('active', t['fg'])])
        style.configure('TCheckbutton', background=t['bg'], foreground=t['fg'])
        style.map('TCheckbutton', background=[('active', t['select'])], foreground=[('active', t['fg'])])
        style.configure('TRadiobutton', background=t['bg'], foreground=t['fg'])
        style.map('TRadiobutton', background=[('active', t['select'])], foreground=[('active', t['fg'])])
        style.configure('TNotebook', background=t['bg'])
        style.configure('TNotebook.Tab', background=t['bg'], foreground=t['fg'])
        style.configure('TEntry', fieldbackground=t['entry_bg'], foreground=t['entry_fg'], insertcolor=t['entry_fg'])
        style.configure('TSpinbox', fieldbackground=t['entry_bg'], foreground=t['entry_fg'], insertcolor=t['entry_fg'])
        style.configure('TCombobox', fieldbackground=t['entry_bg'], foreground=t['entry_fg'])
        style.configure('Treeview', background=t['entry_bg'], foreground=t['entry_fg'], fieldbackground=t['entry_bg'])
        style.map('Treeview', background=[('selected', t['select'])], foreground=[('selected', t['fg'])])
        style.configure('Found.TEntry', fieldbackground='#90EE90', foreground='#000000')
        style.configure('NotFound.TEntry', fieldbackground='#FFB6C1', foreground='#000000')
        style.configure('Toolbar.TFrame', background='#383838')
        style.configure('Tooltip.TFrame', background='#404040', borderwidth=1)
        style.configure('Tooltip.TLabel', background='#404040', foreground='white')

        self.config_manager.set('General', 'theme', theme_name)
        self.config_manager.save_config()
        self._current_theme = t

        # Update live tk widgets if already created across the app
        self._refresh_tk_widget_colors(t)

    def _refresh_tk_widget_colors(self, t: dict):
        try:
            self.module_listbox.configure(bg=t['entry_bg'], fg=t['entry_fg'],
                                          selectbackground=t['select'], selectforeground=t['entry_fg'])
        except AttributeError:
            pass
        try:
            if hasattr(self, 'code_preview') and self.code_preview:
                self.code_preview.reconfigure_colors(t)
        except AttributeError:
            pass
        self._force_widget_refresh(self, t)

    def _force_widget_refresh(self, widget, t: dict):
        for child in widget.winfo_children():
            # Basic Tkinter widgets support these
            try:
                child.configure(background=t['bg'])
                child.configure(activebackground=t['select'])
            except:
                pass
            try:
                child.configure(foreground=t['fg'])
                child.configure(activeforeground=t['fg'])
            except:
                pass
            self._force_widget_refresh(child, t)

    def _create_menu(self):
        """Create application menu bar"""
        menubar = tk.Menu(self, tearoff=0)
        self.config(menu=menubar)

        # File menu
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)

        file_menu.add_command(label="Open File...",
                              command=self._open_file,
                              accelerator="Ctrl+O")
        file_menu.add_command(label="Open Directory...",
                              command=self._open_directory,
                              accelerator="Ctrl+D")
        file_menu.add_separator()
        # file_menu.add_command(label="Recent Files",
        #                       command=self._show_recent_files)
        self.recent_menu = tk.Menu(file_menu, tearoff=0)
        file_menu.add_cascade(label="Recent Files", menu=self.recent_menu)
        self._update_recent_files_menu()
        file_menu.add_separator()
        file_menu.add_command(label="Save Session",
                              command=self._save_session,
                              accelerator="Ctrl+S")
        file_menu.add_command(label="Export Diagram...",
                              command=self._export_diagram,
                              accelerator="Ctrl+E")
        file_menu.add_separator()
        file_menu.add_command(label="Clear Cache",
                              command=self._clear_cache)
        file_menu.add_separator()
        file_menu.add_command(label="Exit",
                              command=self._quit_app,
                              accelerator="Alt+F4")

        # Edit menu
        edit_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Edit", menu=edit_menu)

        edit_menu.add_command(label="Find...",
                              command=self._find_in_tree,
                              accelerator="Ctrl+F")
        edit_menu.add_command(label="Find Next",
                              command=self._find_next_in_tree,
                              accelerator="F3")
        edit_menu.add_separator()
        edit_menu.add_command(label="Copy",
                              command=self._copy_selection,
                              accelerator="Ctrl+C")
        edit_menu.add_separator()
        edit_menu.add_command(label="Preferences...",
                              command=self._show_preferences)

        # View menu
        view_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="View", menu=view_menu)

        theme_menu = tk.Menu(view_menu, tearoff=0)
        view_menu.add_cascade(label="Theme", menu=theme_menu)
        theme_menu.add_command(label="Dark Mode", command=lambda: self._apply_theme_colors('dark'))
        theme_menu.add_command(label="Dark (Yellow Elements)", command=lambda: self._apply_theme_colors('yellow'))
        theme_menu.add_command(label="Dark (Red Elements)", command=lambda: self._apply_theme_colors('red'))
        theme_menu.add_command(label="Light (Green Elements)", command=lambda: self._apply_theme_colors('green'))
        theme_menu.add_command(label="Light (Blue Elements)", command=lambda: self._apply_theme_colors('blue'))
        view_menu.add_separator()

        view_menu.add_command(label="Refresh",
                              command=self._refresh_views,
                              accelerator="F5")
        view_menu.add_separator()
        view_menu.add_command(label="Zoom In",
                              command=self._zoom_in,
                              accelerator="Ctrl++")
        view_menu.add_command(label="Zoom Out",
                              command=self._zoom_out,
                              accelerator="Ctrl+-")
        view_menu.add_command(label="Reset Zoom",
                              command=self._reset_zoom,
                              accelerator="Ctrl+0")
        view_menu.add_separator()
        view_menu.add_command(label="Fit to Window",
                              command=self._fit_to_window)
        view_menu.add_separator()
        view_menu.add_command(label="Expand All",
                              command=self._expand_all)
        view_menu.add_command(label="Collapse All",
                              command=self._collapse_all)

        # Tools menu
        tools_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Tools", menu=tools_menu)

        tools_menu.add_command(label="Code Statistics",
                               command=self._show_statistics)
        tools_menu.add_command(label="Complexity Report",
                               command=self._show_complexity_report)
        tools_menu.add_separator()
        tools_menu.add_command(label="Find Duplicates",
                               command=self._find_duplicates)
        tools_menu.add_command(label="Find Unused",
                               command=self._find_unused)

        # Help menu
        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Help", menu=help_menu)

        help_menu.add_command(label="Documentation",
                              command=self._show_documentation)
        help_menu.add_command(label="Keyboard Shortcuts",
                              command=self._show_shortcuts)
        help_menu.add_separator()
        help_menu.add_command(label="About",
                              command=self._show_about)

    def _update_recent_files_menu(self):
        """Update recent files menu"""
        # Clear existing items
        self.recent_menu.delete(0, tk.END)

        recent_files = self.recent_files_manager.get_recent_files()

        if recent_files:
            for i, filepath in enumerate(recent_files):
                # Show filename and path
                display_name = f"{i + 1}. {os.path.basename(filepath)}"

                # Add menu item
                self.recent_menu.add_command(
                    label=display_name,
                    command=lambda f=filepath: self._open_recent_file(f)
                )

                # Add tooltip with full path
                if i < 9:  # Only first 9 get keyboard shortcuts
                    self.recent_menu.entryconfig(
                        i,
                        accelerator=f"Ctrl+{i + 1}"
                    )

            self.recent_menu.add_separator()
            self.recent_menu.add_command(
                label="Clear Recent Files",
                command=self._clear_recent_files
            )
        else:
            self.recent_menu.add_command(
                label="(No recent files)",
                state='disabled'
            )


    def _create_toolbar(self):
        """Create application toolbar"""
        self.toolbar = ttk.Frame(self, style='Toolbar.TFrame', height=40)
        self.toolbar.pack(fill=tk.X, pady=(0, 2))

        # Prevent toolbar from shrinking
        self.toolbar.pack_propagate(False)

        # File operations
        ttk.Button(self.toolbar, text="📂 Open File",
                   command=self._open_file).pack(side=tk.LEFT, padx=2, pady=5)
        ttk.Button(self.toolbar, text="📁 Open Folder",
                   command=self._open_directory).pack(side=tk.LEFT, padx=2, pady=5)

        ttk.Separator(self.toolbar, orient='vertical').pack(side=tk.LEFT, fill='y', padx=5)

        # View controls
        ttk.Button(self.toolbar, text="🔄 Refresh",
                   command=self._refresh_views).pack(side=tk.LEFT, padx=2, pady=5)

        ttk.Separator(self.toolbar, orient='vertical').pack(side=tk.LEFT, fill='y', padx=5)

        # Search
        ttk.Label(self.toolbar, text="🔍", font=('Segoe UI', 12)).pack(side=tk.LEFT, padx=2)
        self.search_var = tk.StringVar()
        self.search_entry = ttk.Entry(self.toolbar, textvariable=self.search_var, width=20)
        self.search_entry.pack(side=tk.LEFT, padx=2, pady=5)
        self.search_entry.bind('<Return>', lambda e: self._search())

        ttk.Button(self.toolbar, text="Search",
                   command=self._search).pack(side=tk.LEFT, padx=2, pady=5)

        # Right side controls
        ttk.Button(self.toolbar, text="⚙ Settings",
                   command=self._show_preferences).pack(side=tk.RIGHT, padx=5, pady=5)
        ttk.Button(self.toolbar, text="📊 Stats",
                   command=self._show_statistics).pack(side=tk.RIGHT, padx=2, pady=5)

    # ============================================================================
    # MAIN LAYOUT CREATION
    # ============================================================================

    def _create_main_layout(self):
        """Create the main application layout"""
        # Main container
        main_frame = ttk.Frame(self)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Horizontal paned window (left panel | center/right)
        self.main_paned = ttk.PanedWindow(main_frame, orient=tk.HORIZONTAL)
        self.main_paned.pack(fill=tk.BOTH, expand=True)

        # LEFT PANEL - Navigation & Stats
        left_panel = ttk.Frame(self.main_paned, width=250)
        self.main_paned.add(left_panel, weight=0)

        # Stats panel at top
        self.stats_panel = self._create_stats_panel(left_panel)
        self.stats_panel.pack(fill=tk.X, padx=5, pady=5)

        ttk.Separator(left_panel, orient='horizontal').pack(fill=tk.X)

        # Module list
        module_frame = ttk.LabelFrame(left_panel, text="📚 Modules", padding=5)
        module_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        self.module_listbox = tk.Listbox(
            module_frame,
            font=('Segoe UI', 9),
            bg='#2D2D2D' if self.config_manager.get_bool('Features', 'dark_mode', True) else 'white',
            fg='white' if self.config_manager.get_bool('Features', 'dark_mode', True) else 'black',
            selectbackground='#0078D4',
            selectforeground='white',
            activestyle='none'
        )
        self.module_listbox.pack(fill=tk.BOTH, expand=True)

        # Module list scrollbar
        module_scroll = ttk.Scrollbar(module_frame, command=self.module_listbox.yview)
        module_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.module_listbox.configure(yscrollcommand=module_scroll.set)

        # Bind module selection
        self.module_listbox.bind('<<ListboxSelect>>', self._on_module_select)
        self.module_listbox.bind('<Double-Button-1>', self._on_module_double_click)

        # CENTER PANEL - Visualizations
        center_panel = ttk.Frame(self.main_paned)
        self.main_paned.add(center_panel, weight=3)

        # Visualization tabs
        self.viz_notebook = ttk.Notebook(center_panel)
        self.viz_notebook.pack(fill=tk.BOTH, expand=True)

        # Create visualization tabs
        self._create_visualization_tabs()

        # Bind tab change event
        self.viz_notebook.bind('<<NotebookTabChanged>>', self._on_tab_changed)

        # RIGHT PANEL - Code Preview (optional)
        if self.config_manager.get_bool('Features', 'code_preview', True):
            right_panel = ttk.Frame(self.main_paned, width=400)
            self.main_paned.add(right_panel, weight=1)

            self.code_preview = OptimizedCodePreview(right_panel)
            self.code_preview.pack(fill=tk.BOTH, expand=True)
            self.code_preview.cache_manager = self.cache_manager
        else:
            self.code_preview = None

    def _create_stats_panel(self, parent):
        """Create statistics panel"""
        frame = ttk.LabelFrame(parent, text="📊 Statistics", padding=5)

        self.stats_labels = {}
        stats_config = [
            ('modules', 'Modules:', '0'),
            ('classes', 'Classes:', '0'),
            ('functions', 'Functions:', '0'),
            ('lines', 'Total Lines:', '0'),
            ('complexity', 'Avg Complexity:', '0.0'),
        ]

        for i, (key, label, default) in enumerate(stats_config):
            stat_frame = ttk.Frame(frame)
            stat_frame.grid(row=i, column=0, sticky='ew', pady=1)

            ttk.Label(stat_frame, text=label, font=('Segoe UI', 9)).pack(side=tk.LEFT)
            value_label = ttk.Label(stat_frame, text=default,
                                    font=('Segoe UI', 9, 'bold'))
            value_label.pack(side=tk.RIGHT)
            self.stats_labels[key] = value_label

        frame.grid_columnconfigure(0, weight=1)
        return frame

    def _create_visualization_tabs(self):
        """Create all visualization tabs"""
        # Tree View
        self.tree_view = OptimizedTreeView(
            self.viz_notebook,
            on_select_callback=self._on_tree_item_select
        )
        self.viz_notebook.add(self.tree_view, text='🌳 Tree View')

        # Mind Map
        self.mind_map = OptimizedMindMap(
            self.viz_notebook,
            on_select_callback=self._on_visualization_item_select
        )
        self.viz_notebook.add(self.mind_map, text='🧠 Mind Map')

        # Network Graph
        self.network_graph = HierarchicalNetworkGraph(
            self.viz_notebook,
            on_select_callback=self._on_visualization_item_select
        )
        self.viz_notebook.add(self.network_graph, text='🔗 Network')

        # Class Diagram
        self.class_diagram = OptimizedClassDiagram(
            self.viz_notebook,
            on_select_callback=self._on_visualization_item_select
        )
        self.viz_notebook.add(self.class_diagram, text='📊 Classes')

        # Cosmos
        self.cosmos_view = CosmosView(
            self.viz_notebook,
            on_select_callback=self._on_visualization_item_select
        )
        self.viz_notebook.add(self.cosmos_view, text='🌌 Cosmos')

    def _create_statusbar(self):
        """Create status bar"""
        self.statusbar = ttk.Frame(self)
        self.statusbar.pack(fill=tk.X, side=tk.BOTTOM)

        # Status message
        self.status_label = ttk.Label(self.statusbar, text="Ready",
                                      font=('Segoe UI', 9))
        self.status_label.pack(side=tk.LEFT, padx=10)

        # Progress bar
        self.progress_bar = ttk.Progressbar(
            self.statusbar,
            length=150,
            mode='indeterminate'
        )
        self.progress_bar.pack(side=tk.RIGHT, padx=10)

        # File info
        self.file_info_label = ttk.Label(self.statusbar, text="",
                                         font=('Segoe UI', 9))
        self.file_info_label.pack(side=tk.RIGHT, padx=20)

        # Memory usage
        self.memory_label = ttk.Label(self.statusbar, text="",
                                      font=('Segoe UI', 9))
        self.memory_label.pack(side=tk.RIGHT, padx=10)

        # Start memory monitor
        self._update_memory_usage()

    # ============================================================================
    # EVENT BINDINGS
    # ============================================================================

    def _bind_events(self):
        """Bind keyboard shortcuts and window events"""
        # File operations
        self.bind('<Control-o>', lambda e: self._open_file())
        self.bind('<Control-d>', lambda e: self._open_directory())
        self.bind('<Control-s>', lambda e: self._save_session())
        self.bind('<Control-e>', lambda e: self._export_diagram())

        # View operations
        self.bind('<F5>', lambda e: self._refresh_views())
        self.bind('<Control-f>', lambda e: self._find_in_tree())
        self.bind('<F3>', lambda e: self._find_next_in_tree())

        # Zoom
        self.bind('<Control-equal>', lambda e: self._zoom_in())
        self.bind('<Control-plus>', lambda e: self._zoom_in())
        self.bind('<Control-minus>', lambda e: self._zoom_out())
        self.bind('<Control-0>', lambda e: self._reset_zoom())

        # Window events
        self.protocol('WM_DELETE_WINDOW', self._quit_app)
        self.bind('<Configure>', self._on_window_configure)

    def _open_recent_by_index(self, index: int):
        """Open recent file by index (0-8)"""
        recent = self.recent_files_manager.get_recent_files()
        if 0 <= index < len(recent):
            self._open_recent_file(recent[index])


    # ============================================================================
    # FILE OPERATIONS
    # ============================================================================

    def _open_file(self):
        """Open a Python file"""
        initial_dir = self.config_manager.get('General', 'last_path', '')

        filepath = filedialog.askopenfilename(
            title="Select Python File",
            initialdir=initial_dir,
            filetypes=[
                ("Python Files", "*.py"),
                ("All Files", "*.*")
            ]
        )

        if filepath:
            # Update last path
            self.config_manager.set('General', 'last_path', os.path.dirname(filepath))

            # Add to recent files
            self.recent_files_manager.add_file(filepath)
            self._update_recent_files_menu()
            # Analyze file
            self._analyze_path(filepath, is_directory=False)

    def _open_directory(self):
        """Open a directory for analysis"""
        initial_dir = self.config_manager.get('General', 'last_path', '')

        dirpath = filedialog.askdirectory(
            title="Select Directory",
            initialdir=initial_dir
        )

        if dirpath:
            # Update last path
            self.config_manager.set('General', 'last_path', dirpath)

            # Add to recent files
            self.recent_files_manager.add_file(dirpath)
            self._update_recent_files_menu()

            # Analyze directory
            self._analyze_path(dirpath, is_directory=True)

    def _open_recent_file(self, filepath: str):
        """Open a file from recent files"""
        if os.path.exists(filepath):
            self._analyze_path(filepath, is_directory=os.path.isdir(filepath))
        else:
            response = messagebox.askyesno(
                "File Not Found",
                f"The file:\n{filepath}\n\nno longer exists.\n\nRemove from recent files?"
            )
            if response:
                # Remove from recent files
                recent = self.recent_files_manager.get_recent_files()
                if filepath in recent:
                    recent.remove(filepath)
                    self.recent_files_manager.recent_files = recent
                    self.recent_files_manager.save_recent_files()
                    self._update_recent_files_menu()

    def _clear_recent_files(self):
        """Clear all recent files"""
        response = messagebox.askyesno(
            "Clear Recent Files",
            "Are you sure you want to clear all recent files?"
        )
        if response:
            self.recent_files_manager.clear_recent_files()
            self._update_recent_files_menu()
            messagebox.showinfo("Success", "Recent files cleared")

    def _analyze_path(self, path: str, is_directory: bool):
        """Analyze file or directory with progress dialog"""
        if is_directory:
            self._analyze_directory_with_progress(path)
        else:
            # Single file - use simple progress
            self.status_label.configure(text=f"Analyzing {os.path.basename(path)}...")
            self.progress_bar.start(10)

            def analyze():
                try:
                    module = self.analyzer.analyze_file(path)
                    modules = [module]
                    self.after(0, self._analysis_complete, modules)
                except Exception as e:
                    self.after(0, self._analysis_error, str(e))

            self.thread_pool.submit(analyze)

    def _analyze_directory_with_progress(self, dirpath: str):
        """Analyze directory with progress dialog"""
        # Create progress dialog
        progress_dialog = AnalysisProgressDialog(self)

        # Collect all Python files
        py_files = []
        for root, dirs, files in os.walk(dirpath):
            dirs[:] = [d for d in dirs if not d.startswith('.') and
                       d not in ('__pycache__', 'venv', 'env', 'node_modules')]

            for file in files:
                if file.endswith('.py') and not file.startswith('.'):
                    py_files.append(os.path.join(root, file))

        if not py_files:
            progress_dialog.destroy()
            messagebox.showinfo("No Files", "No Python files found in directory")
            return

        progress_dialog.set_total(len(py_files))

        def analyze():
            modules = []

            for i, filepath in enumerate(py_files):
                # Check if cancelled
                if progress_dialog.cancelled:
                    break

                filename = os.path.basename(filepath)

                # Update progress in main thread
                self.after(0, progress_dialog.update_progress, i + 1, filename)

                try:
                    module = self.analyzer.analyze_file(filepath)
                    modules.append(module)

                    # Record success
                    self.after(0, progress_dialog.add_success, filename)

                except SyntaxError as e:
                    error_msg = f"Syntax error at line {getattr(e, 'lineno', '?')}: {e.msg if hasattr(e, 'msg') else str(e)}"
                    self.after(0, progress_dialog.add_error, filename, error_msg)

                except Exception as e:
                    error_msg = str(e)[:100]  # Limit error message length
                    self.after(0, progress_dialog.add_error, filename, error_msg)

            # Finish
            self.after(0, progress_dialog.finish)

            # Update UI with results
            if modules:
                self.after(100, self._analysis_complete, modules)
            else:
                self.after(100, self._analysis_error, "No valid Python files found")

        # Start analysis in background
        self.thread_pool.submit(analyze)


    def _analysis_progress(self, current: int, total: int, filename: str):
        """Update analysis progress"""
        percent = int((current / max(total, 1)) * 100)
        self.after(0, lambda: self.status_label.configure(
            text=f"Analyzing {filename} ({current}/{total} - {percent}%)"
        ))

    def _analysis_complete(self, modules: List[ModuleInfo]):
        self.progress_bar.stop()
        self.modules = modules

        # Reset all viz tabs so they reload fresh
        self.mind_map.is_loaded = False
        self.network_graph.is_loaded = False
        self.class_diagram.is_loaded = False

        self._update_module_list()
        self._update_statistics()
        self._update_visualizations()

        total_lines = sum(m.line_count for m in modules)
        self.status_label.configure(
            text=f"Analysis complete: {len(modules)} modules, {total_lines:,} lines"
        )

    def _analysis_error(self, error_msg: str):
        """Handle analysis error"""
        self.progress_bar.stop()
        self.status_label.configure(text="Analysis failed")
        messagebox.showerror("Analysis Error", f"Failed to analyze:\n{error_msg}")

    # ============================================================================
    # UI UPDATE METHODS
    # ============================================================================

    def _update_module_list(self):
        """Update module listbox"""
        self.module_listbox.delete(0, tk.END)

        for module in sorted(self.modules, key=lambda m: m.name.lower()):
            icon = "📝" if module.has_main else "📄"
            self.module_listbox.insert(tk.END, f"{icon} {module.name}")

    def _update_statistics(self):
        """Update statistics panel"""
        if not self.modules:
            return

        total_classes = sum(len(m.classes) for m in self.modules)
        total_functions = sum(
            len(m.functions) + sum(len(c.methods) for c in m.classes)
            for m in self.modules
        )
        total_lines = sum(m.line_count for m in self.modules)

        # Calculate average complexity - handle None values
        all_complexities = []
        for module in self.modules:
            for func in module.functions:
                if func.complexity is not None and isinstance(func.complexity, (int, float)):
                    all_complexities.append(func.complexity)
            for cls in module.classes:
                for method in cls.methods:
                    if method.complexity is not None and isinstance(method.complexity, (int, float)):
                        all_complexities.append(method.complexity)

        avg_complexity = sum(all_complexities) / max(len(all_complexities), 1) if all_complexities else 0

        # Update labels
        self.stats_labels['modules'].configure(text=str(len(self.modules)))
        self.stats_labels['classes'].configure(text=str(total_classes))
        self.stats_labels['functions'].configure(text=str(total_functions))
        self.stats_labels['lines'].configure(text=f"{total_lines:,}")
        self.stats_labels['complexity'].configure(text=f"{avg_complexity:.1f}")

    def _update_visualizations(self):
        """Update all visualization tabs"""
        if not self.modules:
            return

        # Get current tab
        current_tab = self.viz_notebook.index(self.viz_notebook.select())

        # Update tree view (always update as it's the primary view)
        self.tree_view.load_modules(self.modules, lazy=True)

        # Only update current visualization to save resources
        if current_tab == 1:  # Mind Map
            self.mind_map.load_modules(self.modules)
        elif current_tab == 2:  # Network
            self.network_graph.load_modules(self.modules)
        elif current_tab == 3:  # Classes
            self.class_diagram.load_modules(self.modules)
        elif current_tab == 4:
            self.cosmos_view.load_modules(self.modules)

    def _update_memory_usage(self):
        """Update memory usage display"""
        try:
            import psutil
            process = psutil.Process()
            memory_mb = process.memory_info().rss / 1024 / 1024
            self.memory_label.configure(text=f"Memory: {memory_mb:.1f} MB")
        except ImportError:
            # psutil not installed - just skip memory display
            self.memory_label.configure(text="")
        except Exception:
            # Any other error - ignore
            pass

        # Schedule next update
        self.after(5000, self._update_memory_usage)

    # ============================================================================
    # EVENT HANDLERS
    # ============================================================================

    def _on_module_select(self, event):
        """Handle module selection"""
        selection = self.module_listbox.curselection()
        if selection and self.code_preview:
            index = selection[0]
            if index < len(self.modules):
                module = self.modules[index]
                self.code_preview.load_file(module.path)
                self.file_info_label.configure(text=os.path.basename(module.path))

    def _on_module_double_click(self, event):
        """Handle module double-click"""
        selection = self.module_listbox.curselection()
        if selection:
            index = selection[0]
            if index < len(self.modules):
                module = self.modules[index]
                # Switch to tree view and expand module
                self.viz_notebook.select(0)
                # Find and expand module in tree
                for item in self.tree_view.tree.get_children():
                    item_text = self.tree_view.tree.item(item, 'text')
                    if module.name in item_text:
                        self.tree_view.tree.see(item)
                        self.tree_view.tree.selection_set(item)
                        self.tree_view.tree.item(item, open=True)
                        break

    def _on_tree_item_select(self, item_data):
        """Handle tree item selection"""
        item_type, data = item_data

        if self.code_preview and hasattr(data, 'parent_module'):
            # Load file and highlight lines
            module = data.parent_module
            self.code_preview.load_file(
                module.path,
                getattr(data, 'lineno', None),
                getattr(data, 'end_lineno', None)
            )

    def _on_visualization_item_select(self, item_data):
        """Handle visualization item selection"""
        item_type, data = item_data

        if self.code_preview:
            # Try to find the source file
            if hasattr(data, 'parent_module'):
                module = data.parent_module
            elif hasattr(data, 'path'):
                module = data
            else:
                # Search for module containing this item
                module = self._find_module_for_item(data)

            if module:
                self.code_preview.load_file(
                    module.path,
                    getattr(data, 'lineno', None),
                    getattr(data, 'end_lineno', None)
                )

    def _find_module_for_item(self, item):
        """Find module containing an item"""
        for module in self.modules:
            # Check classes
            for cls in module.classes:
                if cls == item:
                    return module
                # Check methods
                for method in cls.methods:
                    if method == item:
                        return module
            # Check functions
            for func in module.functions:
                if func == item:
                    return module
        return None

    def _on_tab_changed(self, event):
        """Handle tab change - lazy load visualizations"""
        current_tab = self.viz_notebook.index(self.viz_notebook.select())

        # Load visualization if not already loaded
        if self.modules:
            if current_tab == 1 and not self.mind_map.is_loaded:
                self.mind_map.load_modules(self.modules)
            elif current_tab == 2 and not self.network_graph.is_loaded:
                self.network_graph.load_modules(self.modules)
            elif current_tab == 3 and not self.class_diagram.is_loaded:
                self.class_diagram.load_modules(self.modules)
            elif current_tab == 4:
                if not self.cosmos_view.is_loaded:
                    self.cosmos_view.load_modules(self.modules)
                else:
                    self.cosmos_view.resume()
                # pause all others
                self.cosmos_view._active = True
            else:
                if hasattr(self, 'cosmos_view'):
                    self.cosmos_view.pause()

    def _on_window_configure(self, event):
        """Handle window resize/move"""
        if event.widget == self:
            # Save geometry periodically
            geometry = self.geometry()
            self.config_manager.set('General', 'window_geometry', geometry)

    # ============================================================================
    # ACTION METHODS
    # ============================================================================

    def _search(self):
        """Search in current view"""
        query = self.search_var.get()
        if not query:
            return

        # Search in current tab
        current_tab = self.viz_notebook.index(self.viz_notebook.select())

        if current_tab == 0:  # Tree view
            self.tree_view.search(query)
        else:
            self.status_label.configure(text="Search is only available in Tree View")

    def _refresh_views(self):
        """Refresh all views"""
        if self.modules:
            self._update_visualizations()
            self.status_label.configure(text="Views refreshed")

    def _clear_cache(self):
        """Clear all caches"""
        self.cache_manager.clear()
        self.status_label.configure(text="Cache cleared")

    def _save_session(self):
        """Save current session"""
        if not self.modules:
            return

        # Save module paths
        module_paths = [m.path for m in self.modules]
        self.config_manager.set('Session', 'modules', json.dumps(module_paths))
        self.config_manager.save_config()

        self.status_label.configure(text="Session saved")

    def _restore_session(self):
        """Restore last session"""
        try:
            modules_json = self.config_manager.get('Session', 'modules', '[]')
            module_paths = json.loads(modules_json)

            if module_paths:
                # Load modules in background
                self.after(100, lambda: self._load_module_paths(module_paths))
        except:
            pass

    def _load_module_paths(self, paths):
        """Load specific module paths"""
        valid_paths = [p for p in paths if os.path.exists(p)]
        if valid_paths:
            # Analyze all paths
            self.status_label.configure(text="Restoring session...")
            self.progress_bar.start(10)

            def analyze():
                modules = []
                for path in valid_paths:
                    try:
                        module = self.analyzer.analyze_file(path)
                        modules.append(module)
                    except:
                        pass

                self.after(0, self._analysis_complete, modules)

            self.thread_pool.submit(analyze)

    # ============================================================================
    # MENU CALLBACKS
    # ============================================================================

  def _export_diagram(self):
        """Export current diagram"""
        current_tab = self.viz_notebook.index(self.viz_notebook.select())

        if current_tab == 0:
            messagebox.showinfo("Export", "Tree view export not supported")
            return

        filepath = filedialog.asksaveasfilename(
            defaultextension='.ps',
            filetypes=[
                ('PostScript', '*.ps'),
                ('Encapsulated PostScript', '*.eps')
            ]
        )

        if filepath:
            canvas = None
            if current_tab == 1:
                canvas = self.mind_map.canvas
            elif current_tab == 2:
                canvas = self.network_graph.canvas
            elif current_tab == 3:
                canvas = self.class_diagram.canvas

            if canvas:
                canvas.postscript(file=filepath)
                self.status_label.configure(text=f"Exported to {filepath}")

    def _find_in_tree(self):
        """Show find in tree"""
        self.viz_notebook.select(0)  # Switch to tree view
        self.tree_view.search_entry.focus()

    def _find_next_in_tree(self):
        """Find next in tree"""
        if self.viz_notebook.index(self.viz_notebook.select()) == 0:
            self.tree_view.search()

    def _copy_selection(self):
        """Copy current selection"""
        # Delegate to current view
        pass

    def _show_preferences(self):
        """Show preferences dialog"""
        PreferencesDialog(self, self.config_manager)

    def _zoom_in(self):
        """Zoom in current view"""
        current_tab = self.viz_notebook.index(self.viz_notebook.select())

        if current_tab == 1:
            self.mind_map.canvas.zoom_in()
        elif current_tab == 2:
            self.network_graph.canvas.zoom_in()
        elif current_tab == 3:
            self.class_diagram.canvas.zoom_in()

    def _zoom_out(self):
        """Zoom out current view"""
        current_tab = self.viz_notebook.index(self.viz_notebook.select())

        if current_tab == 1:
            self.mind_map.canvas.zoom_out()
        elif current_tab == 2:
            self.network_graph.canvas.zoom_out()
        elif current_tab == 3:
            self.class_diagram.canvas.zoom_out()

    def _reset_zoom(self):
        """Reset zoom in current view"""
        current_tab = self.viz_notebook.index(self.viz_notebook.select())

        if current_tab == 1:
            self.mind_map.canvas.reset_zoom()
        elif current_tab == 2:
            self.network_graph.canvas.reset_zoom()
        elif current_tab == 3:
            self.class_diagram.canvas.reset_zoom()

    def _fit_to_window(self):
        """Fit current view to window"""
        current_tab = self.viz_notebook.index(self.viz_notebook.select())

        if current_tab == 1:
            self.mind_map._fit_to_view()
        elif current_tab == 2:
            self.network_graph._fit_view()
        elif current_tab == 3:
            self.class_diagram._fit_view()

    def _expand_all(self):
        """Expand all tree nodes"""
        if self.viz_notebook.index(self.viz_notebook.select()) == 0:
            for item in self.tree_view.tree.get_children():
                self.tree_view._expand_recursive(item)

    def _collapse_all(self):
        """Collapse all tree nodes"""
        if self.viz_notebook.index(self.viz_notebook.select()) == 0:
            for item in self.tree_view.tree.get_children():
                self.tree_view._collapse_recursive(item)

    def _show_statistics(self):
        """Show detailed statistics"""
        if not self.modules:
            messagebox.showinfo("Statistics", "No modules loaded")
            return

        StatisticsDialog(self, self.modules)

    def _show_complexity_report(self):
        """Show complexity report"""
        if not self.modules:
            messagebox.showinfo("Complexity Report", "No modules loaded")
            return

        ComplexityReportDialog(self, self.modules)

    def _find_duplicates(self):
        """Find duplicate code"""
        if not self.modules:
            messagebox.showinfo("Find Duplicates", "No modules loaded. Please open a file or directory first.")
            return

        try:
            DuplicateDetectionDialog(self, self.modules)
        except Exception as e:
            messagebox.showerror("Error", f"Duplicate detection failed: {e}")

    def _find_unused(self):
        if not self.modules:
            messagebox.showinfo("Find Unused", "No modules loaded. Please open a file or directory first.")
            return

        UnusedCodeDialog(self, self.modules)

    def _show_documentation(self):
        """Show documentation"""
        import webbrowser
        webbrowser.open("https://github.com/yourusername/python-code-visualizer")

    def _show_shortcuts(self):
        """Show keyboard shortcuts"""
        shortcuts = """
        File Operations:
        Ctrl+O     Open File
        Ctrl+D     Open Directory
        Ctrl+S     Save Session
        Ctrl+E     Export Diagram

        View Operations:
        F5         Refresh
        Ctrl+F     Find
        F3         Find Next

        Zoom:
        Ctrl++     Zoom In
        Ctrl+-     Zoom Out
        Ctrl+0     Reset Zoom

        Navigation:
        Space      Expand/Collapse Node
        Enter      Go to Definition
        """

        messagebox.showinfo("Keyboard Shortcuts", shortcuts)

    def _show_about(self):
        """Show about dialog"""
        about_text = """
        Python Code Visualizer Pro
        Version 2.0.0

        A professional tool for visualizing and analyzing
        Python codebases with multiple visualization modes.

        Features:
        • Tree View with lazy loading
        • Mind Map visualization
        • Hierarchical Network Graph
        • UML Class Diagrams
        • Syntax-highlighted code preview
        • Performance optimized for large codebases

        © 2024 Code Visualizer Pro
        """

        messagebox.showinfo("About", about_text)

    def _quit_app(self):
        """Quit application"""
        # Save configuration
        self.config_manager.save_config()

        # Shutdown thread pool
        self.thread_pool.shutdown()
        self.cosmos_view.stop()

        # Destroy window
        self.destroy()


# ============================================================================
# COSMOS VIEW
# ============================================================================

class CosmosView(ttk.Frame):
    """Pygame-based constellation/solar system code visualization embedded in tk via PIL."""

    # ── cosmos constants ──────────────────────────────────────────────────────
    _STAR_COUNT       = 320
    _MOON_ORBIT_BASE  = 18
    _FPS              = 30
    _C_BG             = (4,   6,  14)
    _C_TEXT           = (200, 220, 255)
    _C_DIM            = (80,  100, 140)
    _C_HI             = (255, 215,  50)
    _C_RING           = (200, 220, 255)
    _C_DEAD           = (110, 110, 120)
    _C_DEAD_DK        = (60,  60,  70)

    _COMPLEXITY_COLORS = [
        (60,  120, 220),
        (60,  160, 210),
        (50,  190, 160),
        (60,  200, 100),
        (180, 200,  50),
        (220, 160,  30),
        (230, 100,  20),
        (220,  40,  30),
        (200,  20,  80),
    ]
    _NEBULA_COLORS = [
        (30,  100, 200),
        (140,  40, 180),
        (20,  160, 100),
        (180,  80,  20),
    ]
    _DEC_COLORS = {
        'property':       (255, 210,  40),
        'staticmethod':   (40,  210, 255),
        'classmethod':    (255, 130,  50),
        'abstractmethod': (200,  80, 200),
    }
    _ARC_COLORS = {
        'inherit': (255, 220,   0),
        'call':    (50,  255, 180),
    }

    def __init__(self, parent, on_select_callback=None):
        super().__init__(parent)
        self.on_select_callback = on_select_callback
        self.is_loaded          = False
        self._running           = False
        self._tick              = 0
        self._layout            = []
        self._arcs              = []
        self._name_to_planet    = {}
        self._stars             = []
        self._selected          = None
        self._dragging          = False
        self._drag_prev         = (0, 0)
        self._cam_ox            = 0.0
        self._cam_oy            = 0.0
        self._cam_zoom          = 1.0
        self._surf              = None
        self._fonts             = {}
        self._photo             = None
        self._after_id          = None
        self._W                 = 100
        self._H                 = 100

        self._canvas = tk.Canvas(self, bg='#04060e', highlightthickness=0)
        self._canvas.pack(fill=tk.BOTH, expand=True)
        self._active = False

        self._canvas.bind('<Configure>',       self._on_resize)
        self._canvas.bind('<ButtonPress-3>',   self._on_rb_press)
        self._canvas.bind('<ButtonRelease-3>', self._on_rb_release)
        self._canvas.bind('<B3-Motion>',       self._on_rb_drag)
        self._canvas.bind('<ButtonPress-1>',   self._on_lb_click)
        self._canvas.bind('<MouseWheel>',      self._on_scroll)
        self._canvas.bind('<Button-4>',        self._on_scroll)
        self._canvas.bind('<Button-5>',        self._on_scroll)
        self._canvas.bind('<Motion>',          self._on_motion)

    # ── public ────────────────────────────────────────────────────────────────

    def load_modules(self, modules):
        self.is_loaded = True
        cosmos_mods    = self._convert_modules(modules)
        self._stars    = self._gen_stars(self._STAR_COUNT)
        self._layout, self._name_to_planet = self._build_layout(cosmos_mods)
        self._arcs     = self._build_arcs(self._name_to_planet)
        self._cam_ox   = self._W / 2
        self._cam_oy   = self._H / 2
        self._cam_zoom = 1.0
        self._start_loop()

    def stop(self):
        self._running = False
        if self._after_id:
            try:
                self.after_cancel(self._after_id)
            except Exception:
                pass

    # ── module conversion ─────────────────────────────────────────────────────

    def _convert_modules(self, modules):
        result = []
        for mod in modules:
            classes = []
            for cls in mod.classes:
                loc        = max(1, (cls.end_lineno or cls.lineno) - cls.lineno)
                n_methods  = len(cls.methods)
                complexity = max(1, min(n_methods // 2 + 1, 9))
                calls      = []
                for m in cls.methods:
                    for c in (m.calls or []):
                        base = c.split('.')[0]
                        if base and base not in calls:
                            calls.append(base)
                inherits = cls.bases[0] if cls.bases else None
                dead     = getattr(cls, 'is_abstract', False)
                classes.append({
                    'name':       cls.name,
                    'loc':        loc,
                    'complexity': complexity,
                    'methods':    [m.name for m in cls.methods],
                    'attributes': list(cls.attributes or []),
                    'decorators': list(cls.decorators or []),
                    'inherits':   inherits,
                    'dead':       dead,
                    'calls':      calls,
                })
            functions = [f.name for f in (mod.functions or [])]
            result.append({
                'name':      mod.name,
                'classes':   classes,
                'functions': functions,
            })
        return result

    # ── layout ────────────────────────────────────────────────────────────────

    def _build_layout(self, modules):
        name_to_planet = {}
        layout         = []
        occupied       = []

        for mi, mod in enumerate(modules):
            for _ in range(200):
                rx = random.randint(-500, 500)
                ry = random.randint(-380, 380)
                if all(math.hypot(rx - ox, ry - oy) > 280 for ox, oy in occupied):
                    break
            occupied.append((rx, ry))
            mod_cx = rx
            mod_cy = ry
            planets  = []
            n_cls    = len(mod['classes'])

            for ci, cls in enumerate(mod['classes']):
                pr     = max(18, min(int(max(1, cls['loc']) ** 0.52), 48))
                spread = max(80, n_cls * 55)
                if n_cls == 1:
                    px, py = mod_cx, mod_cy
                else:
                    pa = 2 * math.pi * ci / n_cls + random.uniform(-0.4, 0.4)
                    radius = spread * random.uniform(0.2, 0.7)
                    px = mod_cx + radius * math.cos(pa)
                    py = mod_cy + radius * 0.65 * math.sin(pa)

                moons   = []
                methods = cls.get('methods', [])
                for moi, method in enumerate(methods):
                    orbit_r = pr + self._MOON_ORBIT_BASE + moi * 4
                    orbit_r = min(orbit_r, pr + 55)
                    moons.append({
                        'name':      method,
                        'orbit_r':   orbit_r,
                        'angle':     2 * math.pi * moi / max(len(methods), 1),
                        'speed':     0.04 + moi * 0.008,
                        'r':         max(3, 5 - moi // 3),
                        'cur_angle': 2 * math.pi * moi / max(len(methods), 1),
                    })

                planet = {
                    'name':  cls['name'],
                    'wx':    px,
                    'wy':    py,
                    'r':     pr,
                    'data':  cls,
                    'moons': moons,
                }
                planets.append(planet)
                name_to_planet[cls['name']] = planet

            asteroids = []
            for fi, fn in enumerate(mod.get('functions', [])):
                fa  = 2 * math.pi * fi / max(len(mod['functions']), 1)
                far = 30 + fi * 8
                asteroids.append({
                    'name':    fn,
                    'wx':      mod_cx + far * math.cos(fa),
                    'wy':      mod_cy + far * math.sin(fa) * 0.5,
                    'angle':   fa,
                    'speed':   0.003 + fi * 0.001,
                    'orbit_r': far,
                    'cx':      mod_cx,
                    'cy':      mod_cy,
                })

            max_dist = 0
            for p in planets:
                d        = math.hypot(p['wx'] - mod_cx, p['wy'] - mod_cy) + p['r'] + 60
                max_dist = max(max_dist, d)
            neb_r = max(90, max_dist)

            layout.append({
                'mod':       mod,
                'wx':        mod_cx,
                'wy':        mod_cy,
                'neb_r':     neb_r,
                'color_i':   mi % len(self._NEBULA_COLORS),
                'planets':   planets,
                'asteroids': asteroids,
            })

        return layout, name_to_planet

    def _build_arcs(self, name_to_planet):
        arcs = []
        seen = set()
        for name, planet in name_to_planet.items():
            d      = planet['data']
            parent = d.get('inherits')
            if parent and parent in name_to_planet:
                k = (min(name, parent), max(name, parent), 'inherit')
                if k not in seen:
                    seen.add(k)
                    arcs.append((planet, name_to_planet[parent], 'inherit'))
            for c in d.get('calls', []):
                if c in name_to_planet and c != name:
                    k = (min(name, c), max(name, c), 'call')
                    if k not in seen:
                        seen.add(k)
                        arcs.append((planet, name_to_planet[c], 'call'))
        return arcs

    # ── camera helpers ────────────────────────────────────────────────────────

    def _w2s(self, wx, wy):
        return (int(wx * self._cam_zoom + self._cam_ox),
                int(wy * self._cam_zoom + self._cam_oy))

    def _s2w(self, sx, sy):
        return ((sx - self._cam_ox) / self._cam_zoom,
                (sy - self._cam_oy) / self._cam_zoom)

    def _zoom_at(self, sx, sy, f):
        wx, wy         = self._s2w(sx, sy)
        self._cam_zoom = max(0.15, min(5.0, self._cam_zoom * f))
        self._cam_ox   = sx - wx * self._cam_zoom
        self._cam_oy   = sy - wy * self._cam_zoom

    def _sr(self, r):
        return max(1, int(r * self._cam_zoom))

    # ── stars ─────────────────────────────────────────────────────────────────

    def _gen_stars(self, n):
        w = max(self._W, 800)
        h = max(self._H, 600)
        return [
            (random.randint(0, w), random.randint(0, h),
             random.uniform(0.5, 2.5), random.uniform(0.3, 1.0))
            for _ in range(n)
        ]


    def _draw_stars(self, surf):
        t = self._tick
        for x, y, size, phase in self._stars:
            b   = int(120 + 80 * math.sin(t * 0.015 + phase * 6))
            col = (b, b, int(b * 0.9))
            r   = max(1, int(size))
            if size > 1.8:
                pygame.draw.circle(surf, col, (x, y), r)
            else:
                surf.set_at((x, y), col)

    # ── nebula ────────────────────────────────────────────────────────────────

    @staticmethod
    def _dim(col, f):
        return tuple(max(0, int(c * f)) for c in col)

    def _draw_nebula(self, surf, neb):
        cx, cy = self._w2s(neb['wx'], neb['wy'])
        sr     = self._sr(neb['neb_r'])
        col    = self._NEBULA_COLORS[neb['color_i']]
        for i in range(5, 0, -1):
            gr = int(sr * (0.4 + 0.12 * i))
            c  = self._dim(col, 0.04 + 0.03 * i)
            pygame.draw.circle(surf, c, (cx, cy), gr)
        if self._cam_zoom > 0.25:
            bright = tuple(min(c + 120, 255) for c in col)
            lbl    = self._fonts['md'].render(neb['mod']['name'], True, bright)
            surf.blit(lbl, (cx - lbl.get_width() // 2,
                            cy - self._sr(neb['neb_r']) - lbl.get_height() - 4))

    # ── planet ────────────────────────────────────────────────────────────────

    def _cc(self, c):
        idx = max(0, min(c - 1, len(self._COMPLEXITY_COLORS) - 1))
        return self._COMPLEXITY_COLORS[idx]

    def _glow_circle(self, surf, color, pos, r, layers=4):
        for i in range(layers, 0, -1):
            alpha = int(50 * i / layers)
            gr    = r + (layers - i + 1) * 3
            tmp   = pygame.Surface((gr * 2 + 2, gr * 2 + 2), pygame.SRCALPHA)
            pygame.draw.circle(tmp, color + (alpha,), (gr + 1, gr + 1), gr)
            surf.blit(tmp, (pos[0] - gr - 1, pos[1] - gr - 1))
        pygame.draw.circle(surf, color, pos, r)

    def _draw_planet(self, surf, planet, selected, frozen):
        data     = planet['data']
        dead     = data.get('dead', False)
        attrs    = data.get('attributes', [])
        decs     = data.get('decorators', [])
        cx, cy   = self._w2s(planet['wx'], planet['wy'])
        pr       = self._sr(planet['r'])
        base_col = self._C_DEAD if dead else self._cc(data.get('complexity', 1))
        t        = self._tick

        # for ri in range(len(attrs)):
        for ri in range(min(len(attrs), 3)):
            rr  = pr + 6 + ri * 5
            a   = max(30, 100 - ri * 20)
            rc  = self._C_DEAD_DK if dead else self._C_RING
            tmp = pygame.Surface((rr * 2 + 4, rr * 2 + 4), pygame.SRCALPHA)
            pygame.draw.ellipse(tmp, rc + (a,), (2, rr // 2, rr * 2, rr), max(1, self._sr(1)))
            surf.blit(tmp, (cx - rr - 2, cy - rr // 2 - 2))

        if not dead:
            self._glow_circle(surf, base_col, (cx, cy), pr)
        else:
            pygame.draw.circle(surf, self._C_DEAD, (cx, cy), pr)
            pygame.draw.circle(surf, self._C_DEAD_DK, (cx, cy), pr, max(1, self._sr(1)))

        if pr > 10:
            for li in range(1, 3):
                ly = cy - pr + int(pr * li * 0.6)
                lw = int(math.sqrt(max(0, pr * pr - (ly - cy) ** 2)))
                if lw > 2:
                    lc = tuple(max(c - 40, 0) for c in base_col) if not dead else (50, 50, 60)
                    pygame.draw.line(surf, lc, (cx - lw, ly), (cx + lw, ly), max(1, self._sr(1)))

        if not dead and pr > 8:
            hx  = cx - pr // 3
            hy  = cy - pr // 3
            hr  = max(2, pr // 4)
            tmp2 = pygame.Surface((hr * 2, hr * 2), pygame.SRCALPHA)
            pygame.draw.circle(tmp2, (255, 255, 255, 60), (hr, hr), hr)
            surf.blit(tmp2, (hx - hr, hy - hr))

        if selected:
            pygame.draw.circle(surf, self._C_HI, (cx, cy), pr + self._sr(5), max(2, self._sr(2)))

        if dead and pr > 6:
            o = int(pr * 0.6)
            pygame.draw.line(surf, (150, 40, 40), (cx - o, cy - o), (cx + o, cy + o), max(1, self._sr(2)))
            pygame.draw.line(surf, (150, 40, 40), (cx + o, cy - o), (cx - o, cy + o), max(1, self._sr(2)))

        for di, dec in enumerate(decs[:4]):
            dc      = self._DEC_COLORS.get(dec, (200, 200, 200))
            dangle  = math.pi * 0.25 + di * math.pi * 0.4
            flare_r = pr + self._sr(4)
            fx      = int(cx + flare_r * math.cos(dangle))
            fy      = int(cy + flare_r * math.sin(dangle) * 0.6)
            pulse   = 0.6 + 0.4 * math.sin(t * 0.07 + di * 1.5)
            fr      = max(2, int(self._sr(4) * pulse))
            self._glow_circle(surf, dc, (fx, fy), fr, layers=2)

        moon_base = tuple(min(int(c * 0.6 + 80), 255) for c in base_col) if not dead else (60, 60, 70)
        for mi2, moon in enumerate(planet['moons']):
            ma       = moon['cur_angle'] if frozen else moon['angle'] + t * moon['speed']
            moon['cur_angle'] = ma
            wmx      = planet['wx'] + moon['orbit_r'] * math.cos(ma)
            wmy      = planet['wy'] + moon['orbit_r'] * math.sin(ma)
            mx2, my2 = self._w2s(wmx, wmy)
            mr       = max(2, self._sr(moon['r']))
            shift    = mi2 * 15
            mc       = tuple(min(c + shift, 255) for c in moon_base) if not dead else (60, 60, 70)
            pygame.draw.circle(surf, mc, (mx2, my2), mr)
            dc2      = tuple(max(c - 40, 0) for c in mc)
            pygame.draw.circle(surf, dc2, (mx2, my2), mr, 1)

        if self._cam_zoom > 0.4:
            lc  = (100, 100, 110) if dead else self._C_TEXT
            lbl = self._fonts['sm'].render(data['name'], True, lc)
            surf.blit(lbl, (cx - lbl.get_width() // 2, cy + pr + self._sr(4)))

        if dead and self._cam_zoom > 0.5 and pr > 12:
            dl = self._fonts['sm'].render('UNUSED', True, (140, 40, 40))
            surf.blit(dl, (cx - dl.get_width() // 2, cy - dl.get_height() // 2))

    # ── arcs ──────────────────────────────────────────────────────────────────

    def _draw_arc(self, surf, p1, p2, atype):
        col      = self._ARC_COLORS[atype]
        sx1, sy1 = self._w2s(p1['wx'], p1['wy'])
        sx2, sy2 = self._w2s(p2['wx'], p2['wy'])
        r1       = self._sr(p1['r'])
        r2       = self._sr(p2['r'])
        dx, dy   = sx2 - sx1, sy2 - sy1
        dist     = max(1, math.hypot(dx, dy))
        ux, uy   = dx / dist, dy / dist
        start    = (int(sx1 + ux * r1), int(sy1 + uy * r1))
        end      = (int(sx2 - ux * r2), int(sy2 - uy * r2))
        mx2, my2 = (start[0] + end[0]) // 2, (start[1] + end[1]) // 2
        perp_x, perp_y = -uy, ux
        curve_amt = min(dist * 0.30, 100)
        ctrl      = (mx2 + perp_x * curve_amt, my2 + perp_y * curve_amt)
        steps     = max(16, int(dist // 12))
        pts       = []
        for i in range(steps + 1):
            t2  = i / steps
            bx  = int((1 - t2) ** 2 * start[0] + 2 * (1 - t2) * t2 * ctrl[0] + t2 ** 2 * end[0])
            by  = int((1 - t2) ** 2 * start[1] + 2 * (1 - t2) * t2 * ctrl[1] + t2 ** 2 * end[1])
            pts.append((bx, by))
        lw = max(1, self._sr(1))
        if atype == 'inherit':
            dim = self._dim(col, 0.35)
            if len(pts) >= 2:
                pygame.draw.lines(surf, dim, False, pts, lw + 3)
                pygame.draw.lines(surf, col, False, pts, lw + 1)
        else:
            seg    = 10
            gap    = 6
            total  = seg + gap
            phase  = (self._tick * 2) % total
            for pi in range(len(pts) - 1):
                if phase < seg:
                    bright = 0.5 + 0.5 * math.sin(pi * 0.4 - self._tick * 0.1)
                    bc     = tuple(min(int(c * (0.4 + bright * 0.6)), 255) for c in col)
                    pygame.draw.line(surf, bc, pts[pi], pts[pi + 1], max(1, lw))
                phase = (phase + 1) % total
        if len(pts) >= 4:
            dx2, dy2 = pts[-1][0] - pts[-4][0], pts[-1][1] - pts[-4][1]
            d2       = max(1, math.hypot(dx2, dy2))
            ux2, uy2 = dx2 / d2, dy2 / d2
            px2, py2 = -uy2, ux2
            sz       = max(8, self._sr(7))
            a1       = (int(pts[-1][0] - ux2 * sz + px2 * sz * 0.4),
                        int(pts[-1][1] - uy2 * sz + py2 * sz * 0.4))
            a2       = (int(pts[-1][0] - ux2 * sz - px2 * sz * 0.4),
                        int(pts[-1][1] - uy2 * sz - py2 * sz * 0.4))
            pygame.draw.polygon(surf, col, [pts[-1], a1, a2])

    # ── asteroids ─────────────────────────────────────────────────────────────

    def _draw_asteroids(self, surf, asteroids):
        if self._cam_zoom < 2.0:
            return
        for ast in asteroids:
            ax, ay = self._w2s(ast['wx'], ast['wy'])
            ar     = max(2, self._sr(3))
            pygame.draw.circle(surf, (100, 110, 130), (ax, ay), ar)
    # ── tooltip ───────────────────────────────────────────────────────────────

    def _find_hovered(self, mx, my):
        for neb in self._layout:
            for planet in neb['planets']:
                for moon in planet['moons']:
                    ma       = moon['cur_angle']
                    wmx      = planet['wx'] + moon['orbit_r'] * math.cos(ma)
                    wmy      = planet['wy'] + moon['orbit_r'] * math.sin(ma)
                    moox, mooy = self._w2s(wmx, wmy)
                    if math.hypot(mx - moox, my - mooy) <= max(4, self._sr(moon['r']) + 3):
                        return planet, moon['name']
                cx2, cy2 = self._w2s(planet['wx'], planet['wy'])
                if math.hypot(mx - cx2, my - cy2) <= self._sr(planet['r']) + self._sr(6):
                    return planet, None
        return None, None

    def _draw_tooltip(self, surf, planet, mx, my):
        if not planet:
            return
        d     = planet['data']
        dead  = d.get('dead', False)
        col   = self._C_DEAD if dead else self._cc(d.get('complexity', 1))
        lines = [
            (self._fonts['md'], d['name'],                                                         self._C_HI),
            (self._fonts['sm'], f"LOC: {d.get('loc','?')}  Complexity: {d.get('complexity','?')}", col),
            (self._fonts['sm'], f"Methods ({len(d.get('methods',[]))}): {', '.join(d.get('methods',[])[:4])}{'…' if len(d.get('methods',[]))>4 else ''}", self._C_TEXT),
            (self._fonts['sm'], f"Attrs: {', '.join(d.get('attributes',[])[:4]) or '—'}",          self._C_DIM),
            (self._fonts['sm'], f"Inherits: {d.get('inherits') or '—'}",                           self._C_DIM),
            (self._fonts['sm'], f"Dead: {'⚠ YES' if dead else 'No'}",                              (200, 60, 60) if dead else self._C_DIM),
        ]
        pw  = 280
        ph  = sum(f.get_height() + 3 for f, _, _ in lines) + 14
        tx  = min(mx + 14, self._W - pw - 4)
        ty  = min(my + 14, self._H - ph - 4)
        bg  = pygame.Surface((pw, ph), pygame.SRCALPHA)
        bg.fill((8, 12, 20, 230))
        surf.blit(bg, (tx, ty))
        pygame.draw.rect(surf, col, (tx, ty, pw, ph), 1)
        cy2 = ty + 7
        for fnt, text, tc in lines:
            lbl = fnt.render(text, True, tc)
            surf.blit(lbl, (tx + 8, cy2))
            cy2 += fnt.get_height() + 3

    # ── legend ────────────────────────────────────────────────────────────────

    def _draw_legend(self, surf):
        items = [
            (self._COMPLEXITY_COLORS[0], 'Low complexity'),
            (self._COMPLEXITY_COLORS[4], 'Mid complexity'),
            (self._COMPLEXITY_COLORS[7], 'High complexity'),
            (self._C_DEAD,               'Abstract/dead class'),
            ((100, 110, 130),            'Moon = method'),
            (self._C_RING,               'Ring = attribute'),
            (self._ARC_COLORS['inherit'],'── Inheritance'),
            (self._ARC_COLORS['call'],   '╌╌ Call (pulse)'),
        ]
        x, y = 10, self._H - len(items) * 18 - 14
        bh   = len(items) * 18 + 12
        bg   = pygame.Surface((200, bh), pygame.SRCALPHA)
        bg.fill((4, 6, 14, 210))
        surf.blit(bg, (x - 4, y - 4))
        for i, (col, lbl) in enumerate(items):
            pygame.draw.circle(surf, col, (x + 7, y + i * 18 + 7), 4)
            surf.blit(self._fonts['sm'].render(lbl, True, self._C_DIM), (x + 17, y + i * 18))

    # ── main render loop ──────────────────────────────────────────────────────

    def _ensure_pygame(self):
        if not pygame.get_init():
            pygame.init()
        if not self._fonts:
            self._fonts['sm'] = pygame.font.SysFont('Consolas', 11)
            self._fonts['md'] = pygame.font.SysFont('Consolas', 13, bold=True)
            self._fonts['lg'] = pygame.font.SysFont('Consolas', 16, bold=True)

    def _ensure_surface(self):
        w = self._canvas.winfo_width()
        h = self._canvas.winfo_height()
        if w <= 1 or h <= 1:
            return False
        if self._surf is None or self._W != w or self._H != h:
            self._W    = w
            self._H    = h
            self._surf = pygame.Surface((w, h))
        return True

    def _frame(self):
        if not self._running:
            return
        try:
            self._ensure_pygame()
            if not self._ensure_surface():
                self._after_id = self.after(100, self._frame)
                delay = 1000 // self._FPS if self._active else 500
                self._after_id = self.after(delay, self._frame)
                return
            surf = self._surf
            surf.fill(self._C_BG)
            self._draw_stars(surf)

            for neb in self._layout:
                self._draw_nebula(surf, neb)

            for p1, p2, atype in self._arcs:
                self._draw_arc(surf, p1, p2, atype)

            for neb in self._layout:
                self._draw_asteroids(surf, neb['asteroids'])

            mx = self._last_mx if hasattr(self, '_last_mx') else 0
            my = self._last_my if hasattr(self, '_last_my') else 0
            hov_planet, hov_moon = self._find_hovered(mx, my)

            for neb in self._layout:
                for planet in neb['planets']:
                    is_sel = (self._selected is planet)
                    frozen = (hov_planet is planet)
                    self._draw_planet(surf, planet, is_sel, frozen)

            if hov_moon:
                bg2 = pygame.Surface((180, 22), pygame.SRCALPHA)
                bg2.fill((8, 12, 20, 220))
                surf.blit(bg2, (mx + 10, my + 10))
                pygame.draw.rect(surf, (80, 90, 120), (mx + 10, my + 10, 180, 22), 1)
                surf.blit(self._fonts['sm'].render(f'method: {hov_moon}', True, (160, 170, 200)),
                          (mx + 14, my + 14))
            elif hov_planet:
                self._draw_tooltip(surf, hov_planet, mx, my)

            self._draw_legend(surf)

            surf.blit(self._fonts['lg'].render('✦ Code Cosmos', True, self._C_HI), (10, 10))
            surf.blit(self._fonts['sm'].render(
                'Left-click: select   Right-drag: pan   Scroll: zoom',
                True, self._C_DIM), (10, 30))
            zt = self._fonts['sm'].render(f'zoom {self._cam_zoom:.2f}x', True, self._C_DIM)
            surf.blit(zt, (self._W - zt.get_width() - 10, 10))

            raw        = pygame.image.tostring(surf, 'RGB')
            img        = PIL.Image.frombytes('RGB', (self._W, self._H), raw)
            self._photo = PIL.ImageTk.PhotoImage(image=img)
            self._canvas.delete('all')
            self._canvas.create_image(0, 0, anchor='nw', image=self._photo)

            self._tick += 1
        except Exception as e:
            print(f'CosmosView frame error: {e}')

        self._after_id = self.after(1000 // self._FPS, self._frame)

    def _start_loop(self):
        if self._running:
            return
        self._running = True
        self._ensure_pygame()
        self._active = True
        self._frame()

    def pause(self):
        self._active = False

    def resume(self):
        self._active = True

    # ── events ────────────────────────────────────────────────────────────────

    def _on_resize(self, event):
        self._W = event.width
        self._H = event.height
        self._surf = None

    def _on_rb_press(self, event):
        self._dragging  = True
        self._drag_prev = (event.x, event.y)

    def _on_rb_release(self, event):
        self._dragging = False

    def _on_rb_drag(self, event):
        if self._dragging:
            self._cam_ox += event.x - self._drag_prev[0]
            self._cam_oy += event.y - self._drag_prev[1]
            self._drag_prev = (event.x, event.y)

    def _on_lb_click(self, event):
        planet, _ = self._find_hovered(event.x, event.y)
        self._selected = planet
        if planet and self.on_select_callback:
            self.on_select_callback(('class', planet['data']))

    def _on_scroll(self, event):
        if event.num == 4 or event.delta > 0:
            self._zoom_at(event.x, event.y, 1.1)
        else:
            self._zoom_at(event.x, event.y, 0.9)

    def _on_motion(self, event):
        self._last_mx = event.x
        self._last_my = event.y



# ============================================================================
# DIALOG WINDOWS
# ============================================================================

class PreferencesDialog(tk.Toplevel):
    """Functional preferences dialog with real settings"""

    def __init__(self, parent, config_manager):
        super().__init__(parent)

        self.config_manager = config_manager
        self.parent_app = parent
        self.title("⚙ Preferences")
        self.geometry("600x500")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        # Center window
        self.update_idletasks()
        x = (self.winfo_screenwidth() - 600) // 2
        y = (self.winfo_screenheight() - 500) // 2
        self.geometry(f"+{x}+{y}")

        # Store settings
        self.settings = {}

        # Create UI
        self._create_widgets()
        self._load_current_settings()

    def _create_widgets(self):
        """Create preference widgets"""
        # Create notebook for categories
        notebook = ttk.Notebook(self)
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # GENERAL TAB
        general_frame = ttk.Frame(notebook, padding=10)
        notebook.add(general_frame, text="General")

        # Remember last path
        row = 0
        self.settings['remember_path'] = tk.BooleanVar()
        ttk.Checkbutton(
            general_frame,
            text="Remember last opened directory",
            variable=self.settings['remember_path']
        ).grid(row=row, column=0, sticky='w', pady=5)

        # Auto-restore session
        row += 1
        self.settings['auto_restore'] = tk.BooleanVar()
        ttk.Checkbutton(
            general_frame,
            text="Automatically restore last session on startup",
            variable=self.settings['auto_restore']
        ).grid(row=row, column=0, sticky='w', pady=5)

        # Save window size
        row += 1
        self.settings['save_geometry'] = tk.BooleanVar()
        ttk.Checkbutton(
            general_frame,
            text="Remember window size and position",
            variable=self.settings['save_geometry']
        ).grid(row=row, column=0, sticky='w', pady=5)

        # Theme
        row += 1
        self.settings['theme'] = tk.StringVar()
        themes = [('Dark Mode', 'dark'), ('Yellow (Dark)', 'yellow'), ('Red (Dark)', 'red'),
                  ('Green (Light)', 'green'), ('Blue (Light)', 'blue')]
        for label, value in themes:
            tk.Radiobutton(
                general_frame, text=label,
                variable=self.settings['theme'], value=value,
                bg='#2B2B2B', fg='#FFD700',
                selectcolor='#404040', activebackground='#2B2B2B',
                activeforeground='#FFD700',
                command=lambda v=value: self._live_apply_theme(v)
            ).grid(row=row, column=0, sticky='w', padx=20)
            row += 1

        # PERFORMANCE TAB
        perf_frame = ttk.Frame(notebook, padding=10)
        notebook.add(perf_frame, text="Performance")

        row = 0
        ttk.Label(perf_frame, text="Analysis Settings:", font=('Segoe UI', 10, 'bold')).grid(
            row=row, column=0, sticky='w', pady=(0, 10), columnspan=2
        )

        # Use threading
        row += 1
        self.settings['use_threading'] = tk.BooleanVar()
        ttk.Checkbutton(
            perf_frame,
            text="Use background threads (prevents UI freezing)",
            variable=self.settings['use_threading']
        ).grid(row=row, column=0, sticky='w', pady=5, columnspan=2)

        # Lazy loading
        row += 1
        self.settings['lazy_loading'] = tk.BooleanVar()
        ttk.Checkbutton(
            perf_frame,
            text="Enable lazy loading (faster for large projects)",
            variable=self.settings['lazy_loading']
        ).grid(row=row, column=0, sticky='w', pady=5, columnspan=2)

        # Cache files
        row += 1
        self.settings['cache_files'] = tk.BooleanVar()
        ttk.Checkbutton(
            perf_frame,
            text="Cache analyzed files (uses more memory)",
            variable=self.settings['cache_files']
        ).grid(row=row, column=0, sticky='w', pady=5, columnspan=2)

        # Cache size
        row += 1
        ttk.Label(perf_frame, text="Cache Size (MB):").grid(
            row=row, column=0, sticky='w', pady=(15, 5)
        )

        self.settings['cache_size'] = tk.IntVar()
        cache_spin = ttk.Spinbox(
            perf_frame,
            from_=10, to=500,
            textvariable=self.settings['cache_size'],
            width=10
        )
        cache_spin.grid(row=row, column=1, sticky='w', pady=(15, 5))

        # Max initial nodes
        row += 1
        ttk.Label(perf_frame, text="Max Nodes to Load Initially:").grid(
            row=row, column=0, sticky='w', pady=5
        )

        self.settings['max_nodes'] = tk.IntVar()
        nodes_spin = ttk.Spinbox(
            perf_frame,
            from_=50, to=1000,
            textvariable=self.settings['max_nodes'],
            width=10,
            increment=50
        )
        nodes_spin.grid(row=row, column=1, sticky='w', pady=5)

        # Analysis timeout
        row += 1
        ttk.Label(perf_frame, text="Analysis Timeout (seconds):").grid(
            row=row, column=0, sticky='w', pady=5
        )

        self.settings['timeout'] = tk.IntVar()
        timeout_spin = ttk.Spinbox(
            perf_frame,
            from_=10, to=300,
            textvariable=self.settings['timeout'],
            width=10,
            increment=10
        )
        timeout_spin.grid(row=row, column=1, sticky='w', pady=5)

        # DISPLAY TAB
        display_frame = ttk.Frame(notebook, padding=10)
        notebook.add(display_frame, text="Display")

        row = 0
        ttk.Label(display_frame, text="Font Sizes:", font=('Segoe UI', 10, 'bold')).grid(
            row=row, column=0, sticky='w', pady=(0, 10), columnspan=2
        )

        # Tree font size
        row += 1
        ttk.Label(display_frame, text="Tree View Font Size:").grid(
            row=row, column=0, sticky='w', pady=5
        )

        self.settings['tree_font_size'] = tk.IntVar()
        ttk.Spinbox(
            display_frame,
            from_=8, to=16,
            textvariable=self.settings['tree_font_size'],
            width=10
        ).grid(row=row, column=1, sticky='w', pady=5)

        # Code preview font size
        row += 1
        ttk.Label(display_frame, text="Code Preview Font Size:").grid(
            row=row, column=0, sticky='w', pady=5
        )

        self.settings['code_font_size'] = tk.IntVar()
        ttk.Spinbox(
            display_frame,
            from_=8, to=16,
            textvariable=self.settings['code_font_size'],
            width=10
        ).grid(row=row, column=1, sticky='w', pady=5)

        # Diagram font size
        row += 1
        ttk.Label(display_frame, text="Diagram Font Size:").grid(
            row=row, column=0, sticky='w', pady=5
        )

        self.settings['diagram_font_size'] = tk.IntVar()
        ttk.Spinbox(
            display_frame,
            from_=6, to=14,
            textvariable=self.settings['diagram_font_size'],
            width=10
        ).grid(row=row, column=1, sticky='w', pady=5)

        # Zoom settings
        row += 1
        ttk.Label(display_frame, text="Zoom Settings:", font=('Segoe UI', 10, 'bold')).grid(
            row=row, column=0, sticky='w', pady=(15, 10), columnspan=2
        )

        row += 1
        ttk.Label(display_frame, text="Minimum Zoom (%):").grid(
            row=row, column=0, sticky='w', pady=5
        )

        self.settings['min_zoom'] = tk.IntVar()
        ttk.Spinbox(
            display_frame,
            from_=5, to=50,
            textvariable=self.settings['min_zoom'],
            width=10,
            increment=5
        ).grid(row=row, column=1, sticky='w', pady=5)

        row += 1
        ttk.Label(display_frame, text="Maximum Zoom (%):").grid(
            row=row, column=0, sticky='w', pady=5
        )

        self.settings['max_zoom'] = tk.IntVar()
        ttk.Spinbox(
            display_frame,
            from_=200, to=5000,
            textvariable=self.settings['max_zoom'],
            width=10,
            increment=100
        ).grid(row=row, column=1, sticky='w', pady=5)

        # BUTTON PANEL
        button_frame = ttk.Frame(self)
        button_frame.pack(fill=tk.X, padx=10, pady=10)

        ttk.Button(
            button_frame,
            text="Restore Defaults",
            command=self._restore_defaults
        ).pack(side=tk.LEFT, padx=5)

        ttk.Button(
            button_frame,
            text="Cancel",
            command=self.destroy
        ).pack(side=tk.RIGHT, padx=5)

        ttk.Button(
            button_frame,
            text="Apply",
            command=self._apply_settings
        ).pack(side=tk.RIGHT, padx=5)

        ttk.Button(
            button_frame,
            text="OK",
            command=self._save_and_close
        ).pack(side=tk.RIGHT, padx=5)

    def _load_current_settings(self):
        """Load current settings from config"""
        # General
        self.settings['remember_path'].set(True)
        self.settings['auto_restore'].set(True)
        self.settings['save_geometry'].set(True)
        self.settings['theme'].set(
            self.config_manager.get('General', 'theme', 'yellow')
        )

        # Performance
        self.settings['use_threading'].set(
            self.config_manager.get_bool('Performance', 'use_threading', True)
        )
        self.settings['lazy_loading'].set(
            self.config_manager.get_bool('Performance', 'lazy_loading', True)
        )
        self.settings['cache_files'].set(
            self.config_manager.get_bool('Performance', 'cache_files', True)
        )
        self.settings['cache_size'].set(
            self.config_manager.get_int('Performance', 'cache_size_mb', 50)
        )
        self.settings['max_nodes'].set(
            self.config_manager.get_int('Performance', 'max_initial_nodes', 200)
        )
        self.settings['timeout'].set(
            self.config_manager.get_int('Performance', 'analysis_timeout', 30)
        )

        # Display
        self.settings['tree_font_size'].set(
            self.config_manager.get_int('Display', 'tree_font_size', 9)
        )
        self.settings['code_font_size'].set(
            self.config_manager.get_int('Display', 'code_font_size', 10)
        )
        self.settings['diagram_font_size'].set(
            self.config_manager.get_int('Display', 'diagram_font_size', 8)
        )
        self.settings['min_zoom'].set(
            self.config_manager.get_int('Display', 'min_zoom', 10)
        )
        self.settings['max_zoom'].set(
            self.config_manager.get_int('Display', 'max_zoom', 5000)
        )

    def _restore_defaults(self):
        """Restore default settings"""
        response = messagebox.askyesno(
            "Restore Defaults",
            "Are you sure you want to restore all settings to defaults?"
        )

        if response:
            self.config_manager.set_defaults()
            # self.config_manager.set_defaults()
            self._load_current_settings()

    def _apply_settings(self):
        """Apply settings without closing"""
        self._save_to_config()
        # messagebox.showinfo("Success", "Settings applied. Some changes may require restart.")

    def _save_and_close(self):
        self._save_to_config()
        self.destroy()

    def _live_apply_theme(self, theme_value: str):
        self.config_manager.set('General', 'theme', theme_value)
        if hasattr(self.parent_app, '_apply_theme_colors'):
            self.parent_app._apply_theme_colors(theme_value)

    def _save_to_config(self):
        """Save all settings to config file"""
        # Performance
        self.config_manager.set('Performance', 'use_threading',
                                str(self.settings['use_threading'].get()).lower())
        self.config_manager.set('Performance', 'lazy_loading',
                                str(self.settings['lazy_loading'].get()).lower())
        self.config_manager.set('Performance', 'cache_files',
                                str(self.settings['cache_files'].get()).lower())
        self.config_manager.set('Performance', 'cache_size_mb',
                                str(self.settings['cache_size'].get()))
        self.config_manager.set('Performance', 'max_initial_nodes',
                                str(self.settings['max_nodes'].get()))
        self.config_manager.set('Performance', 'analysis_timeout',
                                str(self.settings['timeout'].get()))

        # Display
        self.config_manager.set('Display', 'tree_font_size',
                                str(self.settings['tree_font_size'].get()))
        self.config_manager.set('Display', 'code_font_size',
                                str(self.settings['code_font_size'].get()))
        self.config_manager.set('Display', 'diagram_font_size',
                                str(self.settings['diagram_font_size'].get()))
        self.config_manager.set('Display', 'min_zoom',
                                str(self.settings['min_zoom'].get()))
        self.config_manager.set('Display', 'max_zoom',
                                str(self.settings['max_zoom'].get()))

        # Features
        # self.config_manager.set('Features', 'dark_mode',
        #                         str(self.settings['dark_mode'].get()).lower())
        self.config_manager.set('General', 'theme',
                                self.settings['theme'].get())
        self.config_manager.save_config()
        # Live apply
        self.config_manager.save_config()
        if hasattr(self.parent_app, '_apply_theme_colors'):
            self.parent_app._apply_theme_colors(self.settings['theme'].get())



# ============================================================================
# RECENT FILES MANAGER
# ============================================================================

class RecentFilesManager:
    """Manage recently opened files"""

    def __init__(self, config_manager: ConfigManager, max_recent=10):
        self.config_manager = config_manager
        self.max_recent = max_recent
        self.recent_files = []
        self.load_recent_files()

    def load_recent_files(self):
        """Load recent files from config"""
        try:
            recent_json = self.config_manager.get('General', 'recent_files', '[]')
            self.recent_files = json.loads(recent_json)

            # Filter out files that no longer exist
            self.recent_files = [f for f in self.recent_files if os.path.exists(f)]
        except:
            self.recent_files = []

    def add_file(self, filepath: str):
        """Add a file to recent files"""
        # Remove if already exists
        if filepath in self.recent_files:
            self.recent_files.remove(filepath)

        # Add to beginning
        self.recent_files.insert(0, filepath)

        # Keep only max_recent files
        self.recent_files = self.recent_files[:self.max_recent]

        # Save to config
        self.save_recent_files()

    def save_recent_files(self):
        """Save recent files to config"""
        self.config_manager.set('General', 'recent_files', json.dumps(self.recent_files))
        self.config_manager.save_config()

    def get_recent_files(self) -> List[str]:
        """Get list of recent files"""
        return self.recent_files.copy()

    def clear_recent_files(self):
        """Clear all recent files"""
        self.recent_files = []
        self.save_recent_files()

class StatisticsDialog(tk.Toplevel):
    """Detailed statistics dialog"""

    def __init__(self, parent, modules):
        super().__init__(parent)

        self.title("Code Statistics")
        self.geometry("600x500")

        # Create text widget for stats
        text = tk.Text(self, wrap=tk.NONE, font=('Consolas', 10))
        text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Generate statistics
        stats = self._generate_statistics(modules)
        text.insert('1.0', stats)
        text.configure(state='disabled')

        # Close button
        ttk.Button(self, text="Close", command=self.destroy).pack(pady=10)

    def _generate_statistics(self, modules):
        """Generate detailed statistics"""
        # Calculate various metrics
        total_modules = len(modules)
        total_classes = sum(len(m.classes) for m in modules)
        total_functions = sum(len(m.functions) for m in modules)
        total_methods = sum(sum(len(c.methods) for c in m.classes) for m in modules)
        total_lines = sum(m.line_count for m in modules)

        return f"""
CODE STATISTICS REPORT
======================

Modules:     {total_modules}
Classes:     {total_classes}
Functions:   {total_functions}
Methods:     {total_methods}
Total Lines: {total_lines:,}

Top 10 Largest Modules:
{self._get_top_modules(modules)}

Top 10 Most Complex Functions:
{self._get_complex_functions(modules)}
"""

    def _get_top_modules(self, modules):
        """Get top modules by line count"""
        sorted_modules = sorted(modules, key=lambda m: m.line_count, reverse=True)[:10]
        return '\n'.join(f"  {m.name}: {m.line_count} lines" for m in sorted_modules)

    def _get_complex_functions(self, modules):
        """Get most complex functions"""
        all_funcs = []
        for m in modules:
            for f in m.functions:
                all_funcs.append((f.name, f.complexity, m.name))
            for c in m.classes:
                for method in c.methods:
                    all_funcs.append((f"{c.name}.{method.name}", method.complexity, m.name))

        sorted_funcs = sorted(all_funcs, key=lambda x: x[1], reverse=True)[:10]
        return '\n'.join(f"  {name}: {comp} ({module})"
                         for name, comp, module in sorted_funcs)


class ComplexityReportDialog(tk.Toplevel):
    """Complexity analysis report dialog"""

    def __init__(self, parent, modules):
        super().__init__(parent)

        self.title("Complexity Report")
        self.geometry("800x600")

        # Title
        title = ttk.Label(self, text="Code Complexity Report",
                          font=('Segoe UI', 14, 'bold'))
        title.pack(pady=10)

        # Create frame for treeview
        tree_frame = ttk.Frame(self)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Create treeview
        tree = ttk.Treeview(tree_frame,
                            columns=('complexity', 'lines', 'module'),
                            show='tree headings')

        tree.heading('#0', text='Function/Method')
        tree.heading('complexity', text='Complexity')
        tree.heading('lines', text='Lines')
        tree.heading('module', text='Module')

        tree.column('#0', width=300, minwidth=200, anchor='w')
        tree.column('complexity', width=100, minwidth=80, anchor='center')
        tree.column('lines', width=80, minwidth=60, anchor='center')
        tree.column('module', width=200, minwidth=150, anchor='w')

        # Scrollbar
        scrollbar = ttk.Scrollbar(tree_frame, orient='vertical', command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)

        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Enable mouse wheel
        def on_mousewheel(event):
            tree.yview_scroll(int(-1 * (event.delta / 120)), "units")

        tree.bind("<MouseWheel>", on_mousewheel)

        # Populate tree
        self._populate_tree(tree, modules)

        # Info label
        info = ttk.Label(self,
                         text="Formula: (LOC% × variables × external_calls × cyclomatic) ÷ total_lines",
                         font=('Segoe UI', 9, 'italic'))
        info.pack(pady=5)

        # Close button
        ttk.Button(self, text="Close", command=self.destroy).pack(pady=10)

    def _populate_tree(self, tree, modules):
        """Populate tree with complexity data"""
        for module in modules:
            # Module functions
            for func in module.functions:
                complexity = func.complexity if func.complexity is not None else 0
                tree.insert('', 'end', text=func.name,
                            values=(complexity,
                                    func.end_lineno - func.lineno,
                                    module.name))

            # Class methods
            for cls in module.classes:
                for method in cls.methods:
                    complexity = method.complexity if method.complexity is not None else 0
                    tree.insert('', 'end', text=f"{cls.name}.{method.name}",
                                values=(complexity,
                                        method.end_lineno - method.lineno,
                                        module.name))

# ============================================================================
# CODE ANALYSIS TOOLS
# ============================================================================

class DuplicateFunctionDetector:
    """Detect duplicate/similar functions"""

    def __init__(self, modules: List[ModuleInfo]):
        self.modules = modules
        self.duplicates = []

    def find_duplicates(self) -> List[Tuple[str, str, int]]:
        """Find duplicate functions - same name and arguments in same class"""
        self.duplicates = []

        # Group by class/module
        function_registry = defaultdict(list)

        for module in self.modules:
            # Check module-level functions
            for func in module.functions:
                key = f"MODULE_{module.name}_{func.name}_{len(func.args)}"
                function_registry[key].append({
                    'location': f"{module.name}.{func.name}",
                    'args': func.args,
                    'path': module.path,
                    'line': func.lineno
                })

            # Check class methods
            for cls in module.classes:
                for method in cls.methods:
                    # Key: class_name + method_name + arg_count
                    key = f"CLASS_{module.name}_{cls.name}_{method.name}_{len(method.args)}"
                    function_registry[key].append({
                        'location': f"{module.name}.{cls.name}.{method.name}",
                        'args': method.args,
                        'path': module.path,
                        'line': method.lineno
                    })

        # Find duplicates (same key = same name/class/args)
        for key, functions in function_registry.items():
            if len(functions) > 1:
                # Multiple functions with same signature
                for i in range(len(functions)):
                    for j in range(i + 1, len(functions)):
                        func1 = functions[i]
                        func2 = functions[j]

                        # Check if args match exactly
                        if func1['args'] == func2['args']:
                            self.duplicates.append((
                                func1['location'],
                                func2['location'],
                                100,  # 100% duplicate
                                func1['path'],
                                func1['line'],
                                func2['path'],
                                func2['line']
                            ))

        return self.duplicates

class UnusedCodeDetector:
    """Detect unused functions and classes"""

    def __init__(self, modules: List[ModuleInfo]):
        self.modules = modules
        self.unused_functions = []
        self.unused_classes = []

    def find_unused(self) -> Tuple[List[str], List[str]]:
        """Find unused functions and classes"""
        # Build call graph
        all_calls = set()
        defined_functions = {}
        defined_classes = {}

        for module in self.modules:
            # Track defined functions
            for func in module.functions:
                func_name = f"{module.name}.{func.name}"
                defined_functions[func_name] = {
                    'module': module.name,
                    'name': func.name,
                    'path': module.path,
                    'line': func.lineno
                }

                # Track calls from this function
                for call in func.calls:
                    all_calls.add(call)

            # Track defined classes and their methods
            for cls in module.classes:
                class_name = f"{module.name}.{cls.name}"
                defined_classes[class_name] = {
                    'module': module.name,
                    'name': cls.name,
                    'path': module.path,
                    'line': cls.lineno
                }

                for method in cls.methods:
                    method_name = f"{module.name}.{cls.name}.{method.name}"
                    defined_functions[method_name] = {
                        'module': module.name,
                        'name': f"{cls.name}.{method.name}",
                        'path': module.path,
                        'line': method.lineno
                    }

                    # Track calls from methods
                    for call in method.calls:
                        all_calls.add(call)

        # Find unused functions (not called anywhere)
        self.unused_functions = []
        for func_full_name, func_info in defined_functions.items():
            func_simple_name = func_info['name']

            # Skip special methods and main functions
            if func_simple_name.startswith('__') or func_simple_name == 'main':
                continue

            # Check if function is called
            is_called = False
            for call in all_calls:
                if func_simple_name in call or func_full_name in call:
                    is_called = True
                    break

            if not is_called:
                self.unused_functions.append({
                    'name': func_full_name,
                    'path': func_info['path'],
                    'line': func_info['line']
                })

        # Find unused classes (not instantiated or inherited)
        self.unused_classes = []
        used_classes = set()

        # Mark classes that are used as base classes
        for module in self.modules:
            for cls in module.classes:
                for base in cls.bases:
                    used_classes.add(base)

        # Check which classes are instantiated (simplified check)
        for class_full_name, class_info in defined_classes.items():
            class_simple_name = class_info['name']

            # Skip if used as base class
            if class_simple_name in used_classes:
                continue

            # Check if class name appears in calls (instantiation)
            is_used = False
            for call in all_calls:
                if class_simple_name in call:
                    is_used = True
                    break

            if not is_used:
                self.unused_classes.append({
                    'name': class_full_name,
                    'path': class_info['path'],
                    'line': class_info['line']
                })

        return self.unused_functions, self.unused_classes


# ============================================================================
# RESULT DIALOGS FOR DUPLICATE & UNUSED DETECTION
# ============================================================================

class DuplicateDetectionDialog(tk.Toplevel):
    """Dialog showing duplicate function detection results"""

    def __init__(self, parent, modules: List[ModuleInfo]):
        super().__init__(parent)

        self.title("🔍 Duplicate Function Detection")
        self.geometry("900x600")

        # Run detection
        self.status_label = ttk.Label(self, text="Analyzing code for duplicates...")
        self.status_label.pack(pady=20)

        self.update()

        detector = DuplicateFunctionDetector(modules)
        duplicates = detector.find_duplicates()

        self.status_label.destroy()

        # Create UI
        if duplicates:
            self._show_results(duplicates)
        else:
            self._show_no_duplicates()

    def _show_results(self, duplicates):
        """Show duplicate detection results"""
        # Header
        header = ttk.Label(
            self,
            text=f"Found {len(duplicates)} duplicate function(s)",
            font=('Segoe UI', 12, 'bold')
        )
        header.pack(pady=10)

        # Create treeview frame
        frame = ttk.Frame(self)
        frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        tree = ttk.Treeview(
            frame,
            columns=('function1', 'function2', 'similarity', 'location'),
            show='headings'
        )

        tree.heading('function1', text='Function 1')
        tree.heading('function2', text='Function 2')
        tree.heading('similarity', text='Match')
        tree.heading('location', text='Location')

        tree.column('function1', width=250, anchor='w')
        tree.column('function2', width=250, anchor='w')
        tree.column('similarity', width=80, anchor='center')
        tree.column('location', width=250, anchor='center')

        # Populate tree
        for func1, func2, similarity, path1, line1, path2, line2 in duplicates:
            tree.insert('', 'end', values=(
                func1,
                func2,
                f"{similarity}%",
                f"{os.path.basename(path1)}:{line1} & {os.path.basename(path2)}:{line2}"
            ))

        # Scrollbar
        scrollbar = ttk.Scrollbar(frame, orient='vertical', command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)

        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Mouse wheel
        def on_mousewheel(event):
            tree.yview_scroll(int(-1 * (event.delta / 120)), "units")

        tree.bind("<MouseWheel>", on_mousewheel)

        # Info label
        info = ttk.Label(
            self,
            text="Duplicates = Same name + Same arguments in same class/module",
            font=('Segoe UI', 9, 'italic')
        )
        info.pack(pady=5)

        # Close button
        ttk.Button(self, text="Close", command=self.destroy).pack(pady=10)

    def _show_no_duplicates(self):
        """Show message when no duplicates found"""
        message = ttk.Label(
            self,
            text="✅ No duplicate functions detected!",
            font=('Segoe UI', 14, 'bold'),
            foreground='green'
        )
        message.pack(pady=50)

        ttk.Button(self, text="Close", command=self.destroy).pack(pady=10)



class UnusedCodeDialog(tk.Toplevel):
    """Dialog showing unused code detection results"""

    def __init__(self, parent, modules: List[ModuleInfo]):
        super().__init__(parent)

        self.title("🗑️ Unused Code Detection")
        self.geometry("800x600")

        # Run detection
        self.status_label = ttk.Label(self, text="Analyzing code for unused functions...")
        self.status_label.pack(pady=20)

        self.update()

        detector = UnusedCodeDetector(modules)
        unused_funcs, unused_classes = detector.find_unused()

        self.status_label.destroy()

        # Create UI
        if unused_funcs or unused_classes:
            self._show_results(unused_funcs, unused_classes)
        else:
            self._show_no_unused()

    def _show_results(self, unused_funcs, unused_classes):
        """Show unused code results"""
        # Header
        header = ttk.Label(
            self,
            text=f"Found {len(unused_funcs)} unused function(s) and {len(unused_classes)} unused class(es)",
            font=('Segoe UI', 12, 'bold')
        )
        header.pack(pady=10)

        # Create notebook
        notebook = ttk.Notebook(self)
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Unused Functions Tab
        func_frame = ttk.Frame(notebook)
        notebook.add(func_frame, text=f"Unused Functions ({len(unused_funcs)})")

        func_tree = ttk.Treeview(
            func_frame,
            columns=('name', 'location'),
            show='headings'
        )
        func_tree.heading('name', text='Function Name')
        func_tree.heading('location', text='Location')

        func_tree.column('name', width=400)
        func_tree.column('location', width=350)

        for func in unused_funcs:
            func_tree.insert('', 'end', values=(
                func['name'],
                f"{func['path']}:{func['line']}"
            ))

        func_scroll = ttk.Scrollbar(func_frame, orient='vertical', command=func_tree.yview)
        func_tree.configure(yscrollcommand=func_scroll.set)

        func_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        func_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        # Unused Classes Tab
        class_frame = ttk.Frame(notebook)
        notebook.add(class_frame, text=f"Unused Classes ({len(unused_classes)})")

        class_tree = ttk.Treeview(
            class_frame,
            columns=('name', 'location'),
            show='headings'
        )
        class_tree.heading('name', text='Class Name')
        class_tree.heading('location', text='Location')

        class_tree.column('name', width=400)
        class_tree.column('location', width=350, anchor='center')

        for cls in unused_classes:
            class_tree.insert('', 'end', values=(
                cls['name'],
                f"{cls['path']}:{cls['line']}"
            ))

        class_scroll = ttk.Scrollbar(class_frame, orient='vertical', command=class_tree.yview)
        class_tree.configure(yscrollcommand=class_scroll.set)

        class_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        class_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        # Warning
        warning = ttk.Label(
            self,
            text="⚠ Warning: Some 'unused' code may be called dynamically or be API endpoints.",
            font=('Segoe UI', 9, 'italic'),
            foreground='orange'
        )
        warning.pack(pady=5)

        # Close button
        ttk.Button(self, text="Close", command=self.destroy).pack(pady=10)

    def _show_no_unused(self):
        """Show message when no unused code found"""
        message = ttk.Label(
            self,
            text="✅ No unused code detected!",
            font=('Segoe UI', 14, 'bold'),
            foreground='green'
        )
        message.pack(pady=50)

        ttk.Button(self, text="Close", command=self.destroy).pack(pady=10)

# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

def main():
    """Main entry point"""
    app = PythonCodeVisualizerApp()
    app.mainloop()


if __name__ == "__main__":
    main()
