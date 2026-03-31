#analyzer.py
"""
This is the "Slow Eye." It combines the Latency Logic from Brain_test.py, 
the DPI Scaling and Monitor Matching from camera_test.py, and the RAM Management 
from resize_image.py.
"""
from typing import TYPE_CHECKING

if TYPE_CHECKING:
	# This allows VS Code to see 'sniff_and_crawl'
	# but prevents a circular import at runtime
	from audio.navigator import Navigator
	from audio.speaker import Speaker
	from pilot import Pilot

import sys
import os
import psutil
import win32api
import win32gui
import win32com.client
import win32process
import time
import gc
import subprocess
import winsound
import mss
import numpy as np
import fitz  # PyMuPDF
import ollama
import json
import queue
import uiautomation as auto
import sounddevice as sd
from vosk import Model, KaldiRecognizer, SetLogLevel
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import globals
from globals import *


from pilot import Pilot
from data.db_interface import DatabaseInterface
from audio.speaker import Speaker
from core.settings_manager import SettingsManager

# C. Pass settings to the Speaker
myworld = DatabaseInterface() 
ruby_settings = SettingsManager(myworld) 
mouth = Speaker(ruby_settings)
pilot = Pilot(mouth, myworld)

"""
	In Python, self refers to the specific instance of the class you are currently 
	working with.  By saying self.mouth, you are creating a "pocket" inside the 
	Analyzer's myworld. You are taking the radio you were handed (mouth) 
	and putting it in that pocket (self.mouth).

	Now, every other function inside the Analyzer (like analyze_with_ai) can reach 
	into that pocket and use the radio.
	"""
# Verify the folder named "model" exists in the current directory
if not os.path.exists("model"):
	print("ERROR: Please ensure the folder is named 'model' (lowercase).")
	exit()

# Load the Brain (Tool name is Capital 'Model', Folder name is lowercase 'model')
model_brain = Model("model")

# --- THE POSTAL SERVICE: THREAD-SAFE QUEUE ---
# By defining audio_queue at the top level of the file (outside the class), both speak() 
# and _audio_worker() are looking at the exact same myworld address.
q = queue.Queue()

