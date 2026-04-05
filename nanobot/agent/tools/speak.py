"""SpeakTool: synthesize text via Kokoro TTS and send as a Telegram voice message."""

from __future__ import annotations

import uuid
from typing import Any, Awaitable, Callable

import httpx

from nanobot.agent.tools.base import Tool
from nanobot.bus.events import OutboundMessage
from nanobot.config.paths import get_media_dir


class SpeakTool(Tool):
    """Tool to synthesize text to speech and send as a voice message."""

    def __init__(
        self,
        send_callback: Callable[[OutboundMessage], Awaitable[None]] | None = None,
        default_channel: str = "",
        default_chat_id: str = "",
        default_message_id: str | None = None,
        tts_url: str = "http://localhost:8880",
        voice: str = "af_bella",
        model: str = "kokoro",
        response_format: str = "ogg",
    ):
        self._send_callback = send_callback
        self._default_channel = default_channel
        self._default_chat_id = default_chat_id
        self._default_message_id = default_message_id
        self._tts_url = tts_url
        self._voice = voice
        self._model = model
        self._response_format = response_format
        self._sent_in_turn: bool = False

    def set_context(self, channel: str, chat_id: str, message_id: str | None = None) -> None:
        """Set the current message context."""
        self._default_channel = channel
        self._default_chat_id = chat_id
        self._default_message_id = message_id

    def start_turn(self) -> None:
        """Reset per-turn send tracking."""
        self._sent_in_turn = False

    def set_send_callback(self, callback: Callable[[OutboundMessage], Awaitable[None]]) -> None:
        """Set the callback for sending messages."""
        self._send_callback = callback

    @property
    def name(self) -> str:
        return "speak"

    @property
    def description(self) -> str:
        return (
            "Synthesize text to speech using Kokoro TTS and send it as a Telegram voice message. "
            "Use this when the user asks you to speak, say something aloud, or reply with voice. "
            "Do NOT use this for regular text replies — use message() for that."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "The text to synthesize",
                },
                "voice": {
                    "type": "string",
                    "description": "Optional voice override (e.g. af_bella, bm_george, af_heart)",
                },
                "channel": {
                    "type": "string",
                    "description": "Optional: target channel (telegram, discord, etc.)",
                },
                "chat_id": {
                    "type": "string",
                    "description": "Optional: target chat/user ID",
                },
            },
            "required": ["text"],
        }

    async def execute(
        self,
        text: str,
        voice: str | None = None,
        channel: str | None = None,
        chat_id: str | None = None,
        **kwargs: Any,
    ) -> str:
        channel = channel or self._default_channel
        chat_id = chat_id or self._default_chat_id
        if not channel or not chat_id:
            return "Error: No target channel/chat specified"
        if not self._send_callback:
            return "Error: TTS sending not configured"

        selected_voice = voice or self._voice
        # Kokoro's "opus" format returns OGG/Opus, which we save as .ogg for Telegram's send_voice
        ext = ".ogg" if self._response_format == "opus" else f".{self._response_format}"
        media_dir = get_media_dir("telegram")
        file_path = media_dir / f"tts_{uuid.uuid4().hex}{ext}"

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(
                    f"{self._tts_url}/v1/audio/speech",
                    json={
                        "model": self._model,
                        "input": text,
                        "voice": selected_voice,
                        "response_format": self._response_format,
                    },
                )
                resp.raise_for_status()
                file_path.write_bytes(resp.content)
        except Exception as e:
            return f"Error: TTS synthesis failed: {e}"

        msg = OutboundMessage(
            channel=channel,
            chat_id=chat_id,
            content="",
            media=[str(file_path)],
            metadata={"message_id": self._default_message_id},
        )
        try:
            await self._send_callback(msg)
            if channel == self._default_channel and chat_id == self._default_chat_id:
                self._sent_in_turn = True
            return f"Voice message sent ({len(text)} chars, voice={selected_voice})"
        except Exception as e:
            return f"Error: Failed to send voice message: {e}"
