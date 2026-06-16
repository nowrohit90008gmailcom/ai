"""
modules/thumbnail_generator.py — Add text overlay + branding to ComfyUI thumbnails.

Pipeline:
  1. Load raw thumbnail (1080×1920) from ComfyUI
  2. Add semi-transparent dark gradient at bottom 40%
  3. Add channel-colored stripe at top
  4. Add bold white title text (wrapped, centered)
  5. Add channel emoji badge in top-left
  6. Save as thumbnail.png (final, ready for YouTube)

Uses Pillow (Pillow>=9.0.0).
"""

import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from config import CHANNELS, VIDEO_WIDTH, VIDEO_HEIGHT
from modules.logger import get_logger

log = get_logger("thumbnail_generator")

# Font sizes (pixels, for 1080-wide thumbnail)
TITLE_FONT_SIZE   = 72
BADGE_FONT_SIZE   = 56
CHANNEL_FONT_SIZE = 36

# Layout constants
GRADIENT_START_Y  = 0.50   # gradient starts at 50% height
STRIPE_HEIGHT     = 12     # top color stripe in px
PADDING           = 60     # text margin from edges


class ThumbnailGenerator:
    """Creates final polished thumbnails using Pillow."""

    def generate(self, channel: str, raw_thumbnail: Path,
                  title: str, output_path: Path) -> bool:
        """
        Overlay text and branding on a raw ComfyUI thumbnail.
        Returns True on success.
        """
        if not raw_thumbnail.exists():
            log.warning(f"Raw thumbnail not found: {raw_thumbnail}")
            return False

        try:
            img = Image.open(raw_thumbnail).convert("RGBA")
            img = img.resize((VIDEO_WIDTH, VIDEO_HEIGHT), Image.LANCZOS)

            draw = ImageDraw.Draw(img)
            cfg  = CHANNELS[channel]

            # 1 — Dark gradient overlay (bottom 50%)
            self._draw_gradient(img, draw)

            # 2 — Channel color stripe at top
            stripe_color = self._hex_to_rgb(cfg["color_theme"])
            draw.rectangle([(0, 0), (VIDEO_WIDTH, STRIPE_HEIGHT)],
                            fill=(*stripe_color, 220))

            # 3 — Bold title text (wrapped to 2–3 lines, large)
            title_clean = title[:80].upper()
            self._draw_outlined_text(
                draw, title_clean,
                font_size=TITLE_FONT_SIZE,
                y_ratio=0.62,
                color=(255, 255, 255),
                outline_color=(0, 0, 0),
                max_width=VIDEO_WIDTH - 2 * PADDING,
            )

            # 4 — Channel name badge at bottom
            ch_name = cfg["name"].upper()
            self._draw_outlined_text(
                draw, ch_name,
                font_size=CHANNEL_FONT_SIZE,
                y_ratio=0.90,
                color=stripe_color,
                outline_color=(0, 0, 0),
            )

            # 5 — "SHORTS" pill badge top-right
            self._draw_shorts_badge(draw, stripe_color)

            # Convert back to RGB and save
            final = img.convert("RGB")
            final.save(str(output_path), "PNG", quality=95)
            log.info(f"[{channel}] Thumbnail saved: {output_path.name}")
            return True

        except Exception as e:
            log.error(f"Thumbnail generation failed: {e}")
            return False

    # ─── Drawing Helpers ─────────────────────────────────────────────────────
    @staticmethod
    def _draw_gradient(img: Image.Image, draw: ImageDraw.ImageDraw):
        """Draw a semi-transparent black gradient over the bottom half."""
        w, h = img.size
        start_y = int(h * GRADIENT_START_Y)

        for y in range(start_y, h):
            progress = (y - start_y) / (h - start_y)
            alpha    = int(200 * (progress ** 0.7))
            draw.line([(0, y), (w, y)], fill=(0, 0, 0, alpha))

    @staticmethod
    def _load_font(size: int) -> ImageFont.FreeTypeFont:
        """Try to load a bold system font, fall back to default."""
        font_candidates = [
            "arialbd.ttf",      # Windows
            "Arial Bold.ttf",
            "DejaVuSans-Bold.ttf",   # Linux
            "LiberationSans-Bold.ttf",
        ]
        for name in font_candidates:
            try:
                return ImageFont.truetype(name, size)
            except (IOError, OSError):
                continue
        return ImageFont.load_default()

    def _draw_outlined_text(
        self, draw: ImageDraw.ImageDraw, text: str,
        font_size: int, y_ratio: float,
        color: tuple, outline_color: tuple,
        max_width: int = VIDEO_WIDTH - 120,
    ):
        """Draw text with outline, centered horizontally, at y_ratio of image height."""
        font = self._load_font(font_size)

        # Word wrap
        avg_char_width = font_size * 0.55
        chars_per_line = max(1, int(max_width / avg_char_width))
        lines = textwrap.wrap(text, width=chars_per_line)
        if not lines:
            return

        line_height = font_size + 10
        total_height = len(lines) * line_height
        y_start = int(VIDEO_HEIGHT * y_ratio) - total_height // 2

        for i, line in enumerate(lines):
            # Measure
            bbox = draw.textbbox((0, 0), line, font=font)
            text_w = bbox[2] - bbox[0]
            x = (VIDEO_WIDTH - text_w) // 2
            y = y_start + i * line_height

            # Outline (draw text 8 times at offsets)
            for dx in range(-3, 4, 3):
                for dy in range(-3, 4, 3):
                    if dx != 0 or dy != 0:
                        draw.text((x + dx, y + dy), line, font=font,
                                   fill=(*outline_color, 255))
            # Main text
            draw.text((x, y), line, font=font, fill=(*color, 255))

    def _draw_shorts_badge(self, draw: ImageDraw.ImageDraw, color: tuple):
        """Draw a '#SHORTS' pill badge in the top-right corner."""
        badge_text = "#SHORTS"
        font  = self._load_font(BADGE_FONT_SIZE - 12)
        bbox  = draw.textbbox((0, 0), badge_text, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        pad   = 16
        x     = VIDEO_WIDTH - text_w - 2 * pad - 24
        y     = STRIPE_HEIGHT + 24
        # Background pill
        draw.rounded_rectangle(
            [(x - pad, y - pad // 2),
             (x + text_w + pad, y + text_h + pad // 2)],
            radius=20,
            fill=(*color, 200),
        )
        draw.text((x, y), badge_text, font=font, fill=(255, 255, 255, 255))

    @staticmethod
    def _hex_to_rgb(hex_color: str) -> tuple:
        """Convert #rrggbb to (r, g, b)."""
        hex_color = hex_color.lstrip("#")
        return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