class Analyzer:
	def __init__(self, mouth: Speaker, myworld: DatabaseInterface, pilot: Pilot, \
			  navigator: "Navigator"):
		"""The 'Slow Eye' that understands context via AI."""
		self.mouth = mouth
		self.myworld = myworld # Storing the database connection
		self.pilot = pilot
		self.navigator = navigator
		self.prefs = self.myworld.prefs
		self.last_description = ""

	def check_for_new_items(self):
		"""
		Stub for AI deep scan. 
		Currently returns False to simulate 'No new items found'.
		"""
		print("[STUB]: Analyzer is checking for new items...")
		# For testing, we simulate that nothing new was found
		return False

	def _get_target_region(self):
		"""Identifies the window under mouse to prevent panoramic processing."""
		x, y = auto.GetCursorPos()
		try:
			target_element = auto.ControlFromPoint(x, y)
			if not target_element: return None
			
			target_window = target_element.GetTopLevelControl() or target_element
			rect = target_window.BoundingRectangle
			width, height = rect.right - rect.left, rect.bottom - rect.top
			
			# Panoramic Filter: Rejects desktop-wide snapshots
			if width > 3000: return None
			return {'top': rect.top, 'left': rect.left, 'width': width, 'height': height}
		except Exception:
			return None

	def analyze_with_ai(self, image=None, prompt='Describe this UI briefly.'):
		"""
		Prevents 'myworld Stomp' by using unique temporary files for each AI call.
		"""
		
		start_time = time.time()
		
		# Generate a unique filename for this specific request
		# This prevents the AI from reading 'Icon 3' while we are saving 'Icon 4'
		unique_id = int(time.time() * 1000)
		temp_path = os.path.join(globals.RUBY_ROOT, f"temp_vision_{unique_id}.png")

		try:
			if image is not None:
				# TASKBAR PATH: Save the pre-cropped PIL image
				image.save(temp_path)
			else:
				# LIVE CAPTURE PATH: Capture, process, and save
				with mss.mss() as sct:
					region = self._get_target_region()
					# ... [Your existing capture logic here] ...
					# Ensure you save the final result to 'temp_path'
					# cv2.imwrite(temp_path, resized_image)

			# Give the OS a millisecond to finalize the file write
			time.sleep(0.1)

			# Moondream Inference
			response = ollama.chat(model='moondream', messages=[
				{'role': 'user', 'content': prompt, 'images': [temp_path]}
			])
			result = response['message']['content'].strip()

			# --- CLEANUP ---
			# Delete the unique file immediately so we don't clutter your drive
			if os.path.exists(temp_path):
				os.remove(temp_path)
			
			# Force garbage collection to prevent the latency creep you saw (23s -> 33s)
			gc.collect()

			return result

		except Exception as e:
			print(f"[AI ERROR]: {e}")
			if os.path.exists(temp_path):
				os.remove(temp_path)
			return ""
		
	def _callback(self, indata, frames, time, status):
		"""This is the internal pipeline that feeds the audio queue."""
		if status:
			print(f"[AUDIO ERROR]: {status}")
		# Put the raw audio data into the global or class-level queue 'q'
		q.put(bytes(indata))
		
	def listen(self, tone): #Ruby is listening
		
		print("analyzer->listen")
		winsound.Beep(tone, 100)
	
	def stop_listen(self, tone): #Ruby has stopped listening.
		
		print("analyzer->stop_listen")
		winsound.Beep(tone, 50)
		time.sleep(0.005)
		winsound.Beep(tone, 50)

	def wait_for_wake_word(self, wake_word="Ruby"):
		"""
		Blocks execution and listens continuously using the Kaldi/Queue pattern.
		"""
		print(f"analyzer->System Sleeping. Listening for: {wake_word}")
		
		# Outer loop to keep the process alive until wake
		while True:
			self.listen(self.prefs.LISTEN_TONE)
			with sd.RawInputStream(samplerate=16000, blocksize=8000, dtype='int16',
								   channels=1, callback=self._callback, device=1):
				
				rec = KaldiRecognizer(model_brain, 16000)
				
				# Inner loop for real-time processing
				while True:
					try:
						data = q.get_nowait()
						if rec.AcceptWaveform(data):
							result = json.loads(rec.Result())
							text = result.get("text", "").lower().strip()
							
							if text:
								# Check for both phonetic variations
								if wake_word in text or "ruby" in text:
									print("analyzer->Wake word detected!")
									self.stop_listen(self.prefs.PAUSE_TONE)
									return True
					except queue.Empty:
						pass
					
					# Small sleep to prevent 100% CPU usage during silence
					time.sleep(0.01)

	
	def get_open_document_path(self):
		"""
		Uses win32com.client.Dispatch correctly to access Word properties.
		Indented with Physical Tabs.
		"""
		try:
			# Use the full namespace to call Dispatch
			word = win32com.client.Dispatch("Word.Application")
			
			# Ensure Word is actually managing documents
			if word.Documents.Count > 0:
				# This is the 'ActiveDocument' that the user is looking at
				doc = word.ActiveDocument
				
				# Extract the path
				path_truth = doc.FullName
				print(f"eyes_ai->Found path: {path_truth}")
				return path_truth
			else:
				print("eyes_ai->No active documents found.")
				return None
				
		except Exception as e:
			print(f"eyes_ai->COM error: {e}")
			return None
		
	def update_recent_files(self, full_path):
		"""
		Updates the access date and increments the open count for a file.
		"""
		cursor = self.myworld.to_myworld.cursor()
		try:
			filename = os.path.basename(full_path)
			
			# THE UPSERT: Insert new record OR Update existing one
			# We increment open_count by 1 every time this is called
			cursor.execute('''
				INSERT INTO recent_files (path, filename, open_count, last_accessed)
				VALUES (?, ?, 1, CURRENT_TIMESTAMP)
				ON CONFLICT(path) DO UPDATE SET
					open_count = open_count + 1,
					last_accessed = CURRENT_TIMESTAMP
			''', (full_path, filename))
			
			self.myworld.to_myworld.commit()
			
			# Fetch the new count just for the debug log
			cursor.execute('SELECT open_count FROM recent_files WHERE path = ?', (full_path,))
			count = cursor.fetchone()[0]
			
			cursor.close()
			print(f"myworld->'{filename}' updated. Total opens: {count}")
			
		except Exception as e:
			print(f"myworld->Database update failed: {e}")

	def start_capture(self):
		target = globals.click_exe.strip()
		bin_path = os.path.dirname(target).strip()
		
		if not os.path.exists(target):
			print(f"SYSTEM ERROR File not found at {target}")
			return None

		print(f"Ruby: Launching Capture EXE at {target}")
		
		try:
			# Adding cwd ensures the EXE can find its own local files
			return subprocess.Popen(
				[target], 
				shell=False, 
				cwd=bin_path
			)
		except Exception as e:
			print(f"CRITICAL: Failed to launch capture process: {e}")
			return None

	def get_click_status(self, click_proc):
		click_state = "0"
		
		if os.path.exists(globals.click_file):
			# Retry loop: 3 attempts with 10ms gaps handles the 'File In Use' race condition
			for attempt in range(3):
				try:
					print(f":check click attempt {attempt + 1}")
					with open(globals.click_file, 'r') as f:
						content = f.read().strip()
						click_state = content[0] if content else "0"
					
					# If we successfully read it, break the retry loop
					print("removing click file")
					os.remove(globals.click_file)
					break 
					
				except (PermissionError, IOError):
					# The file is locked by the capture utility; wait and try again
					time.sleep(0.01)
				except Exception:
					# Generic failure (e.g. malformed data)
					click_state = "0"
					break

		# 2. Cleanup: Ensure the one-shot process is gone
		try:
			if click_proc:
				click_proc.kill() 
		except:
			pass

		return click_state

	def read_word_document_continuous(self):
		"""
		Reads the document with a paragraph-pause check for mouse clicks.
		"""

		click_proc = self.start_capture()
		female = 1
		male = 0
	
		word = None

		# Loop 10 times, waiting 1 second between each attempt
		for attempt in range(5):
			print(f"attempt: {attempt}")
			try:
				word = win32com.client.GetActiveObject("Word.Application")
				if word: break 
			except Exception:
				try:						
					word = win32com.client.Dispatch("Word.Application")
					if word: break
				except:
					time.sleep(1.0)

		if not word:
			print("Word is taking too long to start. Please try again.")
			return

		# 2. Wait for the Document to actually open inside Word
		doc = None
		for doc_attempt in range(10):
			if word.Documents.Count > 0:
				try:
					doc = word.ActiveDocument
					# Verify we can actually access the content
					test = doc.Content.Text 
					break
				except:
					pass
			print(f"Waiting for document to load... attempt {doc_attempt}")
			if doc_attempt == 9:
				self.mouth.speak("Word might have a save box open.  Check and try again.")
				return
			time.sleep(1.0)

		if not doc:
			print("Word is open, but no document is loaded.")
			return
		
		doc = word.ActiveDocument
		paragraphs = doc.Paragraphs
		total = paragraphs.Count
		print(f":Paragraphs {total}")
		#print(f":filename {total}")

		current_index = self.myworld.get_last_paragraph(doc.Name)
		if current_index == 0: current_index = 1

		while current_index <= total:
			para_text = paragraphs(current_index).Range.Text.strip()
			print(f":Paragraph {current_index}")
			if len(para_text) > 1:
				self.mouth.speak(para_text, female)
				#self.mouth.wait_until_silent()

			# 1. Give the EXE a moment to finish writing if it just clicked
			#time.sleep(0.3) 

			if click_proc and click_proc.poll() is not None:
				# The process died, which means a click happened!
				click_state = self.get_click_status(click_proc)
			else:
				# Process is still active, waiting for the user
				click_state = "0"

			"""
			if os.path.exists(globals.click_file):
				try:
					print(f":check click 1")
					with open(globals.click_file, 'r') as f:
						# Take only the first char to ignore debug strings
						print(f":check click 2")
						content = f.read().strip()
						print(f":check click 3")
						click_state = content[0] if content else "0"
					print(f"removing click file")
					os.remove(globals.click_file)
				except Exception:
					click_state = "0" # If file is locked, assume no click

			# 2. Use .kill() for a cleaner process tree removal
			try:
				click_proc.kill() 
			except:
				pass
			"""

			if click_state == "1":
				self.mouth.speak("pausing", male)
				self.mouth.begin_pause()
				click_proc = self.start_capture()
				# Note: We do NOT increment current_index here so we can re-read
				# or continue to the last paragraph we were on.
			
			elif click_state == "2":
				self.mouth.speak("do you want to bookmark your place", male)
				mouth.wait_until_silent()
				captured_command = mouth.get_intent()
				if captured_command == "yes":
					self.myworld.save_last_paragraph(doc.Name, current_index, self.navigator)
					self.mouth.speak("Position bookmarked.", male)
				else:
					current_index = 0
					self.myworld.save_last_paragraph(doc.Name, current_index, self.navigator)
				self.mouth.speak("Closing Word.", male)
				doc.Close(False)
				word.Quit()
				return 

			else:
				current_index += 1
				# Only re-invoke if we haven't reached the end
				if current_index <= total:
					click_proc = self.start_capture()

		# End of document reached
		self.myworld.save_last_paragraph(doc.Name, 0, self.navigator) 
		self.mouth.speak("reading document complete. Closing Word.", male)
		doc.Close(False)
		word.Quit()
		return None

	def read_text_document_continuous(self, full_path):
		"""
		Uses Word to read .txt files silently without the conversion popup.
		"""
		female = 1
		male = 0
		
		try:
			# 1. Start Word and open the file silently
			word = win32com.client.Dispatch("Word.Application")
			# ConfirmConversions=False skips the popup in your screenshot
			doc = word.Documents.Open(full_path, ConfirmConversions=False, ReadOnly=True)
			word.Visible = True
			paragraphs = doc.Paragraphs
			total = paragraphs.Count
			print(f":Paragraphs {total}")
			current_index = 1 # Word collections start at 1
			
			click_proc = self.start_capture()

			while current_index <= total:
				line_text = paragraphs(current_index).Range.Text.strip()
				print(f":Paragraph {current_index}")
				
				if len(line_text) > 1:
					self.mouth.speak(line_text, female)

				time.sleep(0.3)
				
				# Click Check Logic
				click_state = "0"
				if os.path.exists(globals.click_file):
					try:
						with open(globals.click_file, 'r') as f:
							content = f.read().strip()
							click_state = content[0] if content else "0"
						os.remove(globals.click_file)
					except:
						pass

				if click_state == "1": # Pause
					try: click_proc.kill()
					except: pass
					self.mouth.speak("pausing", female)
					self.mouth.begin_pause() 
					click_proc = self.start_capture()
				elif click_state == "2": # Exit
					#try: click_proc.kill()
					#except: pass
					self.mouth.speak("do you want to bookmark your place", female)
					mouth.wait_until_silent()
					captured_command = mouth.get_intent()
					if captured_command == "yes":
						self.myworld.save_last_paragraph(doc.Name, current_index, self.navigator)
						self.mouth.speak("Position bookmarked.", female)
					else:
						current_index = 0
						self.myworld.save_last_paragraph(doc.Name, current_index, self.navigator)

						doc.Close(False) # Close without saving
						word.Quit()
						self.mouth.speak("Closing text reader.", male)
						return
				else:
					current_index += 1
					# Reset capture for next paragraph
					#try: click_proc.kill()
					#except: pass
					if current_index <= total:
						click_proc = self.start_capture()
						
			doc.Close(False)
			word.Quit()
			self.mouth.speak("End of text file.", male)

		except Exception as e:
			print(f"Ruby Error: {e}")
			self.mouth.speak("Error reading text file.", male)

	def read_rtf_document_continuous(self, full_path):
		"""
		Specifically handles Rich Text Format (.rtf) using the Word Object Model.
		"""
		female = 1
		male = 0
		
		try:
			# 1. Connect to Word
			word = win32com.client.Dispatch("Word.Application")
			# RTF files open natively, so no extra flags are usually needed
			doc = word.Documents.Open(full_path, ReadOnly=True)
			
			paragraphs = doc.Paragraphs
			total = paragraphs.Count
			print(f":Paragraphs {total}")
			current_index = 1 
			
			click_proc = self.start_capture()

			while current_index <= total:
				# .Range.Text extracts the clean string, ignoring RTF tags
				line_text = paragraphs(current_index).Range.Text.strip()
				print(f":Paragraph {current_index}")
			
				if len(line_text) > 1:
					self.mouth.speak(line_text, female)

				time.sleep(0.3)
				
				# Click Check Logic
				click_state = "0"
				if os.path.exists(globals.click_file):
					try:
						with open(globals.click_file, 'r') as f:
							content = f.read().strip()
							click_state = content[0] if content else "0"
						os.remove(globals.click_file)
					except:
						pass

				if click_state == "1": # Pause
					#try: click_proc.kill()
					#except: pass
					self.mouth.speak("pausing", female)
					self.mouth.begin_pause() 
					click_proc = self.start_capture()
				elif click_state == "2": # Exit
					self.mouth.speak("do you want to bookmark your place", female)
					mouth.wait_until_silent()
					captured_command = mouth.get_intent()
					if captured_command == "yes":
						self.myworld.save_last_paragraph(doc.Name, current_index, self.navigator)
						self.mouth.speak("Position bookmarked.", female)
					else:
						current_index = 0
						self.myworld.save_last_paragraph(doc.Name, current_index, self.navigator)

					doc.Close(False)
					word.Quit()
					self.mouth.speak("Closing Rich Text reader.", male)
					return
				else:
					current_index += 1
					try: click_proc.kill()
					except: pass
					if current_index <= total:
						click_proc = self.start_capture()
						
			doc.Close(False)
			word.Quit()
			self.mouth.speak("End of Rich Text file.", male)

		except Exception as e:
			print(f"Ruby RTF Error: {e}")
			self.mouth.speak("Error reading rich text.", male)

