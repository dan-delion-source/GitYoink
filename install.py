#!/usr/bin/env python3
"""
Installation script for GitYoink.
Supports Linux, macOS, and Windows.
Installs GitYoink to an isolated virtual environment and creates an executable shim.
"""

import os
import sys
import platform
import subprocess
import shutil
import argparse
import venv
from pathlib import Path

APP_NAME = "gityoink"
PACKAGE_NAME = "repoyoink" # internal package name

def get_paths():
    system = platform.system()
    home = Path.home()
    if system == "Windows":
        install_dir = home / "AppData" / "Local" / APP_NAME
        bin_dir = Path(os.environ.get("LOCALAPPDATA", home / "AppData" / "Local")) / "Programs" / APP_NAME / "bin"
        venv_bin = install_dir / "Scripts" / f"{PACKAGE_NAME}.exe"
        shim_name = f"{APP_NAME}.cmd"
    else:
        install_dir = home / ".local" / "share" / APP_NAME
        bin_dir = home / ".local" / "bin"
        venv_bin = install_dir / "bin" / PACKAGE_NAME
        shim_name = APP_NAME

    return install_dir, bin_dir, venv_bin, shim_name

def create_venv(install_dir):
    print(f"📦 Creating virtual environment in {install_dir}...")
    if install_dir.exists():
        print(f"🗑️  Removing existing installation at {install_dir}...")
        shutil.rmtree(install_dir)
    
    builder = venv.EnvBuilder(with_pip=True, clear=True)
    builder.create(install_dir)

def install_package(install_dir):
    system = platform.system()
    print(f"📥 Installing {APP_NAME} dependencies and package...")
    
    if system == "Windows":
        pip_exe = install_dir / "Scripts" / "pip.exe"
    else:
        pip_exe = install_dir / "bin" / "pip"
        
    src_dir = Path(__file__).parent.absolute()
    
    try:
        subprocess.check_call([str(pip_exe), "install", str(src_dir)], stdout=subprocess.DEVNULL)
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to install package: {e}")
        sys.exit(1)

def create_shim(bin_dir, venv_bin, shim_name):
    system = platform.system()
    print(f"🔗 Creating executable wrapper '{shim_name}' in {bin_dir}...")
    
    bin_dir.mkdir(parents=True, exist_ok=True)
    shim_path = bin_dir / shim_name
    
    if system == "Windows":
        with open(shim_path, "w") as f:
            f.write(f'@echo off\n"{venv_bin}" %*\n')
    else:
        with open(shim_path, "w") as f:
            f.write(f'#!/bin/sh\nexec "{venv_bin}" "$@"\n')
        shim_path.chmod(0o755)
        
    return shim_path

def create_desktop_shortcut(bin_dir, shim_name):
    system = platform.system()
    print("🖥️  Creating desktop shortcut...")
    home = Path.home()
    
    if system == "Linux":
        apps_dir = home / ".local" / "share" / "applications"
        apps_dir.mkdir(parents=True, exist_ok=True)
        desktop_file = apps_dir / f"{APP_NAME}.desktop"
        content = f"""[Desktop Entry]
Version=1.0
Type=Application
Name=GitYoink
Comment=Terminal-based selective GitHub repository downloader
Exec={bin_dir / shim_name}
Icon=utilities-terminal
Terminal=true
Categories=Utility;Development;
"""
        with open(desktop_file, "w") as f:
            f.write(content)
        desktop_file.chmod(0o755)
        print(f"   Created Linux application shortcut at {desktop_file}")
        
    elif system == "Darwin":
        desktop_dir = home / "Desktop"
        command_file = desktop_dir / "GitYoink.command"
        with open(command_file, "w") as f:
            f.write(f'#!/bin/sh\nexec "{bin_dir / shim_name}"\n')
        command_file.chmod(0o755)
        print(f"   Created macOS double-clickable shortcut at {command_file}")
        
    elif system == "Windows":
        desktop_dir = home / "Desktop"
        shortcut_path = desktop_dir / "GitYoink.bat"
        content = f"""@echo off
title GitYoink
call "{bin_dir / shim_name}"
"""
        with open(shortcut_path, "w") as f:
            f.write(content)
        print(f"   Created Windows shortcut at {shortcut_path}")

def check_path_instructions(bin_dir):
    system = platform.system()
    path_env = os.environ.get("PATH", "")
    if str(bin_dir) not in path_env:
        print(f"\n⚠️  IMPORTANT: The directory {bin_dir} is not in your PATH.")
        if system == "Windows":
            print(f"   Please add {bin_dir} to your user PATH environment variable to run '{APP_NAME}' from any terminal.")
        elif system == "Darwin":
            print(f"   Please add the following line to your ~/.zprofile or ~/.bash_profile:")
            print(f"   export PATH=\"{bin_dir}:$PATH\"")
        else:
            print(f"   Please add the following line to your ~/.bashrc or ~/.zshrc:")
            print(f"   export PATH=\"{bin_dir}:$PATH\"")

def uninstall():
    install_dir, bin_dir, _, shim_name = get_paths()
    shim_path = bin_dir / shim_name
    system = platform.system()
    home = Path.home()
    
    print(f"🗑️  Uninstalling {APP_NAME}...")
    
    removed = False
    
    if install_dir.exists():
        print(f"   Removing application data at {install_dir}...")
        shutil.rmtree(install_dir)
        removed = True
        
    if shim_path.exists():
        print(f"   Removing executable wrapper at {shim_path}...")
        shim_path.unlink()
        removed = True

    # Remove shortcuts
    if system == "Linux":
        desktop_file = home / ".local" / "share" / "applications" / f"{APP_NAME}.desktop"
        if desktop_file.exists():
            print(f"   Removing Linux application shortcut at {desktop_file}...")
            desktop_file.unlink()
            removed = True
    elif system == "Darwin":
        command_file = home / "Desktop" / "GitYoink.command"
        if command_file.exists():
            print(f"   Removing macOS double-clickable shortcut at {command_file}...")
            command_file.unlink()
            removed = True
    elif system == "Windows":
        shortcut_path = home / "Desktop" / "GitYoink.bat"
        if shortcut_path.exists():
            print(f"   Removing Windows shortcut at {shortcut_path}...")
            shortcut_path.unlink()
            removed = True

    if not removed:
        print(f"   {APP_NAME} is not currently installed.")
    else:
        print(f"✅ Successfully uninstalled {APP_NAME}.")

def main():
    parser = argparse.ArgumentParser(description=f"{APP_NAME} installation script")
    parser.add_argument("--uninstall", action="store_true", help=f"Uninstall {APP_NAME}")
    args = parser.parse_args()
    
    if args.uninstall:
        uninstall()
        sys.exit(0)
        
    print(f"🚀 Starting installation of {APP_NAME}...")
    
    install_dir, bin_dir, venv_bin, shim_name = get_paths()
    
    create_venv(install_dir)
    install_package(install_dir)
    shim_path = create_shim(bin_dir, venv_bin, shim_name)
    create_desktop_shortcut(bin_dir, shim_name)
    
    print(f"✅ Installation complete! You can now run '{APP_NAME}' from your terminal.")
    
    check_path_instructions(bin_dir)

if __name__ == "__main__":
    main()
