# Wrestling Logger

CLI utility that builds a Google Doc recap ("Master Doc") from your event metadata, play-by-play text, personal notes, and highlight video transcripts.

## Prerequisites
- Python 3.10+
- `pip install -r requirements.txt`
- Google Cloud project with Drive + Docs APIs enabled
- `credentials.json` desktop client credentials (same directory as the script)

## Usage
```bash
python3 create_show_doc.py
```
Follow the prompts:
1. **Metadata** – date (`YYYY-MM-DD`), promotion, and show name.
2. **Play-by-Play** – paste the recap text, then type `::end::` on a new line.
3. **Your Angle** – paste personal notes, then `::end::`.
4. **YouTube IDs** – comma-separated highlight IDs.

The script:
- Fetches each transcript via `yt-dlp` with per-ID failure handling (manual + auto captions, optional cookie support).
- Assembles the sections (`PLAY BY PLAY ANALYSIS`, `YOUR ANGLE`, transcript summaries).
- Authenticates via Installed App Flow (token saved to `token.json`).
- Creates a Google Doc via Drive API and writes the assembled body using Docs API `documents.batchUpdate`.

Successful completion prints the new Doc ID + URL.

### Transcript cookies
- Set `YTDLP_COOKIES_FILE=/abs/path/to/cookies.txt` to let `yt-dlp` read a Netscape cookies export (useful for age/region/member-restricted videos).
- Or set `YTDLP_COOKIES_FROM_BROWSER=chrome` (any shorthand supported by `yt-dlp`) to import cookies directly from a local browser profile.

## References
- [Drive API `files().create()`](https://developers.google.com/workspace/drive/api/v3/reference/files/create)
- [Docs API `documents.batchUpdate`](https://developers.google.com/workspace/docs/api/how-tos/move-text)
- [Drive quickstart OAuth Option B](https://developers.google.com/workspace/drive/api/quickstart/python)
- [`yt-dlp` README](https://github.com/yt-dlp/yt-dlp)
