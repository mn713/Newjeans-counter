"""
Countdown video generator — "There are NNNN days until NewJeans is free"

USAGE:
    python countdown.py --background my_video.mp4 --output out.mp4

Optional:
    python countdown.py --background my_video.mp4 --output out.mp4 --date 2029-08-01
    python countdown.py --background my_video.mp4 --output out.mp4 --emoji-image hearts.png

Requires:
    pip install moviepy pillow --break-system-packages   (or without the flag, in a venv)

Also requires:
    - An Inter SemiBold (weight 600) .ttf/.otf font file. Place it next to
      this script, or point --font at its path.
    - A background video file of your own (any resolution — it will be
      cropped/resized to a 1080x1920 vertical frame for TikTok).

HOW THE TEXT IS DRAWN:
    The text and hearts are drawn directly with Pillow (the image library)
    into one transparent PNG overlay, which is then laid on top of your
    video. This gives full, predictable control over spacing — moviepy's
    own text tool was reporting inaccurate text heights, which caused the
    lines to overlap in earlier versions of this script.

ABOUT THE EMOJI/HEARTS LINE:
    By default this draws five colored heart shapes directly (no emoji font
    needed, so it always renders correctly). If you'd rather use your own
    image (e.g. a screenshot of real emoji), pass --emoji-image path/to/it.png
    and it'll be used instead — ideally as a PNG with a transparent background.
"""

import argparse
import datetime
import tempfile
from pathlib import Path

from moviepy import VideoFileClip, CompositeVideoClip, ImageClip
from PIL import Image, ImageDraw, ImageFont

# ---- Fixed settings you can tweak ----
TARGET_DATE_DEFAULT = datetime.date(2029, 8, 1)
LINE1_TEMPLATE = "There are {days} days until"
LINE2 = "NewJeans is free"
FONT_PATH_DEFAULT = "Inter-SemiBold.ttf"
MAIN_FONT_SIZE = 70
LINE_GAP = 15                 # extra space between the two text lines
TEXT_TO_EMOJI_GAP = 20        # space between text block and hearts/emoji
TEXT_COLOR = "white"
FRAME_SIZE = (1080, 1920)  # TikTok vertical
SAFE_MARGIN = 60  # px kept clear at top/bottom of the frame

# Approximate emoji heart colors, in order: blue, pink, yellow, purple, green
HEART_COLORS = [
    (85, 172, 236, 255),
    (255, 122, 172, 255),
    (255, 205, 15, 255),
    (170, 142, 214, 255),
    (119, 178, 85, 255),
]
HEART_SIZE = 90   # px, size of each individual heart (used only if no --emoji-image given)
HEART_GAP = 20     # px, space between hearts
EMOJI_IMAGE_HEIGHT = 90  # px, target height when using a custom --emoji-image


def days_until(target_date: datetime.date) -> int:
    today = datetime.date.today()
    return (target_date - today).days


