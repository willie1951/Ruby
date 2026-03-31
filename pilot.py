#pilot.py
import win32api
import win32gui
import time

import uiautomation as auto

class Pilot:
	"""
	The Physical Execution layer. 
	Translates Ruby' intent into hardware actions.
	"""
	# This locks the object to ONLY these attributes. 
	# No hidden inheritance mess can creep in here.

	def __init__(self, mouth, myworld):
		self.mouth = mouth
		self.myworld = myworld

	def press_key(self, key_name):
		"""Standardizes key presses like 'enter', 'tab', 'down'."""
		# Mapping simple names to Windows SendKeys format
		key_map = {
			"enter": "{Enter}",
			"tab": "{Tab}",
			"down": "{Down}",
			"up": "{Up}",
			"esc": "{Esc}",
			"win": "{Win}",
			"space": "{Space}"
		}
		# If the key isn't in our map, we send it as-is (e.g., 'a' or '{F4}')
		formatted_key = key_map.get(key_name.lower(), key_name)
		
		try:
			auto.SendKeys(formatted_key)
			print(f"pilot->pressed: {key_name}")
		except Exception as e:
			print(f"[ERROR] Pilot failed to press {key_name}: {e}")

	def type_text(self, text):
		"""Types a string into the currently focused field."""
		try:
			auto.SendKeys(text)
			print(f"pilot->typed: {text}")
		except Exception as e:
			print(f"[ERROR] Pilot failed to type text: {e}")

	def teleport_and_dwell(self, x, y, duration=0.3):
		print("pilot.py->teleport_and_dwell")
		"""Moves mouse and waits for the OS to acknowledge the hover state."""
		
		# 1. Absolute Move
		win32api.SetCursorPos((x, y))
		
		# 2. The Dwell (Let the OS Tooltip fire)
		time.sleep(duration)
		
		# 3. Micro-Jiggle (Force a UI refresh if the app is 'sleepy')
		win32api.SetCursorPos((x + 1, y))
		time.sleep(0.1)

	