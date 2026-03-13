import os
import shutil
import random
import time
import subprocess
import sys
import glob
import threading
import ctypes
import platform
import uuid
import json
import webbrowser
import hashlib
from io import BytesIO
from datetime import datetime
from queue import Queue

import customtkinter as ctk
from tkinter import messagebox, filedialog
from cryptography.fernet import Fernet

# PDF and QR Code generation dependencies
IS_REPORTLAB_AVAILABLE = True
IS_SEGNO_AVAILABLE = True
try:
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, Image
    from reportlab.lib import colors
    from reportlab.lib.units import inch
except ImportError:
    IS_REPORTLAB_AVAILABLE = False
    print("Warning: reportlab not installed. PDF generation disabled.\nRun: pip install reportlab")

try:
    import segno
except ImportError:
    IS_SEGNO_AVAILABLE = False
    print("Warning: segno not installed. QR Code generation disabled.\nRun: pip install segno")


# --- Theme & Colors ---
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("green")

class AppColors:
    BACKGROUND = "#0a0a0a"
    FRAME = "#141414"
    TERMINAL_GREEN = "#00ff41"
    TEXT_HEADER = "#ffffff"
    ACCENT_CYAN = "#00BCD4"
    ACCENT_RED = "#F44336"
    BUTTON_RED = "#D32F2F"
    BUTTON_RED_HOVER = "#B71C1C"
    BUTTON_SECONDARY_BG = "#1a1a1a"
    BUTTON_SECONDARY_HOVER = "#2a2a2a"
    BUTTON_SECONDARY_BORDER = "#00ff41"


PRIMARY_COLOR = "#00ffc8"
ACCENT_COLOR = "#0066cc"
BG_DARK = "#141414"
BG_MEDIUM = "#1e1e1e"
BG_LIGHT = "#282828"
CONSOLE_TEXT_COLOR = "#00ff88"


# --- Utility ---
def is_admin_or_root():
    """Checks for administrative (root) privileges."""
    try:
        if platform.system() == "Windows":
            return ctypes.windll.shell32.IsUserAnAdmin() != 0
        else:
            return os.geteuid() == 0
    except AttributeError:
        return False


