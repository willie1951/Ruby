#navigator.py
"""
This combines your physical 
movement logic with your vector guidance (Warmer/Colder) logic into one "tool" 
that Ruby can use.
"""
from typing import TYPE_CHECKING

if TYPE_CHECKING:
	# prevents a circular import at runtime
	from audio.speaker import Speaker
	from pilot import Pilot
	from vision.analyzer import Analyzer


#standard libraries
import os
import math
import win32gui
import win32api
import win32con
import win32com
import pyautogui
import subprocess
import time

#third party libraries
#import pyautogui as pag
import uiautomation as auto

import globals
from globals import *

#local imports

from pilot import Pilot
from audio.speaker import Speaker 
from data.db_interface import DatabaseInterface

class Navigator:

	def __init__(self, mouth: Speaker, myworld: DatabaseInterface, pilot: Pilot):
		self.mouth = mouth
		self.myworld = myworld
		self.pilot = pilot
		self.prefs = self.myworld.prefs
  
		
		
  
		self.active_hwnd = None # For tracking the window we just opened
		
		self.target_threshold = 50
		# Coordinate state (Anchor Point)
		self.origin_x = 0
		self.origin_y = 0
		
	def start_up(self, analyzer: "Analyzer"):
		
		#print("Synchronizing preferences...") 
		#self.myworld.sync_prefs_to_db() 

		is_aligned = self.myworld.get_state("SCREEN_ALIGNED", default=False)
		print(f"[SYSTEM]: Screen Alignment State = {is_aligned}")
		# 1. Hardware/Session Persistence Sync
		# Check DB for the screen index; if missing, use user_preferences.py
		db_screen =self.myworld.get_state("DEFAULT_SCREEN") 
		active_screen = db_screen if db_screen is not None else self.prefs.DEFAULT_SCREEN 

		# 2. Greeting & Identity Handshake
		label_key = f"SCREEN_{active_screen}_LABEL"
		screen_position = getattr(self.prefs, label_key, f"screen {active_screen}")

		if(self.prefs.PROGRESS_STATE == 1):#only for first time taskbar scan
			print("[INIT]: Mapping Screen 3 Taskbar...")

		# 3. Health & Environment Check
		if not self.myworld.check_health():

			self.mouth.speak("Warning:self.my world memory is reaching disk limits.")
			self.mouth.wait_until_silent()

		# 4. Restore Medium Persistence (The Anchor Stack)
		self.prefs.SCREEN_ALIGNED =self.myworld.get_state("SCREEN_ALIGNED", default=False)
		self.myworld.set_state("CURRENT_ANCHOR", 10)
		last_location = {"name": "Recycle Bin", "context": 10}
	
	def maximize_view(self, app_class="OpusApp"):
		"""
		Waits for the window to appear, then forces it to a maximized state.
		"""
		hwnd = 0
		# 1. Wait up to 5 seconds for the window to actually exist
		for _ in range(10):
			hwnd = win32gui.FindWindow(app_class, None)
			if hwnd:
				break
			time.sleep(0.5)

		if hwnd:
			# 2. If minimized, restore it
			if win32gui.IsIconic(hwnd):
				win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
			
			# 3. Maximize and Bring to front
			win32gui.ShowWindow(hwnd, win32con.SW_SHOWMAXIMIZED)
			
			# Force focus (this is what merges those two 'Word' processes)
			win32gui.SetForegroundWindow(hwnd)
			win32gui.BringWindowToTop(hwnd)
			
			time.sleep(0.5)
			return True
			
		print(f"Ruby Error: Could not find window class {app_class}")
		return False
	
	def handle_direct_filename(self, target_name, exact=True):
		"""
		Resolves matches from the fuzzy search list with extension awareness.
		"""
		# 1. Get full filenames (e.g., ['serge.pdf', 'serge.docx'])
		matches = self.handle_fuzzy_filename(target_name)
		
		if not matches:
			self.mouth.speak(f"No match found for {target_name}.")
			return None

		# 2. If single match, confirm it
		if len(matches) == 1:
			found_file = matches[0]
			self.mouth.speak(f"I found {found_file}. Is this the one?")
			if "yes" in self.mouth.get_intent():
				return found_file
			return None

		# 3. Multiple matches: Use the category logic to differentiate
		self.mouth.speak(f"I found {len(matches)} files with that name.")
		
		for entry in matches:
			ext = os.path.splitext(entry)[1].lower()
			
			# Map extensions to spoken categories
			if ext in [".doc", ".docx"]: 
				category = "Word document"
			elif ext == ".pdf": 
				category = "P D F document"
			elif ext == ".txt": 
				category = "Text file"
			else: 
				category = "File"

			self.mouth.speak(f"Is it the {category} named {entry}?")
			
			# Listen for "yes" or left-click
			response = self.mouth.get_intent()
			if "yes" in response:
				return entry
			elif "no" not in response and response != "":
				# User might have said a different filename or "stop"
				break

		self.mouth.speak("End of list.")
		return None

	def sniff_and_crawl(self):
		"""
		Sniffs the UI and trims the path to just the filename for speech.
		"""
		curr = None
		for _ in range(5):
			curr = auto.GetFocusedControl()
			if curr and curr.Name:
				print(f"filename: {curr.Name}")
				break
			time.sleep(0.1)

		if not curr:
			return "BOUNDARY", None
		curr_str = str(curr)
		
		try:

			if "Name: " in curr_str:
				# Split at 'Name: ', take the second part, 
				# then split at the next newline or end of string
				remainder = curr_str.split("Name: ")[2].split("\n")[0].strip()
				file_name = remainder.split("Handle:")[0].strip()
			else:
				# Fallback to direct attribute
				file_name = curr.Name
		except Exception:
			file_name = curr.Name if curr.Name else "Unknown"

		print(f"navigator->Detected: {file_name}")
		
		return file_name

	def open_with_word(self, full_path):
		"""
		_silent
		Opens a document in Word while suppressing the 'File Conversion' popup.
		"""
		try:
			# 1. Connect to or start the Word Application
			try:
				word = win32com.client.GetActiveObject("Word.Application")
			except:
				word = win32com.client.Dispatch("Word.Application")
			
			# 2. Make Word visible so you can see the manual
			word.Visible = True
			
			# 3. Open with ConfirmConversions set to False
			# This is the 'magic' flag that stops the .txt popup
			word.Documents.Open(full_path, ConfirmConversions=False, ReadOnly=True)
			
			print(f"Ruby: {os.path.basename(full_path)} opened without prompts.")
			
		except Exception as e:
			print(f"Ruby: Could not bypass conversion popup: {e}")

	def open_and_read_selected_file(self, filename, analyzer = None):
		"""
		Branches to the correct reading engine based on extension.
		"""
		# 1. Handle the default instance inside the function
		if analyzer is None:
			# Import locally if needed to avoid circular imports
			from vision.analyzer import Analyzer 
			# Pass the existing instances from the Navigator (self)
			analyzer = Analyzer(
				mouth=self.mouth, 
				myworld=self.myworld, 
				pilot=self.pilot, 
				navigator=self
			)

		# documents to access are in documents folder.
		full_path = os.path.join(globals.Documents_folder, filename)
		ext = os.path.splitext(filename)[1].lower()
		
		# Define our readable 'Word' types
		#word_types = [".txt", ".docx", ".doc", ".rtf"]
		file_name_only, extension = os.path.splitext(full_path)
		if "txt" in extension :
			analyzer.read_text_document_continuous(full_path)
		elif "docx" in extension:
			self.open_with_word(full_path)
			analyzer.read_word_document_continuous()
		elif "doc" in extension:
			self.open_with_word(full_path)
			analyzer.read_word_document_continuous()
		elif "rtf" in extension:
			analyzer.read_rtf_document_continuous(full_path)
		else:
			if "pdf" in extension:#_pdf_
				self.mouth.speak("I found a pdf file, would you like to run n v d a to read it?", male)
				response = self.mouth.get_intent()
				if("yes" in response):
				
					# 2. Launch Chrome with the file path as an argument
					# Using --new-window ensures Ruby doesn't get lost in existing tabs
					
					self.open_pdf_with_chrome(full_path)

					# 3. Give Chrome a moment to render the UI before maximizing
					time.sleep(2.5)						
					# 4. Now maximize using the Chrome/Edge class name
					#self.maximize_view("Chrome_WidgetWin_1")
					#return proc
										
					self.mouth.speak("Max is going to sleep. say Max to wake me up.")
					self.mouth.wait_until_silent()
					# This loop blocks everything until 'Max' is heard
					while True:
						# We use a specialized listener that ONLY looks for the wake word
						analyzer.wait_for_wake_word() 		
						break
					self.mouth.speak("I'm back'")
					self.mouth.wait_until_silent()

			elif "xls" in extension:
				self.mouth.speak("I found an excel file, would you like to run n v d a to read it?", male)
				response = self.mouth.get_intent()
				if("yes" in response):
					os.startfile(full_path), time.sleep(2.0)
					self.mouth.speak("Going to sleep. speek Max to wake me up.")
					self.mouth.wait_until_silent()
					while True:
						# We use a specialized listener that ONLY looks for the wake word
						analyzer.wait_for_wake_word() 		
						break
					self.mouth.speak("I'm back'")
					self.mouth.wait_until_silent()

	def open_pdf_with_chrome(self, full_path):
		# 1. Potential locations
		possible_paths = [
			r"C:\Program Files\Google\Chrome\Application\chrome.exe",
			r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
			os.path.join(os.environ.get("LOCALAPPDATA", ""), r"Google\Chrome\Application\chrome.exe")
		]
		
		chrome_executable = next((p for p in possible_paths if os.path.exists(p)), "chrome")

		try:
			print(f"Ruby: Launching {os.path.basename(full_path)}...")
			
			# Use a list instead of a string to bypass cmd.exe overhead
			# Added --start-maximized to help the OS out before your manual call
			cmd = [chrome_executable, "--new-window", "--start-maximized", full_path]
			
			subprocess.Popen(cmd)
			
			# 3 seconds is good for the Dell 5410's 64GB RAM to settle the UI
			time.sleep(3.0)
			self.maximize_view("Chrome_WidgetWin_1")
			return True
			
		except Exception as e:
			print(f"Ruby Error: Launch failed: {e}")
			return False

	def handle_fuzzy_filename(self, search_phrase):
		"""
		Returns matching filenames INCLUDING extensions, using the 'in' operator.
		"""
		path = globals.Documents_folder
		search_phrase = search_phrase.lower()
		
		try:
			all_files = [f for f in os.listdir(path) if os.path.isfile(os.path.join(path, f))]
		except Exception:
			self.mouth.speak("Access denied.")
			return []
		
		if search_phrase == "list":
			return all_files
	
		matches = []
		for entry in all_files:
			# 1. Get the base name (no extension) to avoid matching the extension itself
			file_base_name = os.path.splitext(entry)[0].lower()
			
			# 2. Fuzzy match: Check if phrase exists anywhere in the base name
			if search_phrase in file_base_name:
				matches.append(entry)
		
		# 3. Sort by length so the most "precise" match (shortest filename) is first
		if len(matches) > 0:
			matches.sort(key=len)
			return matches
			
		return []

	