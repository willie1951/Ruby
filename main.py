#main.py
#taskkill /F /IM ruby.exe /T
#python -m PyInstaller --onefile --add-data "model;model" --collect-all vosk --collect-all uiautomation --collect-all sounddevice --name ruby.exe main.py
"""
in root folder /blind GUI
Handshake: Max starts and asks "Review the screen?".State Logic: When you hit Y, 
the state moves to SCANNING and the Sonar Grid populates myworld.db.Duplex 
Simulation: When Max is listing items, hitting SPACE (simulating "Run that") 
raises the interrupt_requested flag, kills the speech loop, and the Navigator 
clicks the coordinates of the last item mentioned.DPI Safety: Because the ctypes 
call is first, your Screen 2 coordinates ($1920, -3$) will map perfectly 
to the icons.
"""

# 1. THE OVERRIDE: Must be the absolute first thing executed!
"""
0 (Unaware): Windows "stretches" the app. Everything looks blurry, and coordinates 
are wrong.

1 (System Aware): The app scales based on the primary monitor. If Screen 1 and 
Screen 2 have different scaling, your mouse coordinates will be "offset" 
when you move between them.

2 (Per-Monitor): This is the Gold Standard. It tells Windows: "Don't touch my 
coordinates. I will handle the math myself based on whichever monitor the 
mouse is currently over."
#import sqlite3
#import keyboard
#import sounddevice as sd
#import winsound
#import win32com.client
#import pythoncom
#import json
#import queue
#import pyttsx3
"""
import ctypes
try:
	per_monitor_aware = 2
	ctypes.windll.shcore.SetProcessDpiAwareness(per_monitor_aware) 
except Exception:
	try:
		# Fallback: System-Wide (No arguments allowed)
		# This effectively sets it to awareness level 1
		ctypes.windll.user32.SetProcessDPIAware()
	except Exception:
		pass

#standard libraries
import os
import sys
import subprocess
import win32api
import time

#third party libraries
import uiautomation as auto

# 1. LOCAL MODULES (Imports must happen first)

import globals
from globals import *

from data.db_interface import DatabaseInterface
from core.settings_manager import SettingsManager
#from core.state_manager import StateManager
from audio.speaker import Speaker
from audio.navigator import Navigator
from vision.analyzer import Analyzer
from pilot import Pilot

# --- 2. INSTANTIATE CLASSES (The Handshake) must be ordered ---
# A. Create the Database Foundation first
myworld = DatabaseInterface() 

# B. Pass 'myworld' into SettingsManager so it can use the 'to_myworld' bridge
ruby_settings = SettingsManager(myworld) 

# C. Pass settings to the Speaker
mouth = Speaker(ruby_settings)

# Use the Pilot class here, NOT the Navigator class
pilot = Pilot(mouth, myworld)

# The "Driver" (Mapping & Files)
navigator = Navigator(mouth, myworld, pilot)

# 4. The Eye (This MUST come before line 631)
analyzer = Analyzer(mouth, myworld, pilot, navigator)

# THE DISPATCHER (The missing link)
# We pass the DB and the Voice so it can load data and announce changes
#state_instance = StateManager(myworld, mouth)

# Pass everything to the Analyzer (the 'memory' argument is 'myworld')
eyes_ai = Analyzer(mouth, myworld, pilot, navigator)

# --- 3. INITIALIZATION CALLS ---

# Since sync_prefs_to_db is now a method of the DatabaseInterface class:
#myworld.sync_prefs_to_db()

# 2. Update your sub-paths relative to the new root

"""
the DatabaseInterface is the "Black Box Recorder." It logs every AI description 
and every move Max makes so that he can learn from his environment over time.

Without that import, Max would have "short-term memory"—he'd see the screen, 
tell you about it, and then forget it ever happened the moment the next scan starts.
"""

def enter_desktop_state():
	"""
	User may specify a file to read or find a list
	"""
	
	menu_phrase = "As a reminder these four universal commands are: repeat, pause, sleep, exit."
	mouth.speak(menu_phrase)
	mouth.wait_until_silent()
	
	
	print("main->enter_desktop_state")
	
	while True:
		# 0. See if there is an unfinished read in myworld, the user may want to continue.
		#query: select filename from recent_files where last_paragrapg is not null
		last_doc = myworld.get_last_unfinished_document()
		
		captured_command = None
		if last_doc: 
			#Handles Multiple Dots: ie. manual.v2.docx
			file_name_only, extension = os.path.splitext(last_doc)
			last_para = myworld.get_last_paragraph(last_doc)
			if last_para and last_para > 1:

				menu_phrase = f"should we continue with {last_doc}"
				mouth.speak(menu_phrase, female)
				mouth.wait_until_silent()
				captured_command = mouth.get_intent()
		
		if captured_command:
			status = handle_universal(captured_command, mouth, eyes_ai, file_name_only)
			if status == "continue": continue
			if status == "break": break
			if status == "reset": 
				captured_command = "return to top"
				break

			# Confirmation Step
			if "yes" in captured_command:
				navigator.open_and_read_selected_file(last_doc)
				continue #to top
			# continue below.
		menu_phrase = "say a filename or list"
		mouth.speak(menu_phrase, female)
		mouth.wait_until_silent()

		# 2. Wait for intent with Hardware Confirmation
		captured_command = mouth.get_intent()
		
		if captured_command:
			status = handle_universal(captured_command, mouth, eyes_ai, captured_command)#file_name_only used twice)
			if status == "continue": continue
			if status == "break": break
			if status == "reset": 
				captured_command = "return to top"
				break
	
		if captured_command != "return to top":
			mouth.speak(f"I heard {captured_command}. Is that correct?")#filename
			mouth.wait_until_silent()
			confirmation = mouth.get_intent()#yes or click
			
			if "yes" in confirmation:
				file = navigator.handle_direct_filename(captured_command)
						
				if file: 
					navigator.open_and_read_selected_file(file)
			else: # repeat
				continue # back to top
		continue # back to top

def handle_universal(command, mouth, eyes_ai, file_name):
		# Returns True if a universal command was handled, False otherwise
	if "repeat" in command:
		return "continue"
	
	if "pause" in command:
		mouth.click_left_tone()
		mouth.begin_pause()
		return "continue"
	
	if "exit" in command:
		mouth.speak("exiting Ruby")
		return "break"
		
	if "sleep" in command:
		mouth.speak("Going to sleep. say Ruby to wake me up.")
		mouth.wait_until_silent()
		while True:
			eyes_ai.wait_for_wake_word()
			mouth.speak(f"We can resume {file_name} later")
			mouth.wait_until_silent()
			mouth.speak(f"Should I continue?")
			mouth.wait_until_silent()
			response = mouth.get_intent()
			if "yes" in response:
				return "continue"
			else:
				mouth.speak("exiting Ruby")
				break
		return "reset"
	return None

# --- MAIN LOOP ---
if __name__ == "__main__":
	# 1. Essential for One-File EXEs to prevent the "Process Loop"
	import multiprocessing
	multiprocessing.freeze_support()
	
	# 2. Your original logic now sits safely behind the guard
	navigator.start_up(analyzer)         
	enter_desktop_state()
	
