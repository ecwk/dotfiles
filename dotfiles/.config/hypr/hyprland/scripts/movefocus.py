import sys
import subprocess
import threading

from pynput.keyboard import Key, Listener, KeyCode

direction = sys.argv[1]
subprocess.run(['hyprctl', 'dispatch', 'hy3:movefocus', direction])

timer = None

# Collect events until released
def reset_submap():
    subprocess.run(['hyprctl', 'dispatch', 'submap', 'reset'])
    listener.stop()

def start_timer():
    global timer
    if timer:
        timer.cancel()
    timer = threading.Timer(2, reset_submap)
    timer.start()

def on_press(key):
    if key == KeyCode.from_char("h"):
        return start_timer()

start_timer()
listener = Listener(on_press=on_press)
listener.start()
