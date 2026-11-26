# Clipper: one-time setup (about 1 hour)

Do these steps once. After that, you only run `python app.py`.

---

## Step 1: Install Python and FFmpeg (10 min)

**Windows**
1. Install Python 3.11 or newer from https://www.python.org/downloads/. On the first installer screen, tick **"Add python.exe to PATH"**.
2. Open **PowerShell** and install FFmpeg:
   ```
   winget install Gyan.FFmpeg
   ```
   Close PowerShell and open it again so the new PATH takes effect.

**Mac**
```
brew install python ffmpeg
```

Check that both work:
```
python --version
ffmpeg -version
```

## Step 2: Install Clipper (5 min)

Open a terminal inside the `clipper` folder:

**Windows**
```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

**Mac / Linux**
```
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Open `.env` in Notepad or any editor. You'll fill it in during the next steps.

### Claude API key
1. Go to https://console.anthropic.com, sign up, and open **Settings → Billing**. Add about $5 of credit, which covers roughly 20–25 streams.
2. Open **API Keys → Create Key** and copy the key.
3. In `.env`, set `ANTHROPIC_API_KEY=sk-ant-...`

## Step 3: Connect YouTube (15 min)

1. Go to https://console.cloud.google.com and create a **New Project** named "Clipper".
2. Open **APIs & Services → Library**, search **YouTube Data API v3**, and click **Enable**.
3. Open **APIs & Services → OAuth consent screen**:
   - User type: **External**, then fill in the app name and your email.
   - Scopes: you can skip this.
   - Test users: **add your own Google account** (the one that owns the channel).
   - When it's done, click **Publish App** (set it to "In production"). Otherwise your login expires every 7 days. You don't need to submit it for verification.
4. Open **APIs & Services → Credentials → Create credentials → OAuth client ID**:
   - Application type: **Desktop app**
   - Click **Download JSON**, rename the file to `client_secret.json`, and put it in the `clipper/secrets/` folder.
5. In the terminal, with the venv active, run:
   ```
   python connect_youtube.py
   ```
   A browser opens. Pick your channel's Google account. If you see "Google hasn't verified this app", click **Advanced → Go to Clipper**, because it's your own app. Then click **Allow**.

> **Important: videos may upload as Private at first.**
> Google keeps uploads from new API projects **private** until the project passes a free audit.
> To lift this, fill in the YouTube API audit form: https://support.google.com/youtube/contact/yt_api_form
> Until then, you can open YouTube Studio and switch each Short to Public by hand.
>
> **Daily limit:** the free quota allows about **6 YouTube uploads per day**. You can request more on the same form.

## Step 4: Connect Instagram and Facebook (20–30 min)

### 4a. Prepare your accounts
1. In the Instagram app, go to **Settings → Account type and tools** and switch to a **Professional account** (Creator or Business).
2. Link Instagram to your **Facebook Page**: in Instagram go to **Settings → Accounts Center**, or in your Facebook Page go to **Settings → Linked accounts → Instagram**.

### 4b. Create a Meta app
1. Go to https://developers.facebook.com, click **My Apps → Create App**, and choose **"Other" → "Business"**.
2. In the app dashboard, add the products **Instagram Graph API** (or "Instagram") and **Facebook Login for Business**.
3. The app can stay in **Development mode**. It works for accounts you own and administer.

### 4c. Get a token that doesn't expire
1. Open the **Graph API Explorer** at https://developers.facebook.com/tools/explorer/
2. On the right, select your app, then click **Generate Access Token** and add these permissions:
   `pages_show_list`, `pages_read_engagement`, `pages_manage_posts`,
   `instagram_basic`, `instagram_content_publish`, `business_management`.
   Approve the pop-up and select your Page and Instagram account.
3. Copy the token. Open https://developers.facebook.com/tools/debug/accesstoken/, paste it, click **Debug**, then **Extend Access Token** at the bottom. Copy the new long-lived token.
4. Back in Graph API Explorer, paste the long-lived token in the token box and run:
   ```
   me/accounts
   ```
   The result lists your Page. Copy its **`access_token`**: this Page token does not expire. Also copy its **`id`**, which is your Page ID.
5. Paste the Page token in the token box and run (replace PAGE_ID with your Page ID):
   ```
   PAGE_ID?fields=instagram_business_account
   ```
   Copy the `instagram_business_account.id`.
6. Put the values in `.env`:
   ```
   META_PAGE_ACCESS_TOKEN=EAAG....   (Page token from step 4)
   FACEBOOK_PAGE_ID=1234567890
   INSTAGRAM_USER_ID=1784xxxxxxxxxxx
   ```

> Instagram allows **50 API posts per 24 hours**, which is plenty.

## Step 5: Check everything

```
python check_setup.py
```
Fix anything marked `[!!]`, then start the app:
```
python app.py
```
Open **http://localhost:8000**.

---

## Optional settings in `.env`

| Setting | What it does |
|---|---|
| `DEFAULT_NUM_CLIPS` | How many clips per stream (default 8) |
| `MIN_CLIP_SECONDS` / `MAX_CLIP_SECONDS` | Clip length range (default 25–60 s) |
| `WHISPER_MODEL` | Caption accuracy: `base` (fastest), `small` (default), `medium` (best; use with a GPU) |
| `WHISPER_DEVICE` | `cuda` if you have an NVIDIA GPU with CUDA installed, otherwise `cpu` |
| `CAPTION_LANGUAGE` | `en`, `hi`, … Leave empty to auto-detect |
| `POST_LANGUAGE` | Language for titles and captions: `English`, `Hinglish`, `Hindi`… |
| `CAPTION_FONT` | Caption font. For Hindi (Devanagari) captions on Windows use `Nirmala UI` |
| `YOUTUBE_PRIVACY` | `public`, `unlisted` or `private` |
