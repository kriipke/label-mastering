#!/usr/bin/env python3
"""
Techno Label Audio QC

Checks delivery files against label mastering spec:
- WAV/PCM, 24-bit, 48 kHz
- Integrated LUFS & True Peak limits per master type
- Optional strict filename convention

Requires: ffmpeg, ffprobe
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# ----------------------------
# Helpers
# ----------------------------

def die(msg: str, code: int = 1) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    raise SystemExit(code)

def which_or_die(bin_name: str) -> str:
    p = shutil.which(bin_name)
    if not p:
        die(f"Missing required tool '{bin_name}' on PATH.")
    return p

def run(cmd: List[str]) -> Tuple[int, str, str]:
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return proc.returncode, proc.stdout, proc.stderr

def load_json(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        die(f"Failed to read config JSON: {path} ({e})")

def is_wav(path: Path) -> bool:
    return path.suffix.lower() == ".wav"

def pretty(x: Any) -> str:
    if x is None:
        return "n/a"
    if isinstance(x, float):
        return f"{x:.2f}"
    return str(x)


# ----------------------------
# Data structures
# ----------------------------

@dataclass
class AudioInfo:
    path: Path
    format_name: Optional[str] = None
    codec_name: Optional[str] = None
    sample_rate_hz: Optional[int] = None
    bit_depth: Optional[int] = None
    channels: Optional[int] = None
    duration_s: Optional[float] = None

@dataclass
class LoudnessInfo:
    integrated_lufs: Optional[float] = None
    true_peak_db: Optional[float] = None

@dataclass
class QCResult:
    path: Path
    master_type: Optional[str]
    audio: AudioInfo
    loudness: LoudnessInfo
    checks: List[Dict[str, Any]]
    passed: bool


# ----------------------------
# Probing
# ----------------------------

def ffprobe_audio_info(ffprobe_bin: str, path: Path) -> AudioInfo:
    """
    Uses ffprobe to extract basic audio stream info.
    """
    cmd = [
        ffprobe_bin,
        "-v", "error",
        "-select_streams", "a:0",
        "-show_entries",
        "format=format_name,duration:stream=codec_name,sample_rate,channels,bits_per_raw_sample,bits_per_sample",
        "-of", "json",
        str(path),
    ]
    rc, out, err = run(cmd)
    if rc != 0:
        die(f"ffprobe failed on {path.name}: {err.strip()}")

    data = json.loads(out)
    fmt = data.get("format", {})
    streams = data.get("streams", [])
    s0 = streams[0] if streams else {}

    # bits_per_raw_sample is often present for PCM; fall back to bits_per_sample
    bprs = s0.get("bits_per_raw_sample")
    bps = s0.get("bits_per_sample")
    bit_depth = None
    for v in (bprs, bps):
        try:
            if v is not None and str(v).strip() != "":
                bit_depth = int(v)
                break
        except Exception:
            pass

    sample_rate = None
    try:
        if s0.get("sample_rate") is not None:
            sample_rate = int(s0["sample_rate"])
    except Exception:
        pass

    channels = None
    try:
        if s0.get("channels") is not None:
            channels = int(s0["channels"])
    except Exception:
        pass

    duration = None
    try:
        if fmt.get("duration") is not None:
            duration = float(fmt["duration"])
    except Exception:
        pass

    return AudioInfo(
        path=path,
        format_name=fmt.get("format_name"),
        codec_name=s0.get("codec_name"),
        sample_rate_hz=sample_rate,
        bit_depth=bit_depth,
        channels=channels,
        duration_s=duration,
    )

def ffmpeg_loudness(ffmpeg_bin: str, path: Path) -> LoudnessInfo:
    """
    Uses ffmpeg ebur128 to get integrated loudness, and loudnorm summary to estimate true peak.
    Notes:
      - ebur128 prints I (integrated) in stderr.
      - loudnorm prints measured_TP (true peak) in stderr in JSON-ish.
    We run both to be robust.
    """

    integrated_lufs = None
    true_peak_db = None

    # Integrated LUFS via ebur128
    cmd_i = [
        ffmpeg_bin,
        "-hide_banner",
        "-nostats",
        "-i", str(path),
        "-filter_complex", "ebur128=framelog=verbose",
        "-f", "null", "-"
    ]
    rc, out, err = run(cmd_i)
    if rc != 0:
        # ffmpeg often returns 0; if not, still try loudnorm before dying
        pass

    # Parse "I:  -8.3 LUFS" near end
    m = re.findall(r"\bI:\s*([-+]?\d+(\.\d+)?)\s*LUFS\b", err)
    if m:
        try:
            integrated_lufs = float(m[-1][0])
        except Exception:
            integrated_lufs = None

    # True peak via loudnorm (1-pass measurement mode)
    cmd_tp = [
        ffmpeg_bin,
        "-hide_banner",
        "-nostats",
        "-i", str(path),
        "-af", "loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json",
        "-f", "null", "-"
    ]
    rc2, out2, err2 = run(cmd_tp)

    # Parse "measured_TP": "-1.02"
    m2 = re.search(r'"measured_TP"\s*:\s*"([-+]?\d+(\.\d+)?)"', err2)
    if m2:
        try:
            true_peak_db = float(m2.group(1))
        except Exception:
            true_peak_db = None

    return LoudnessInfo(integrated_lufs=integrated_lufs, true_peak_db=true_peak_db)


# ----------------------------
# Naming / master type detection
# ----------------------------

def detect_master_type_from_filename(name: str, allowed_types: List[str]) -> Optional[str]:
    upper = name.upper()
    for t in allowed_types:
        if f"[{t}]" in upper:
            return t
    return None

def validate_naming(path: Path, naming_cfg: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Checks strict naming format:
    ARTIST – TRACK TITLE (CATALOG) [MASTER TYPE].wav
    """
    dash = naming_cfg.get("dash", " – ")
    catalog_regex = naming_cfg.get("catalog_regex", r"\([A-Z]+-\d+\)")
    allowed_types = naming_cfg.get("master_types", [])
    fname = path.name

    # Quick checks
    if not fname.lower().endswith(".wav"):
        return False, "Not a .wav file name"

    # Must contain dash separator
    if dash not in fname:
        return False, f"Missing required dash separator '{dash}'"

    # Must contain catalog pattern
    if not re.search(catalog_regex, fname):
        return False, f"Missing/invalid catalog number (regex: {catalog_regex})"

    # Must contain [MASTER TYPE] and be in allowed list
    mt = detect_master_type_from_filename(fname, allowed_types)
    if mt is None:
        return False, f"Missing/invalid master type tag (allowed: {', '.join(allowed_types)})"

    # Basic bracket sanity
    if "[" not in fname or "]" not in fname:
        return False, "Missing [MASTER TYPE] brackets"

    return True, "OK"


