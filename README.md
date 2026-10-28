# Video to Shorts - Vertical 9:16 Clips with AI Captions

The Video to Shorts API from ENT-E turns a long video URL into vertical 9:16 clips for TikTok, Instagram Reels and YouTube Shorts, with burned-in animated captions. One call per short, with no editor, no timeline and no manual subtitles.

## Video to shorts API: long video in, vertical 9:16 short with captions out

Tell it where the highlight starts and ends. The Actor then:
1. reframes the clip to 9:16 (`blur`, `crop` or `pad`),
2. transcribes the speech with Whisper,
3. burns in word-by-word captions with the current word highlighted,
4. returns a ready-to-post 30 fps H.264/AAC MP4, plus a JPEG thumbnail and an `.srt` of the captions.

The Actor doesn't pick highlights for you. You (or your agent, from a transcript) choose `startSeconds` and `endSeconds`; it does the editing work.

## What you get

- **Vertical video 9:16** at 1080×1920 (default) or 720×1280.
- **Three reframe modes:**
  - `blur` (default): the full frame sits over a blurred copy of itself, so nothing is cut off. Good for slides, gameplay and two-person shots.
  - `crop`: fills the screen. Aim it with `cropPosition` from 0 (left) to 1 (right).
  - `pad`: the full frame with solid bars in `padColor`.
- **Burned-in captions included in the price.** Pick a preset `captionStyle` (`bold`, `pop`, `boxed` or `minimal`), then fine-tune `font`, `fontSize`, colors, outline, box, uppercase, words per caption, karaoke highlighting and position. With `captionPosition: "auto"`, captions sit in the free area under the video in blur/pad mode, so they don't cover faces.
- **Six bundled fonts:** `poppins`, `anton`, `bebas`, `luckiest`, `archivo` and `dejavu`.
- **Up to 180 s per short** (`maxClipSeconds`, default 60).
- **Batch** with `clips`: many highlights from one long video in one run, each with its own settings.
- **Failed clips are free.**

## Use cases

### Long video to TikTok, Reels and YouTube Shorts

```json
{
  "url": "https://example.com/webinars/q3-product-update.mp4",
  "startSeconds": 754,
  "endSeconds": 812
}
```

Defaults: blur reframe, 1080×1920, `bold` captions, auto language.

### Repurpose podcast clips into shorts (batch)

Cut several highlights from one episode in one run. Top-level settings apply to every clip, and each clip can override them.

```json
{
  "mode": "crop",
  "captionStyle": "pop",
  "language": "en",
  "clips": [
    { "url": "https://example.com/podcast/ep-88.mp4", "startSeconds": 312, "endSeconds": 355 },
    { "url": "https://example.com/podcast/ep-88.mp4", "startSeconds": 1490, "endSeconds": 1548, "cropPosition": 0.7 },
    { "url": "https://example.com/podcast/ep-88.mp4", "startSeconds": 2710, "endSeconds": 2766, "cropPosition": 0.3 }
  ]
}
```

Use `cropPosition` to keep each speaker in frame when they sit left or right of center.

### Burned-in captions with your brand style

```json
{
  "url": "https://example.com/videos/tutorial-12.mp4",
  "startSeconds": 60,
  "endSeconds": 105,
  "captionStyle": "bold",
  "font": "anton",
  "textColor": "#FFFFFF",
  "highlightColor": "#3DFF5A",
  "wordsPerCaption": 2,
  "captionPosition": "center"
}
```

### Vertical video 9:16 without captions (reframe and trim only)

```json
{
  "url": "https://example.com/footage/b-roll-wide.mov",
  "startSeconds": 10,
  "endSeconds": 25,
  "mode": "pad",
  "padColor": "#FFFFFF",
  "captions": false
}
```

### Agent workflow: transcript, then pick moments, then render shorts

1. Get a timed transcript of the long video from any Whisper-based transcription tool.
2. Let your LLM choose 3–5 moments with start and end times.
3. Send them here as `clips`.

## Pricing (pay per event)

| Event | Price |
|---|---|
| Short created (per successful short; includes captions, thumbnail and SRT) | $0.08 |
| Clip minute (per started minute of **output** video) | $0.12 |
| Actor start (per run, one event per GB of memory, minimum one; default 4 GB = 4 events) | $0.00005 per event |

