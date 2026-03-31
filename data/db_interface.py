#db_interface.py
"""
in /data
Encapsulation: Everything to do with SQLite is now inside the DatabaseInterface 
class. In main.py, you'll just do memory = DatabaseInterface() and call 
memory.check_health().

Dual-Monitor Friendly: It stores everything as offsets, which works perfectly 
with the "Anchor" logic you built for Screen 2.

Pruning Ready: By tracking access_count and last_accessed, you have the data 
needed to automatically delete "old" screens if you ever hit that 1% limit.
"""
from typing import TYPE_CHECKING
if TYPE_CHECKING:
	from audio.navigator import Navigator

import sys
import os
import sqlite3
import shutil
#import datetime
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import globals
from globals import *

class DatabaseInterface:
	def __init__(self):
		# Tiered Database Mapping
		#self.path_myworld = "data/myworld.db"
		self.to_myworld = sqlite3.connect(globals.db_path, check_same_thread=False)
		self.to_myworld.row_factory = sqlite3.Row # Allows accessing columns by name	
  
		self.initialize_myworld()
		
	def get_user_name(self):
		"""Retrieves the saved user name from session state."""
		query = "SELECT value FROM session_state WHERE key = 'USER_NAME'"
		result = self.to_myworld.execute(query).fetchone()
		return result['value'] if result else None

	def save_user_name(self, name):
		"""Saves the user name to the session state table."""
		query = "INSERT OR REPLACE INTO session_state (key, value) VALUES ('USER_NAME', ?)"
		self.to_myworld.execute(query, (name,))
		self.to_myworld.commit()

	def initialize_myworld(self):
		"""Initializes the primary MyWorld database structure and loads preferences."""
		print("db_interface->initialize_myworld")

		# 1. Validation Layer: If the database is missing, the delivery failed.
		if not os.path.exists(globals.db_path):
			try:
				with open(globals.error_log_path, 'a') as log:
					log.write(f"CRITICAL FAILURE: myworld.db not found at {globals.db_path}. Execution halted.\n")
			except:
				pass
			os._exit(1)

		schema = """
			CREATE TABLE IF NOT EXISTS states (
				id INTEGER PRIMARY KEY AUTOINCREMENT,
				name TEXT UNIQUE,
				access_count INTEGER DEFAULT 0,
				last_accessed DATETIME
			);
			CREATE TABLE IF NOT EXISTS ui_elements (
				id INTEGER PRIMARY KEY AUTOINCREMENT,
				state_id INTEGER,
				name TEXT,
				offset_x INTEGER,
				offset_y INTEGER,
				width INTEGER,
				height INTEGER,
				FOREIGN KEY (state_id) REFERENCES states (id)
			);
			CREATE TABLE IF NOT EXISTS session_state (
				key TEXT PRIMARY KEY,
				value TEXT,
				updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
			);
			CREATE TABLE IF NOT EXISTS user_preferences (
				key TEXT PRIMARY KEY, 
				value TEXT
			);
			CREATE TABLE IF NOT EXISTS meta (
				key TEXT PRIMARY KEY, 
				val INTEGER
			);
		"""

		try:
			# 2. Execute the full schema FIRST
			self.to_myworld.executescript(schema)
			
			# 3. Set the disk health threshold
			threshold = self.get_disk_threshold()
			self.to_myworld.execute("INSERT OR REPLACE INTO meta VALUES ('threshold', ?)", (threshold,))
			
			# 4. Finalize the DB setup
			self.to_myworld.commit()

			# 5. NOW create the container and fill it
			# This ensures the table definitely exists before we read it
			self.prefs = type('Prefs', (), {})()
			self.populate_prefs(self.prefs)
			
			print("db_interface->myworld initialization and pref loading complete.")

		except Exception as e:
			print(f"[CRITICAL ERROR]: Failed to initialize MyWorld: {e}")

	def get_disk_threshold(self):
		"""Calculates 1% of free space for pruning logic."""
		_, _, free = shutil.disk_usage("/")
		return int(free * 0.01)

	def set_state(self, key, value):
		"""Saves a temporary session state variable to MyWorld."""
		print(f"db_interface->set_state: {key} = {value}")
		query = "INSERT OR REPLACE INTO session_state (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)"
		
		# Execute and commit using the persistent bridge
		self.to_myworld.execute(query, (key, str(value)))
		self.to_myworld.commit()

	def get_state(self, key, default=None):
		"""Retrieves a session state variable with automatic type conversion."""
		query = "SELECT value FROM session_state WHERE key = ?"
		
		# Fetch using persistent bridge + Row factory
		result = self.to_myworld.execute(query, (key,)).fetchone()
		
		if result:
			# Use result['value'] thanks to row_factory
			val = result['value']
			
			# Boolean Conversion
			if val.lower() == 'true': return True
			if val.lower() == 'false': return False
			
			# Numeric Conversion
			try: 
				return int(val)
			except ValueError: 
				return val
				
		return default

	def save_state(self, key, value):
		"""Saves a system preference to the session_state table."""
		
		query = "INSERT OR REPLACE INTO session_state (key, value) VALUES (?, ?)"
		self.to_myworld.execute(query, (key, str(value)))
		self.to_myworld.commit()

	def update_prefs(self, key, value):
		"""
		Saves a preference to the user_preferences table.
		If the key exists, it updates the value. If not, it creates it.
		"""
		query = "INSERT OR REPLACE INTO user_preferences (key, value) VALUES (?, ?)"
		try:
			# We cast to string because SQLite 'value' column is TEXT
			self.to_myworld.execute(query, (key, str(value)))
			self.to_myworld.commit()
			# print(f"db_interface->Updated {key} to {value}")
		except Exception as e:
			print(f"[DB ERROR] Failed to update preference {key}: {e}")
   
	def update_monitor_offset(self, monitor_index, new_x, new_y):
		"""
		Silently updates the hardware offsets in data/myworld.db.
		This is called by the SettingsManager during a Coordinate Mismatch.
		"""
		
		query = "UPDATE monitors SET offset_x = ?, offset_y = ? WHERE monitor_index = ?"
		self.to_myworld.execute(query, (new_x, new_y, monitor_index))
		self.to_myworld.commit()
		
		# Log for developer, silent for user
		print(f"[SQL]: Recalibrated Monitor {monitor_index} to {new_x}, {new_y}")

	def log_app_usage(self, app_name):
		"""
		Logs app usage into the common_apps table.
		Increments access_count if the app exists.
		"""
		cursor = self.to_myworld.cursor()
		
		# The 'UPSERT' query we discussed
		query = """
		INSERT INTO common_apps (app_name, access_count, last_accessed)
		VALUES (?, 1, CURRENT_TIMESTAMP)
		ON CONFLICT(app_name) DO UPDATE SET 
			access_count = access_count + 1,
			last_accessed = CURRENT_TIMESTAMP;
		"""
		
		try:
			# .strip().lower() ensures 'Chrome' and 'chrome' are the same
			cursor.execute(query, (app_name.strip().lower(),))
			self.to_myworld.commit()
			print(f"db->logged usage for: {app_name}")
		except Exception as e:
			print(f"[ERROR] DatabaseInterface failed to log {app_name}: {e}")

	def check_app_experience(self, app_name: str) -> bool:
		"""Checks if we have successfully launched this app before."""
		cursor = self.to_myworld.cursor()
		
		# We look for a record that matches the app name 
		# and has valid coordinate data (indicating a successful past launch)
		query = "SELECT count(*) FROM ui_elements WHERE element_name = ? AND context = 'app_anchor'"
		
		try:
			cursor.execute(query, (app_name.lower(),))
			result = cursor.fetchone()
			
			# If count > 0, we've 'learned' this app
			has_experience = result[0] > 0
			print(f"db_interface->Experience for '{app_name}': {has_experience}")
			return has_experience
			
		except sqlite3.Error as e:
			print(f"db_interface->Error checking experience: {e}")
			return False

	def check_for_anchors(self, app_name):
		cursor = self.to_myworld.cursor()
		# Query to find any saved locations for the given app_name
		cursor.execute(
			"SELECT ctrl_type, x, y FROM app_controls WHERE app_id = ?", 
			(app_name,)
		)
		
		anchors = cursor.fetchall()
		
		if not anchors:
			print(f"Ruby: No anchors found for {app_name}.")
		else:
			count = len(anchors)
			print(f"Ruby: Found {count} anchors.")
			
		return anchors
	
	def get_last_document(self):
		"""retrieves the last saved document"""
		try:
			cursor = self.to_myworld.cursor()
		
			query = "SELECT filename FROM recent_files ORDER BY last_accessed DESC LIMIT 1"
			cursor.execute(query)
			row = cursor.fetchone()
			if row:
				doc_name = row[0]
			return doc_name
		
		except Exception as e:
					print(f"Ruby: Database error: {e}")
					return None

	def get_last_unfinished_document(self):
		"""retrieves the last saved document"""
		doc_name = None
		try:
			cursor = self.to_myworld.cursor()
		
			query = "SELECT filename FROM recent_files WHERE last_paragraph > 0 ORDER BY rowid DESC LIMIT 1"
			cursor.execute(query)
			row = cursor.fetchone()
			if row:
				doc_name = row[0]
			return doc_name
		
		except Exception as e:
					print(f"Ruby: Database error: {e}")
					return None
		
	def get_last_paragraph(self, doc_name):
		"""
		Retrieves the saved paragraph index for the document.
		Returns 1 if no record is found or if the record is 0.
		"""
		try:
			cursor = self.to_myworld.cursor()
			
			query = "SELECT last_paragraph FROM recent_files WHERE filename = ?"
			cursor.execute(query, (doc_name,))
			result = cursor.fetchone()

			# result[0] is our paragraph_index
			if result and result[0] > 0:
				return result[0]
			
			# If 0 or not found, start at the first paragraph
			return 1

		except Exception as e:
			print(f"Ruby: Error fetching progress: {e}")
			return 1
		
	def save_last_paragraph(self, doc_name, paragraph_index, navigator):
		"""
		Updates the database with the last read paragraph for a specific document.
		"""
		try:
			# 1. Use your existing connection
			cursor = self.to_myworld.cursor()
			
			# 2. Check if the file already exists
			check_query = "SELECT rowid FROM recent_files WHERE filename = ?"
			cursor.execute(check_query, (doc_name,))
			result = cursor.fetchone()

			if result:
				# Update existing record
				query = "UPDATE recent_files SET last_paragraph = ?, last_accessed = CURRENT_TIMESTAMP WHERE filename = ?"
				params = (paragraph_index, doc_name)
			else:
				# If navigator is white, ensure you are passing the actual object, not a string
				full_pathname = os.path.join(globals.Documents_folder, doc_name)
				
				query = "INSERT INTO recent_files (path, filename, last_paragraph, last_accessed) VALUES (?, ?, ?, CURRENT_TIMESTAMP)"
				params = (full_pathname, doc_name, paragraph_index)

			cursor.execute(query, params)
			self.to_myworld.commit()
			
		except Exception as e:
			print(f"Ruby: Error saving position: {e}")

	def get_anchor_save(self, item_name):
		"""
		Queries myworld for a specific anchor by name.
		Returns a tuple of (offset_x, offset_y) or None.
		"""
		cursor = self.to_myworld.cursor()
		# Context 10 is our Desktop layer
		query = "SELECT offset_x, offset_y FROM ui_elements WHERE name = ? AND context = 10"
		cursor.execute(query, (item_name,))
		row = cursor.fetchone()
		
		if row:
			# Returns (x, y) as a simple tuple
			return (row['offset_x'], row['offset_y'])
		return None

	def bootstrap_desktop_save(self):
		cursor = self.to_myworld.cursor()
		
		# Check for existing desktop entry
		cursor.execute("SELECT app_id FROM apps WHERE app_id = 'desktop'")
		if cursor.fetchone() is None:
			# 1. Register Parent
			cursor.execute("INSERT INTO apps (app_id, executable) VALUES (?, ?)", ("desktop", "explorer.exe"))
			
			# 2. Get real desktop file names
			path = os.path.join(os.environ['USERPROFILE'], 'Desktop')
			try:				
				files = [f for f in os.listdir(path) if not f.startswith('desktop.ini')]
				for filename in files:
					# Use 0,0 as placeholders until the first sonar scan
					cursor.execute("""
						INSERT INTO components (app_id, role, rel_x, rel_y) 
						VALUES ('desktop', ?, 0, 0)
					""", (filename,))
				self.to_myworld.commit()
				print(f"Ruby: Auto-discovered {len(files)} desktop icons.")
			except Exception as e:
				print(f"Bootstrap Error: {e}")
						
	def get_last_anchor_save(self):
		"""Retrieves the most recent high-level 'Head' node from the Anchor Stack."""
		
		# Finds the state with the most recent access timestamp
		query = "SELECT name FROM states ORDER BY last_accessed DESC LIMIT 1"
		result = self.to_myworld.execute(query).fetchone()
		
		return {"name": result[0]} if result else None
		
	def get_element_with_fallback_save(self, element_name, context="CHROME"):
		"""
		1. Look in 'applications.db' (Factory World Section)
		2. If missing, look in 'myworld.db' (User Section)
		3. If missing, return None (Triggers a new Sonar Scan)
		"""
		# Search World Section (Static)
		world_item = self.get_memory_items(context, db_type="apps")
		for item in world_item:
			if item[0] == element_name: return item

		# Search User Section (Dynamic)
		user_item = self.get_memory_items(context, db_type="myworld")
		for item in user_item:
			if item[0] == element_name: return item
			
		return None
	
	def prune_myworld_save(self):
		"""Deletes the least-accessed 10% of user-learned states."""
		
		# Delete elements belonging to the oldest/least used states
		self.to_myworld.execute("""
			DELETE FROM ui_elements WHERE state_id IN (
				SELECT id FROM states ORDER BY last_accessed ASC, access_count ASC LIMIT 5
			)
		""")
		self.to_myworld.execute("DELETE FROM states WHERE id NOT IN (SELECT state_id FROM ui_elements)")
		self.to_myworld.commit()
				
	def count_taskbar_items_in_myworld_save(self, state_instance):
		"""
		Retrieves counts specifically from the self.myworld deliverable.
		Prepares the system for the initial Orientation Report.
		"""
		# 1. Query self.myworld for the specific deliverable contexts
		# Context 10: Desktop, Context 8: Taskbar
		#desktop_items = self.myworld.get_memory_items(10)
		taskbar_items = self.get_memory_items(8)

		#desktop_count = len(desktop_items)
		taskbar_count = len(taskbar_items)
		
		return taskbar_count #desktop_count, taskbar_count

	def check_health(self):
		print("db_interface->check_health")
		# Use the variable defined in __init__ instead of a dictionary
		
		if os.path.exists(globals.db_path):
			# Perform a simple integrity check
			try:
				myworld_size = os.path.getsize(globals.db_path)
				# Use the existing persistent connection instead of opening/closing
				cursor = self.to_myworld.cursor()
				row = cursor.execute("SELECT val FROM meta WHERE key='threshold'").fetchone()
				threshold = row[0] if row else self.get_disk_threshold()
			except:
				return False
		
		if myworld_size > threshold:
			print("[DATA]: Threshold reached. Pruning oldest items...")
			self.prune_myworld()
			return False
		return True
		
	def populate_prefs(self, target_obj):
		"""
		Fetches all key/value pairs from the database and attaches 
		them as attributes to the target object.
		"""
		try:
			cursor = self.to_myworld.cursor()
			# We use the user_preferences table you defined in the schema
			cursor.execute("SELECT key, value FROM user_preferences")

			rows = cursor.fetchall()
			for row in rows:
				clean_key = row['key'].upper()
				val = row['value']

				# Attempt type conversion (Boolean/Int) for logic gates
				if val.lower() == 'true': val = True
				elif val.lower() == 'false': val = False
				else:
					try:
						val = int(val)
					except ValueError:
						pass # Stay as string

				setattr(target_obj, clean_key, val)
			
			print(f"db_interface->{len(rows)} preferences loaded into memory.")
		except Exception as e:
			print(f"db_interface->Preference load failure: {e}")
   
	def set_pref(self, key, value):
		"""
		Saves or updates a preference in the database.
		"""

		clean_key = key.upper()
		query = "INSERT OR REPLACE INTO user_preferences (key, value) VALUES (?, ?)"
		try:
			self.to_myworld.execute(query, (clean_key, str(value)))
			self.to_myworld.commit()
		except Exception as e:
			print(f"db_interface->Failed to set pref {clean_key}: {e}")

  