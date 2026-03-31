#globals.py
female = 1
male = 0
click_state = 0

import os
import sys

# 1. Dynamically find the root folder of Ruby
if getattr(sys, 'frozen', False):
	# Production: Folder where ruby.exe lives
	RUBY_ROOT = os.path.dirname(sys.executable)
	# Frozen EXE targets
	MOUTH_PATH = os.path.join(RUBY_ROOT, "mouth.exe")
	click_exe = os.path.join(RUBY_ROOT, "click_capture.exe") # Changed .bin to .exe
else:
	# Development: The /zz folder
	RUBY_ROOT = os.path.dirname(os.path.abspath(__file__))
	# Dev targets (kept as strings for simple joining in speaker.py)
	MOUTH_PATH = os.path.join(RUBY_ROOT, "mouth.py")
	click_exe = os.path.join(RUBY_ROOT, "click_capture.py")
	
click_file = os.path.join(RUBY_ROOT, "click.txt")
click_exe = os.path.join(RUBY_ROOT, "click_capture.exe")
db_path = os.path.join(RUBY_ROOT, "data", "myworld.db")
error_log_path = os.path.join(RUBY_ROOT, "error_log.txt")
Documents_folder = os.path.join(os.path.expanduser("~"), "Documents")
Downloads_folder = os.path.join(os.path.expanduser("~"), "Downloads")



