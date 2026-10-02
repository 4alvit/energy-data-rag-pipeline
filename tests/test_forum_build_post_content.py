"""Unit tests for JSON answer normalization, without ingestion dependencies."""

import ast
import unittest
from pathlib import Path
from unittest.mock import Mock


def load_build_post_content(parser):
    source = Path(__file__).resolve().parents[1] / "src/energy_rag/ingestion/forum_loader.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    function = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_build_post_content"
    )
    namespace = {"BeautifulSoup": parser}
    # Compile the checked-in function only; do not load optional ingestion clients.
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(source), "exec"), namespace)  # noqa: S102
    return namespace["_build_post_content"]


class ForumBuildPostContentTests(unittest.TestCase):
    def setUp(self):
        self.parser = Mock()
        self.build = load_build_post_content(self.parser)

    def test_plain_string_answers_and_replies(self):
        for key in ("answers", "replies"):
            with self.subTest(key=key):
                text = self.build({"title": "T", "body": "B", key: ["hello"]})
                self.assertIn("### Answer 1\nhello", text)
        self.parser.assert_not_called()

    def test_dictionary_answers_keep_acceptance_and_content_alias(self):
        text = self.build(
            {
                "answers": [
                    {"body": "first", "accepted": True},
                    {"content": "second", "is_accepted": True},
                ]
            }
        )
        self.assertIn("### Answer 1 ✓\nfirst", text)
        self.assertIn("### Answer 2 ✓\nsecond", text)

    def test_empty_answers_are_omitted(self):
        text = self.build({"answers": [None, "", {"body": None}]})
        self.assertNotIn("### Answer", text)

    def test_string_html_uses_the_existing_html_cleaner(self):
        self.parser.return_value.get_text.return_value = "clean answer"
        text = self.build({"answers": ["<b>answer</b>"]})
        self.parser.assert_called_once_with("<b>answer</b>", "html.parser")
        self.parser.return_value.get_text.assert_called_once_with(separator="\n", strip=True)
        self.assertIn("### Answer 1\nclean answer", text)


if __name__ == "__main__":
    unittest.main()
