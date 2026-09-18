import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.character_generator import (
    synthesize_personality_prompt,
    generate_character_personality,
)


class TestCharacterGenerator(unittest.TestCase):
    def test_synthesize_personality_prompt(self):
        name = "Furina"
        lore = "Furina is a major character in Fontaine, known for her dramatic theatrical flair and secret vulnerabilities."
        prompt = synthesize_personality_prompt(name, lore)

        self.assertIn("Furina", prompt)
        self.assertIn("Fontaine", prompt)
        self.assertIn("[happy]", prompt)
        self.assertIn("[blush]", prompt)
        self.assertIn("Never break character", prompt)

    def test_generate_character_empty(self):
        res = generate_character_personality("   ")
        self.assertFalse(res["success"])
        self.assertIn("cannot be empty", res["error"])

    def test_generate_character_fallback_or_online(self):
        res = generate_character_personality("Furina")
        self.assertTrue(res["success"])
        self.assertEqual(res["character_name"], "Furina")
        self.assertIn("[3D Avatar Emotion & Gesture Rules]", res["system_prompt"])
        self.assertIn("[gesture:wave]", res["system_prompt"])


if __name__ == "__main__":
    unittest.main()
