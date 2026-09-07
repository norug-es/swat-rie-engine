import hashlib
import importlib.util
import json
import shutil
import subprocess
import tempfile
from urllib.parse import urlparse
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from .config import settings


REMOTE_MEDIA_HOSTS = ("tiktok.com", "youtube.com", "youtu.be", "instagram.com", "facebook.com")


def download_remote_media(url: str) -> tuple[str, str, bytes]:
    if not settings.remote_media_enabled:
        raise ValueError("remote media download is disabled")
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower().removeprefix("www.")
    if parsed.scheme not in {"http", "https"} or not any(host == allowed or host.endswith(f".{allowed}") for allowed in REMOTE_MEDIA_HOSTS):
        raise ValueError("only supported social video URLs can be downloaded")

    try:
        from yt_dlp import YoutubeDL
        with tempfile.TemporaryDirectory(prefix="rie-download-") as temp_dir:
            output = str(Path(temp_dir) / "source.%(ext)s")
            options = {
                "outtmpl": output,
                "format": "best[ext=mp4]/best",
                "noplaylist": True,
                "max_filesize": settings.max_upload_bytes,
                "socket_timeout": settings.remote_media_timeout_seconds,
                "quiet": True,
                "no_warnings": True,
            }
            with YoutubeDL(options) as downloader:
                info = downloader.extract_info(url, download=True)
                downloaded = Path(downloader.prepare_filename(info))
                if not downloaded.exists():
                    candidates = list(Path(temp_dir).glob("source.*"))
                    if not candidates:
                        raise ValueError("downloader returned no media file")
                    downloaded = candidates[0]
                data = downloaded.read_bytes()
                if len(data) > settings.max_upload_bytes:
                    raise ValueError(f"download exceeds {settings.max_upload_bytes} bytes")
                return downloaded.name, info.get("ext") or "video/mp4", data
    except ImportError as exc:
        raise ValueError("yt-dlp is not installed") from exc


