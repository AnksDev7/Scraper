# YouTube Scraper

A Streamlit app for collecting video information from a YouTube channel or comments from an individual video. Choose the scraping mode in the app; channel scraping uses the YouTube Data API, while comment scraping uses `yt-dlp`.

## Features

### Channel videos

- Search by channel URL, `@handle`, username, or channel ID.
- Choose how many videos to return and how many recent uploads to scan.
- Sort results by most views, newest first, or oldest first.
- Download video details as a CSV file.
- Optionally download available video thumbnails in a ZIP file.
- Requires a YouTube Data API v3 key.

### Video comments

- Paste a YouTube video URL to fetch its available comments.
- Does not require a YouTube Data API key.
- View the results in the app and download them as a CSV file.
- Uses `yt-dlp`. Results depend on comment availability and YouTube's current access restrictions.

## Requirements

- Python 3
- Packages listed in [`requirements.txt`](requirements.txt)

## Run locally

Open a terminal in the project folder and install the dependencies:

```bash
python -m pip install -r requirements.txt
```

Start the app:

```bash
streamlit run app_gui.py
```

Open the local URL printed by Streamlit, usually `http://localhost:8501`.

## Use the app

1. Choose **Channel videos** or **Video comments** below the app title.
2. For **Channel videos**, enter a YouTube Data API v3 key and the channel identifier, then select the scrape options.
3. For **Video comments**, paste a video URL. An API key is not needed for this mode.
4. Submit the form to view the results, then use the download button to save a CSV or, for channel videos, an optional thumbnail ZIP.

### YouTube Data API key

For channel scraping, provide a key with YouTube Data API v3 enabled in the app, or configure `YT_API_KEY` as an environment variable where the app runs. A key entered in the app takes priority. Do not commit API keys to the repository.

## Deploy with Streamlit

Deploy the repository using your Streamlit hosting provider and set the app's main file to:

```text
app_gui.py
```

Ensure both `app_gui.py` and `Yt_Comment_Scrape.py` are included in the deployed branch. The host should install the packages from `requirements.txt`. To use channel scraping on the hosted app, configure `YT_API_KEY` as an environment variable in the host's app settings. The video-comment mode does not need this key.

## Project files

- [`app_gui.py`](app_gui.py) — Main Streamlit app, channel-video scraping interface, and results downloads.
- [`Yt_Comment_Scrape.py`](Yt_Comment_Scrape.py) — Comment-scraping function used by the app.
- [`requirements.txt`](requirements.txt) — Python package dependencies.
