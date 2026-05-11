"""
device.py — DeviceMixin
=======================
Provides the "Device" tab for the MountainBikeApp GUI.

Features
--------
- USB serial port selector with auto-refresh
- Connect / Disconnect button
- Serial dashboard text area (live feed from Teensy status thread)
- Teensy SD file list: name, size — populated via MTB:LIST command
- Host file list: name, size, date — shows ~/Documents/MTB_DAQ/Archived_Data
- Download selected SD files, delete from SD, refresh both lists
- Progress bar + status label during transfers
- CRC32 verification of every downloaded file

MTB: protocol (device side in sd_transfer.cpp)
-----------------------------------------------
  MTB:STATUS\\n  → MTB:MODE:<m>\\nMTB:VER:<v>\\nMTB:END\\n
  MTB:LIST\\n    → MTB:FILE:<name>|<size>\\n  (×N)  MTB:END\\n
  MTB:GET:<f>\\n → MTB:SIZE:<n>\\nMTB:END\\n  (or MTB:ERR:…\\nMTB:END\\n)
                   then <n> raw bytes, then MTB:CRC32:<hex>\\nMTB:END\\n
  MTB:DEL:<f>\\n → MTB:OK\\nMTB:END\\n  or  MTB:ERR:…\\nMTB:END\\n
"""

import os
import queue
import struct
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk
import zlib

try:
    import serial
    import serial.tools.list_ports
    _SERIAL_OK = True
except ImportError:
    _SERIAL_OK = False

from constants import BG, DARK, FIELD, BTN_FG, GRID
import widgets as w


# ── helpers ───────────────────────────────────────────────────────────────────

def _fmt_size(n_bytes):
    """Human-readable file size."""
    if n_bytes < 1024:
        return f"{n_bytes} B"
    elif n_bytes < 1024 * 1024:
        return f"{n_bytes/1024:.1f} KB"
    else:
        return f"{n_bytes/1024/1024:.2f} MB"


def _fmt_date(ts):
    """Format a Unix timestamp as YYYY-MM-DD HH:MM."""
    import datetime
    return datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")


def _fmt_speed(bytes_per_sec):
    """Human-readable transfer rate."""
    if bytes_per_sec < 1024:
        return f"{bytes_per_sec:.0f} B/s"
    if bytes_per_sec < 1024 * 1024:
        return f"{bytes_per_sec/1024:.1f} KB/s"
    return f"{bytes_per_sec/1024/1024:.2f} MB/s"


class DownloadCancelled(Exception):
    """Raised inside _cmd_get when the user cancels a download."""


def _fmt_eta(seconds):
    """Human-readable ETA (m:ss or h:mm:ss)."""
    s = int(round(seconds))
    if s < 60:
        return f"{s}s"
    if s < 3600:
        return f"{s//60}m{s%60:02d}s"
    return f"{s//3600}h{(s%3600)//60:02d}m{s%60:02d}s"


# ── mixin ─────────────────────────────────────────────────────────────────────

