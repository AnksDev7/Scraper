from yt_dlp import YoutubeDL


COMMENT_FIELDS = [
    "id", "author", "author_id", "text", "timestamp", "like_count",
]


def scrape_video_comments(video_url):
    """Return the available comments for a YouTube video and its reported count."""
    video_url = video_url.strip()
    if not video_url:
        raise ValueError("Video URL is required.")

    options = {
        "getcomments": True,
        "skip_download": True,
        "quiet": True,
        "no_warnings": True,
        "ignore_no_formats_error": True,
        "extractor_args": {
            "youtube": {
                "max_comments": ["all"],
                "player_client": ["web_safari"],
            }
        },
    }

    with YoutubeDL(options) as youtube_dl:
        info = youtube_dl.extract_info(video_url, download=False)

    if not info:
        raise ValueError("No video information was returned.")

    reported_count = (
        info.get("comment_count") or info.get("n_comments") or 0
    )
    comments = info.get("comments") or info.get("comment_entries") or []
    rows = [
        {
            "id": comment.get("id"),
            "author": comment.get("author"),
            "author_id": comment.get("author_id"),
            "text": comment.get("text"),
            "timestamp": comment.get("timestamp"),
            "like_count": comment.get("like_count"),
        }
        for comment in comments
    ]
    return rows, reported_count
