#speaker.py

from typing import TYPE_CHECKING

if TYPE_CHECKING:
	# This allows VS Code to see 'sniff_and_crawl'
	# but prevents a circular import at runtime
	from audio.navigator import Navigator
	from vision.analyzer import Analyzer
	from core.settings_manager import SettingsManager

import sys
import os
import subprocess
import sounddevice as sd
import win32api
import winsound
import json
import queue
import pyttsx3
import time
import sqlite3

# Add root to path for user_preferences
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import globals 
from globals import *
from vosk import Model, KaldiRecognizer, SetLogLevel
SetLogLevel(-1)
from data.db_interface import DatabaseInterface
myworld = DatabaseInterface() 
# Global defaults
model_brain = Model("model")
q = queue.Queue()

class Speaker:

	def __init__(self, settings_manager, navigator: "Navigator" = None, last_phrase="Ready for your command.", \
			  last_context="all"):
		self.settings = settings_manager
		self.navigator = navigator
		self.last_phrase = last_phrase
		self.last_context = last_context
		
		self.sm = None
		# Primary engine instance for property checks
		self.engine = pyttsx3.init()
		self.speaking_state = False
		self.conn = sqlite3.connect('data/myworld.db', check_same_thread=False)
		self.myworld = myworld
		self.prefs = self.myworld.prefs

	def speak(self, text, voice=0):     
		print(f"Speak: {text}")
		
		# 1. Establish the "Source of Truth" for the executable
		if getattr(sys, 'frozen', False):
			# Running as EXE: RUBY_ROOT is the folder containing ruby.exe
			RUBY_ROOT = os.path.dirname(sys.executable)
			# We point to a separate tiny EXE to avoid the Fork Bomb
			exe_target = os.path.join(RUBY_ROOT, "mouth.exe")
		else:
			# Running in VS Code/Dev: use the actual Python interpreter
			exe_target = sys.executable

		rate = self.prefs.VOICE_RATE
		safe_text = text.replace("'", "\\'")
		voice_idx = 0 if voice == 0 else 1

		# 2. Logic for Dev vs. Production
		if getattr(sys, 'frozen', False):
			# EXE Mode: Pass arguments to our specialized mouth tool
			cmd = [exe_target, str(rate), str(voice_idx), safe_text]
		else:
			# Dev Mode: Continue using the -c string injection
			python_code = (
				"import pyttsx3; "
				"e = pyttsx3.init(); "
				f"e.setProperty('rate', {rate}); "
				"v = e.getProperty('voices'); "
				f"e.setProperty('voice', v[{voice_idx}].id); "
				f"e.say('{safe_text}'); "
				"e.runAndWait()"
			)
			cmd = [exe_target, "-c", python_code]

		try:
			# Hardware(soft) reset occurs when this process exits
			subprocess.run(cmd, check=True)
		except subprocess.CalledProcessError as e:
			print(f"[AUDIO ERROR]: Subprocess failed. {e}")


	def is_speaking(self):
		return not q.empty() or (self.sm and self.sm.is_max_speaking)

	def wait_until_silent(self):
		while self.is_speaking():
			time.sleep(0.1)
		# Mechanical settling time for Dell Latitude
		time.sleep(0.8)

	def listen(self):
		"""
		Use self= Speaker(ruby_settings), selfto invoke
		"""
		winsound.Beep(self.prefs.LISTEN_TONE, 100)

	def click_left_tone(self):
		"""
		Use self= Speaker(ruby_settings), selfto invoke
		"""
		winsound.Beep(self.prefs.PAUSE_TONE, self.prefs.CLICK_LEFT_TIME)
	
	def click_right(self):
		"""
		Use self= Speaker(ruby_settings), selfto invoke
		"""
		winsound.Beep(self.prefs.PAUSE_TONE, 250)
		time.sleep(0.005)
		winsound.Beep(self.prefs.PAUSE_TONE, 250)
		
	def stop_listen(self):
		"""
		Use self= Speaker(ruby_settings), self to invoke
		"""
		winsound.Beep(self.prefs.LISTEN_TONE, 50)
		time.sleep(0.005)
		winsound.Beep(self.prefs.LISTEN_TONE, 50)

	def _callback(self, indata, frames, time, status):
		q.put(bytes(indata))

	def get_intent(self, bypass_sleep=False):
		"""
		Use self= Speaker(ruby_settings), selfto invoke
		"""
		left_click = 0x01
		right_click = 0x02

		while True: # Outer Loop: Handles Re-entry after Pause
			start_listening_time = time.time()
			print("speaker-get_intent[LISTENING LOCALLY...]")
			self.listen()

			# The Mic stream is scoped here; it closes automatically when we 'break'
			with sd.RawInputStream(samplerate=16000, blocksize=8000, dtype='int16',
								   channels=1, callback=self._callback, device=1):     
				
				rec = KaldiRecognizer(model_brain, 16000)
				
				inner_listening = True
				while inner_listening:
					# A. Check Voice Queue
					try:
						data = q.get_nowait()
						if rec.AcceptWaveform(data):
							result = json.loads(rec.Result())
							text = result.get("text", "").lower().strip()
							if text:
								self.stop_listen()
								return text
					except queue.Empty:
						pass

					# B. Check Physical Clicks
					if win32api.GetAsyncKeyState(left_click) & 0x8000:
						self.stop_listen()
						return "yes"
					
					if win32api.GetAsyncKeyState(right_click) & 0x8000:
						self.stop_listen()
						return "no"

					# C. Timeout Check
					if not bypass_sleep:
						elapsed = time.time() - start_listening_time
						if elapsed > self.prefs.RESPONSE_TIMEOUT:
							self.stop_listen()
							inner_listening = False # Break the inner loop to close mic
				
			# 3. IF WE ARE HERE: The Mic is closed. Enter Pause.
			self.begin_pause()
			# After begin_pause returns, the Outer Loop starts over at the top.

	def begin_pause(self):
		"""
		Music-filled idle state. Blocks mic until a mouse click.
		"""
		WAKE_MUSIC = self.prefs.MUSIC_FILE 
		left_click = 0x01
		right_click = 0x02
		
		# 1. FLUSH: Clear the initial state to prevent immediate wake-up
		win32api.GetAsyncKeyState(left_click)
		win32api.GetAsyncKeyState(right_click)		# Use absolute path if possible or verify relative to root
		
		print(f"[SYSTEM]: Entering Pause Mode. Playing: {WAKE_MUSIC}")
		
		# Start background music
		try:
			# Added winsound.SND_FILENAME to specify we are passing a path
			winsound.PlaySound(
				WAKE_MUSIC, 
				winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_LOOP | winsound.SND_NODEFAULT
			)
		except Exception as e:
			print(f"[ERROR]: Could not play pause music: {e}")

		while True:
			l_state = win32api.GetAsyncKeyState(left_click)
			r_state = win32api.GetAsyncKeyState(right_click)

			# Check for Left or Right Click to wake up
			if (l_state & 0x8000) or (r_state & 0x8000):
				# Stop Music
				winsound.PlaySound(None, winsound.SND_PURGE)
				time.sleep(0.5) # Longer debounce to prevent immediate re-trigger
				
				print("[SYSTEM]: Wake signal received. Re-enabling mic.")
				return 
				
			time.sleep(0.1)

	
		