class DeviceMixin:
    """
    Mixin for MountainBikeApp.  Requires that self._source_dir is set before
    _build_device_tab() is called (done in __init__ of MountainBikeApp).
    """

    # ── tab builder ───────────────────────────────────────────────────────────

    def _build_device_tab(self):
        """Construct all widgets inside self.device_tab."""
        tab = self.device_tab

        # ── connection bar ────────────────────────────────────────────────────
        conn_bar = tk.Frame(tab, bg=BG)
        conn_bar.pack(side=tk.TOP, fill=tk.X, padx=8, pady=(8, 4))

        tk.Label(conn_bar, text="Port:", bg=BG, fg=DARK).pack(side=tk.LEFT)

        self._dev_port_var = tk.StringVar()
        self._dev_port_combo = ttk.Combobox(
            conn_bar, textvariable=self._dev_port_var,
            state="readonly", width=22)
        self._dev_port_combo.pack(side=tk.LEFT, padx=(4, 2))

        w.make_btn(conn_bar, "⟳ Refresh Ports",
                   self._dev_refresh_ports).pack(side=tk.LEFT, padx=2)

        tk.Label(conn_bar, text="Baud:", bg=BG, fg=DARK).pack(
            side=tk.LEFT, padx=(8, 0))
        self._dev_baud_var = tk.StringVar(value="115200")
        self._dev_baud_combo = ttk.Combobox(
            conn_bar, textvariable=self._dev_baud_var,
            state="readonly", width=10,
            values=["9600", "19200", "38400", "57600", "115200",
                    "230400", "460800", "921600", "1000000", "2000000"])
        self._dev_baud_combo.pack(side=tk.LEFT, padx=(4, 2))

        self._dev_connect_btn = w.make_btn(
            conn_bar, "Connect", self._dev_toggle_connect)
        self._dev_connect_btn.pack(side=tk.LEFT, padx=6)

        self._dev_status_var = tk.StringVar(value="Not connected")
        tk.Label(conn_bar, textvariable=self._dev_status_var,
                 bg=BG, fg=DARK, anchor="w").pack(side=tk.LEFT, padx=8)

        # ── body: dashboard (left) + file panels (right) ──────────────────────
        body = tk.Frame(tab, bg=BG)
        body.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)
        body.columnconfigure(0, weight=2)
        body.columnconfigure(1, weight=3)
        body.rowconfigure(0, weight=1)

        self._build_dashboard_panel(body)
        self._build_files_panel(body)

        # ── internal state ────────────────────────────────────────────────────
        self._serial      = None
        self._serial_lock = threading.Lock()
        self._rx_queue    = queue.Queue()
        self._reader_running  = False
        self._reader_thread   = None
        self._dev_connected   = False
        self._dev_cancel_flag = False

        self._dev_refresh_ports()
        self._dev_poll_dashboard()   # start periodic dashboard drain

    # ── dashboard panel ───────────────────────────────────────────────────────

    def _build_dashboard_panel(self, parent):
        frame = tk.Frame(parent, bg=BG)
        frame.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        frame.rowconfigure(1, weight=1)
        frame.columnconfigure(0, weight=1)

        hdr = tk.Frame(frame, bg=BG)
        hdr.grid(row=0, column=0, sticky="ew")
        tk.Label(hdr, text="Serial Dashboard", bg=BG, fg=DARK,
                 font=("TkDefaultFont", 10, "bold")).pack(side=tk.LEFT)
        w.make_btn(hdr, "Clear", self._dev_clear_dashboard).pack(
            side=tk.RIGHT, padx=2)

        txt_frame = tk.Frame(frame, bg=FIELD,
                             highlightbackground=DARK, highlightthickness=1)
        txt_frame.grid(row=1, column=0, sticky="nsew", pady=4)
        txt_frame.rowconfigure(0, weight=1)
        txt_frame.columnconfigure(0, weight=1)

        self._dev_dashboard = tk.Text(
            txt_frame,
            bg=FIELD, fg=DARK, insertbackground=DARK,
            relief="flat", bd=0, wrap=tk.NONE,
            font=("TkFixedFont", 9),
            state=tk.DISABLED)
        self._dev_dashboard.grid(row=0, column=0, sticky="nsew")

        vsb = ttk.Scrollbar(txt_frame, orient=tk.VERTICAL,
                            command=self._dev_dashboard.yview)
        vsb.grid(row=0, column=1, sticky="ns")
        hsb = ttk.Scrollbar(txt_frame, orient=tk.HORIZONTAL,
                            command=self._dev_dashboard.xview)
        hsb.grid(row=1, column=0, sticky="ew")
        self._dev_dashboard.configure(yscrollcommand=vsb.set,
                                      xscrollcommand=hsb.set)

    # ── files panel ───────────────────────────────────────────────────────────

    def _build_files_panel(self, parent):
        frame = tk.Frame(parent, bg=BG)
        frame.grid(row=0, column=1, sticky="nsew")
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(1, weight=1)   # SD tree
        frame.rowconfigure(4, weight=1)   # host tree

        # ── SD files ──────────────────────────────────────────────────────────
        sd_hdr = tk.Frame(frame, bg=BG)
        sd_hdr.grid(row=0, column=0, sticky="ew")
        tk.Label(sd_hdr, text="Teensy SD Files", bg=BG, fg=DARK,
                 font=("TkDefaultFont", 10, "bold")).pack(side=tk.LEFT)
        w.make_btn(sd_hdr, "⟳ Refresh SD",
                   self._dev_refresh_sd).pack(side=tk.RIGHT, padx=2)

        sd_tree_frame = tk.Frame(frame, bg=FIELD,
                                 highlightbackground=DARK, highlightthickness=1)
        sd_tree_frame.grid(row=1, column=0, sticky="nsew", pady=(2, 2))
        sd_tree_frame.rowconfigure(0, weight=1)
        sd_tree_frame.columnconfigure(0, weight=1)

        self._dev_sd_tree = ttk.Treeview(
            sd_tree_frame,
            columns=("name", "size"),
            show="headings",
            selectmode="extended")
        self._dev_sd_tree.heading("name", text="Filename")
        self._dev_sd_tree.heading("size", text="Size")
        self._dev_sd_tree.column("name", width=220, stretch=True)
        self._dev_sd_tree.column("size", width=80, anchor="e", stretch=False)
        self._dev_sd_tree.grid(row=0, column=0, sticky="nsew")

        sd_vsb = ttk.Scrollbar(sd_tree_frame, orient=tk.VERTICAL,
                               command=self._dev_sd_tree.yview)
        sd_vsb.grid(row=0, column=1, sticky="ns")
        self._dev_sd_tree.configure(yscrollcommand=sd_vsb.set)

        # SD action buttons
        sd_btns = tk.Frame(frame, bg=BG)
        sd_btns.grid(row=2, column=0, sticky="ew", pady=(0, 6))
        w.make_btn(sd_btns, "Select All",
                   self._dev_select_all_sd).pack(side=tk.LEFT, padx=(0, 4))
        w.make_btn(sd_btns, "Clear Selection",
                   self._dev_clear_sd_selection).pack(side=tk.LEFT, padx=(0, 12))
        w.make_btn(sd_btns, "⬇ Download Selected",
                   self._dev_download_selected).pack(side=tk.LEFT, padx=(0, 4))
        self._dev_cancel_btn = w.make_btn(
            sd_btns, "✖ Cancel Download", self._dev_cancel_download)
        self._dev_cancel_btn.pack(side=tk.LEFT, padx=(0, 12))
        self._dev_cancel_btn.configure(state=tk.DISABLED)
        w.make_btn(sd_btns, "🗑 Delete Selected",
                   self._dev_delete_selected).pack(side=tk.LEFT)

        # ── Host files ────────────────────────────────────────────────────────
        host_hdr = tk.Frame(frame, bg=BG)
        host_hdr.grid(row=3, column=0, sticky="ew")
        tk.Label(host_hdr, text="Host Files", bg=BG, fg=DARK,
                 font=("TkDefaultFont", 10, "bold")).pack(side=tk.LEFT)
        self._dev_host_dir_var = tk.StringVar(value=self._source_dir)
        tk.Label(host_hdr, textvariable=self._dev_host_dir_var,
                 bg=BG, fg=GRID, font=("TkFixedFont", 8)).pack(
            side=tk.LEFT, padx=6)
        w.make_btn(host_hdr, "⟳ Refresh",
                   self._dev_refresh_host).pack(side=tk.RIGHT, padx=2)

        host_tree_frame = tk.Frame(frame, bg=FIELD,
                                   highlightbackground=DARK, highlightthickness=1)
        host_tree_frame.grid(row=4, column=0, sticky="nsew", pady=(2, 2))
        host_tree_frame.rowconfigure(0, weight=1)
        host_tree_frame.columnconfigure(0, weight=1)

        self._dev_host_tree = ttk.Treeview(
            host_tree_frame,
            columns=("name", "size", "date"),
            show="headings",
            selectmode="extended")
        self._dev_host_tree.heading("name", text="Filename")
        self._dev_host_tree.heading("size", text="Size")
        self._dev_host_tree.heading("date", text="Modified")
        self._dev_host_tree.column("name", width=200, stretch=True)
        self._dev_host_tree.column("size", width=80, anchor="e", stretch=False)
        self._dev_host_tree.column("date", width=130, anchor="center",
                                   stretch=False)
        self._dev_host_tree.grid(row=0, column=0, sticky="nsew")

        host_vsb = ttk.Scrollbar(host_tree_frame, orient=tk.VERTICAL,
                                  command=self._dev_host_tree.yview)
        host_vsb.grid(row=0, column=1, sticky="ns")
        self._dev_host_tree.configure(yscrollcommand=host_vsb.set)

        # ── Progress + transfer status ─────────────────────────────────────────
        self._dev_progress_var = tk.DoubleVar(value=0.0)
        self._dev_progress = ttk.Progressbar(
            frame, variable=self._dev_progress_var,
            maximum=100.0, mode="determinate")
        self._dev_progress.grid(row=5, column=0, sticky="ew", pady=(4, 2))

        self._dev_xfer_var = tk.StringVar(value="")
        tk.Label(frame, textvariable=self._dev_xfer_var,
                 bg=BG, fg=DARK, anchor="w",
                 font=("TkFixedFont", 9)).grid(
            row=6, column=0, sticky="ew")

        # Populate host list immediately
        self._dev_refresh_host()

    # ── port management ───────────────────────────────────────────────────────

    def _dev_refresh_ports(self):
        if not _SERIAL_OK:
            self._dev_port_combo["values"] = ["pyserial not installed"]
            return
        ports = [p.device for p in serial.tools.list_ports.comports()]
        # Prefer ports that look like Teensy (ACM / usbmodem)
        ports.sort(key=lambda p: (
            0 if ("ACM" in p or "usbmodem" in p or "COM" in p) else 1, p))
        self._dev_port_combo["values"] = ports or ["(no ports found)"]
        if ports and not self._dev_port_var.get():
            self._dev_port_var.set(ports[0])

    def _dev_toggle_connect(self):
        if self._dev_connected:
            self._dev_disconnect()
        else:
            self._dev_connect()

    def _dev_connect(self):
        if not _SERIAL_OK:
            messagebox.showerror("Error", "pyserial is not installed.\n"
                                 "Run: pip install pyserial")
            return
        port = self._dev_port_var.get()
        if not port or port.startswith("("):
            messagebox.showwarning("No Port", "Select a serial port first.")
            return
        try:
            baud = int(self._dev_baud_var.get())
        except (ValueError, AttributeError):
            baud = 115200
        try:
            self._serial = serial.Serial(port, baudrate=baud, timeout=2)
            time.sleep(0.1)
            self._serial.reset_input_buffer()
        except Exception as e:
            messagebox.showerror("Connect Failed", str(e))
            self._serial = None
            return

        self._dev_connected = True
        self._dev_connect_btn.configure(text="Disconnect")
        self._dev_baud_combo.configure(state="disabled")
        self._dev_status_var.set(f"Connected: {port} @ {baud} baud")

        # Start background reader thread
        self._reader_running = True
        self._reader_thread = threading.Thread(
            target=self._dev_reader_loop, daemon=True)
        self._reader_thread.start()

    def _dev_disconnect(self):
        self._reader_running = False
        if self._reader_thread:
            self._reader_thread.join(timeout=1.0)
            self._reader_thread = None
        if self._serial:
            try:
                self._serial.close()
            except Exception:
                pass
            self._serial = None
        self._dev_connected   = False
        self._dev_connect_btn.configure(text="Connect")
        self._dev_baud_combo.configure(state="readonly")
        self._dev_status_var.set("Not connected")

    # ── background reader ─────────────────────────────────────────────────────

    def _dev_reader_loop(self):
        """Background thread: non-blocking reads → _rx_queue."""
        buf = b""
        while self._reader_running:
            try:
                with self._serial_lock:
                    if self._serial and self._serial.in_waiting:
                        buf += self._serial.read(self._serial.in_waiting)
            except Exception:
                break
            # Slice complete lines into the queue, hold partial last line
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                self._rx_queue.put(line.decode("ascii", errors="replace") + "\n")
            time.sleep(0.02)

    def _dev_poll_dashboard(self):
        """Drain _rx_queue into the dashboard text widget; re-schedule via after()."""
        lines = []
        try:
            while True:
                lines.append(self._rx_queue.get_nowait())
        except queue.Empty:
            pass
        if lines:
            self._dev_dashboard.configure(state=tk.NORMAL)
            self._dev_dashboard.insert(tk.END, "".join(lines))
            self._dev_dashboard.see(tk.END)
            self._dev_dashboard.configure(state=tk.DISABLED)
        self.after(80, self._dev_poll_dashboard)

    def _dev_clear_dashboard(self):
        self._dev_dashboard.configure(state=tk.NORMAL)
        self._dev_dashboard.delete("1.0", tk.END)
        self._dev_dashboard.configure(state=tk.DISABLED)

    # ── SD file list ──────────────────────────────────────────────────────────

    def _dev_refresh_sd(self):
        if not self._dev_connected:
            messagebox.showwarning("Not Connected",
                                   "Connect to the Teensy first.")
            return
        threading.Thread(target=self._dev_refresh_sd_worker,
                         daemon=True).start()

    def _dev_refresh_sd_worker(self):
        try:
            files = self._cmd_list()
        except Exception as e:
            self.after(0, lambda: self._dev_set_xfer(f"LIST error: {e}"))
            return
        def _update():
            for item in self._dev_sd_tree.get_children():
                self._dev_sd_tree.delete(item)
            for name, size in sorted(files):
                self._dev_sd_tree.insert("", tk.END, values=(name, _fmt_size(size)))
            self._dev_set_xfer(f"{len(files)} file(s) on SD")
        self.after(0, _update)

    def _dev_select_all_sd(self):
        children = self._dev_sd_tree.get_children()
        if children:
            self._dev_sd_tree.selection_set(children)

    def _dev_clear_sd_selection(self):
        sel = self._dev_sd_tree.selection()
        if sel:
            self._dev_sd_tree.selection_remove(sel)

    # ── host file list ────────────────────────────────────────────────────────

    def _dev_refresh_host(self):
        for item in self._dev_host_tree.get_children():
            self._dev_host_tree.delete(item)
        src = self._source_dir
        if not os.path.isdir(src):
            return
        entries = []
        for fname in os.listdir(src):
            fpath = os.path.join(src, fname)
            if os.path.isfile(fpath):
                entries.append((fname,
                                 os.path.getsize(fpath),
                                 os.path.getmtime(fpath)))
        entries.sort(key=lambda x: x[2], reverse=True)
        for fname, fsize, fmtime in entries:
            self._dev_host_tree.insert(
                "", tk.END,
                values=(fname, _fmt_size(fsize), _fmt_date(fmtime)))

    # ── download ──────────────────────────────────────────────────────────────

    def _dev_download_selected(self):
        sel = self._dev_sd_tree.selection()
        if not sel:
            messagebox.showwarning("No Selection",
                                   "Select one or more SD files to download.")
            return
        if not self._dev_connected:
            messagebox.showwarning("Not Connected",
                                   "Connect to the Teensy first.")
            return
        names = [self._dev_sd_tree.item(iid, "values")[0] for iid in sel]
        os.makedirs(self._source_dir, exist_ok=True)
        threading.Thread(target=self._dev_download_worker,
                         args=(names,), daemon=True).start()

    def _dev_download_worker(self, names):
        self._dev_cancel_flag = False
        self.after(0, lambda: self._dev_cancel_btn.configure(state=tk.NORMAL))
        total = len(names)
        try:
            for idx, name in enumerate(names):
                self._dev_xfer_name      = name
                self._dev_xfer_index     = idx + 1
                self._dev_xfer_total_cnt = total
                self._dev_xfer_start_t   = time.monotonic()
                self._dev_xfer_last_ui_t = 0.0
                self.after(0, lambda n=name, i=idx: self._dev_set_xfer(
                    f"Downloading {n} ({i+1}/{total})…"))
                self.after(0, lambda i=idx, t=total:
                           self._dev_progress_var.set(100.0 * i / t))
                try:
                    data, crc_ok = self._cmd_get(
                        name, progress_cb=self._dev_xfer_progress)
                except DownloadCancelled:
                    # Force-disconnect: in-flight bytes from the Teensy would
                    # desync the protocol, so the cleanest recovery is to drop
                    # the link and have the user reconnect.
                    self.after(0, self._dev_disconnect)
                    self.after(0, lambda n=name: self._dev_set_xfer(
                        f"Cancelled {n} — disconnected; reconnect to continue"))
                    self.after(0, lambda: self._dev_progress_var.set(0.0))
                    return
                except Exception as e:
                    self.after(0, lambda e=e, n=name:
                               messagebox.showerror("Download Error",
                                                    f"{n}: {e}"))
                    self.after(0, lambda: self._dev_progress_var.set(0))
                    return

                dest = os.path.join(self._source_dir, name)
                with open(dest, "wb") as f:
                    f.write(data)

                if not crc_ok:
                    self.after(0, lambda n=name:
                               messagebox.showwarning("CRC Mismatch",
                                                      f"{n} downloaded but CRC32 "
                                                      f"did not match. "
                                                      f"File may be corrupt."))

            self.after(0, lambda: self._dev_progress_var.set(100.0))
            self.after(0, lambda: self._dev_set_xfer(
                f"Downloaded {total} file(s) → {self._source_dir}"))
            self.after(0, self._dev_refresh_host)
            self.after(500, lambda: self._dev_progress_var.set(0.0))
        finally:
            self.after(0, lambda:
                       self._dev_cancel_btn.configure(state=tk.DISABLED))

    def _dev_cancel_download(self):
        """Signal the download worker to abort. Drops the serial connection
        because the Teensy will keep streaming the rest of the file and we
        can't cleanly resync the protocol mid-transfer."""
        self._dev_cancel_flag = True
        # Closing the serial port from this thread also unblocks any
        # pyserial.read() that's currently sitting in a kernel wait.
        try:
            if self._serial:
                self._serial.cancel_read()
        except Exception:
            pass

    def _dev_xfer_progress(self, received, total):
        """Called from download thread; schedule progress + speed/ETA update.
        Throttled to ~10 Hz so we don't drown the tkinter event queue and
        starve the worker thread (each after() call from a non-main thread
        contends for Tk's lock on macOS)."""
        now = time.monotonic()
        last = getattr(self, "_dev_xfer_last_ui_t", 0.0)
        is_final = (received >= total)
        if not is_final and (now - last) < 0.1:
            return
        self._dev_xfer_last_ui_t = now

        pct = 100.0 * received / total if total > 0 else 0
        self.after(0, lambda: self._dev_progress_var.set(pct))

        elapsed = now - getattr(self, "_dev_xfer_start_t", now)
        if elapsed < 0.2 or received <= 0:
            return
        speed = received / elapsed                       # bytes/sec
        remaining = max(total - received, 0)
        eta_s = remaining / speed if speed > 0 else 0
        msg = (f"Downloading {self._dev_xfer_name} "
               f"({self._dev_xfer_index}/{self._dev_xfer_total_cnt})  "
               f"{_fmt_size(received)}/{_fmt_size(total)}  "
               f"@ {_fmt_speed(speed)}  ETA {_fmt_eta(eta_s)}")
        self.after(0, lambda m=msg: self._dev_set_xfer(m))

    # ── delete ────────────────────────────────────────────────────────────────

    def _dev_delete_selected(self):
        sel = self._dev_sd_tree.selection()
        if not sel:
            messagebox.showwarning("No Selection",
                                   "Select one or more SD files to delete.")
            return
        if not self._dev_connected:
            messagebox.showwarning("Not Connected",
                                   "Connect to the Teensy first.")
            return
        names = [self._dev_sd_tree.item(iid, "values")[0] for iid in sel]
        if not messagebox.askyesno(
                "Confirm Delete",
                f"Delete {len(names)} file(s) from the Teensy SD card?\n\n"
                + "\n".join(names)):
            return
        threading.Thread(target=self._dev_delete_worker,
                         args=(names,), daemon=True).start()

    def _dev_delete_worker(self, names):
        errors = []
        for name in names:
            self.after(0, lambda n=name:
                       self._dev_set_xfer(f"Deleting {n}…"))
            try:
                self._cmd_del(name)
            except Exception as e:
                errors.append(f"{name}: {e}")
        if errors:
            self.after(0, lambda:
                       messagebox.showerror("Delete Error", "\n".join(errors)))
        self.after(0, self._dev_refresh_sd)
        self.after(0, lambda:
                   self._dev_set_xfer(f"Deleted {len(names)-len(errors)} file(s)"))

    # ── status label helper ────────────────────────────────────────────────────

    def _dev_set_xfer(self, msg):
        self._dev_xfer_var.set(msg)

    # ── protocol commands ─────────────────────────────────────────────────────
    #
    # All _cmd_* methods acquire _serial_lock so they get exclusive port access
    # while the reader thread backs off. They are designed to be called from
    # worker threads (not the tkinter main thread).

    def _cmd_readline(self, timeout=5.0):
        """Read one ASCII line from the serial port (lock must be held)."""
        buf = b""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._serial.in_waiting:
                ch = self._serial.read(1)
                buf += ch
                if ch == b"\n":
                    return buf.decode("ascii", errors="replace").strip()
            else:
                time.sleep(0.005)
        raise TimeoutError("Timeout waiting for response from Teensy")

    def _cmd_list(self):
        """Send MTB:LIST; return list of (name, size_bytes) tuples."""
        with self._serial_lock:
            self._serial.reset_input_buffer()
            self._serial.write(b"MTB:LIST\n")
            self._serial.flush()
            files = []
            while True:
                line = self._cmd_readline()
                if line == "MTB:END":
                    break
                if line.startswith("MTB:ERR:"):
                    raise RuntimeError(line[8:])
                if line.startswith("MTB:FILE:"):
                    payload = line[9:]
                    if "|" in payload:
                        name, size_str = payload.rsplit("|", 1)
                        try:
                            files.append((name, int(size_str)))
                        except ValueError:
                            pass
                # Non-MTB lines (dashboard output) are silently skipped
        return files

    def _cmd_get(self, filename, progress_cb=None):
        """
        Send MTB:GET:<filename>; download binary data; verify CRC32.
        Returns (bytes_data, crc_ok).
        """
        with self._serial_lock:
            self._serial.reset_input_buffer()
            self._serial.write(f"MTB:GET:{filename}\n".encode())
            self._serial.flush()

            # Read until MTB:SIZE or MTB:ERR
            file_size = None
            while True:
                line = self._cmd_readline()
                if line.startswith("MTB:SIZE:"):
                    file_size = int(line[9:])
                    break
                if line.startswith("MTB:ERR:"):
                    raise RuntimeError(line[8:])
                # Skip dashboard lines

            # Read exactly file_size raw bytes
            data = bytearray()
            deadline = time.monotonic() + max(file_size / 1000 + 10, 30)
            while len(data) < file_size:
                if self._dev_cancel_flag:
                    raise DownloadCancelled()
                if time.monotonic() > deadline:
                    raise TimeoutError(
                        f"Timeout: received {len(data)}/{file_size} bytes")
                chunk = self._serial.read(
                    min(4096, file_size - len(data)))
                if chunk:
                    data.extend(chunk)
                    if progress_cb:
                        progress_cb(len(data), file_size)

            # Read CRC32 and END lines
            expected_crc = None
            while True:
                line = self._cmd_readline()
                if line.startswith("MTB:CRC32:"):
                    try:
                        expected_crc = int(line[10:], 16)
                    except ValueError:
                        pass
                elif line == "MTB:END":
                    break

        # Verify integrity (zlib.crc32 uses same polynomial as Teensy crc32_update)
        actual_crc = zlib.crc32(bytes(data)) & 0xFFFFFFFF
        crc_ok = (expected_crc is not None) and (actual_crc == expected_crc)
        return bytes(data), crc_ok

    def _cmd_del(self, filename):
        """Send MTB:DEL:<filename>; raise RuntimeError on failure."""
        with self._serial_lock:
            self._serial.reset_input_buffer()
            self._serial.write(f"MTB:DEL:{filename}\n".encode())
            self._serial.flush()
            while True:
                line = self._cmd_readline()
                if line == "MTB:OK":
                    # consume END
                    while self._cmd_readline() != "MTB:END":
                        pass
                    return
                if line.startswith("MTB:ERR:"):
                    raise RuntimeError(line[8:])
                if line == "MTB:END":
                    return