# ----------------------------
# QC rules
# ----------------------------

def check_expected_audio(audio: AudioInfo, expected: Dict[str, Any]) -> List[Dict[str, Any]]:
    checks = []

    # Format / extension
    checks.append({
        "id": "file_is_wav",
        "pass": is_wav(audio.path),
        "details": f"ext={audio.path.suffix.lower()} expected=.wav"
    })

    # Codec
    codec_expected = expected.get("codec_contains", "pcm")
    codec_ok = (audio.codec_name or "").lower().find(codec_expected.lower()) >= 0
    checks.append({
        "id": "codec_pcm",
        "pass": codec_ok,
        "details": f"codec={audio.codec_name} expected_contains={codec_expected}"
    })

    # Sample rate
    sr_expected = int(expected.get("sample_rate_hz", 48000))
    sr_ok = (audio.sample_rate_hz == sr_expected)
    checks.append({
        "id": "sample_rate_48k",
        "pass": sr_ok,
        "details": f"sample_rate={audio.sample_rate_hz} expected={sr_expected}"
    })

    # Bit depth
    bd_expected = int(expected.get("bit_depth", 24))
    bd_ok = (audio.bit_depth == bd_expected)
    checks.append({
        "id": "bit_depth_24",
        "pass": bd_ok,
        "details": f"bit_depth={audio.bit_depth} expected={bd_expected}"
    })

    # Channels
    allowed = expected.get("channels_allowed", [2])
    ch_ok = (audio.channels in allowed)
    checks.append({
        "id": "channels_allowed",
        "pass": ch_ok,
        "details": f"channels={audio.channels} allowed={allowed}"
    })

    return checks