There are no platform usage fees on top. Captions cost the same with every `model`. Failed clips are free. You pay for the short you get, not for the length of the source video.

**Worked example: one podcast episode, five shorts**
- Each short is 30–60 s, which is 1 started minute: $0.08 + $0.12 = **$0.20 per short**.
- Five shorts: **$1.00**, plus $0.0002 actor start for the batch run.
- Ten 60-second shorts: **$2.00**.

**Longer shorts:**
- A 61–120 s short: $0.08 + 2 × $0.12 = **$0.32**.
- A full 180 s short: $0.08 + 3 × $0.12 = **$0.44**.

Billing rounds up to the next started minute of output, ignoring up to 0.5 s of encoder padding, so a 60 s short (even if it renders at 60.03 s) is 1 minute and a 61 s short is 2.

## Input reference

| Field | Type | Default | Notes |
|---|---|---|---|
| `url` | string | (none) | Direct link to one video file, up to 4 GB (not a YouTube/TikTok page) |
| `clips` | array | (none) | Batch. Items are `{ "url": ..., <any setting below> }` or plain URL strings. |
| `startSeconds` | number | `0` | Start of the short in the source (decimals allowed) |
| `endSeconds` | number | (none) | End of the short. If empty, the clip runs to the end of the source or to `maxClipSeconds`. |
| `maxClipSeconds` | integer | `60` | Hard cap on output length, 5–180 |
| `mode` | string | `blur` | `blur`, `crop`, `pad` |
| `cropPosition` | number | `0.5` | `crop` only. 0 = left, 1 = right. |
| `blurStrength` | integer | `20` | `blur` only. 4–80. |
| `padColor` | string | `#000000` | `pad` only |
| `resolution` | string | `1080x1920` | `1080x1920` or `720x1280` |
| `quality` | string | `standard` | `high` (CRF 18), `standard` (CRF 21), `small` (CRF 25) |
| `captions` | boolean | `true` | Burn in captions and return an SRT |
| `model` | string | `small` | `base`, `small`, `large-v3-turbo` (same price) |
| `language` | string | `auto` | ISO 639-1 code or `auto` |
| `captionStyle` | string | `bold` | `bold`, `pop`, `boxed`, `minimal` |
| `font` | string | from style | `poppins`, `anton`, `bebas`, `luckiest`, `archivo`, `dejavu` |
| `fontSize` | integer | from style | 20–200 px at 1080 width |
| `textColor`, `highlightColor`, `outlineColor` | string | from style | Hex colors |
| `outlineWidth` | number | from style | 0–20 |
| `captionBox` | boolean | from style | Semi-transparent box behind the text |
| `uppercase` | boolean | from style | |
| `wordsPerCaption` | integer | from style | 1–12 words on screen |
| `highlightWords` | boolean | from style | Karaoke-style current-word highlight |
| `captionPosition` | string | from style | `auto`, `bottom`, `center`, `top` |

You must provide either `url` or `clips`.

## Output reference

Each short produces one dataset row. Here is a real 60 s test render (URLs and transcript shortened):

```json
{
  "sourceUrl": "https://example.com/webinars/q3-product-update.mp4",
  "startSeconds": 60,
  "mode": "blur",
  "resolution": "1080x1920",
  "videoUrl": "https://api.apify.com/v2/key-value-stores/<storeId>/records/4e353b7c87de.mp4?signature=<sig>",
  "thumbnailUrl": "https://api.apify.com/v2/key-value-stores/<storeId>/records/4e353b7c87de.jpg?signature=<sig>",
  "captionsSrtUrl": "https://api.apify.com/v2/key-value-stores/<storeId>/records/4e353b7c87de.srt?signature=<sig>",
  "status": "ok",
  "durationSeconds": 60.03,
  "endSeconds": 120,
  "width": 1080,
  "height": 1920,
  "sizeBytes": 37856647,
  "captioned": true,
  "captionStyle": "bold",
  "language": "en",
  "captionCount": 47,
  "transcript": "…",
  "sourceDurationSeconds": 580.174,
  "billedMinutes": 1
}
```

