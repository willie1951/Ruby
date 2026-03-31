#settings_manager.py
import os
import sqlite3

import globals
from globals import *
from data.db_interface import DatabaseInterface
myworld = DatabaseInterface() 
class SettingsManager:
	def __init__(self, memory):
		# Load initial values into memory
		self.memory = memory
		self.myworld = myworld
		self.prefs = self.myworld.prefs
		self.voice_rate = 170
		self.timeout = 8
		self.tone = 600
		#self.sync_all()

	def update_setting(self, key_name, value):
		"""Updates memory, the .py file, and the .db file."""
		# 1. Update Memory (Mapping short keys to class variables)
		if "rate" in key_name.lower(): self.voice_rate = value
		elif "timeout" in key_name.lower(): self.timeout = value
		elif "tone" in key_name.lower(): self.tone = value
		
		# 2. Update .py file
		lines = []
		with open(self.prefs_path, "r") as f:
			lines = f.readlines()
		
		with open(self.prefs_path, "w") as f:
			for line in lines:
				# Using 'in' instead of '==' to handle possible whitespace/comments
				if key_name.upper() in line and "=" in line:
					f.write(f"{key_name.upper()} = {value}\n")
				else:
					f.write(line)
		
		# 3. Update myworld.db
		self._update_db()
	
	def _update_db(self):
		"""Internal method to keep myworld.db in sync."""
		try:
			cursor = self.memory.to_myworld.cursor() 			
			
			# Ensure the table exists for these shared parameters
			cursor.execute('''CREATE TABLE IF NOT EXISTS user_preferences 
							 (key TEXT PRIMARY KEY, value TEXT)''')
			
			# Note: Your schema uses value TEXT, so we cast to string
			data = [
				('VOICE_RATE', str(self.voice_rate)),
				('RESPONSE_TIMEOUT', str(self.timeout)),
				('LISTEN_TONE', str(self.tone))
			]
			
			cursor.executemany("INSERT OR REPLACE INTO \
					  user_preferences (key, value) VALUES (?, ?)", data)
			self.memory.to_myworld.commit()
			
		except Exception as e:
			print(f"[DB ERROR]: Could not sync user_preferences to myworld.db: {e}")

	def update_monitor_offset(self, monitor_index, new_x, new_y):
		"""
		The 'Silent Recalibrator'. 
		Updates the DB and immediately updates the RAM mirror for the Navigator.
		"""
		try:
			# 1. Update the Database (Disk)
			
			cursor = self.memory.to_myworld.cursor()
			query = "UPDATE monitors SET offset_x = ?, offset_y = ? WHERE monitor_index = ?"
			cursor.execute(query, (new_x, new_y, monitor_index))
			self.memory.to_myworld.commit()
			
			
			# 2. Update the RAM Mirror (The 'Dots')
			# This allows diagnostics to see the fix instantly without a reload
			setattr(self, f"SCREEN_{monitor_index}_OFFSET_X", new_x)
			setattr(self, f"SCREEN_{monitor_index}_OFFSET_Y", new_y)
			
			print(f"[RECALIBRATION]: Monitor {monitor_index} synced to {new_x}, {new_y}")
		except Exception as e:
			print(f"[ERROR]: Monitor sync failed: {e}")