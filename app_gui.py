import csv
import io
import os
import re
import zipfile

import requests
import streamlit as st
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


MAX_SCAN_LIMIT = 5000


def normalize_channel_input(identifier):
    if not identifier:
        raise ValueError("Channel is required")
    if identifier.startswith(("http://", "https://")):
        identifier = identifier.rstrip("/")
        if "/@" in identifier:
            return "@" + identifier.split("/@")[-1]
        if "/channel/" in identifier:
            return identifier.split("/channel/")[-1]
        if "/user/" in identifier:
            return identifier.split("/user/")[-1]
        return identifier.split("/")[-1]
    return identifier


def get_channel_id(youtube, channel_identifier):
    channel_identifier = normalize_channel_input(channel_identifier)
    if channel_identifier.startswith("UC"):
        return channel_identifier

    username = channel_identifier.replace("@", "")
    response = youtube.channels().list(forUsername=username, part="id").execute()
    items = response.get("items", [])
    if items:
        return items[0]["id"]

    response = youtube.search().list(
        q=channel_identifier, type="channel", part="id", maxResults=1
    ).execute()
    items = response.get("items", [])
    if not items:
        raise ValueError(f"Channel not found: {channel_identifier}")
    return items[0]["id"]["channelId"]


def get_channel_stats(youtube, channel_id):
    response = youtube.channels().list(
        id=channel_id, part="snippet,statistics"
    ).execute()
    items = response.get("items", [])
    if not items:
        return {}
    item = items[0]
    stats = item.get("statistics", {})
    return {
        "channel_id": channel_id,
        "channel_title": item.get("snippet", {}).get("title"),
        "subscriber_count": int(stats.get("subscriberCount", 0)),
        "video_count": int(stats.get("videoCount", 0)),
        "view_count": int(stats.get("viewCount", 0)),
    }


def get_uploads_playlist_id(youtube, channel_id):
    response = youtube.channels().list(
        id=channel_id, part="contentDetails"
    ).execute()
    items = response.get("items", [])
    if not items:
        raise ValueError(f"Channel not found: {channel_id}")
    return items[0]["contentDetails"]["relatedPlaylists"]["uploads"]


def get_video_ids_from_playlist(youtube, playlist_id, max_results=500):
    video_ids = []
    next_page_token = None
    while len(video_ids) < max_results:
        response = youtube.playlistItems().list(
            playlistId=playlist_id,
            part="contentDetails",
            maxResults=min(50, max_results - len(video_ids)),
            pageToken=next_page_token,
        ).execute()
        video_ids.extend(
            item["contentDetails"]["videoId"]
            for item in response.get("items", [])
        )
        next_page_token = response.get("nextPageToken")
        if not next_page_token:
            break
    return video_ids


def fetch_video_metadata(youtube, video_ids):
    results = []
    for index in range(0, len(video_ids), 50):
        chunk = video_ids[index:index + 50]
        response = youtube.videos().list(
            id=",".join(chunk), part="snippet,statistics,contentDetails"
        ).execute()
        for item in response.get("items", []):
            stats = item.get("statistics", {})
            snippet = item.get("snippet", {})
            content = item.get("contentDetails", {})
            results.append({
                "video_id": item.get("id"),
                "title": snippet.get("title"),
                "description": snippet.get("description"),
                "publish_time": snippet.get("publishedAt"),
                "thumbnail_url": (
                    snippet.get("thumbnails", {}).get("high", {}).get("url")
                    or snippet.get("thumbnails", {}).get("default", {}).get("url")
                ),
                "view_count": int(stats.get("viewCount", 0)),
                "like_count": (
                    int(stats["likeCount"]) if stats.get("likeCount") is not None
                    else None
                ),
                "comment_count": (
                    int(stats["commentCount"])
                    if stats.get("commentCount") is not None else None
                ),
                "duration": content.get("duration"),
                "tags": "|".join(snippet.get("tags", [])),
            })
    return results


def get_channel_videos(youtube, channel_identifier, top_n, max_videos, sort_order):
    channel_id = get_channel_id(youtube, channel_identifier)
    playlist_id = get_uploads_playlist_id(youtube, channel_id)
    video_ids = get_video_ids_from_playlist(
        youtube, playlist_id, max_results=max_videos
    )
    videos = fetch_video_metadata(youtube, video_ids)
    channel_stats = get_channel_stats(youtube, channel_id)

    sort_keys = {
        "Most views": lambda video: video.get("view_count", 0),
        "Newest first": lambda video: video.get("publish_time") or "",
        "Oldest first": lambda video: video.get("publish_time") or "",
    }
    videos.sort(
        key=sort_keys[sort_order],
        reverse=sort_order != "Oldest first",
    )
    selected_videos = videos[:top_n]
    for video in selected_videos:
        video.update({
            "channel_id": channel_id,
            "channel_title": channel_stats.get("channel_title"),
            "subscriber_count": channel_stats.get("subscriber_count"),
            "channel_view_count": channel_stats.get("view_count"),
            "channel_video_count": channel_stats.get("video_count"),
        })
    return selected_videos, channel_stats.get("channel_title") or "channel"


CSV_FIELDS = [
    "video_id", "title", "publish_time", "view_count", "like_count",
    "comment_count", "duration", "thumbnail_url", "tags", "description",
    "channel_id", "channel_title", "subscriber_count", "channel_view_count",
    "channel_video_count",
]


def make_csv(rows):
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=CSV_FIELDS)
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode("utf-8-sig")