If the clip has no speech, or no audio stream, the short still renders without captions, and the row says so in `warning`. A failed clip returns `sourceUrl`, `startSeconds`, `mode`, `resolution`, `status: "error"` and `error`.

## Use it from AI agents and automations

**MCP (Claude, Cursor, other MCP clients).** Add `https://mcp.apify.com?tools=ent-e/video-to-shorts-captions` as a remote MCP server and sign in with OAuth. Your agent passes a URL and timestamps and gets back `videoUrl`. A 60 s short at 1080×1920 takes about 2–4 minutes to render, and 720×1280 is roughly twice as fast, so the agent should wait for the run to finish before reading the dataset.

**n8n.** Use the Apify node (`@apify/n8n-nodes-apify`). Use **Run an Actor**, then **Get Dataset Items**, and post `videoUrl` to your scheduler or storage. **Run an Actor and get dataset** also works for a single short.

**Make.** Use the Apify app. Renders usually take longer than the 120 s sync wait, so:
1. Run **Run an Actor** asynchronously.
2. Add the **Watch Actor Runs** trigger.
3. Then **Get Dataset Items**.

**Zapier.** Use the Apify app:
- **Run Actor and Fetch Results** for a single short (under 5 minutes).
- For batches, use **Run Actor**, then the **Finished Actor Run** trigger and **Fetch Dataset Items**.

**API.**

```bash
curl -X POST "https://api.apify.com/v2/acts/ent-e~video-to-shorts-captions/runs?token=$APIFY_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"url":"https://example.com/webinars/q3-product-update.mp4","startSeconds":754,"endSeconds":812}'
# then: GET https://api.apify.com/v2/datasets/<defaultDatasetId>/items?token=$APIFY_TOKEN
```

## FAQ

**Does it find the best moments automatically?**
No. You choose `startSeconds` and `endSeconds`. That keeps the output predictable and the cost fixed. To automate it, get a transcript first, let an LLM pick the moments, then send them as `clips`.

**Does it track faces?**
No. There's no automatic face tracking. Use `crop` with `cropPosition` to frame a speaker, or `blur` to keep the whole frame visible.

**Can I paste a YouTube or TikTok link?**
No. The Actor needs a direct link to the video file (cloud storage, CDN or file host), up to 4 GB.

**Which languages do the captions support?**
Speech is transcribed by Whisper in the spoken language (auto-detected or set with `language`). The bundled fonts cover Latin scripts. Use `dejavu` for Cyrillic and Greek. CJK, Arabic and Indic scripts aren't supported yet. For those, set `"captions": false` and add subtitles in your own editor or player.

**How long can a short be?**
5 to 180 seconds (`maxClipSeconds`). The default of 60 s fits the common TikTok, Reels and Shorts length. You pay per started minute of output (up to 0.5 s of padding is ignored), so 60 s costs less than 61 s.

**Am I charged if a clip fails?**
No. A bad URL, an input without video, or an invalid setting returns a free error row. A short that renders without captions (because the clip has no speech) is still a delivered short and is billed normally.

## ENT-E media toolkit

Every tool takes a public file URL, needs nothing installed, charges per file, doesn't charge for failures, and works from MCP, n8n, Make, Zapier and the API.

- **[Media Converter for AI Agents (FFmpeg)](https://apify.com/ent-e/media-converter-ffmpeg)**: audio/video to MP3, Whisper-ready 16 kHz WAV, MP4, WebM, GIF or thumbnails, with trim and batch.
- **[Image Converter & Compressor](https://apify.com/ent-e/image-converter-compressor)**: convert to WebP or AVIF, compress to a target file size, resize, strip EXIF/GPS.
- **[Podcast Loudness Normalizer](https://apify.com/ent-e/podcast-loudness-normalizer)**: normalize to -16, -14, -23 or -24 LUFS with a true-peak ceiling, plus a before/after report.
- **Video to Captions** (coming soon): SRT, VTT, TXT and word-level JSON from any video or audio URL, with Whisper.
- **[Video to Shorts](https://apify.com/ent-e/video-to-shorts-captions)**: vertical 9:16 clips with burned-in animated captions for TikTok, Reels and Shorts.