def make_heart(color, size):
    """Draw a single heart shape (two circles + a triangle) as an RGBA image."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    r = size // 4
    draw.ellipse([0, 0, 2 * r, 2 * r], fill=color)
    draw.ellipse([size - 2 * r, 0, size, 2 * r], fill=color)
    draw.polygon([(0, r), (size, r), (size // 2, size)], fill=color)
    return img


def make_hearts_row_image(size=HEART_SIZE, gap=HEART_GAP):
    """Draw all five hearts in a row and return as a PIL RGBA image."""
    n = len(HEART_COLORS)
    row_w = n * size + (n - 1) * gap
    row = Image.new("RGBA", (row_w, size), (0, 0, 0, 0))
    for i, color in enumerate(HEART_COLORS):
        heart = make_heart(color, size)
        row.paste(heart, (i * (size + gap), 0), heart)
    return row


def build_text_overlay(line1_text, font_path, emoji_image_path=None):
    """
    Draw the two text lines + hearts/emoji directly with Pillow into one
    full-frame transparent PNG, using real font ascent/descent metrics for
    line spacing (not a text clip's reported bounding box, which was
    unreliable). Returns the path to the saved overlay PNG.
    """
    font = ImageFont.truetype(font_path, MAIN_FONT_SIZE)
    ascent, descent = font.getmetrics()
    line_height = ascent + descent

    # Load or draw the emoji/hearts row
    if emoji_image_path:
        emoji_img = Image.open(emoji_image_path).convert("RGBA")
        scale = EMOJI_IMAGE_HEIGHT / emoji_img.height
        new_size = (int(emoji_img.width * scale), EMOJI_IMAGE_HEIGHT)
        emoji_img = emoji_img.resize(new_size, Image.LANCZOS)
    else:
        emoji_img = make_hearts_row_image()

    block_height = line_height + LINE_GAP + line_height + TEXT_TO_EMOJI_GAP + emoji_img.height
    target_center_y = FRAME_SIZE[1] * 0.45
    block_top = target_center_y - block_height / 2
    block_top = max(SAFE_MARGIN, block_top)
    if block_top + block_height > FRAME_SIZE[1] - SAFE_MARGIN:
        block_top = max(SAFE_MARGIN, FRAME_SIZE[1] - SAFE_MARGIN - block_height)

    overlay = Image.new("RGBA", FRAME_SIZE, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    y = block_top
    draw.text((FRAME_SIZE[0] / 2, y), line1_text, font=font, fill=TEXT_COLOR, anchor="ma")
    y += line_height + LINE_GAP
    draw.text((FRAME_SIZE[0] / 2, y), LINE2, font=font, fill=TEXT_COLOR, anchor="ma")
    y += line_height + TEXT_TO_EMOJI_GAP
    overlay.paste(emoji_img, (int((FRAME_SIZE[0] - emoji_img.width) / 2), int(y)), emoji_img)

    overlay_path = Path(tempfile.gettempdir()) / "countdown_overlay.png"
    overlay.save(overlay_path)
    return str(overlay_path)


def make_countdown_video(background_path: str, output_path: str,
                          target_date: datetime.date, font_path: str,
                          emoji_image_path: str = None):
    days = days_until(target_date)
    if days < 0:
        raise ValueError(f"Target date {target_date} is in the past.")

    line1_text = LINE1_TEMPLATE.format(days=days)

    # Load and fit background to a vertical TikTok frame (crop to fill, then resize)
    bg = VideoFileClip(background_path)
    bg = bg.resized(height=FRAME_SIZE[1])
    if bg.w < FRAME_SIZE[0]:
        bg = bg.resized(width=FRAME_SIZE[0])
    x_center = bg.w / 2
    y_center = bg.h / 2
    bg = bg.cropped(
        x_center=x_center, y_center=y_center,
        width=FRAME_SIZE[0], height=FRAME_SIZE[1],
    )
    print(f"[debug] background cropped to: {bg.w}x{bg.h}")

    overlay_path = build_text_overlay(line1_text, font_path, emoji_image_path)
    overlay_clip = ImageClip(overlay_path).with_duration(bg.duration)

    final = CompositeVideoClip([bg, overlay_clip], size=FRAME_SIZE)
    final = final.with_duration(bg.duration)

    # Save one still frame as a plain PNG so we can inspect the exact
    # composited output directly (no player/thumbnail involved).
    debug_frame_path = str(Path(output_path).with_suffix("")) + "_debug_frame.png"
    final.save_frame(debug_frame_path, t=0)
    print(f"[debug] saved a still frame to: {debug_frame_path}")

    final.write_videofile(output_path, fps=bg.fps or 30, codec="libx264",
                           audio_codec="aac")


def parse_date(s: str) -> datetime.date:
    return datetime.datetime.strptime(s, "%Y-%m-%d").date()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate a NewJeans countdown video.")
    parser.add_argument("--background", required=True, help="Path to your background video file")
    parser.add_argument("--output", required=True, help="Path to write the output mp4")
    parser.add_argument("--date", type=parse_date, default=TARGET_DATE_DEFAULT,
                         help="Target date, YYYY-MM-DD (default 2029-08-01)")
    parser.add_argument("--font", default=FONT_PATH_DEFAULT,
                         help="Path to Inter-SemiBold.ttf (default: ./Inter-SemiBold.ttf)")
    parser.add_argument("--emoji-image", default=None,
                         help="Optional path to your own emoji/hearts image (PNG, ideally transparent background). "
                              "If omitted, five hand-drawn hearts are used instead.")
    args = parser.parse_args()

    if not Path(args.font).exists():
        raise SystemExit(
            f"Font file not found at '{args.font}'. Place Inter-SemiBold.ttf next to "
            f"this script, or pass its path via --font."
        )
    if args.emoji_image and not Path(args.emoji_image).exists():
        raise SystemExit(f"Emoji image not found at '{args.emoji_image}'.")

    make_countdown_video(args.background, args.output, args.date, args.font, args.emoji_image)
    print(f"Done: {args.output}")
