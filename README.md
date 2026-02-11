# Techno Label Audio QC (Programmatic)

This repo contains a practical QC checklist and a script to validate delivery files against our label mastering & delivery standards.

It checks what can be verified programmatically:
- File format / encoding
- Bit depth / sample rate
- Loudness (Integrated LUFS)
- True peak (dBTP, from ffmpeg loudness analysis)
- Basic channel layout (stereo/mono)
- Naming convention pattern (optional strict mode)

It **cannot** fully verify subjective or listening-based items like “kick transient integrity” or “no audible pumping” — those remain human QC items.

---

## Mastering Delivery Spec (Reference)

Per track, we require:

### A) Beatport / Download Master (Primary Digital)
- WAV, PCM
- **24-bit / 48 kHz**
- Integrated loudness: **-8 to -6 LUFS**
- **Hard ceiling:** NEVER louder than **-6 LUFS**
- True Peak: **≤ -1.0 dBTP**

### B) Spotify / Streaming Master
- WAV, PCM
- **24-bit / 48 kHz**
- Integrated loudness: **~ -11 LUFS** (target band defined in config)
- True Peak: **≤ -1.0 dBTP**

### C) Vinyl Pre-Master (Required even if pressing later)
- WAV, PCM
- **24-bit / 48 kHz**
- Integrated loudness: **-10 to -12 LUFS**
- True Peak: **≤ -3.0 dBFS** (treated as TP limit for QC)

### Track-to-Track
- Tracks must be **matched by perceived loudness** (requires human QC + optional script report comparison)

### Metadata
Required tags (ISRC assigned post-approval, so NOT required at QC time):
- Artist
- Track Title
- Label Name
- Catalog Number
- Release Year

Rules:
- **No embedded artwork**
- No “master type” notes in metadata
- ISRC added later by label

### Naming
Strict format:
`ARTIST – TRACK TITLE (CATALOG) [MASTER TYPE].wav`

Examples:
- `Artist – Track (IMR-012) [BEATPORT MASTER].wav`
- `Artist – Track (IMR-012) [SPOTIFY MASTER].wav`
- `Artist – Track (IMR-012) [VINYL PREMASTER].wav`

---

## QC Checklist (Mirrors Spec Exactly)

### 1) File / Format QC (Programmatic)
- [ ] File is **WAV**
- [ ] Audio codec is **PCM** (uncompressed)
- [ ] **24-bit**
- [ ] **48 kHz** sample rate
- [ ] Channels are valid (stereo expected unless explicitly approved)

### 2) Loudness & True Peak QC (Programmatic)
**Beatport Master**
- [ ] Integrated LUFS is between **-8 and -6**
- [ ] Integrated LUFS is **NOT louder than -6**
- [ ] True Peak is **≤ -1.0 dBTP**

**Spotify Master**
- [ ] Integrated LUFS is within the configured target band around **-11 LUFS**
- [ ] True Peak is **≤ -1.0 dBTP**

**Vinyl Pre-Master**
- [ ] Integrated LUFS is between **-12 and -10**
- [ ] True Peak is **≤ -3.0 dB** (QC uses TP metric; cutter may have additional requirements)

### 3) Naming QC (Programmatic, Optional Strict Mode)
- [ ] Filename matches:
  - `ARTIST – TRACK TITLE (CATALOG) [MASTER TYPE].wav`
- [ ] MASTER TYPE is one of:
  - `BEATPORT MASTER`
  - `SPOTIFY MASTER`
  - `VINYL PREMASTER`

### 4) Metadata QC (Partially Programmatic)
What the script can check:
- [ ] Artist tag present (if embedded)
- [ ] Title tag present (if embedded)
- [ ] Album/Label fields present (if embedded)
- [ ] Catalog number present (if embedded)
- [ ] Year/date present (if embedded)

What remains **human QC**:
- [ ] Tags are correct and consistent across all masters
- [ ] No embedded artwork (some tools can detect; verify if your pipeline embeds images)

### 5) Human QC (Non-Programmatic, Required)
- [ ] No audible limiter pumping in intros/outros
- [ ] Kick transients preserved; not smeared
- [ ] Mono compatibility verified by listening (and/or correlation meter)
- [ ] Vinyl safety review:
  - [ ] Sub mono below ~120 Hz
  - [ ] No excessive stereo low-mids
  - [ ] No distortion-prone sibilant highs
- [ ] Track-to-track perceived loudness consistency approved

---

## Install

### Requirements
- Python 3.10+
- `ffmpeg` + `ffprobe` installed and on PATH

### Python deps
None (script uses stdlib and shelling out to ffmpeg/ffprobe).

---

## Usage

### Quick QC of a folder
```bash
python3 qc_audio.py qc ./deliverables --config qc_config.json
