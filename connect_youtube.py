"""One-time: log in to your YouTube channel. Opens a browser window.

Run:  python connect_youtube.py
"""
from clipper.uploaders.youtube import get_credentials

get_credentials(interactive=True)
print("YouTube connected. You can close this window.")
