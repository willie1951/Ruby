#wake_ruby.py
#python -m PyInstaller --noconsole --onefile --name wake_ruby.exe wake_ruby.py
import subprocess
import os
import sys
import win32api
import win32con
import winreg
import winsound
from pynput import mouse

# Derived from the listener's own location
RUBY_ROOT = r"C:\Ruby"
RUBY_EXE = os.path.join(RUBY_ROOT, "ruby.exe")

def install_to_registry():
    # Ensure this matches your PyInstaller --name exactly
    path_to_listener = os.path.join(RUBY_ROOT, "wake_ruby.exe") 
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_ALL_ACCESS) as key:
            # Check if already installed to avoid redundant writes
            try:
                existing_val, _ = winreg.QueryValueEx(key, "RubyWake")
                if existing_val == path_to_listener:
                    return
            except FileNotFoundError:
                pass
            
            winreg.SetValueEx(key, "RubyWake", 0, winreg.REG_SZ, path_to_listener)
    except Exception:
        pass

def is_invoked():
    # Bitwise check for key state
    ctrl = (win32api.GetAsyncKeyState(win32con.VK_CONTROL) & 0x8000)
    shift = (win32api.GetAsyncKeyState(win32con.VK_SHIFT) & 0x8000)
    return ctrl and shift

def on_click(x, y, button, pressed):
    if pressed and button == mouse.Button.left:
        if is_invoked():
            # Immediate feedback for the user
            winsound.Beep(1200, 200)
            
            # Launch Ruby with the correct working directory for DB/Model access
            if os.path.exists(RUBY_EXE):
                subprocess.Popen([RUBY_EXE], cwd=RUBY_ROOT)
            else:
                # Error beep (lower pitch) if Ruby is missing
                winsound.Beep(400, 500)

if __name__ == "__main__":
    install_to_registry()
    # Using a context manager ensures the listener is cleaned up on exit
    with mouse.Listener(on_click=on_click) as listener:
        listener.join()