SIGNATURES = (
    ("IMAGE", "image/jpeg", (b"\xff\xd8\xff",)),
    ("IMAGE", "image/png", (b"\x89PNG\r\n\x1a\n",)),
    ("IMAGE", "image/webp", (b"RIFF", b"WEBP")),
    ("AUDIO", "audio/mpeg", (b"ID3",)),
    ("AUDIO", "audio/mpeg", (b"\xff\xfb",)),
    ("AUDIO", "audio/wav", (b"RIFF", b"WAVE")),
    ("AUDIO", "audio/ogg", (b"OggS",)),
    ("VIDEO", "video/mp4", (b"ftyp",)),
    ("DOCUMENT", "application/pdf", (b"%PDF",)),
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def detect_media_type(filename: str, data: bytes, provided_mime: str | None) -> tuple[str, str]:
    head = data[:64]
    for input_type, mime_type, markers in SIGNATURES:
        if all(marker in head for marker in markers):
            return input_type, mime_type

    suffix = Path(filename).suffix.lower()
    if suffix in {".jpg", ".jpeg", ".png", ".webp"}:
        return "IMAGE", provided_mime or "application/octet-stream"
    if suffix in {".mp3", ".wav", ".m4a", ".ogg"}:
        return "AUDIO", provided_mime or "application/octet-stream"
    if suffix in {".mp4", ".webm", ".mov"}:
        return "VIDEO", provided_mime or "application/octet-stream"
    if suffix in {".pdf", ".docx", ".html"}:
        return "DOCUMENT", provided_mime or "application/octet-stream"
    return "UNKNOWN", provided_mime or "application/octet-stream"


def run_ffprobe(path: Path) -> tuple[dict, dict]:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return {}, {"stage": "FFPROBE_METADATA", "status": "MISSING_TOOL", "detail": "ffprobe not found in PATH"}

    cmd = [
        ffprobe,
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(path),
    ]
    try:
        completed = subprocess.run(cmd, capture_output=True, text=True, timeout=20, check=True)
        return json.loads(completed.stdout or "{}"), {
            "stage": "FFPROBE_METADATA",
            "status": "COMPLETE",
            "detail": "container metadata extracted",
        }
    except Exception as exc:
        return {}, {"stage": "FFPROBE_METADATA", "status": "FAILED", "detail": str(exc)[:300]}


def run_ffmpeg(cmd: list[str], timeout: int = 60) -> dict:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return stage("FFMPEG", "MISSING_TOOL", "ffmpeg not found in PATH")
    try:
        completed = subprocess.run(
            [ffmpeg, *cmd],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=True,
        )
        detail = completed.stderr.splitlines()[-1] if completed.stderr.splitlines() else "completed"
        return stage("FFMPEG", "COMPLETE", detail[:300])
    except Exception as exc:
        return stage("FFMPEG", "FAILED", str(exc)[:300])


def normalize_audio(source: Path, artifact_root: Path, artifact_id: str) -> tuple[Path | None, dict]:
    output = artifact_root / f"{artifact_id}.normalized.wav"
    result = run_ffmpeg([
        "-y",
        "-i",
        str(source),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-f",
        "wav",
        str(output),
    ])
    result["stage"] = "AUDIO_NORMALIZATION"
    if result["status"] != "COMPLETE":
        return None, result
    return output, stage("AUDIO_NORMALIZATION", "COMPLETE", str(output))


def extract_keyframes(source: Path, artifact_root: Path, artifact_id: str) -> tuple[list[str], dict]:
    frame_dir = artifact_root / f"{artifact_id}.frames"
    frame_dir.mkdir(parents=True, exist_ok=True)
    output_pattern = frame_dir / "frame-%04d.jpg"
    result = run_ffmpeg([
        "-y",
        "-i",
        str(source),
        "-vf",
        f"fps={settings.video_keyframe_fps}",
        "-frames:v",
        "12",
        str(output_pattern),
    ], timeout=90)
    result["stage"] = "KEYFRAME_EXTRACTION"
    frames = sorted(str(path) for path in frame_dir.glob("*.jpg"))
    if result["status"] != "COMPLETE":
        return frames, result
    return frames, stage("KEYFRAME_EXTRACTION", "COMPLETE", f"{len(frames)} frame(s) extracted")


def hash_keyframes(frame_paths: list[str]) -> tuple[list[str], dict]:
    try:
        import imagehash
        from PIL import Image
    except ImportError:
        return [], stage("PERCEPTUAL_HASH", "MISSING_TOOL", "install ImageHash and Pillow")

    hashes = []
    try:
        for frame_path in frame_paths:
            with Image.open(frame_path) as image:
                hashes.append(f"{Path(frame_path).name}:{imagehash.phash(image)}")
    except Exception as exc:
        return hashes, stage("PERCEPTUAL_HASH", "FAILED", str(exc)[:300])
    return hashes, stage("PERCEPTUAL_HASH", "COMPLETE", f"{len(hashes)} perceptual hash(es) computed")


def transcribe_audio(path: Path) -> tuple[dict | None, dict]:
    if not settings.transcription_enabled:
        return None, stage("TRANSCRIPTION", "MISSING_CONFIG", "set RIE_TRANSCRIPTION_ENABLED=true to enable faster-whisper")
    if not importlib.util.find_spec("faster_whisper"):
        return None, stage("TRANSCRIPTION", "MISSING_TOOL", "faster_whisper is not installed")
    try:
        from faster_whisper import WhisperModel

        model = WhisperModel(settings.whisper_model, device="cpu", compute_type="int8")
        segments, info = model.transcribe(str(path), beam_size=1)
        segment_payload = [
            {"start": round(segment.start, 2), "end": round(segment.end, 2), "text": segment.text.strip()}
            for segment in segments
        ]
        transcript = " ".join(segment["text"] for segment in segment_payload).strip()
        payload = {
            "engine": "faster-whisper",
            "model": settings.whisper_model,
            "language": info.language,
            "language_probability": round(info.language_probability or 0.0, 3),
            "text": transcript,
            "segments": segment_payload,
        }
        return payload, stage("TRANSCRIPTION", "COMPLETE", f"{len(transcript)} chars transcribed")
    except Exception as exc:
        return None, stage("TRANSCRIPTION", "FAILED", str(exc)[:300])


def upsert_pipeline_stage(pipeline: list[dict], new_stage: dict) -> list[dict]:
    updated = []
    replaced = False
    for item in pipeline:
        if item.get("stage") == new_stage["stage"]:
            updated.append(new_stage)
            replaced = True
        else:
            updated.append(item)
    if not replaced:
        updated.append(new_stage)
    return updated


def transcribe_artifact(artifact: dict) -> dict:
    audio_path = artifact.get("metadata", {}).get("normalized_audio_path")
    if not audio_path:
        source_path = artifact.get("storage_path")
        if not source_path:
            artifact["pipeline"] = upsert_pipeline_stage(
                artifact.get("pipeline", []),
                stage("TRANSCRIPTION", "SKIPPED", "artifact has no audio path"),
            )
            return artifact
        audio_path = source_path

    transcript, transcription_stage = transcribe_audio(Path(audio_path))
    artifact.setdefault("metadata", {})["transcription"] = transcript
    artifact["pipeline"] = upsert_pipeline_stage(artifact.get("pipeline", []), transcription_stage)
    frame_paths = artifact.get("metadata", {}).get("keyframes", [])
    if frame_paths:
        perceptual_hashes, perceptual_hash_stage = hash_keyframes(frame_paths)
        artifact.setdefault("metadata", {})["perceptual_hashes"] = perceptual_hashes
        artifact["pipeline"] = upsert_pipeline_stage(artifact.get("pipeline", []), perceptual_hash_stage)
    artifact["updated_at"] = now_iso()
    return artifact


def stage(name: str, status: str, detail: str | None = None) -> dict:
    return {"stage": name, "status": status, "detail": detail}


def ingest_media(filename: str, content_type: str | None, data: bytes) -> dict:
    if not data:
        raise ValueError("empty upload")
    if len(data) > settings.max_upload_bytes:
        raise ValueError(f"upload exceeds {settings.max_upload_bytes} bytes")

    artifact_id = str(uuid4())
    digest = sha256_bytes(data)
    input_type, detected_mime = detect_media_type(filename, data, content_type)
    artifact_root = Path(settings.artifact_dir)
    artifact_root.mkdir(parents=True, exist_ok=True)
    suffix = Path(filename).suffix.lower() or ".bin"
    storage_path = artifact_root / f"{artifact_id}{suffix}"
    storage_path.write_bytes(data)

    metadata = {
        "original_filename": filename,
        "provided_mime": content_type,
        "detected_mime": detected_mime,
    }
    pipeline = [
        stage("SIGNATURE_VALIDATION", "COMPLETE", f"detected={input_type}:{detected_mime}"),
        stage("SHA256_FINGERPRINT", "COMPLETE", digest),
        stage("ARTIFACT_STORAGE", "COMPLETE", str(storage_path)),
    ]

    if input_type in {"AUDIO", "VIDEO"}:
        ffprobe_metadata, ffprobe_stage = run_ffprobe(storage_path)
        metadata["ffprobe"] = ffprobe_metadata
        pipeline.append(ffprobe_stage)

    if input_type == "VIDEO":
        normalized_audio, audio_stage = normalize_audio(storage_path, artifact_root, artifact_id)
        frames, keyframe_stage = extract_keyframes(storage_path, artifact_root, artifact_id)
        perceptual_hashes, perceptual_hash_stage = hash_keyframes(frames)
        metadata["normalized_audio_path"] = str(normalized_audio) if normalized_audio else None
        metadata["keyframes"] = frames
        metadata["perceptual_hashes"] = perceptual_hashes
        pipeline.extend([
            keyframe_stage,
            audio_stage,
        ])
        if normalized_audio:
            transcript, transcription_stage = transcribe_audio(normalized_audio)
            metadata["transcription"] = transcript
        else:
            transcription_stage = stage("TRANSCRIPTION", "SKIPPED", "audio normalization did not complete")
        pipeline.extend([
            transcription_stage,
            stage("DEEPFAKE_ENSEMBLE", "MISSING_TOOL", "requires configured detector ensemble"),
            perceptual_hash_stage,
        ])
    elif input_type == "AUDIO":
        normalized_audio, audio_stage = normalize_audio(storage_path, artifact_root, artifact_id)
        metadata["normalized_audio_path"] = str(normalized_audio) if normalized_audio else None
        if normalized_audio:
            transcript, transcription_stage = transcribe_audio(normalized_audio)
            metadata["transcription"] = transcript
        else:
            transcription_stage = stage("TRANSCRIPTION", "SKIPPED", "audio normalization did not complete")
        pipeline.extend([
            audio_stage,
            transcription_stage,
            stage("SPEAKER_DIARIZATION", "MISSING_TOOL", "requires pyannote or compatible model"),
            stage("SYNTHETIC_AUDIO_DETECTION", "MISSING_TOOL", "requires configured detector ensemble"),
            stage("AUDIO_FINGERPRINT", "MISSING_TOOL", "requires audio fingerprint worker"),
        ])
    elif input_type == "IMAGE":
        pipeline.extend([
            stage("OCR", "MISSING_TOOL", "requires OCR engine"),
            stage("PERCEPTUAL_HASH", "MISSING_TOOL", "requires imagehash/OpenCV"),
            stage("MANIPULATION_ANALYSIS", "MISSING_TOOL", "requires forensic detector"),
        ])
    elif input_type == "DOCUMENT":
        pipeline.extend([
            stage("TEXT_EXTRACTION", "MISSING_TOOL", "requires document parser"),
            stage("MALWARE_SCAN", "MISSING_TOOL", "requires scanner integration"),
        ])
    else:
        pipeline.append(stage("MEDIA_NORMALIZATION", "SKIPPED", "unsupported or unknown media type"))

    return {
        "artifact_id": artifact_id,
        "filename": filename,
        "input_type": input_type,
        "mime_type": detected_mime,
        "size_bytes": len(data),
        "sha256": digest,
        "storage_path": str(storage_path),
        "metadata": metadata,
        "pipeline": pipeline,
        "created_at": now_iso(),
    }
