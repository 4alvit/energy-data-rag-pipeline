"""Unit tests for JSON answer normalization, without ingestion dependencies."""

import ast
import json
import unittest
from collections.abc import Iterator
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock


def load_forum_functions(parser):
    source = Path(__file__).resolve().parents[1] / "src/energy_rag/ingestion/forum_loader.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    functions = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name in {"_build_post_content", "_extract_posts", "load_forum_json"}
    ]
    namespace = {
        "BeautifulSoup": parser,
        "Document": SimpleNamespace,
        "Iterator": Iterator,
        "Path": Path,
        "json": json,
    }
    # Compile the checked-in JSON caller and helpers without optional ingestion clients.
    exec(compile(ast.Module(body=functions, type_ignores=[]), str(source), "exec"), namespace)  # noqa: S102
    return namespace


class ForumBuildPostContentTests(unittest.TestCase):
    def setUp(self):
        self.parser = Mock()
        functions = load_forum_functions(self.parser)
        self.build = functions["_build_post_content"]
        self.load_json = functions["load_forum_json"]

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
        self.assertEqual(text, "")

    def test_whitespace_and_empty_html_answers_are_omitted(self):
        self.parser.return_value.get_text.return_value = ""
        for answer in (" \n", "<p></p>", {"body": "<p></p>", "accepted": True}):
            with self.subTest(answer=answer):
                self.assertEqual(self.build({"replies": [answer]}), "")

    def test_json_loader_skips_empty_posts_and_preserves_nonempty_answers(self):
        self.parser.return_value.get_text.return_value = ""
        posts = [
            {"answers": [""]},
            {"replies": [" \n", None]},
            {"answers": [{"body": "<p></p>"}]},
            {"title": "Question", "answers": ["", "Actual answer", None]},
        ]
        with TemporaryDirectory() as directory:
            source = Path(directory) / "posts.json"
            source.write_text(json.dumps({"posts": posts}), encoding="utf-8")
            documents = list(self.load_json(source))
        self.assertEqual(len(documents), 1)
        self.assertEqual(
            documents[0].page_content,
            "# Question\n\n## Answers\n\n### Answer 2\nActual answer",
        )
        self.assertEqual(documents[0].metadata["title"], "Question")

    def test_string_html_uses_the_existing_html_cleaner(self):
        self.parser.return_value.get_text.return_value = "clean answer"
        text = self.build({"answers": ["<b>answer</b>"]})
        self.parser.assert_called_once_with("<b>answer</b>", "html.parser")
        self.parser.return_value.get_text.assert_called_once_with(separator="\n", strip=True)
        self.assertIn("### Answer 1\nclean answer", text)


if __name__ == "__main__":
    unittest.main()
