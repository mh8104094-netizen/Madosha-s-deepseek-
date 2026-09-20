import importlib.util
from pathlib import Path
import sys
import unittest


MODULE_PATH = Path(__file__).with_name("rag.py")
spec = importlib.util.spec_from_file_location("rag", MODULE_PATH)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)

MiniRAG = module.MiniRAG
chunk_text = module.chunk_text


class MiniRAGTests(unittest.TestCase):
    def test_chunk_validation(self):
        with self.assertRaises(ValueError):
            chunk_text("hello world", chunk_size=5, overlap=5)

    def test_relevant_document_ranks_first(self):
        index = MiniRAG()
        index.fit({
            "python": "Python automation uses scripts APIs workflows and testing.",
            "cooking": "Cooking recipes use ingredients ovens and seasoning.",
        }, chunk_size=20, overlap=2)

        hits = index.search("automation workflows Python", top_k=2)
        self.assertTrue(hits)
        self.assertEqual(hits[0].document_id, "python")

    def test_unknown_query_returns_no_hits(self):
        index = MiniRAG()
        index.fit({"doc": "alpha beta gamma"}, chunk_size=10, overlap=1)
        self.assertEqual(index.search("completely-unrelated"), [])


if __name__ == "__main__":
    unittest.main()
