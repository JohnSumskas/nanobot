"""Audio conversion utilities for format compatibility."""

from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path
from typing import Literal

from loguru import logger


async def convert_audio(
    input_path: str | Path,
    output_format: Literal["ogg", "opus", "wav", "m4a"] = "ogg",
) -> str | None:
    """
    Convert audio file to the specified format using ffmpeg.
    
    Args:
        input_path: Path to input audio file
        output_format: Target format (ogg, opus, wav, m4a)
    
    Returns:
        Path to converted file, or None if conversion failed
    """
    input_path = Path(input_path)
    if not input_path.exists():
        logger.error("Audio file not found: {}", input_path)
        return None
    
    # Determine output extension and codec
    codec_map = {
        "ogg": ("libopus", ".ogg"),
        "opus": ("libopus", ".ogg"),  # Opus codec in OGG container
        "wav": ("pcm_s16le", ".wav"),
        "m4a": ("aac", ".m4a"),
    }
    
    if output_format not in codec_map:
        logger.error("Unsupported output format: {}", output_format)
        return None
    
    codec, ext = codec_map[output_format]
    output_path = input_path.with_suffix(ext)
    
    # Avoid overwriting if input and output are the same
    if input_path == output_path:
        logger.debug("Input and output formats match, no conversion needed")
        return str(input_path)
    
    # Build ffmpeg command
    cmd = [
        "ffmpeg",
        "-i", str(input_path),
        "-c:a", codec,
        "-y",  # Overwrite output file
        str(output_path),
    ]
    
    try:
        logger.debug("Converting audio: {} -> {}", input_path.name, output_path.name)
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await asyncio.wait_for(process.communicate(), timeout=30.0)
        
        if process.returncode != 0:
            error_msg = stderr.decode("utf-8", errors="replace") if stderr else "Unknown error"
            logger.error("Audio conversion failed: {}", error_msg)
            return None
        
        logger.debug("Audio conversion successful: {}", output_path)
        return str(output_path)
    
    except asyncio.TimeoutError:
        logger.error("Audio conversion timed out")
        return None
    except Exception as e:
        logger.error("Audio conversion error: {}", e)
        return None


def is_ffmpeg_available() -> bool:
    """Check if ffmpeg is available in the system."""
    try:
        subprocess.run(
            ["ffmpeg", "-version"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
