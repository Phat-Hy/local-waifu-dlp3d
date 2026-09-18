import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.emotion import (
    EmotionStreamProcessor,
    get_blendshapes_for_emotion,
)


class TestEmotionStreamProcessor(unittest.TestCase):
    def test_blendshape_lookup(self):
        shapes = get_blendshapes_for_emotion("happy")
        self.assertIn("mouthSmile", shapes)
        self.assertEqual(shapes["happy"], 1.0)

        # Fallback to neutral for unknown emotion
        unknown = get_blendshapes_for_emotion("non_existent_emotion")
        self.assertEqual(unknown["neutral"], 1.0)

    def test_sentence_chunking_and_emotion_extraction(self):
        processor = EmotionStreamProcessor()
        tokens = [
            "[happy] Master, ",
            "welcome ",
            "back! ",
            "[blush] I missed ",
            "you so much. ",
            "Did you miss me?"
        ]

        sentences = []
        for token in tokens:
            sentences.extend(processor.process_token(token))
        sentences.extend(processor.flush())

        self.assertEqual(len(sentences), 3)

        # Sentence 1
        self.assertEqual(sentences[0]["text"], "Master, welcome back!")
        self.assertEqual(sentences[0]["emotion"], "happy")
        self.assertIn("mouthSmile", sentences[0]["blendshapes"])

        # Sentence 2
        self.assertEqual(sentences[1]["text"], "I missed you so much.")
        self.assertEqual(sentences[1]["emotion"], "blush")
        self.assertIn("blush", sentences[1]["blendshapes"])

        # Sentence 3 (persists emotion until new tag arrives)
        self.assertEqual(sentences[2]["text"], "Did you miss me?")
        self.assertEqual(sentences[2]["emotion"], "blush")

    def test_gesture_tag_extraction_and_cleaning(self):
        processor = EmotionStreamProcessor()
        tokens = [
            "[happy][gesture:wave] Hello there! ",
            "[shy][gesture:shy] It's nice to see you."
        ]
        sentences = []
        for t in tokens:
            sentences.extend(processor.process_token(t))
        sentences.extend(processor.flush())

        self.assertEqual(len(sentences), 2)
        self.assertEqual(sentences[0]["text"], "Hello there!")
        self.assertEqual(sentences[0]["emotion"], "happy")
        self.assertEqual(sentences[0]["gesture"], "wave")

        self.assertEqual(sentences[1]["text"], "It's nice to see you.")
        self.assertEqual(sentences[1]["emotion"], "shy")
        self.assertEqual(sentences[1]["gesture"], "shy")


if __name__ == "__main__":
    unittest.main()
