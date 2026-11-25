# File formats

All times are seconds (decimals) unless a name says otherwise. On a multi-clip session, source times are on the combined timeline from `source.json`.

## source.json (probe.py)
`clips[]`: `path`, `duration`, `offset` (start on the combined timeline), `has_video`, `has_audio`, `width`, `height`, `fps`, `rotation`, `variable_frame_rate`, audio details. `duration` is the total. `warnings[]`.

## transcript.json (transcribe.py)
```json
{ "version": 3, "engine": "faster-whisper", "model": "small", "language": "en",
  "granularity": "word", "duration": 729.2,
  "segments": [ { "id": 0, "start": 3.1, "end": 6.4, "text": "Yeah, so we can start.",
                  "speaker": "S1",
                  "words": [ { "word": "Yeah,", "start": 3.1, "end": 3.4, "probability": 0.98 } ] } ] }
```
`granularity` is `word`, or `phrase` for an imported SRT (words are spread evenly inside each cue). `speaker` is optional and set by hand or an import. `analysis.levels.json` (written next to `analysis.json`) holds fine audio levels with their real times (`t0` and `step`, or a `t` list, plus `db` and `threshold_db`); the clip and cut-list validators use it to keep edges off sound. `meta.repairs` lists each stretch `transcribe.py` re-transcribed, with `start`, `end`, the old text and the new, and a `status`: `repaired` (lost timing fixed), `filled` (sound with no words, such as speech Whisper skipped in a long file, now has its words), `nothing heard` (sound with no words that a second listen also left empty, usually noise) or `still unreliable`. Word start and end times are pulled onto the sound they were spoken in, so a caption highlight does not come before the word. `transcript.md` has one line per sentence with its real start time and long pauses marked; exact word edges are in `transcript.json`.

## analysis.json (analyse.py)
`candidates[]`: `kind` (`pause`, `dead_stretch`, `lead_in`, `tail_out`), `gap` (the silence), `cut` (the padded span to remove), `gap_seconds`, `cut_seconds`, `at` (hh:mm:ss), `picture_active`, `speech_suspected`, `gap_median_db` and `gap_loud_fraction` (the audio in the gap is not silent: at least 40% of it is as loud as speech), `keep_suggested` (picture changed or speech suspected), `note`. `settings` records the thresholds used, including the motion threshold chosen for this recording. `summary` has counts and `removable_seconds`.

## cutlist.json (you write it; validate_cutlist.py checks it)
```json
{
  "version": 1,
  "source": { "inputs": ["session.mp4"], "duration": 729.168 },
  "notes": "focus on pricing; skip the first 10 minutes",
  "keep": [ { "start": 223.1, "end": 301.4 }, { "start": 303.2, "end": 715.8 } ],
  "cuts": [ { "start": 0.0, "end": 223.1, "kind": "pre_roll", "reason": "setup chatter before recording",
              "text": "so go ahead and record it" } ],
  "speakers": [ { "id": "S1", "name": "Alex Doe", "title": "Head of Product" } ],
  "lower_thirds": [ { "at": 223.5, "speaker": "S1", "seconds": 6 } ],
  "chapters": [ { "at": 223.1, "title": "Why teams review first" } ]
}
```
- `keep`: sorted, non-overlapping, inside the media. The renderer uses only this.
- `cuts`: each has `start`, `end`, `kind`, `reason`; `text` (the words removed) is optional. Every gap between kept ranges should be covered by a cut (the validator warns if not).
- `lower_thirds`: optional. `at` is a source time; use `speaker` (from `speakers`) or give `name` and `title` directly. If absent and the transcript labels speakers, the renderer shows each speaker's name at their first words and every `repeat_every_seconds` after. With neither, none are drawn.
- `chapters`: `at` is a source time; the validator maps it through the cuts. Rules: at least three, the first at 00:00 of the output, each at least 10 s.

## sentences.json (sentences.py)
`sentences[]`: `id`, `start`, `end`, `text`, `words`, `speaker` (or null), `pause_before` (seconds of silence before it). `sentences.md` is the readable form, one `S<id> [hh:mm:ss] (length) text` line each, with long pauses marked. Clips are proposed by these ids.

## clips.json (you write it; validate_clips.py checks and resolves it)
```json
{ "version": 1, "clips": [
  { "id": 1, "from": 43, "to": 56, "score": 88, "trim_pauses": true,
    "title": "Why most migrations stall",
    "hook": "Most migrations stall at the last stretch",
    "reason": "A recognisable problem, then a concrete rule.",
    "caption": "Most migrations stall at the last stretch. The fix is a cutover plan with one owner. #engineering" } ] }
```
`from` and `to` are sentence ids. For the explainer style a clip may also have `highlights` (lower-case words or terms drawn in the accent colour in the captions, such as product names) and `panel_title` (a short label at the top left of the panel). `hook` is the opening words copied exactly. `trim_pauses` (default true) removes dead-air pauses inside the clip when counting its length. Optional `cards` (see `cards.md`): `[{"label": "The first week", "chain": false, "items": [{"text": "Set up laptop", "say": "set up the laptop"}]}]`; the resolved file gives each card its `start` and `end` and each item the source time (`at`) its spoken words begin, and the matching times in the finished clip (`clip_start`, `clip_end`, `clip_at`, after dead-air pauses are removed). Optional: `overlay_title` (the cover headline; defaults to `title`) and `subtitle` (a one-line tagline under it). Mark cover tiers with `|`: CAPITAL words are big magenta lines, lowercase words small white ones (`"HUMAN | in the | LEAD"`); with no `|` the title is wrapped into balanced big lines. Use 2 to 4 tiers, and keep each tier to a word or two. The resolved file (`--out`) adds `start`, `end`, `seconds` (raw), `effective_seconds` (after trimmed pauses), `at` and `text`.

## brand.json
Colours are referenced by token name (`primary`, `secondary`, `text`, `background`, `surface`, `text_muted`). Asset paths are relative to the brand file. Keys: `name`, `logo`, `intro` and `outro` (`card`, `seconds`, `fade_seconds`), `fonts` (`regular`, `medium`, `semibold`, `bold` TTF files), `colors`, `lower_third`, `captions`, `shorts`, `output` (`long` and `short` resolution, fps and `lufs`), `glossary` (words for Whisper to spell correctly), `corrections` (known mishearings fixed automatically, for example `{"e mail": "email"}`).

## render output (render_long.py)
`<out-dir>/long.mp4`, `long.srt` (captions `srt` or `both`), `chapters.txt` (chapter times include the intro; the first is always `00:00`), `overlays.ass` and `filtergraph.txt` (the exact captions and ffmpeg settings, for debugging). The script prints JSON with expected and measured length and warnings.
