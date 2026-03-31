"""
Macks Click Capture Utility (IOC Version)
Build Command:
python -m PyInstaller --noconsole --onefile --distpath "." --name click_capture.exe click_capture.py

Logic:
1. Dynamically resolves the root directory to avoid hardcoded path failures.
2. Initializes 'click.txt' to 0.
3. Uses a blocking Windows Mouse Hook (pynput) to wait for a physical click.
4. On click, writes 1 (Left) or 2 (Right) to 'click.txt' and self-terminates.
"""

import os
import sys
import time
from pynput import mouse

# 1. DYNAMIC PATHING: Ensures transportability between zz, IOC, and production folders
if getattr(sys, 'frozen', False):
	# If running as the compiled click_capture.bin
	application_path = os.path.dirname(os.path.abspath(sys.executable))
else:
	# If running as the raw click_capture.py script
	application_path = os.path.dirname(os.path.abspath(__file__))

# Force the output and error logs to land in the SAME directory as this file
tmp_file_path = os.path.join(application_path, "click.txt")
error_log_path = os.path.join(application_path, "error_log.txt")

# Initialize click state
click_state = 0

def log_error(message):
	try:
		with open(error_log_path, 'a') as log_file:
			log_file.write(f"{time.ctime()}: {message}\n")
	except:
		pass

def on_click(x, y, button, pressed):
	global click_state
	if pressed:
		if button == mouse.Button.left:
			click_state = 1  # Left click
		elif button == mouse.Button.right:
			click_state = 2  # Right click
		
		# Returning False terminates the listener immediately
		return False

# 2. INITIALIZE: Clear or create the file to prevent Macks from reading stale data
try:
	with open(tmp_file_path, 'w') as f:
		f.write("0")
except Exception as e:
	log_error(f"Failed to initialize tmp file: {e}")
	os._exit(1)

# 3. EXECUTION: The Blocking Listener (0% CPU while waiting)
try:
	# Blocks execution here until a click occurs and on_click returns False
	with mouse.Listener(on_click=on_click) as listener:
		listener.join()

	# 4. PAYLOAD: Write the final click result
	with open(tmp_file_path, 'w') as f:
		f.write(str(click_state))
	
	# Forceful exit (os._exit) ensures Windows releases the hook immediately
	# so Macks can continue without 'File In Use' errors.
	os._exit(0)

except Exception as e:
	log_error(f"Critical execution error: {e}")
	os._exit(1)