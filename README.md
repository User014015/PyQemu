# PyQemu Script

` Made in russian language `

PyQemu Script is a small GUI tool that makes working with QEMU easier. Instead of writing long commands by hand, you can configure a virtual machine through a simple interface and let the app generate the QEMU command for you.

It saves time, makes VM setup less annoying, and helps you avoid mistakes in long command lines.

## Download and Run

### Linux (Arch Linux)

Install QEMU first:

```bash
sudo pacman -S qemu-desktop
```

You may also need `python` and `tk`:

```bash
sudo pacman -S python tk
```

Download `main.py` from the latest release, then run:

```bash
python main.py
```

Make sure QEMU is installed and available in your `PATH`.

### Run from source

If you want to try the latest code clone the repository:

```bash
git clone https://github.com/User014015/PyQemu
cd PyQemu-Script
python main.py
```

## Features

- Configure virtual machines through a GUI
- Set CPU and RAM
- Attach ISO files and virtual disks
- Create virtual disks with `qemu-img`
- Configure basic virtual machine options
- Generate and export QEMU shell scripts
- Start virtual machines directly from the app

## Requirements

- Python 3
- Tkinter
- QEMU
- `qemu-img` for creating and managing virtual disks

QEMU must be installed separately; PyQemu Script is a GUI for it, not a replacement for the QEMU engine.

## Status

PyQemu Script is still a work in progress. It's mainly developed for Linux, and compatibility with other platforms may vary.

If you find a bug or have an idea for a feature, feel free to open an issue!

## License

Check the repository for license information.
