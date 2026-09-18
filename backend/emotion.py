"""
Emotion Parser and Sentence Streamer
Extracts bracketed emotion tags from LLM token streams,
maps emotions to 3D facial blendshape weights, and chunks output into speakable sentences for TTS.
"""

import re
from typing import Dict, Any, List, Tuple, Generator

# Default 3D blendshape mappings for common anime emotions (compatible with VRM / Babylon / DLP3D)
EMOTION_BLENDSHAPES: Dict[str, Dict[str, float]] = {
    "happy": {
        "happy": 1.0,
        "mouthSmile": 0.8,
        "browInnerUp": 0.3,
    },
    "smile": {
        "happy": 0.7,
        "mouthSmile": 0.6,
    },
    "blush": {
        "happy": 0.6,
        "blush": 1.0,
        "mouthSmile": 0.4,
        "eyeSquint": 0.3,
    },
    "shy": {
        "blush": 0.8,
        "browInnerUp": 0.5,
        "mouthSmile": 0.2,
    },
    "tsundere": {
        "angry": 0.5,
        "blush": 0.6,
        "browDown": 0.4,
        "mouthFrown": 0.3,
    },
    "surprised": {
        "surprised": 1.0,
        "eyeWide": 0.8,
        "browOuterUp": 0.7,
        "mouthOpen": 0.5,
    },
    "sad": {
        "sad": 0.9,
        "browDown": 0.6,
        "mouthFrown": 0.7,
    },
    "thinking": {
        "browInnerUp": 0.4,
        "lookUp": 0.5,
        "mouthPucker": 0.3,
    },
    "neutral": {
        "neutral": 1.0,
    },
    "angry": {
        "angry": 1.0,
        "browDown": 0.9,
        "mouthFrown": 0.6,
    },
    "wink": {
        "eyeBlinkLeft": 1.0,
        "mouthSmile": 0.7,
    }
}

EMOTION_TAG_PATTERN = re.compile(r"\[([a-zA-Z0-9_\-:]+)\]")
SENTENCE_SPLIT_PATTERN = re.compile(r"([.!?~\n]+)")
SUPPORTED_GESTURES = {"nod", "tilt", "wave", "think", "shy", "excited", "shrug", "lean", "laugh"}


def get_blendshapes_for_emotion(emotion: str) -> Dict[str, float]:
    clean_emotion = emotion.lower().strip()
    return EMOTION_BLENDSHAPES.get(clean_emotion, EMOTION_BLENDSHAPES["neutral"])


class EmotionStreamProcessor:
    """
    Processes incoming text or token streams, tracking current emotional state,
    stripping emotion & gesture tags for clean TTS audio, and yielding complete speakable sentences.
    """
    def __init__(self, default_emotion: str = "neutral"):
        self.current_emotion = default_emotion
        self.buffer = ""

    def process_token(self, token: str) -> List[Dict[str, Any]]:
        """
        Accepts a streamed token, updates buffer, and returns any complete sentences ready for TTS.
        """
        self.buffer += token
        results: List[Dict[str, Any]] = []

        # Check for sentence delimiters in buffer
        match = SENTENCE_SPLIT_PATTERN.search(self.buffer)
        while match:
            end_pos = match.end()
            sentence_raw = self.buffer[:end_pos]
            self.buffer = self.buffer[end_pos:]

            parsed = self._extract_emotion_and_clean_text(sentence_raw)
            if parsed["text"].strip():
                results.append(parsed)

            match = SENTENCE_SPLIT_PATTERN.search(self.buffer)

        return results

    def flush(self) -> List[Dict[str, Any]]:
        """
        Flushes any remaining text in buffer when LLM stream finishes.
        """
        results: List[Dict[str, Any]] = []
        if self.buffer.strip():
            parsed = self._extract_emotion_and_clean_text(self.buffer)
            if parsed["text"].strip():
                results.append(parsed)
            self.buffer = ""
        return results

    def _extract_emotion_and_clean_text(self, raw_text: str) -> Dict[str, Any]:
        """
        Detects any emotion and gesture tags in the sentence, updates self.current_emotion,
        and returns cleaned text alongside blendshape and gesture data.
        """
        detected_tags = EMOTION_TAG_PATTERN.findall(raw_text)
        detected_gesture = "none"
        if detected_tags:
            for tag in detected_tags:
                tag_lower = tag.lower().strip()
                if tag_lower.startswith("gesture:"):
                    g = tag_lower.split(":", 1)[1].strip()
                    if g in SUPPORTED_GESTURES:
                        detected_gesture = g
                elif tag_lower in EMOTION_BLENDSHAPES:
                    self.current_emotion = tag_lower
                    if detected_gesture == "none" and tag_lower in SUPPORTED_GESTURES:
                        detected_gesture = tag_lower
                elif tag_lower in SUPPORTED_GESTURES:
                    detected_gesture = tag_lower

        # Remove bracketed tags from the spoken text so TTS doesn't read tags out loud
        cleaned_text = EMOTION_TAG_PATTERN.sub("", raw_text).strip()

        return {
            "text": cleaned_text,
            "raw": raw_text,
            "emotion": self.current_emotion,
            "gesture": detected_gesture,
            "blendshapes": get_blendshapes_for_emotion(self.current_emotion),
        }