def check_loudness(master_type: str, loud: LoudnessInfo, masters_cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    cfg = masters_cfg.get(master_type, {})
    checks = []

    I = loud.integrated_lufs
    TP = loud.true_peak_db

    # Integrated LUFS checks
    if "lufs_min" in cfg and "lufs_max" in cfg:
        mn = float(cfg["lufs_min"])
        mx = float(cfg["lufs_max"])
        ok = (I is not None) and (mn <= I <= mx)
        checks.append({
            "id": "integrated_lufs_range",
            "pass": ok,
            "details": f"I={pretty(I)} LUFS expected_range=[{mn},{mx}]"
        })

    if "lufs_hard_ceiling" in cfg:
        ceiling = float(cfg["lufs_hard_ceiling"])
        ok = (I is not None) and (I <= ceiling)
        checks.append({
            "id": "integrated_lufs_hard_ceiling",
            "pass": ok,
            "details": f"I={pretty(I)} LUFS ceiling={ceiling} (never louder than this)"
        })

    if "lufs_target" in cfg and "lufs_tolerance" in cfg:
        target = float(cfg["lufs_target"])
        tol = float(cfg["lufs_tolerance"])
        ok = (I is not None) and (target - tol <= I <= target + tol)
        checks.append({
            "id": "integrated_lufs_target_band",
            "pass": ok,
            "details": f"I={pretty(I)} LUFS target={target} ±{tol}"
        })

    # True peak checks
    if "true_peak_max_db" in cfg:
        tpmax = float(cfg["true_peak_max_db"])
        ok = (TP is not None) and (TP <= tpmax)
        checks.append({
            "id": "true_peak_limit",
            "pass": ok,
            "details": f"TP={pretty(TP)} dBTP max={tpmax}"
        })

    return checks


# ----------------------------
# Reporting
# ----------------------------

def write_markdown_report(results: List[QCResult], md_path: Path) -> None:
    lines = []
    lines.append("# Audio QC Report\n")
    for r in results:
        lines.append(f"## {r.path.name}\n")
        lines.append(f"- Master type: **{r.master_type or 'UNKNOWN'}**\n")
        lines.append(f"- Integrated LUFS: **{pretty(r.loudness.integrated_lufs)}**\n")
        lines.append(f"- True Peak (dBTP): **{pretty(r.loudness.true_peak_db)}**\n")
        lines.append(f"- Sample rate: **{pretty(r.audio.sample_rate_hz)}** Hz\n")
        lines.append(f"- Bit depth: **{pretty(r.audio.bit_depth)}**\n")
        lines.append(f"- Channels: **{pretty(r.audio.channels)}**\n")
        lines.append("\n### Checks\n")
        for c in r.checks:
            status = "✅ PASS" if c["pass"] else "❌ FAIL"
            lines.append(f"- {status} `{c['id']}` — {c['details']}\n")
        lines.append("\n")
    md_path.write_text("".join(lines), encoding="utf-8")

def results_to_json(results: List[QCResult]) -> List[Dict[str, Any]]:
    out = []
    for r in results:
        out.append({
            "file": str(r.path),
            "master_type": r.master_type,
            "passed": r.passed,
            "audio": {
                "format_name": r.audio.format_name,
                "codec_name": r.audio.codec_name,
                "sample_rate_hz": r.audio.sample_rate_hz,
                "bit_depth": r.audio.bit_depth,
                "channels": r.audio.channels,
                "duration_s": r.audio.duration_s,
            },
            "loudness": {
                "integrated_lufs": r.loudness.integrated_lufs,
                "true_peak_db": r.loudness.true_peak_db,
            },
            "checks": r.checks,
        })
    return out


# ----------------------------
# Main
# ----------------------------

def cmd_qc(args: argparse.Namespace) -> int:
    ffmpeg = which_or_die("ffmpeg")
    ffprobe = which_or_die("ffprobe")

    config = load_json(Path(args.config))
    expected = config["expected"]
    masters_cfg = config["masters"]
    naming_cfg = config.get("naming", {"strict": False})
    report_cfg = config.get("report", {})

    root = Path(args.path).resolve()
    if not root.exists():
        die(f"Path does not exist: {root}")

    wavs = []
    if root.is_dir():
        wavs = sorted([p for p in root.rglob("*.wav")])
    else:
        wavs = [root]

    if not wavs:
        die(f"No .wav files found under: {root}")

    allowed_types = naming_cfg.get("master_types", [])
    strict_naming = bool(naming_cfg.get("strict", False))

    results: List[QCResult] = []
    any_fail = False

    # Pre-pass: collect loudness numbers so we can also compare across tracks later if desired
    for p in wavs:
        audio = ffprobe_audio_info(ffprobe, p)
        loud = ffmpeg_loudness(ffmpeg, p)

        checks = []
        checks.extend(check_expected_audio(audio, expected))

        master_type = detect_master_type_from_filename(p.name, allowed_types) if allowed_types else None

        # Naming checks
        if strict_naming:
            ok, msg = validate_naming(p, naming_cfg)
            checks.append({"id": "naming_strict", "pass": ok, "details": msg})
        else:
            checks.append({"id": "naming_strict", "pass": True, "details": "strict naming disabled"})

        # Master-type loudness checks (only if detectable)
        if master_type is None:
            checks.append({"id": "master_type_detected", "pass": False, "details": "Could not detect [MASTER TYPE] from filename"})
        else:
            checks.append({"id": "master_type_detected", "pass": True, "details": master_type})
            checks.extend(check_loudness(master_type, loud, masters_cfg))

        passed = all(c["pass"] for c in checks)
        any_fail = any_fail or (not passed)

        results.append(QCResult(
            path=p,
            master_type=master_type,
            audio=audio,
            loudness=loud,
            checks=checks,
            passed=passed,
        ))

    # Console summary
    print("\n=== QC SUMMARY ===")
    for r in results:
        status = "PASS" if r.passed else "FAIL"
        print(f"{status:4} | {r.path.name} | type={r.master_type or 'UNKNOWN'} | I={pretty(r.loudness.integrated_lufs)} LUFS | TP={pretty(r.loudness.true_peak_db)} dBTP")

    # Write reports
    json_path = Path(report_cfg.get("json_path", "qc_report.json"))
    json_path.write_text(json.dumps(results_to_json(results), indent=2), encoding="utf-8")
    print(f"\nWrote JSON report: {json_path}")

    md_path_str = report_cfg.get("markdown_path")
    if md_path_str:
        md_path = Path(md_path_str)
        write_markdown_report(results, md_path)
        print(f"Wrote Markdown report: {md_path}")

    return 2 if any_fail else 0

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="qc_audio.py", description="Techno Label Audio QC")
    sub = p.add_subparsers(dest="cmd", required=True)

    qc = sub.add_parser("qc", help="Run QC on a file or directory")
    qc.add_argument("path", help="Path to .wav file or directory")
    qc.add_argument("--config", default="qc_config.json", help="Path to qc_config.json")
    qc.set_defaults(func=cmd_qc)

    return p

def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return int(args.func(args))

if __name__ == "__main__":
    raise SystemExit(main())
