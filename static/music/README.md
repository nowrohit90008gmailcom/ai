# Background Music Directory

Place royalty-free `.mp3` tracks here. The assembler will randomly pick one per video
and mix it at **12% volume** under the narration.

## Recommended sources (no copyright strikes)
- **YouTube Audio Library** — https://studio.youtube.com/channel/music
  - Filter: "Free to use" → download as MP3
- **Pixabay Music** — https://pixabay.com/music/
  - Free, no attribution required
- **Freesound.org** — https://freesound.org/
  - Filter by CC0 license

## Per-channel recommendations
| Channel | Style | Keywords |
|---|---|---|
| Horror Crime | Dark ambient / drone | "suspense", "thriller", "dark ambient" |
| Manners Fun | Upbeat kids / playful | "children", "happy", "ukulele" |
| Cartoon Stories | Adventure / cartoon | "adventure", "whimsical", "cartoon" |

## File naming (optional but helpful)
```
horror_01_dark_ambient.mp3
horror_02_suspense.mp3
manners_01_happy_kids.mp3
cartoon_01_adventure.mp3
```

The system picks tracks randomly — all files in this folder are used across all channels.
If you want per-channel tracks, create subdirectories: `horror_crime/`, `manners_fun/`, `cartoon_stories/`
and update `MUSIC_DIR` in `config.py` accordingly.
