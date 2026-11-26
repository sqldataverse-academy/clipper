"""Checks that everything is installed and configured.  Run:  python check_setup.py"""
import shutil
import sys

import requests

from clipper import config

ok = True


def show(good: bool, msg: str, fix: str = ""):
    global ok
    print(("  [OK]   " if good else "  [!!]   ") + msg + ("" if good else f"\n         -> {fix}"))
    ok = ok and good


print("\nClipper setup check\n")
show(sys.version_info >= (3, 10), f"Python {sys.version.split()[0]}", "Install Python 3.10 or newer")
show(bool(shutil.which("ffmpeg")), "FFmpeg installed", "Install FFmpeg and add it to PATH (SETUP.md step 1)")
st = config.platform_status()
show(st["claude"], "Claude API key set", "Put ANTHROPIC_API_KEY in .env")
if st["claude"]:
    try:
        import anthropic
        anthropic.Anthropic().models.retrieve(config.CLAUDE_MODEL)
        show(True, f"Claude API key works ({config.CLAUDE_MODEL})")
    except Exception as e:
        show(False, "Claude API key works", f"{e}")

show(st["youtube"], "YouTube OAuth file present", "SETUP.md step 3")
show(config.YOUTUBE_TOKEN_FILE.exists(), "YouTube channel connected", "Run: python connect_youtube.py")

if config.META_PAGE_ACCESS_TOKEN:
    g = f"https://graph.facebook.com/{config.META_GRAPH_VERSION}"
    tok = config.META_PAGE_ACCESS_TOKEN
    if config.FACEBOOK_PAGE_ID:
        r = requests.get(f"{g}/{config.FACEBOOK_PAGE_ID}", params={"fields": "name", "access_token": tok}).json()
        show("name" in r, f"Facebook Page: {r.get('name', r.get('error', {}).get('message'))}", "Check FACEBOOK_PAGE_ID and token")
    else:
        show(False, "FACEBOOK_PAGE_ID set", "SETUP.md step 4")
    if config.INSTAGRAM_USER_ID:
        r = requests.get(f"{g}/{config.INSTAGRAM_USER_ID}", params={"fields": "username", "access_token": tok}).json()
        show("username" in r, f"Instagram: @{r.get('username', r.get('error', {}).get('message'))}", "Check INSTAGRAM_USER_ID and token")
    else:
        show(False, "INSTAGRAM_USER_ID set", "SETUP.md step 4")
else:
    show(False, "Meta (Instagram/Facebook) token set", "SETUP.md step 4")

print("\nAll good! Run: python app.py\n" if ok else "\nFix the [!!] items above (you can still run the app for the parts that work).\n")
