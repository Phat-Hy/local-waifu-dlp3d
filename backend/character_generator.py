"""
Character Personality Search & Generator
Searches the web (Wikipedia & DuckDuckGo APIs) for character lore, personality, and mannerisms,
and synthesizes a tailored 3D avatar system prompt with emotion tags.
"""

import json
import re
import urllib.request
import urllib.parse
from typing import Dict, Any, List, Optional

USER_AGENT = "LocalWaifuDLP3D/1.0 (Desktop Assistant)"


def search_wikipedia_character(character_name: str, timeout: int = 6) -> Optional[Dict[str, str]]:
    """
    Searches Wikipedia for character information and extracts summary lore.
    """
    try:
        # 1. Search for best matching page
        search_query = f"{character_name} anime character" if " " not in character_name else character_name
        search_url = (
            "https://en.wikipedia.org/w/api.php?action=query&list=search&format=json&srlimit=3&srsearch="
            + urllib.parse.quote(search_query)
        )
        req = urllib.request.Request(search_url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        search_results = data.get("query", {}).get("search", [])
        if not search_results:
            return None

        # Pick top result title
        page_title = search_results[0]["title"]

        # 2. Fetch page extract
        extract_url = (
            "https://en.wikipedia.org/w/api.php?action=query&prop=extracts&exintro=1&explaintext=1&format=json&titles="
            + urllib.parse.quote(page_title)
        )
        req2 = urllib.request.Request(extract_url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req2, timeout=timeout) as resp2:
            data2 = json.loads(resp2.read().decode("utf-8"))

        pages = data2.get("query", {}).get("pages", {})
        for page_id, page_info in pages.items():
            if page_id != "-1" and "extract" in page_info:
                extract = page_info["extract"].strip()
                if extract:
                    return {
                        "title": page_title,
                        "source": f"https://en.wikipedia.org/wiki/{urllib.parse.quote(page_title)}",
                        "summary": extract,
                    }
    except Exception as e:
        print(f"[CharacterSearch] Wikipedia lookup error: {e}")

    return None


def search_duckduckgo_character(character_name: str, timeout: int = 6) -> Optional[Dict[str, str]]:
    """
    Fallback character lookup via DuckDuckGo Instant Answer API.
    """
    try:
        url = f"https://api.duckduckgo.com/?q={urllib.parse.quote(character_name)}&format=json&no_html=1&skip_disambig=1"
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        abstract = data.get("AbstractText", "").strip()
        if abstract:
            return {
                "title": data.get("Heading", character_name),
                "source": data.get("AbstractURL", "DuckDuckGo"),
                "summary": abstract,
            }
    except Exception as e:
        print(f"[CharacterSearch] DuckDuckGo lookup error: {e}")

    return None


def synthesize_personality_prompt(character_name: str, lore: str, source_title: str = "") -> str:
    """
    Transforms extracted lore into an expressive, emotion-tagged system prompt for local LLM roleplay.
    """
    # Clean up multi-paragraph extracts to concise 3-4 sentences
    paragraphs = [p.strip() for p in lore.split("\n") if p.strip()]
    condensed_lore = " ".join(paragraphs[:3])
    if len(condensed_lore) > 800:
        condensed_lore = condensed_lore[:800] + "..."

    prompt = f"""You are roleplaying as {character_name}.
Never break character or mention that you are an AI. You embody this character completely in thought, speech, and emotion.

[Character Lore & Identity]
{condensed_lore}

[Roleplay Guidelines & Speech Style]
- Speak in the distinct voice, tone, vocabulary, and mannerisms of {character_name}.
- React authentically according to your personality, emotional temperament, and quirks.
- Treat the user as your cherished companion, responding with vivid emotional depth.

[3D Avatar Emotion & Gesture Rules]
At the beginning of sentences where your emotion or physical posture changes, prepend emotion and gesture tags in brackets:
- Emotion tags: [happy], [smile], [blush], [tsundere], [shy], [surprised], [sad], [thinking], [neutral], [angry], [wink].
- Gesture tags: [gesture:nod], [gesture:tilt], [gesture:wave], [gesture:think], [gesture:shy], [gesture:excited], [gesture:shrug], [gesture:lean].

Example:
[happy][gesture:wave] Ah, it is wonderful to see you! [blush][gesture:shy] I was hoping you would come speak with me today.
"""
    return prompt.strip()


def generate_character_personality(character_name: str) -> Dict[str, Any]:
    """
    Full pipeline: Searches internet for character details and synthesizes the tailored system prompt.
    """
    clean_name = character_name.strip()
    if not clean_name:
        return {"success": False, "error": "Character name cannot be empty."}

    # 1. Try Wikipedia search
    info = search_wikipedia_character(clean_name)
    
    # 2. Fallback to DuckDuckGo if Wikipedia returned nothing
    if not info:
        info = search_duckduckgo_character(clean_name)

    if not info:
        # Fallback default anime synthesis if offline or character not found
        fallback_lore = f"{clean_name} is a charming, expressive character known for their distinct personality, loyal bond, and memorable presence."
        prompt = synthesize_personality_prompt(clean_name, fallback_lore)
        return {
            "success": True,
            "character_name": clean_name,
            "source": "General Template (Web search yielded no specific match)",
            "system_prompt": prompt,
            "note": "Created from template because no online profile was found.",
        }

    prompt = synthesize_personality_prompt(clean_name, info["summary"], info["title"])
    return {
        "success": True,
        "character_name": clean_name,
        "matched_title": info["title"],
        "source": info["source"],
        "summary": info["summary"][:200] + "...",
        "system_prompt": prompt,
    }
