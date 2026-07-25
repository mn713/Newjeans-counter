"""
Posts a video to TikTok using the Content Posting API's Direct Post flow.

This script is meant to be run by the GitHub Actions workflow, not by hand.
It expects these environment variables to already be set:

    TIKTOK_CLIENT_KEY
    TIKTOK_CLIENT_SECRET
    TIKTOK_REFRESH_TOKEN
    VIDEO_PATH          (path to the mp4 file to post)
    VIDEO_TITLE          (the caption text)
    GH_PAT               (used to save a new refresh token if TikTok rotates it)
    GITHUB_REPOSITORY    (owner/repo — GitHub Actions sets this automatically)

WHY THIS SAVES A NEW REFRESH TOKEN:
    TikTok sometimes issues a brand new refresh token every time the old one
    is used, and invalidates the old one. If we didn't save the new one back
    to GitHub, tomorrow's run would fail. This script checks for that and
    updates the GitHub secret automatically when it happens.
"""

import os
import sys
import time
import subprocess
import requests

CLIENT_KEY = os.environ["TIKTOK_CLIENT_KEY"]
CLIENT_SECRET = os.environ["TIKTOK_CLIENT_SECRET"]
REFRESH_TOKEN = os.environ["TIKTOK_REFRESH_TOKEN"]
VIDEO_PATH = os.environ["VIDEO_PATH"]
VIDEO_TITLE = os.environ.get("VIDEO_TITLE", "Daily countdown")
GH_PAT = os.environ.get("GH_PAT")
REPO = os.environ.get("GITHUB_REPOSITORY")


def refresh_access_token():
    print("Refreshing TikTok access token...")
    resp = requests.post(
        "https://open.tiktokapis.com/v2/oauth/token/",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "client_key": CLIENT_KEY,
            "client_secret": CLIENT_SECRET,
            "grant_type": "refresh_token",
            "refresh_token": REFRESH_TOKEN,
        },
    )
    data = resp.json()
    if "access_token" not in data:
        print("Failed to refresh access token. TikTok said:")
        print(data)
        sys.exit(1)

    new_refresh_token = data.get("refresh_token")
    if new_refresh_token and new_refresh_token != REFRESH_TOKEN:
        if GH_PAT and REPO:
            print("TikTok issued a new refresh token — saving it to GitHub secrets...")
            result = subprocess.run(
                ["gh", "secret", "set", "TIKTOK_REFRESH_TOKEN", "--repo", REPO, "--body", new_refresh_token],
                env={**os.environ, "GH_TOKEN": GH_PAT},
            )
            if result.returncode != 0:
                print("WARNING: failed to save the new refresh token. "
                      "Tomorrow's run may fail unless this is fixed manually.")
        else:
            print("WARNING: got a new refresh token but GH_PAT/GITHUB_REPOSITORY "
                  "weren't available to save it. Tomorrow's run may fail.")

    return data["access_token"]


def post_video(access_token, video_path, title):
    file_size = os.path.getsize(video_path)

    print("Starting upload to TikTok...")
    init_resp = requests.post(
        "https://open.tiktokapis.com/v2/post/publish/video/init/",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json; charset=UTF-8",
        },
        json={
            "post_info": {
                "title": title,
                "privacy_level": "SELF_ONLY",  # sandbox/unaudited apps are forced to this anyway
                "disable_duet": False,
                "disable_comment": False,
                "disable_stitch": False,
            },
            "source_info": {
                "source": "FILE_UPLOAD",
                "video_size": file_size,
                "chunk_size": file_size,
                "total_chunk_count": 1,
            },
        },
    )
    init_data = init_resp.json()
    if "data" not in init_data or "publish_id" not in init_data.get("data", {}):
        print("Failed to start the post. TikTok said:")
        print(init_data)
        sys.exit(1)

    publish_id = init_data["data"]["publish_id"]
    upload_url = init_data["data"]["upload_url"]

    with open(video_path, "rb") as f:
        video_bytes = f.read()

    upload_resp = requests.put(
        upload_url,
        headers={
            "Content-Type": "video/mp4",
            "Content-Range": f"bytes 0-{file_size - 1}/{file_size}",
        },
        data=video_bytes,
    )
    if upload_resp.status_code not in (200, 201):
        print(f"Upload failed (status {upload_resp.status_code}):")
        print(upload_resp.text)
        sys.exit(1)

    print(f"Uploaded. publish_id: {publish_id}")
    print("Checking publish status...")

    for _ in range(6):
        time.sleep(5)
        status_resp = requests.post(
            "https://open.tiktokapis.com/v2/post/publish/status/fetch/",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json; charset=UTF-8",
            },
            json={"publish_id": publish_id},
        )
        status_data = status_resp.json()
        status = status_data.get("data", {}).get("status")
        print("Status:", status)
        if status in ("PUBLISH_COMPLETE", "FAILED"):
            if status == "FAILED":
                print("TikTok reported the post failed:", status_data)
                sys.exit(1)
            break

    print("Done — post completed successfully.")


if __name__ == "__main__":
    access_token = refresh_access_token()
    post_video(access_token, VIDEO_PATH, VIDEO_TITLE)