def make_thumbnail_zip(rows):
    output = io.BytesIO()
    downloaded = 0
    failures = []
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for row in rows:
            url = row.get("thumbnail_url")
            video_id = row.get("video_id")
            if not url or not video_id:
                failures.append(video_id or "unknown video")
                continue
            try:
                response = requests.get(
                    url, headers={"User-Agent": "Mozilla/5.0"}, timeout=30
                )
                response.raise_for_status()
                extension = {
                    "image/jpeg": ".jpg",
                    "image/png": ".png",
                    "image/webp": ".webp",
                }.get(
                    response.headers.get("Content-Type", "")
                    .split(";", 1)[0].lower(),
                    ".jpg",
                )
                archive.writestr(f"{video_id}{extension}", response.content)
                downloaded += 1
            except requests.RequestException:
                failures.append(video_id)
    if not downloaded:
        return None, 0, failures
    return output.getvalue(), downloaded, failures


def safe_filename(value):
    filename = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._")
    return filename or "channel"


st.set_page_config(page_title="YouTube Channel Scraper", page_icon="▶️")
st.title("YouTube Channel Scraper")
st.write(
    "Enter your own YouTube Data API key below, or configure YT_API_KEY "
    "in the server terminal. A key entered below takes priority. Keys are "
    "used for the scrape and are not saved by the app."
)

with st.form("scrape_form", clear_on_submit=True):
    api_key = st.text_input(
        "YouTube Data API key", type="password",
        help=(
            "Use a key with YouTube Data API v3 enabled. Leave blank to use "
            "the server's YT_API_KEY, if configured."
        ),
    )
    channel = st.text_input("Channel URL, @handle, username, or channel ID")
    col1, col2 = st.columns(2)
    with col1:
        result_count = st.number_input(
            "Number of videos to return", min_value=1, max_value=5000,
            value=20, step=1,
        )
    with col2:
        scan_limit = st.number_input(
            "Maximum recent uploads to scan", min_value=1,
            max_value=MAX_SCAN_LIMIT, value=500, step=50,
            help=(
                "Sorting applies to this many uploads. Increase this to "
                "include older videos when sorting by views or oldest first."
            ),
        )
    sort_order = st.selectbox(
        "Sort videos by",
        ["Most views", "Newest first", "Oldest first"],
    )
    include_thumbnails = st.checkbox("Prepare thumbnails for download")
    submitted = st.form_submit_button("Fetch videos")

if submitted:
    for key in (
        "scrape_videos",
        "scrape_channel_title",
        "scrape_include_thumbnails",
        "scrape_thumbnail_data",
        "scrape_thumbnail_count",
        "scrape_thumbnail_failures",
    ):
        st.session_state.pop(key, None)

    effective_api_key = api_key.strip() or os.environ.get("YT_API_KEY", "").strip()
    if not effective_api_key:
        st.error(
            "Enter your YouTube Data API key, or configure YT_API_KEY "
            "in the server environment."
        )
    elif not channel.strip():
        st.error("Enter a YouTube channel URL, @handle, username, or ID.")
    else:
        try:
            youtube = build(
                "youtube", "v3", developerKey=effective_api_key,
                cache_discovery=False,
            )
            with st.spinner("Fetching channel videos..."):
                videos, channel_title = get_channel_videos(
                    youtube, channel.strip(), int(result_count),
                    int(scan_limit), sort_order,
                )
            st.session_state["scrape_videos"] = videos
            st.session_state["scrape_channel_title"] = channel_title
            st.session_state["scrape_include_thumbnails"] = include_thumbnails
            if include_thumbnails:
                with st.spinner("Preparing thumbnail download..."):
                    thumbnail_data, thumbnail_count, thumbnail_failures = (
                        make_thumbnail_zip(videos)
                    )
                st.session_state["scrape_thumbnail_data"] = thumbnail_data
                st.session_state["scrape_thumbnail_count"] = thumbnail_count
                st.session_state["scrape_thumbnail_failures"] = len(
                    thumbnail_failures
                )
            else:
                st.session_state.pop("scrape_thumbnail_data", None)
                st.session_state.pop("scrape_thumbnail_count", None)
                st.session_state.pop("scrape_thumbnail_failures", None)
            st.success(f"Found {len(videos)} videos for {channel_title}.")
        except ValueError as exc:
            st.error(f"Could not fetch videos: {exc}")
        except HttpError as exc:
            st.error(
                "The request failed. Check that the API key is valid, "
                "YouTube Data API v3 is enabled, and quota is available. "
                f"YouTube API returned HTTP {exc.status_code}: {exc.reason}"
            )

if st.session_state.get("scrape_videos"):
    videos = st.session_state["scrape_videos"]
    filename = safe_filename(st.session_state["scrape_channel_title"])
    st.dataframe(
        [
            {
                "Title": video.get("title"),
                "Published": video.get("publish_time"),
                "Views": video.get("view_count"),
                "Video ID": video.get("video_id"),
            }
            for video in videos
        ],
        use_container_width=True,
    )
    st.download_button(
        "Download CSV",
        data=make_csv(videos),
        file_name=f"{filename}_videos.csv",
        mime="text/csv",
    )
    if st.session_state.get("scrape_include_thumbnails"):
        thumbnail_data = st.session_state.get("scrape_thumbnail_data")
        thumbnail_count = st.session_state.get("scrape_thumbnail_count", 0)
        thumbnail_failures = st.session_state.get(
            "scrape_thumbnail_failures", 0
        )
        if thumbnail_data:
            st.download_button(
                f"Download thumbnails ZIP ({thumbnail_count})",
                data=thumbnail_data,
                file_name=f"{filename}_thumbnails.zip",
                mime="application/zip",
            )
            if thumbnail_failures:
                st.warning(
                    f"{thumbnail_failures} thumbnail(s) could not be downloaded."
                )
        else:
            st.warning("No thumbnails could be downloaded.")
