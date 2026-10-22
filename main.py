#!/usr/bin/env python3
"""PyQemu Script — themed Tkinter QEMU launcher.

No third-party Python packages are required. On Arch Linux install Tk with:
    sudo pacman -S tk
"""
from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import threading
import queue
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

APP_DIR = Path(__file__).resolve().parent
MACHINES_DIR = APP_DIR / "machines"
CONFIG_DIR = MACHINES_DIR / "configs"
HISTORY_FILE = MACHINES_DIR / "history.txt"
CONFIG_DIR.mkdir(parents=True, exist_ok=True)

BG = "#171b24"
PANEL = "#222833"
PANEL_ALT = "#29364a"
TEXT = "#edf2fa"
MUTED = "#aab5c8"
ACCENT = "#426fe0"
GREEN = "#79d9a0"
BORDER = "#3b4351"


def safe_name(name: str) -> str:
    name = "".join(c if c.isalnum() or c in "-_" else "_" for c in name.strip())
    return name[:64] or "NewVM"


class PyQemuApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("PyQemu Script")
        self.root.geometry("1120x760")
        self.root.minsize(900, 620)
        self.root.configure(bg=BG)
        self.process: subprocess.Popen | None = None
        self.log_queue: queue.Queue[str] = queue.Queue()
        self.selected_config: Path | None = None
        self.disk_paths: list[str] = []
        self.iso_path = tk.StringVar()
        self.vm_name = tk.StringVar(value="NwOS")
        self.arch = tk.StringVar(value="x86_64")
        self.ram = tk.StringVar(value="256")
        self.ram_unit = tk.StringVar(value="MB")
        self.cpus = tk.StringVar(value="1")
        self.boot = tk.StringVar(value="Disk first")
        self.disk_bus = tk.StringVar(value="IDE")
        self.network = tk.BooleanVar(value=True)
        self.kvm = tk.BooleanVar(value=True)
        self.usb = tk.BooleanVar(value=True)
        self.vga = tk.StringVar(value="Standard VGA")
        self.vram = tk.StringVar(value="16")
        self.vram_unit = tk.StringVar(value="MB")
        self.extra_args = tk.StringVar()
        self.status = tk.StringVar(value="Ready")
        self._setup_style()
        self._build_ui()
        self.refresh_vm_list()
        self.root.after(100, self._drain_log_queue)

    def _setup_style(self):
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(".", font=("Sans", 10))
        style.configure("TFrame", background=BG)
        style.configure("Panel.TFrame", background=PANEL)
        style.configure("TLabel", background=BG, foreground=TEXT)
        style.configure("Muted.TLabel", background=BG, foreground=MUTED)
        style.configure("Panel.TLabel", background=PANEL, foreground=TEXT)
        style.configure("Header.TLabel", background=BG, foreground=TEXT, font=("Sans", 17, "bold"))
        style.configure("Subhead.TLabel", background=PANEL, foreground=TEXT, font=("Sans", 11, "bold"))
        style.configure("TButton", padding=(10, 7))
        style.configure("Accent.TButton", background=ACCENT, foreground="white", padding=(12, 9), font=("Sans", 10, "bold"))
        style.map("Accent.TButton", background=[("active", "#5683f2"), ("disabled", "#414a5a")])
        style.configure("TEntry", fieldbackground="#11151c", foreground=TEXT, insertcolor=TEXT)
        style.configure("TCombobox", fieldbackground="#11151c", foreground=TEXT, arrowcolor=TEXT)
        style.configure("TCheckbutton", background=PANEL, foreground=TEXT)
        style.map("TCheckbutton", background=[("active", PANEL)])
        style.configure("TLabelframe", background=PANEL, foreground=TEXT, bordercolor=BORDER)
        style.configure("TLabelframe.Label", background=PANEL, foreground=MUTED)
        style.configure("Treeview", background="#11151c", fieldbackground="#11151c", foreground=TEXT, rowheight=30, bordercolor=BORDER)
        style.configure("Treeview.Heading", background=PANEL_ALT, foreground=TEXT, padding=7)
        style.map("Treeview", background=[("selected", ACCENT)], foreground=[("selected", "white")])
        style.configure("TNotebook", background=PANEL, borderwidth=0)
        style.configure("TNotebook.Tab", padding=(12, 8), background=PANEL_ALT, foreground=TEXT)
        style.map("TNotebook.Tab", background=[("selected", ACCENT)], foreground=[("selected", "white")])
        style.configure("Horizontal.TProgressbar", troughcolor="#11151c", background=ACCENT)

    def _build_ui(self):
        header = ttk.Frame(self.root, padding=(18, 14, 18, 10))
        header.pack(fill="x")
        ttk.Label(header, text="PyQemu Script", style="Header.TLabel").pack(side="left")
        ttk.Label(header, text="Virtual Machine Manager", style="Muted.TLabel").pack(side="left", padx=14, pady=(7, 0))
        ttk.Label(header, textvariable=self.status, style="Muted.TLabel").pack(side="right", pady=(7, 0))

        body = ttk.Panedwindow(self.root, orient="horizontal")
        body.pack(fill="both", expand=True, padx=14, pady=(0, 12))
        sidebar = ttk.Frame(body, style="Panel.TFrame", padding=12, width=260)
        main = ttk.Frame(body, style="Panel.TFrame", padding=14)
        body.add(sidebar, weight=1)
        body.add(main, weight=4)

        ttk.Label(sidebar, text="ВИРТУАЛЬНЫЕ МАШИНЫ", style="Subhead.TLabel").pack(anchor="w", pady=(2, 12))
        self.vm_tree = ttk.Treeview(sidebar, columns=("arch", "ram"), show="tree headings", selectmode="browse")
        self.vm_tree.heading("#0", text="Машина")
        self.vm_tree.heading("arch", text="Арх.")
        self.vm_tree.heading("ram", text="RAM")
        self.vm_tree.column("#0", width=105, minwidth=80)
        self.vm_tree.column("arch", width=60, anchor="center")
        self.vm_tree.column("ram", width=70, anchor="e")
        self.vm_tree.pack(fill="both", expand=True)
        self.vm_tree.bind("<<TreeviewSelect>>", self._on_vm_select)
        left_buttons = ttk.Frame(sidebar, style="Panel.TFrame")
        left_buttons.pack(fill="x", pady=(10, 0))
        ttk.Button(left_buttons, text="+ Новая VM", command=self.new_vm).pack(fill="x", pady=3)
        ttk.Button(left_buttons, text="Обновить список", command=self.refresh_vm_list).pack(fill="x", pady=3)
        ttk.Button(left_buttons, text="Удалить конфиг", command=self.delete_config).pack(fill="x", pady=3)
        ttk.Label(sidebar, text="Конфиги хранятся в machines/configs", style="Muted.TLabel", wraplength=220).pack(anchor="w", pady=(14, 0))

        top = ttk.Frame(main, style="Panel.TFrame")
        top.pack(fill="x", pady=(0, 10))
        ttk.Label(top, textvariable=self.vm_name, style="Subhead.TLabel").pack(side="left")
        self.start_btn = ttk.Button(top, text="▶ Запустить", style="Accent.TButton", command=self.start_vm)
        self.start_btn.pack(side="right", padx=(8, 0))
        ttk.Button(top, text="Сохранить конфиг", command=self.save_config).pack(side="right", padx=4)
        ttk.Button(top, text="Экспорт .sh", command=self.export_script).pack(side="right", padx=4)

        self.tabs = ttk.Notebook(main)
        self.tabs.pack(fill="both", expand=True)
        basic = ttk.Frame(self.tabs, style="Panel.TFrame", padding=14)
        hardware = ttk.Frame(self.tabs, style="Panel.TFrame", padding=14)
        media = ttk.Frame(self.tabs, style="Panel.TFrame", padding=14)
        advanced = ttk.Frame(self.tabs, style="Panel.TFrame", padding=14)
        self.tabs.add(basic, text="Основное")
        self.tabs.add(hardware, text="CPU и память")
        self.tabs.add(media, text="Диски и ISO")
        self.tabs.add(advanced, text="Экран и другое")
        self._build_basic_tab(basic)
        self._build_hardware_tab(hardware)
        self._build_media_tab(media)
        self._build_advanced_tab(advanced)

        log_frame = ttk.Frame(main, style="Panel.TFrame")
        log_frame.pack(fill="both", expand=False, pady=(12, 0))
        log_head = ttk.Frame(log_frame, style="Panel.TFrame")
        log_head.pack(fill="x", pady=(0, 6))
        ttk.Label(log_head, text="ЖУРНАЛ QEMU", style="Subhead.TLabel").pack(side="left")
        ttk.Button(log_head, text="Очистить", command=self.clear_log).pack(side="right")
        self.log_text = tk.Text(log_frame, height=7, bg="#11151c", fg="#c7d0df", insertbackground=TEXT,
                                relief="flat", wrap="word", font=("Monospace", 9), padx=9, pady=8)
        self.log_text.pack(fill="both", expand=True)
        self.log_text.insert("end", "Добро пожаловать в PyQemu Script. Настройте VM и нажмите «Запустить».\n")
        self.log_text.configure(state="disabled")

    def _label_entry(self, parent, label, var, row, width=30):
        ttk.Label(parent, text=label, style="Panel.TLabel").grid(row=row, column=0, sticky="w", padx=(0, 12), pady=7)
        entry = ttk.Entry(parent, textvariable=var, width=width)
        entry.grid(row=row, column=1, sticky="ew", pady=7)
        return entry

    def _build_basic_tab(self, tab):
        tab.columnconfigure(1, weight=1)
        self._label_entry(tab, "Имя виртуальной машины", self.vm_name, 0)
        ttk.Label(tab, text="Архитектура", style="Panel.TLabel").grid(row=1, column=0, sticky="w", padx=(0, 12), pady=7)
        ttk.Combobox(tab, textvariable=self.arch, values=("x86_64", "i386"), state="readonly").grid(row=1, column=1, sticky="ew", pady=7)
        ttk.Label(tab, text="Порядок загрузки", style="Panel.TLabel").grid(row=2, column=0, sticky="w", padx=(0, 12), pady=7)
        ttk.Combobox(tab, textvariable=self.boot, values=("Disk first", "CD first", "CD then disk"), state="readonly").grid(row=2, column=1, sticky="ew", pady=7)
        options = ttk.LabelFrame(tab, text="Параметры запуска", padding=12)
        options.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(18, 8))
        ttk.Checkbutton(options, text="Использовать KVM (ускорение)", variable=self.kvm).pack(anchor="w", pady=4)
        ttk.Checkbutton(options, text="Сетевой адаптер user-mode (NAT)", variable=self.network).pack(anchor="w", pady=4)
        ttk.Checkbutton(options, text="USB-контроллер и USB-планшет", variable=self.usb).pack(anchor="w", pady=4)
        ttk.Label(tab, text="Подсказка: KVM требует поддержки виртуализации хостом.", style="Muted.TLabel", wraplength=600).grid(row=4, column=0, columnspan=2, sticky="w", pady=(8, 0))

    def _build_hardware_tab(self, tab):
        tab.columnconfigure(1, weight=1)
        self._label_entry(tab, "Оперативная память", self.ram, 0)
        ttk.Combobox(tab, textvariable=self.ram_unit, values=("B", "KB", "MB", "GB"), state="readonly", width=8).grid(row=0, column=2, padx=(8, 0))
        self._label_entry(tab, "Количество CPU", self.cpus, 1)
        info = ttk.LabelFrame(tab, text="Память", padding=12)
        info.grid(row=2, column=0, columnspan=3, sticky="ew", pady=18)
        ttk.Label(info, text="RAM передаётся QEMU в выбранных единицах. Фактический максимум зависит от хоста и QEMU.", style="Panel.TLabel", wraplength=620).pack(anchor="w")

    def _build_media_tab(self, tab):
        tab.columnconfigure(0, weight=1)
        iso_row = ttk.Frame(tab, style="Panel.TFrame")
        iso_row.grid(row=0, column=0, sticky="ew")
        iso_row.columnconfigure(0, weight=1)
        ttk.Label(tab, text="Установочный ISO (необязательно)", style="Panel.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 6))
        ttk.Entry(tab, textvariable=self.iso_path).grid(row=1, column=0, sticky="ew", padx=(0, 8))
        ttk.Button(tab, text="Обзор…", command=self.browse_iso).grid(row=1, column=1)
        ttk.Label(tab, text="Виртуальные диски", style="Panel.TLabel").grid(row=2, column=0, sticky="w", pady=(18, 6))
        self.disk_list = tk.Listbox(tab, height=7, bg="#11151c", fg=TEXT, selectbackground=ACCENT,
                                    relief="flat", highlightthickness=1, highlightbackground=BORDER)
        self.disk_list.grid(row=3, column=0, columnspan=2, sticky="nsew")
        tab.rowconfigure(3, weight=1)
        buttons = ttk.Frame(tab, style="Panel.TFrame")
        buttons.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        ttk.Button(buttons, text="Подключить диск…", command=self.add_disk).pack(side="left", padx=(0, 6))
        ttk.Button(buttons, text="Создать диск…", command=self.create_disk).pack(side="left", padx=6)
        ttk.Button(buttons, text="Убрать выбранный", command=self.remove_disk).pack(side="left", padx=6)
        ttk.Label(tab, text="Интерфейс диска", style="Panel.TLabel").grid(row=5, column=0, sticky="w", pady=(14, 4))
        ttk.Combobox(tab, textvariable=self.disk_bus, values=("IDE", "SATA", "SCSI", "VirtIO"), state="readonly").grid(row=6, column=0, sticky="w")

    def _build_advanced_tab(self, tab):
        tab.columnconfigure(1, weight=1)
        ttk.Label(tab, text="Видеоустройство", style="Panel.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 12), pady=7)
        ttk.Combobox(tab, textvariable=self.vga, values=("Standard VGA", "VirtIO GPU", "QXL", "Без видео"), state="readonly").grid(row=0, column=1, sticky="ew", pady=7)
        ttk.Label(tab, text="Видеопамять", style="Panel.TLabel").grid(row=1, column=0, sticky="w", padx=(0, 12), pady=7)
        ttk.Entry(tab, textvariable=self.vram, width=14).grid(row=1, column=1, sticky="w", pady=7)
        ttk.Combobox(tab, textvariable=self.vram_unit, values=("B", "KB", "MB", "GB"), state="readonly", width=8).grid(row=1, column=2, sticky="w", padx=8)
        ttk.Label(tab, text="Дополнительные аргументы QEMU", style="Panel.TLabel").grid(row=2, column=0, columnspan=3, sticky="w", pady=(16, 5))
        self.extra_text = tk.Text(tab, height=4, bg="#11151c", fg=TEXT, insertbackground=TEXT, relief="flat", wrap="word")
        self.extra_text.grid(row=3, column=0, columnspan=3, sticky="ew")
        ttk.Label(tab, text="Вводите аргументы как в командной строке, например: -no-reboot", style="Muted.TLabel").grid(row=4, column=0, columnspan=3, sticky="w", pady=8)

    def log(self, text):
        self.log_queue.put(str(text))

    def _drain_log_queue(self):
        try:
            while True:
                line = self.log_queue.get_nowait()
                self.log_text.configure(state="normal")
                self.log_text.insert("end", line.rstrip() + "\n")
                self.log_text.see("end")
                self.log_text.configure(state="disabled")
        except queue.Empty:
            pass
        self.root.after(100, self._drain_log_queue)

    def clear_log(self):
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

    def browse_iso(self):
        path = filedialog.askopenfilename(title="Выберите ISO", filetypes=[("ISO images", "*.iso"), ("Все файлы", "*")])
        if path:
            self.iso_path.set(path)

    def add_disk(self):
        paths = filedialog.askopenfilenames(title="Выберите виртуальный диск", filetypes=[("Disk images", "*.qcow2 *.img *.raw *.vmdk"), ("Все файлы", "*")])
        for path in paths:
            if path not in self.disk_paths:
                self.disk_paths.append(path)
                self.disk_list.insert("end", path)

    def remove_disk(self):
        selection = self.disk_list.curselection()
        if selection:
            index = selection[0]
            self.disk_list.delete(index)
            del self.disk_paths[index]

    def create_disk(self):
        qemu_img = shutil.which("qemu-img")
        if not qemu_img:
            messagebox.showerror("qemu-img не найден", "Установите QEMU (например, sudo pacman -S qemu-full) и проверьте PATH.")
            return
        path = filedialog.asksaveasfilename(title="Создать виртуальный диск", initialfile="new_disk.qcow2",
                                            defaultextension=".qcow2",
                                            filetypes=[("QCOW2", "*.qcow2"), ("Raw image", "*.raw")])
        if not path:
            return
        win = tk.Toplevel(self.root)
        win.title("Создание диска")
        win.configure(bg=BG)
        win.transient(self.root)
        frm = ttk.Frame(win, padding=16)
        frm.pack(fill="both", expand=True)
        ttk.Label(frm, text="Размер диска (например, 2G или 512M)").pack(anchor="w")
        size = tk.StringVar(value="2G")
        ttk.Entry(frm, textvariable=size, width=20).pack(anchor="w", pady=8)
        def do_create():
            value = size.get().strip()
            if not value or any(c in value for c in " ;&|`$\\"):
                messagebox.showerror("Некорректный размер", "Укажите размер, например 2G или 512M.", parent=win)
                return
            fmt = "qcow2" if path.endswith(".qcow2") else "raw"
            try:
                result = subprocess.run([qemu_img, "create", "-f", fmt, path, value], capture_output=True, text=True, check=True)
                self.log(result.stdout or f"Создан диск: {path}")
                if path not in self.disk_paths:
                    self.disk_paths.append(path)
                    self.disk_list.insert("end", path)
                win.destroy()
            except subprocess.CalledProcessError as exc:
                messagebox.showerror("Ошибка qemu-img", exc.stderr or str(exc), parent=win)
        ttk.Button(frm, text="Создать", style="Accent.TButton", command=do_create).pack(anchor="e")
        win.grab_set()

    def _ram_string(self):
        value = float(self.ram.get())
        if value <= 0:
            raise ValueError("RAM должна быть больше нуля.")
        unit = self.ram_unit.get()
        if unit == "B":
            return f"{int(value)}B"
        if unit == "KB":
            return f"{value:g}K"
        if unit == "GB":
            return f"{value:g}G"
        return f"{value:g}M"

    def _detect_disk_format(self, disk: str) -> str:
        """Return the actual image format; never pass format=auto to QEMU."""
        path = Path(disk)
        suffix = path.suffix.lower()
        known_formats = {
            ".qcow2": "qcow2",
            ".qcow": "qcow",
            ".raw": "raw",
            ".img": "raw",
            ".vmdk": "vmdk",
            ".vdi": "vdi",
            ".vpc": "vpc",
            ".vhdx": "vhdx",
        }
        # Prefer inspecting the actual image: extension and content may differ.
        qemu_img = shutil.which("qemu-img")
        if qemu_img:
            try:
                info = subprocess.run(
                    [qemu_img, "info", "--output=json", str(path)],
                    capture_output=True, text=True, check=True,
                )
                fmt = json.loads(info.stdout).get("format")
                if fmt:
                    return str(fmt)
            except (subprocess.CalledProcessError, json.JSONDecodeError, OSError):
                pass
        # Fallback for common extensions if qemu-img isn't installed.
        if suffix in known_formats:
            return known_formats[suffix]
        raise ValueError(
            f"Не удалось определить формат диска: {disk}\n"
            "Переименуйте файл с расширением .qcow2/.img/.raw или установите qemu-img."
        )

    @staticmethod
    def _qemu_drive_path(path: str) -> str:
        # QEMU's -drive uses commas as option separators; double commas in paths.
        return path.replace(",", ",,")

    def build_command(self):
        name = safe_name(self.vm_name.get())
        binary = "qemu-system-" + self.arch.get()
        if not shutil.which(binary):
            raise ValueError(f"Не найден {binary}. Установите пакет QEMU.")
        try:
            cpus = int(self.cpus.get())
            if cpus < 1:
                raise ValueError
        except ValueError:
            raise ValueError("Количество CPU должно быть целым числом больше нуля.")
        args = [binary, "-name", name, "-m", self._ram_string(), "-smp", str(cpus)]
        if self.kvm.get() and os.path.exists("/dev/kvm"):
            args += ["-enable-kvm"]
        elif self.kvm.get():
            self.log("Предупреждение: /dev/kvm недоступен; запуск без KVM.")
        if self.iso_path.get().strip():
            iso = str(Path(self.iso_path.get()).expanduser())
            if not Path(iso).is_file():
                raise ValueError(f"ISO не найден: {iso}")
            args += ["-cdrom", iso]
        bus = self.disk_bus.get().lower()
        if bus == "sata" and self.disk_paths:
            args += ["-device", "ich9-ahci,id=sata"]
        for index, disk in enumerate(self.disk_paths):
            if not Path(disk).is_file():
                raise ValueError(f"Диск не найден: {disk}")
            image_format = self._detect_disk_format(disk)
            qemu_path = self._qemu_drive_path(disk)
            drive_id = f"disk{index}"
            if bus == "virtio":
                args += ["-drive", f"file={qemu_path},format={image_format},if=virtio"]
            elif bus == "ide":
                args += ["-drive", f"file={qemu_path},format={image_format},if=ide"]
            elif bus == "sata":
                args += ["-drive", f"file={qemu_path},format={image_format},if=none,id={drive_id}",
                         "-device", f"ide-hd,drive={drive_id},bus=sata.{index}"]
            else:
                args += ["-drive", f"file={qemu_path},format={image_format},if=none,id={drive_id}",
                         "-device", f"scsi-hd,drive={drive_id}"]
        if self.boot.get() == "CD first":
            args += ["-boot", "order=d"]
        elif self.boot.get() == "CD then disk":
            args += ["-boot", "order=dc"]
        else:
            args += ["-boot", "order=c"]
        if self.network.get():
            args += ["-nic", "user"]
        else:
            args += ["-nic", "none"]
        if self.usb.get():
            args += ["-device", "qemu-xhci", "-device", "usb-tablet"]
        if self.vga.get() == "Standard VGA":
            args += ["-vga", "std"]
        elif self.vga.get() == "VirtIO GPU":
            args += ["-device", "virtio-vga"]
        elif self.vga.get() == "QXL":
            args += ["-vga", "qxl"]
        else:
            args += ["-vga", "none", "-display", "none"]
        extra = self.extra_text.get("1.0", "end").strip()
        if extra:
            args += shlex.split(extra)
        return args

    def save_config(self, quiet=False):
        try:
            name = safe_name(self.vm_name.get())
            config = {
                "name": name, "arch": self.arch.get(), "ram": self.ram.get(), "ram_unit": self.ram_unit.get(),
                "cpus": self.cpus.get(), "boot": self.boot.get(), "disk_bus": self.disk_bus.get(),
                "iso": self.iso_path.get(), "disks": self.disk_paths, "network": self.network.get(),
                "kvm": self.kvm.get(), "usb": self.usb.get(), "vga": self.vga.get(),
                "vram": self.vram.get(), "vram_unit": self.vram_unit.get(),
                "extra_args": self.extra_text.get("1.0", "end").strip()
            }
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            path = CONFIG_DIR / f"{name}.json"
            path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
            self.selected_config = path
            self.refresh_vm_list(select=path)
            self.status.set("Конфигурация сохранена")
            if not quiet:
                self.log(f"Конфигурация сохранена: {path}")
            return path
        except OSError as exc:
            messagebox.showerror("Ошибка сохранения", str(exc))
            return None

    def load_config(self, path: Path):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            self.vm_name.set(data.get("name", path.stem))
            self.arch.set(data.get("arch", "x86_64"))
            self.ram.set(str(data.get("ram", "256")))
            self.ram_unit.set(data.get("ram_unit", "MB"))
            self.cpus.set(str(data.get("cpus", "1")))
            self.boot.set(data.get("boot", "Disk first"))
            self.disk_bus.set(data.get("disk_bus", "IDE"))
            self.iso_path.set(data.get("iso", ""))
            self.disk_paths = list(data.get("disks", []))
            self.disk_list.delete(0, "end")
            for disk in self.disk_paths:
                self.disk_list.insert("end", disk)
            self.network.set(data.get("network", True))
            self.kvm.set(data.get("kvm", True))
            self.usb.set(data.get("usb", True))
            self.vga.set(data.get("vga", "Standard VGA"))
            self.vram.set(str(data.get("vram", "16")))
            self.vram_unit.set(data.get("vram_unit", "MB"))
            self.extra_text.delete("1.0", "end")
            self.extra_text.insert("1.0", data.get("extra_args", ""))
            self.selected_config = path
            self.status.set(f"Выбрана: {path.stem}")
        except (OSError, json.JSONDecodeError) as exc:
            messagebox.showerror("Ошибка конфигурации", str(exc))

    def refresh_vm_list(self, select: Path | None = None):
        for item in self.vm_tree.get_children():
            self.vm_tree.delete(item)
        found = []
        for path in sorted(CONFIG_DIR.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                found.append((path, data))
            except (OSError, json.JSONDecodeError):
                continue
        for path, data in found:
            ram = f"{data.get('ram', '?')} {data.get('ram_unit', 'MB')}"
            self.vm_tree.insert("", "end", iid=str(path), text=data.get("name", path.stem),
                                values=(data.get("arch", "?"), ram))
        if select and str(select) in self.vm_tree.get_children():
            self.vm_tree.selection_set(str(select))
            self.vm_tree.focus(str(select))

    def _on_vm_select(self, _event=None):
        selection = self.vm_tree.selection()
        if selection:
            self.load_config(Path(selection[0]))

    def new_vm(self):
        self.vm_name.set("NewVM")
        self.arch.set("x86_64")
        self.ram.set("256")
        self.ram_unit.set("MB")
        self.cpus.set("1")
        self.boot.set("Disk first")
        self.disk_bus.set("IDE")
        self.iso_path.set("")
        self.disk_paths = []
        self.disk_list.delete(0, "end")
        self.network.set(True)
        self.kvm.set(True)
        self.usb.set(True)
        self.vga.set("Standard VGA")
        self.vram.set("16")
        self.vram_unit.set("MB")
        self.extra_text.delete("1.0", "end")
        self.selected_config = None
        self.vm_tree.selection_remove(self.vm_tree.selection())
        self.status.set("Новая конфигурация")

    def delete_config(self):
        selection = self.vm_tree.selection()
        if not selection:
            messagebox.showinfo("Удаление", "Сначала выберите сохранённую VM.")
            return
        path = Path(selection[0])
        if messagebox.askyesno("Удалить конфигурацию", f"Удалить конфигурацию {path.stem}?\nФайлы дисков не удаляются."):
            try:
                path.unlink()
                self.selected_config = None
                self.refresh_vm_list()
                self.new_vm()
                self.log(f"Удалена конфигурация: {path}")
            except OSError as exc:
                messagebox.showerror("Ошибка", str(exc))

    def export_script(self):
        try:
            args = self.build_command()
        except (ValueError, OSError) as exc:
            messagebox.showerror("Нельзя создать скрипт", str(exc))
            return
        path = filedialog.asksaveasfilename(title="Экспорт QEMU-скрипта",
                                            initialfile=f"{safe_name(self.vm_name.get())}.sh",
                                            defaultextension=".sh", filetypes=[("Shell script", "*.sh")])
        if not path:
            return
        script = "#!/usr/bin/env bash\n# Generated by PyQemu Script\nset -eu\nexec " + shlex.join(args) + "\n"
        try:
            Path(path).write_text(script, encoding="utf-8")
            os.chmod(path, 0o755)
            self.log(f"Экспортирован скрипт: {path}")
            self.status.set("Скрипт экспортирован")
        except OSError as exc:
            messagebox.showerror("Ошибка экспорта", str(exc))

    def start_vm(self):
        if self.process and self.process.poll() is None:
            messagebox.showinfo("QEMU уже работает", "Этот экземпляр QEMU уже запущен.")
            return
        try:
            args = self.build_command()
        except (ValueError, OSError) as exc:
            messagebox.showerror("Ошибка запуска", str(exc))
            return
        self.save_config(quiet=True)
        self.start_btn.configure(state="disabled")
        self.status.set("Запуск QEMU…")
        self.log("$ " + shlex.join(args))
        def runner():
            try:
                self.process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                                text=True, bufsize=1)
                self.log("QEMU запущен.")
                if self.process.stdout:
                    for line in self.process.stdout:
                        self.log(line)
                code = self.process.wait()
                self.log(f"QEMU завершился с кодом {code}.")
            except Exception as exc:
                self.log(f"Ошибка запуска QEMU: {exc}")
            finally:
                self.root.after(0, self._vm_stopped)
        threading.Thread(target=runner, daemon=True).start()

    def _vm_stopped(self):
        self.start_btn.configure(state="normal")
        self.status.set("Ready")


if __name__ == "__main__":
    root = tk.Tk()
    app = PyQemuApp(root)
    root.mainloop()
