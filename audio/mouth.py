import pyttsx3
import sys

def talk(rate, voice_idx, text):
	try:
		engine = pyttsx3.init()
		
		# Set Rate
		engine.setProperty('rate', int(rate))
		
		# Set Voice
		voices = engine.getProperty('voices')
		if int(voice_idx) < len(voices):
			engine.setProperty('voice', voices[int(voice_idx)].id)
		
		engine.say(text)
		engine.runAndWait()
	except Exception as e:
		# Minimal error reporting to avoid hanging
		pass

if __name__ == "__main__":
	# Expecting: mouth.py <rate> <voice_idx> <text>
	if len(sys.argv) > 3:
		r = sys.argv[1]
		v = sys.argv[2]
		t = " ".join(sys.argv[3:]) # Catch all remaining words as text
		talk(r, v, t)