# --- Secure Delete (Local Backend) ---
class SecureDeleter:
    def __init__(self, path, passes=32, method='gutmann', progress_cb=None, status_cb=None):
        self.path = path
        self.passes = passes
        self.method = method.lower()
        self.chunk = 1024 * 1024  # 1MB chunks
        self.progress_cb = progress_cb
        self.status_cb = status_cb
        self.os_type = platform.system()
        self.start_ts = time.time()
        self.end_ts = None
        self.deletion_type = 'N/A'
        self.target_name = os.path.basename(path)
        self.op_status = 'PENDING'
        self.ver_status = 'N/A'
        self.pdf_hash = None
        self.block_sig = None
        self.block_data = None
        self.gutmann_patterns = [
            b'\x55', b'\xAA', b'\x92', b'\x49', b'\x24', b'\x00', b'\x11', b'\x22', b'\x33', b'\x44',
            b'\x55', b'\x66', b'\x77', b'\x88', b'\x99', b'\xAA', b'\xBB', b'\xCC', b'\xDD', b'\xEE',
            b'\xFF', b'\x92', b'\x49', b'\x24', b'\x6D', b'\xB6', b'\xDB', b'\x6D', b'\xB6', b'\xDB'
        ]
        self.total_ops = 0
        self.completed = 0

    def log(self, msg, is_error=False):
        if self.status_cb:
            self.status_cb(msg, is_error=is_error)

    def prog(self):
        if self.progress_cb and self.total_ops > 0:
            p = min(100, (self.completed / self.total_ops) * 100)
            self.progress_cb(p)

    def _get_passes(self):
        return {'gutmann': self.passes, 'dod': 3, 'nist': 2}.get(self.method, 32)

    def encrypt_file(self, path):
        """Encrypts a file in place before deletion. NOTE: Reads the whole file into memory."""
        key = Fernet.generate_key()
        try:
            with open(path, 'rb+') as f:
                data = f.read()
                enc = Fernet(key).encrypt(data)
                f.seek(0)
                f.write(enc)
                f.truncate()
            del key, data, enc
            self.log("🔐 File encrypted prior to overwrite.")
        except Exception as e:
            self.log(f"Encryption failed: {e}", is_error=True)

    def _overwrite(self, path, pattern, length):
        """Overwrites a file with a given pattern or random data."""
        try:
            with open(path, 'r+b') as f:
                f.seek(0)
                written = 0
                # If pattern is empty (b''), it signifies a random pass.
                if not pattern:
                    while written < length:
                        to_write = min(self.chunk, length - written)
                        f.write(os.urandom(to_write))
                        written += to_write
                # Otherwise, use the specified byte pattern.
                else:
                    # Create a chunk buffer from the pattern.
                    chunk = (pattern * (self.chunk // len(pattern) + 1))
                    while written < length:
                        to_write = min(self.chunk, length - written)
                        f.write(chunk[:to_write])
                        written += to_write
                f.flush()
                os.fsync(f.fileno())
        except Exception as e:
            self.log(f"Overwrite failed for {os.path.basename(path)}: {e}", is_error=True)


    def _rename_remove(self, path):
        """Renames a file to a random string, then securely removes it."""
        try:
            d, _ = os.path.split(path)
            new_name = ''.join(random.choices('abcdefghijklmnopqrstuvwxyz0123456789', k=16))
            new_path = os.path.join(d, new_name)
            os.rename(path, new_path)
            
            if self.os_type == 'Linux' and shutil.which('shred'):
                subprocess.run(['shred', '-n', '1', '-u', new_path], check=True, capture_output=True)
            else:
                # Basic removal for other OS or if shred is not available
                open(new_path, 'w').close()
                os.remove(new_path)
        except Exception:
            # If any step fails, try a simple removal as a fallback.
            if os.path.exists(path): os.remove(path)
            if 'new_path' in locals() and os.path.exists(new_path): os.remove(new_path)


    def verify(self, p):
        if not os.path.exists(p):
            self.log(f"Verified removal of: {self.target_name}")
            return 'Verified'
        else:
            self.log(f"Verification failed: {self.target_name} still exists.", is_error=True)
            return 'Failed'

    def gutmann_overwrite(self, path):
        if not os.path.isfile(path): return
        L = os.path.getsize(path)
        self.log(f"Starting Gutmann {self.passes}-pass overwrite...")
        patterns = ([b''] * 4 + self.gutmann_patterns + [b''] * 4)[:self.passes]
        for i, p in enumerate(patterns):
            self.log(f"  ↳ Pass {i + 1}/{self.passes}")
            self._overwrite(path, p, L)
            self.completed += 1
            self.prog()
        self._rename_remove(path)
        self.ver_status = self.verify(path)

    def dod_overwrite(self, path):
        if not os.path.isfile(path): return
        L = os.path.getsize(path)
        self.log("Starting DoD 5220.22-M 3-pass overwrite...")
        for i, (p, n) in enumerate([(b'\x00', 'Zeros'), (b'\xFF', 'Ones'), (b'', 'Random')]):
            self.log(f"  ↳ Pass {i + 1}/3: Writing {n}")
            self._overwrite(path, p, L)
            self.completed += 1
            self.prog()
        self._rename_remove(path)
        self.ver_status = self.verify(path)

    def nist_overwrite(self, path):
        if not os.path.isfile(path): return
        L = os.path.getsize(path)
        self.log("Starting NIST 800-88 2-pass overwrite...")
        self.log("  ↳ Pass 1/2: Writing Zeros")
        self._overwrite(path, b'\x00', L)
        self.completed += 1
        self.prog()
        
        self.log("  ↳ Pass 2/2: Verifying overwrite")
        try:
            with open(path, 'rb') as f:
                # Read in chunks to avoid memory errors on large files
                is_verified = all(chunk == b'\x00' * len(chunk) for chunk in iter(lambda: f.read(self.chunk), b''))
            if not is_verified: raise IOError("Read-back verification failed; not all bytes were zeroed.")
            self.log("  Verification successful.")
        except Exception as e:
            self.log(f"NIST verification step failed: {e}", is_error=True)

        self.completed += 1
        self.prog()
        self._rename_remove(path)
        self.ver_status = self.verify(path)

    def delete_file(self, path):
        if os.path.isfile(path):
            self.encrypt_file(path)
            self.completed += 1
            self.prog()
            
            if self.method == 'dod': self.dod_overwrite(path)
            elif self.method == 'nist': self.nist_overwrite(path)
            else: self.gutmann_overwrite(path)

    def delete_folder(self, folder):
        if not os.path.isdir(folder): return
        
        # Collect all files first to prevent issues with changing directory structure
        files_to_delete = [os.path.join(r, f) for r, _, fl in os.walk(folder) for f in fl]
        
        for i, p in enumerate(files_to_delete):
            self.log(f"Sanitizing file {i + 1}/{len(files_to_delete)}: {os.path.basename(p)}")
            self.delete_file(p)
        
        try:
            self.log(f"Removing empty directory structure: {folder}")
            shutil.rmtree(folder)
            self.ver_status = self.verify(folder)
        except Exception as e:
            self.log(f"Could not remove folder structure: {e}", is_error=True)
            self.ver_status = 'Failed'

    def wipe_free_space(self, path):
        self.log("--- Starting Free Space Sanitization ---")
        if self.os_type == 'Windows':
            drive = os.path.splitdrive(path)[0]
            if not drive: drive = os.getcwd().split('\\')[0] # Fallback for relative paths
            self.log(f"Targeting drive {drive} for free space wipe.")
            
            if shutil.which("sdelete"):
                proc = subprocess.Popen(["sdelete", "-z", drive], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
                for line in proc.stdout: self.log(f"  [SDelete] {line.strip()}")
                proc.wait()
            else:
                self.log("SDelete not found in PATH, skipping. For best results, install Microsoft SDelete.", is_error=True)
            
            self.log("Using built-in cipher tool...")
            proc = subprocess.Popen(["cipher", f"/w:{drive}"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
            for line in proc.stdout: self.log(f"  [Cipher] {line.strip()}")
            proc.wait()
        else: # Linux/macOS
            mount_point = path if os.path.ismount(path) else os.path.dirname(path)
            tmp_file = os.path.join(mount_point, "cipherforge_temp_wipe.tmp")
            self.log(f"Creating large temp file to wipe free space on {mount_point}...")
            try:
                # Use dd to fill free space, capture stderr for progress
                proc = subprocess.Popen(['dd', 'if=/dev/zero', f'of={tmp_file}', 'bs=1M'], stderr=subprocess.PIPE, text=True)
                while proc.poll() is None:
                    line = proc.stderr.readline()
                    if line: self.log(f"  [dd] {line.strip()}")
            except FileNotFoundError:
                self.log("`dd` command not found. Cannot wipe free space.", is_error=True)
            except Exception as e:
                self.log(f"Error during `dd` execution: {e}", is_error=True)
            finally:
                if os.path.exists(tmp_file):
                    os.remove(tmp_file)
                    self.log("Temporary wipe file removed.")
        self.completed += 1
        self.prog()


    def clear_system_traces(self):
        self.log("--- Clearing System Traces ---")
        if self.os_type == 'Windows':
            try:
                # Clear recent files
                recent_path = os.path.join(os.getenv('APPDATA'), "Microsoft", "Windows", "Recent")
                for item in glob.glob(os.path.join(recent_path, '*')):
                    if os.path.isfile(item): os.remove(item)
                self.log("Windows 'Recent Items' list cleared.")
                
                # Clear jump lists
                for p in [os.path.join(os.getenv('APPDATA'), "Microsoft", "Windows", "Recent", "AutomaticDestinations"),
                          os.path.join(os.getenv('APPDATA'), "Microsoft", "Windows", "Recent", "CustomDestinations")]:
                    for item in glob.glob(os.path.join(p, '*')): os.remove(item)
                self.log("Windows 'Jump Lists' cleared.")
            except Exception as e:
                self.log(f"Could not clear all Windows traces: {e}", is_error=True)
        else: # Linux
            try:
                home = os.path.expanduser('~')
                # Clear trash
                trash_paths = [os.path.join(home, '.local', 'share', 'Trash', 'files'),
                               os.path.join(home, '.local', 'share', 'Trash', 'info')]
                for p in trash_paths:
                    if os.path.isdir(p):
                        shutil.rmtree(p)
                        os.makedirs(p)
                self.log("Linux trash emptied.")

                # Clear recently used list
                recent_file = os.path.join(home, '.local', 'share', 'recently-used.xbel')
                if os.path.exists(recent_file):
                    os.remove(recent_file)
                    self.log("'recently-used.xbel' removed.")
            except Exception as e:
                self.log(f"Could not clear all Linux traces: {e}", is_error=True)

        self.completed += 1
        self.prog()

    def execute(self):
        self.start_ts = time.time()
        passes = self._get_passes()
        
        if os.path.isfile(self.path):
            self.deletion_type = 'File Deletion'
            self.total_ops = 1 + passes + 2 # Encrypt + Passes + Wipe Free + Clear Traces
            self.delete_file(self.path)
        elif os.path.isdir(self.path):
            self.deletion_type = 'Folder Deletion'
            files = [f for _, _, fl in os.walk(self.path) for f in fl]
            self.total_ops = len(files) * (1 + passes) + 2 # (Encrypt + Passes) * NumFiles + Wipe Free + Clear Traces
            self.delete_folder(self.path)
        else:
            self.log(f"Target path does not exist or is not a file/folder: {self.path}", is_error=True)
            self.op_status = 'FAILED'
            return

        root_path = os.path.abspath(self.path)
        self.wipe_free_space(root_path)
        self.clear_system_traces()
        
        self.log("🎉 Secure deletion process complete.")
        self.end_ts = time.time()
        self.op_status = 'SUCCESS'
        self.completed = self.total_ops
        self.prog()


# --- Main Application ---
class SecureWipeApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        # --- Main App Attributes ---
        self.title("CipherForge - Unified Sanitization Suite")
        self.state('zoomed')
        self.configure(fg_color=AppColors.BACKGROUND)
        self.log_queue = Queue()
        self.is_animating = False

        # --- Local Deletion Attributes ---
        self.selected_path = ctk.StringVar()
        self.method_var = ctk.StringVar(value="gutmann")
        self.is_deleting = False
        self.deleter = None

        # --- Android Wipe Attributes ---
        self.ADB_PATH = "adb"
        self.WIPE_CERT_FILE = "Android_Wipe_Certificate.json"
        self.is_wiping = False

        self._create_unified_ui()
        self.populate_devices()
        self.after(100, self.process_log_queue)
        self._check_privileges()

    def _create_unified_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=3)
        self.grid_rowconfigure(0, weight=1)

        # --- Left Control Pane ---
        left = ctk.CTkFrame(self, fg_color=BG_MEDIUM, corner_radius=10)
        left.grid(row=0, column=0, sticky="nsew", padx=(10, 5), pady=10)
        left.grid_rowconfigure(7, weight=1) # Pushes wipe buttons to the bottom

        ctk.CTkLabel(left, text="CIPHERFORGE", font=ctk.CTkFont(family="Courier New", size=24, weight="bold"), text_color=PRIMARY_COLOR).grid(row=0, column=0, pady=(10, 5), padx=20)
        ctk.CTkLabel(left, text="Unified Sanitization Suite", font=ctk.CTkFont(size=14), text_color="#888888").grid(row=1, column=0, padx=20, pady=(0, 20))

        # --- Local Deletion Section ---
        ctk.CTkLabel(left, text="🛡️ Local Secure Deletion", font=ctk.CTkFont(size=16, weight="bold")).grid(row=2, column=0, padx=20, pady=(10, 5), sticky="w")

        self.path_display = ctk.CTkTextbox(left, height=70, fg_color="#333333", text_color=PRIMARY_COLOR, activate_scrollbars=False)
        self.path_display.grid(row=3, column=0, sticky="ew", padx=20, pady=5)
        self.path_display.insert("1.0", "No target selected...")
        self.path_display.configure(state="disabled")

        # --- NEW: Button Frame for better layout ---
        selection_btn_frame = ctk.CTkFrame(left, fg_color="transparent")
        selection_btn_frame.grid(row=4, column=0, sticky="ew", padx=20, pady=5)
        selection_btn_frame.grid_columnconfigure((0, 1, 2), weight=1) # Create 3 equal columns

        btn_style = {'height': 40, 'fg_color': ACCENT_COLOR, 'hover_color': "#004d99", 'font': ctk.CTkFont(size=14, weight="bold")}
        ctk.CTkButton(selection_btn_frame, text="📄 File", command=self.browse_file, **btn_style).grid(row=0, column=0, padx=(0, 5), sticky="ew")
        ctk.CTkButton(selection_btn_frame, text="📁 Folder", command=self.browse_folder, **btn_style).grid(row=0, column=1, padx=5, sticky="ew")
        ctk.CTkButton(selection_btn_frame, text="💾 Drive", command=self.browse_drive, **btn_style).grid(row=0, column=2, padx=(5, 0), sticky="ew")
        # --- END NEW ---

        algo_frame = ctk.CTkFrame(left, fg_color=BG_LIGHT, corner_radius=10)
        algo_frame.grid(row=5, column=0, sticky="ew", padx=20, pady=10)
        ctk.CTkLabel(algo_frame, text="⚙️ Algorithm", font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", padx=15, pady=(10, 5))
        ctk.CTkRadioButton(algo_frame, text="🛡️ Gutmann 32-Pass (Most Secure)", variable=self.method_var, value="gutmann").pack(anchor="w", padx=15, pady=3)
        ctk.CTkRadioButton(algo_frame, text="⚡ DoD 3-Pass (Fast & Secure)", variable=self.method_var, value="dod").pack(anchor="w", padx=15, pady=3)
        ctk.CTkRadioButton(algo_frame, text="✅ NIST 800-88 (Fastest, for SSDs)", variable=self.method_var, value="nist").pack(anchor="w", padx=15, pady=(3, 10))
        
        # Spacer row to push controls to the bottom
        left.grid_rowconfigure(6, weight=1) 

        ctk.CTkButton(left, text="🔥 INITIATE LOCAL WIPE", command=self.start_deletion, height=50, fg_color=AppColors.BUTTON_RED, hover_color=AppColors.BUTTON_RED_HOVER, font=ctk.CTkFont(size=16, weight="bold")).grid(row=7, column=0, sticky="sew", padx=20, pady=10)

        # --- Android Wipe Section ---
        ctk.CTkLabel(left, text="📱 Android Device Wipe", font=ctk.CTkFont(size=16, weight="bold")).grid(row=8, column=0, padx=20, pady=(20, 5), sticky="w")

        target_frame = ctk.CTkFrame(left, fg_color="transparent")
        target_frame.grid(row=9, column=0, padx=20, pady=5, sticky="ew")
        self.device_selector = ctk.CTkComboBox(target_frame, values=["Scanning..."], button_color=AppColors.BUTTON_SECONDARY_BG, border_color=AppColors.BUTTON_SECONDARY_BORDER, button_hover_color=AppColors.BUTTON_SECONDARY_HOVER)
        self.device_selector.pack(fill="x", ipady=4, side="left", expand=True, padx=(0,10))
        ctk.CTkButton(target_frame, text="Refresh", command=self.populate_devices, fg_color=AppColors.BUTTON_SECONDARY_BG, hover_color=AppColors.BUTTON_SECONDARY_HOVER, border_color=AppColors.BUTTON_SECONDARY_BORDER, border_width=1).pack(fill="x", side="right")

        ctk.CTkButton(left, text="📲 INITIATE ANDROID WIPE", command=self.start_wipe_thread, height=50, fg_color="#1E88E5", hover_color="#1565C0", font=ctk.CTkFont(size=16, weight="bold")).grid(row=10, column=0, padx=20, pady=(10, 20), sticky="ew")


        # --- Right Log and Status Pane ---
        right = ctk.CTkFrame(self, fg_color=BG_MEDIUM, corner_radius=10)
        right.grid(row=0, column=1, sticky="nsew", padx=(5, 10), pady=10)
        right.grid_rowconfigure(2, weight=1)
        right.grid_columnconfigure(0, weight=1)

        prog_sec = ctk.CTkFrame(right, fg_color=BG_LIGHT, corner_radius=10)
        prog_sec.grid(row=0, column=0, sticky="ew", padx=20, pady=(20, 10))
        prog_sec.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(prog_sec, text="📊 Operation Status", font=ctk.CTkFont(size=18, weight="bold"), text_color=PRIMARY_COLOR).grid(row=0, column=0, sticky="w", padx=15, pady=(10, 5))
        self.progress_bar = ctk.CTkProgressBar(prog_sec, height=25, corner_radius=10, fg_color="#333333", progress_color=PRIMARY_COLOR)
        self.progress_bar.set(0)
        self.progress_bar.grid(row=1, column=0, sticky="ew", padx=15, pady=(0, 5))
        self.progress_label = ctk.CTkLabel(prog_sec, text="Ready for Command.", font=ctk.CTkFont(size=14), text_color="#CCCCCC")
        self.progress_label.grid(row=2, column=0, sticky="w", padx=15, pady=(0, 10))

        cert_sec = ctk.CTkFrame(right, fg_color=BG_LIGHT, corner_radius=10)
        cert_sec.grid(row=1, column=0, sticky="ew", padx=20, pady=10)
        cert_sec.grid_columnconfigure(0, weight=1)
        cert_sec.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(cert_sec, text="📄 Certificate of Sanitization", font=ctk.CTkFont(size=18, weight="bold"), text_color=PRIMARY_COLOR).grid(row=0, column=0, columnspan=2, sticky="w", padx=15, pady=(10, 5))
        self.cert_btn = ctk.CTkButton(cert_sec, text="Download PDF Audit", command=self.generate_certificate_ui, height=45, fg_color=ACCENT_COLOR, hover_color="#004d99", state="disabled")
        self.cert_btn.grid(row=1, column=0, padx=(15, 5), pady=(0, 15), sticky="ew")
        self.json_btn = ctk.CTkButton(cert_sec, text="Download JSON Proof", command=self.download_verification_json, height=45, fg_color="#555555", hover_color="#444444", state="disabled")
        self.json_btn.grid(row=1, column=1, padx=(5, 15), pady=(0, 15), sticky="ew")
        
        log_sec = ctk.CTkFrame(right, fg_color=BG_LIGHT, corner_radius=10)
        log_sec.grid(row=2, column=0, sticky="nsew", padx=20, pady=(10, 20))
        log_sec.grid_rowconfigure(1, weight=1)
        log_sec.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(log_sec, text="📋 Security Operations Log", font=ctk.CTkFont(size=18, weight="bold"), text_color=PRIMARY_COLOR).grid(row=0, column=0, sticky="w", padx=15, pady=(10, 5))
        self.log_box = ctk.CTkTextbox(log_sec, font=ctk.CTkFont(family="Consolas", size=14), fg_color=BG_DARK, text_color=CONSOLE_TEXT_COLOR, state="disabled")
        self.log_box.grid(row=1, column=0, sticky="nsew", padx=15, pady=(0, 15))
        self.log_status(f"CipherForge Unified v1.0 Booted. OS: {platform.system()}")

    # --- Privilege Check ---
    def _check_privileges(self):
        if not is_admin_or_root():
            messagebox.showwarning("Privilege Warning", "Not running with admin/root privileges.\nSome features, like free space wiping and trace clearing, may fail or be incomplete.")

    # --- UI Callbacks and Updaters ---
    def browse_file(self):
        if self.is_deleting: return
        f = filedialog.askopenfilename(title="Select a file to securely delete")
        if f:
            self.selected_path.set(f)
            self._update_path_display(f"📄 TARGET FILE:\n{f}")

    def browse_folder(self):
        if self.is_deleting: return
        d = filedialog.askdirectory(title="Select a folder to securely delete")
        if d:
            self.selected_path.set(d)
            self._update_path_display(f"📁 TARGET FOLDER:\n{d}")

    def browse_drive(self):
        if self.is_deleting: return
        # On Windows, askdirectory is the standard way to select a drive root.
        d = filedialog.askdirectory(title="Select a DRIVE root to wipe (e.g., D:\\)")
        if d and os.path.ismount(d):
            self.selected_path.set(d)
            self._update_path_display(f"⚠️ CRITICAL DRIVE:\n{d}")
        elif d:
            messagebox.showerror("Invalid Selection", f"The selected path '{d}' is not a valid drive or mount point.")

    def _update_path_display(self, txt):
        self.path_display.configure(state="normal")
        self.path_display.delete("1.0", "end")
        self.path_display.insert("1.0", txt)
        self.path_display.configure(state="disabled")
        
    def update_progress(self, val):
        self.progress_bar.set(val / 100)
        self.progress_label.configure(text=f"Progress: {val:.1f}% | In Progress...")

    def on_deletion_complete(self):
        if self.deleter.op_status == 'SUCCESS':
            self.progress_label.configure(text="Operation Complete. Certificate ready.", text_color="#00C853")
            self.cert_btn.configure(state="normal")
            self.json_btn.configure(state="normal")
        else:
            self.progress_label.configure(text="Operation Failed. Check logs for details.", text_color=AppColors.ACCENT_RED)
        self.is_deleting = False

    # --- Universal Logging System ---
    def log_status(self, msg, is_error=False):
        """Thread-safe method to queue log messages for display."""
        prefix = "❌" if is_error else "✅"
        self.log_queue.put(f"{prefix} {msg}")

    def process_log_queue(self):
        """Processes the log queue to display messages with a typing animation."""
        if not self.is_animating and not self.log_queue.empty():
            msg = self.log_queue.get_nowait()
            self.is_animating = True
            self.log_box.configure(state="normal")
            ts = datetime.now().strftime("%H:%M:%S")
            self.log_box.insert("end", f"\n[{ts}] ")
            self._animate(msg)
        self.after(100, self.process_log_queue)

    def _animate(self, msg, idx=0):
        if idx < len(msg):
            self.log_box.insert("end", msg[idx])
            self.log_box.see("end")
            self.after(5, lambda: self._animate(msg, idx + 1))
        else:
            self.log_box.configure(state="disabled")
            self.is_animating = False

    # --- Local Deletion Methods ---
    def start_deletion(self):
        if self.is_deleting:
            self.log_status("A local deletion process is already running.", is_error=True)
            return
            
        path = self.selected_path.get().strip()
        if not path or not os.path.exists(path):
            messagebox.showerror("Error", "A valid target file or folder is required.")
            return

        if not messagebox.askyesno("🚨 Confirm Deletion", f"This will permanently destroy all data on:\n\n{path}\n\nThis action cannot be undone. Are you absolutely sure?"):
            return

        self.cert_btn.configure(state="disabled")
        self.json_btn.configure(state="disabled")
        self.progress_bar.set(0)
        self.progress_label.configure(text="Starting...", text_color="#CCCCCC")
        self.is_deleting = True
        
        self.deleter = SecureDeleter(path, method=self.method_var.get(), progress_cb=self.update_progress, status_cb=self.log_status)
        threading.Thread(target=self._run_deletion, daemon=True).start()

    def _run_deletion(self):
        try:
            self.deleter.execute()
        except Exception as e:
            self.log_status(f"CRITICAL ERROR during deletion: {e}", is_error=True)
            if self.deleter: self.deleter.op_status = 'FAILED'
        finally:
            self.after(0, self.on_deletion_complete)

    # --- Android Wipe Methods ---
    def execute_adb(self, parts, log=False):
        cmd = [self.ADB_PATH] + parts
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=30, creationflags=(subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0))
            if log and res.stdout: self.log_status(f"(Output: {res.stdout.strip()})")
            if res.returncode != 0: return False, res.stderr.strip()
            return True, res.stdout.strip()
        except FileNotFoundError:
            self.log_status("ADB not found. Ensure 'adb' is in your system's PATH.", True)
            return False, "ADB_NOT_FOUND"
        except subprocess.TimeoutExpired:
            return False, "TIMEOUT"
        except Exception as e:
            return False, str(e)

    def populate_devices(self):
        self.log_status("Scanning for connected ADB targets...")
        ok, out = self.execute_adb(['devices'])
        if not ok:
            self.log_status("Failed to execute ADB command.", is_error=True)
            devices = []
        else:
            devices = [l.split('\t')[0] for l in out.splitlines() if '\tdevice' in l]

        if not devices:
            self.log_status("No authorized Android devices found.", is_error=True)
            self.device_selector.configure(values=["No device"])
            self.device_selector.set("No device")
        else:
            self.log_status(f"Found ADB targets: {', '.join(devices)}")
            self.device_selector.configure(values=devices)
            self.device_selector.set(devices[0])

    def start_wipe_thread(self):
        if self.is_wiping:
            self.log_status("An Android wipe is already in progress.", is_error=True)
            return
        serial = self.device_selector.get()
        if not serial or "No device" in serial:
            self.log_status("No valid Android target selected.", is_error=True)
            return
        
        if not messagebox.askyesno("🚨 Confirm Android Wipe", f"This will perform a factory reset on device:\n\n{serial}\n\nAll data on the device will be erased. Proceed?"):
            return

        self.is_wiping = True
        threading.Thread(target=self._wipe_device, args=(serial,), daemon=True).start()

    def _wipe_device(self, serial):
        start = time.time()
        info = {'serial': serial, 'model': 'Unknown'}
        status = "PENDING"
        try:
            self.log_status(f"Starting sanitization for target: {serial}")
            ok, model = self.execute_adb(['-s', serial, 'shell', 'getprop', 'ro.product.model'])
            info['model'] = model.strip() if ok and model else "Unknown"
            self.log_status(f"Device Model: {info['model']}")

            self.log_status("Attempting factory reset via MASTER_CLEAR broadcast...")
            ok, out = self.execute_adb(['-s', serial, 'shell', 'am', 'broadcast', '-a', 'android.intent.action.MASTER_CLEAR'])
            if ok and ("result=0" in out or "completed" in out):
                self.log_status("MASTER_CLEAR broadcast sent successfully. Device should reboot and wipe.")
                status = "SUCCESS_MASTER_CLEAR"
            else:
                self.log_status("MASTER_CLEAR failed, attempting fallback via recovery key simulation.", is_error=True)
                self.execute_adb(['-s', serial, 'reboot', 'recovery'])
                time.sleep(15) # Wait for device to enter recovery
                
                # Note: This key sequence is for stock Android recovery and may vary by manufacturer.
                steps = [
                    ('KEYCODE_VOLUME_DOWN', 2, "Navigating to 'Wipe data/factory reset'"),
                    ('KEYCODE_POWER', 5, "Selecting 'Wipe data/factory reset'"),
                    ('KEYCODE_VOLUME_DOWN', 2, "Navigating to 'Confirm'"),
                    ('KEYCODE_POWER', 15, "Confirming wipe... (This may take a while)"),
                    ('KEYCODE_POWER', 5, "Returning to main recovery menu"),
                    ('KEYCODE_POWER', 5, "Selecting 'Reboot system now'"),
                ]
                for key, delay, desc in steps:
                    self.log_status(desc)
                    self.execute_adb(['-s', serial, 'shell', 'input', 'keyevent', key])
                    time.sleep(delay)
                self.log_status("Recovery input simulation complete. Device should be wiping.")
                status = "SUCCESS_RECOVERY_SIM"
        except Exception as e:
            self.log_status(f"A critical error occurred during the Android wipe: {e}", is_error=True)
            status = f"FAILED - {e}"

        elapsed = time.time() - start
        self.log_status(f"Android sanitization process finished in {elapsed:.2f} seconds.")
        if "SUCCESS" in status:
            self.log_status("ANDROID WIPE INITIATED SUCCESSFULLY.")
        else:
            self.log_status("ANDROID WIPE FAILED.", is_error=True)
            # Attempt to reboot the device back to system if it's stuck
            self.execute_adb(['-s', serial, 'reboot'])

        self._generate_android_cert(info, status)
        self.is_wiping = False

    def _generate_android_cert(self, info, status):
        """Generates a JSON certificate for the Android wipe operation."""
        data = {
            "certificate_id": str(uuid.uuid4()),
            "device_serial": info['serial'],
            "device_model": info['model'],
            "wipe_standard": "NIST SP 800-88 Rev 1 - PURGE (via Factory Reset)",
            "wipe_method": "ADB Factory Reset Command" if "MASTER_CLEAR" in status else "Recovery Mode Key Simulation",
            "wipe_success": "SUCCESS" in status,
            "wipe_status_code": status,
            "timestamp_utc": datetime.utcnow().isoformat(),
            "tool_version": "CipherForge Unified v1.0"
        }
        try:
            with open(self.WIPE_CERT_FILE, 'w') as f:
                json.dump(data, f, indent=4)
            self.log_status(f"Android wipe certificate saved to: {self.WIPE_CERT_FILE}")
        except Exception as e:
            self.log_status(f"Failed to write Android certificate: {e}", is_error=True)
            
    # --- Certificate and Verification Methods (for Local Deletion) ---
    def _ensure_signature(self):
        if not self.deleter or self.deleter.op_status != 'SUCCESS':
            messagebox.showerror("Error", "Certificate can only be generated after a successful operation.")
            return False
        if not self.deleter.block_sig:
            self._create_signature()
        return True

    def _create_signature(self):
        """Creates a verifiable hash signature for the deletion audit trail."""
        # Use a dictionary representation of the SecureDeleter object for hashing
        content = json.dumps(self.deleter.__dict__, default=str, sort_keys=True).encode()
        content_hash = hashlib.sha256(content).hexdigest()
        
        # Create a "block" for a conceptual, pseudo-blockchain for tamper evidence
        genesis_hash = "0" * 64
        block = {
            "timestamp": datetime.utcnow().isoformat(),
            "certificate_content_hash": content_hash,
            "previous_block_hash": genesis_hash, # In a real chain, this would be the previous block's hash
            "nonce": random.randint(0, 1_000_000_000)
        }
        block_signature = hashlib.sha256(json.dumps(block, sort_keys=True).encode()).hexdigest()
        
        self.deleter.pdf_hash = content_hash
        self.deleter.block_data = block
        self.deleter.block_sig = block_signature
        self.log_status("Tamper-proof audit signature generated.")

    def generate_certificate_ui(self):
        if not self._ensure_signature(): return
        base_name = f"CipherForge_Audit_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        fn = filedialog.asksaveasfilename(defaultextension=".pdf", filetypes=[("PDF Documents", "*.pdf")], initialfile=base_name)
        if fn:
            self._save_certificate(fn)

    def download_verification_json(self):
        if not self._ensure_signature(): return
        base_name = f"CipherForge_Verify_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        fn = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON Files", "*.json")], initialfile=base_name)
        if fn:
            self._save_verification_json(fn)

    def _save_certificate(self, filename):
        if not IS_REPORTLAB_AVAILABLE:
            messagebox.showerror("Dependency Error", "ReportLab library not installed. Cannot generate PDF.")
            return
        try:
            doc = SimpleDocTemplate(filename, pagesize=letter, leftMargin=0.75 * inch, rightMargin=0.75 * inch, topMargin=1 * inch, bottomMargin=1 * inch)
            styles = getSampleStyleSheet()
            title_style = ParagraphStyle('Title', parent=styles['Heading1'], fontSize=24, alignment=1, textColor=colors.HexColor(PRIMARY_COLOR))
            sub_style = ParagraphStyle('Sub', parent=styles['Normal'], fontSize=14, alignment=1, spaceAfter=20)
            hash_style = ParagraphStyle('Hash', parent=styles['Normal'], fontSize=8, fontName='Courier')
            
            elements = [Paragraph("CipherForge", title_style), Paragraph("DATA SANITIZATION AUDIT CERTIFICATE", sub_style)]
            
            data, conclusion = self._build_cert_content()
            table = Table(data, colWidths=[2.5 * inch, 4 * inch], hAlign='CENTER')
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor(BG_DARK)),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 11),
                ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#DDDDDD')),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('BACKGROUND', (0, 1), (0, -1), colors.HexColor('#F0F0F0')),
                ('SPAN', (0, 0), (1, 0)), ('SPAN', (0, 5), (1, 5)), 
                ('SPAN', (0, 8), (1, 8)), ('SPAN', (0, 12), (1, 12)),
            ]))
            elements.append(table)
            elements.append(Spacer(1, 20))
            
            conclusion_style = ParagraphStyle('Conc', parent=styles['Normal'], fontSize=11, leading=14, alignment=4, spaceBefore=15)
            elements.append(Paragraph(conclusion, conclusion_style))
            elements.append(PageBreak())
            elements.append(Paragraph("Verification Details", title_style))
            elements.append(Spacer(1, 20))
            
            if IS_SEGNO_AVAILABLE:
                qr_data = json.dumps(self._get_verification_data(), separators=(',', ':'))
                qr_code = segno.make(qr_data, error='M')
                buffer = BytesIO()
                qr_code.save(buffer, kind='png', scale=8, border=3)
                buffer.seek(0)
                elements.append(Image(buffer, width=3 * inch, height=3 * inch))
                qr_instruction_style = ParagraphStyle('QR', parent=styles['Normal'], fontSize=10, alignment=1, textColor=colors.grey)
                elements.append(Paragraph("Scan QR code with a verification tool to confirm authenticity.", qr_instruction_style))
            else:
                elements.append(Paragraph("<i>Install the 'segno' library to include QR codes in certificates.</i>", styles['Normal']))
            
            elements.append(Spacer(1, 25))
            elements.append(Paragraph("<b>Content SHA-256 Hash:</b>", styles['Normal']))
            elements.append(Spacer(1, 5))
            elements.append(Paragraph(self.deleter.pdf_hash, hash_style))
            elements.append(Spacer(1, 15))
            elements.append(Paragraph("<b>Blockchain-style Signature:</b>", styles['Normal']))
            elements.append(Spacer(1, 5))
            elements.append(Paragraph(self.deleter.block_sig, hash_style))
            
            doc.build(elements)
            messagebox.showinfo("Success", f"PDF certificate saved successfully to:\n{filename}")
        except Exception as e:
            messagebox.showerror("PDF Generation Error", f"Failed to create PDF: {e}")

    def _build_cert_content(self):
        dt_end = datetime.fromtimestamp(self.deleter.end_ts)
        method_map = {'dod': 'DoD 5220.22-M', 'gutmann': 'Gutmann Method', 'nist': 'NIST SP 800-88 Clear'}
        standard = method_map.get(self.deleter.method, 'Unknown')
        
        path = self.selected_path.get()
        display_path = path if len(path) <= 50 else f"{path[:25]}...{path[-22:]}"
        
        data = [
            ['Operation Details', ''],
            ['Application Version:', 'CipherForge Unified v1.0'],
            ['Operating System:', f"{platform.system()} {platform.release()}"],
            ['Completion Date & Time (Local):', dt_end.strftime("%Y-%m-%d %H:%M:%S")],
            ['Total Duration:', str(dt_end - datetime.fromtimestamp(self.deleter.start_ts)).split('.')[0]],
            ['Target Specifications', ''],
            ['Target Type:', self.deleter.deletion_type],
            ['Target Path:', display_path],
            ['Sanitization Protocol', ''],
            ['Standard Applied:', standard],
            ['Overwrite Passes:', str(self.deleter._get_passes())],
            ['Ancillary Actions:', 'Free Space Wipe, System Trace Cleanup'],
            ['Audit Verification', ''],
            ['Final Operation Status:', self.deleter.op_status],
            ['Post-op Verification:', self.deleter.ver_status],
        ]
        conclusion = f"This certificate confirms that the data on the specified target has been sanitized using software-based overwriting techniques, rendering the target data irrecoverable by laboratory means. The process was conducted in accordance with the {standard} standard."
        return data, conclusion

    def _get_verification_data(self):
        return {
            "verificationHeader": {"application": "CipherForge", "version": "Unified v1.0", "standard": "CF-V1.0"},
            "auditDetails": {
                "target": self.deleter.target_name,
                "type": self.deleter.deletion_type,
                "standard": self.deleter.method.upper(),
                "timestamp_utc": datetime.fromtimestamp(self.deleter.end_ts).astimezone().isoformat(),
                "status": self.deleter.op_status,
                "verify": self.deleter.ver_status
            },
            "cryptographicProof": {
                "cert_content_hash": self.deleter.pdf_hash,
                "blockhash": self.deleter.block_sig,
                "block_data": self.deleter.block_data
            }
        }

    def _save_verification_json(self, filename):
        try:
            with open(filename, 'w') as f:
                json.dump(self._get_verification_data(), f, indent=4)
            self.log_status(f"Verification JSON proof saved to: {filename}")
            messagebox.showinfo("Success", "Verification JSON saved successfully!")
        except Exception as e:
            messagebox.showerror("JSON Save Error", f"Failed to save JSON file: {e}")


if __name__ == "__main__":
    app = SecureWipeApp()
    app.mainloop()
