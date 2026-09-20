# Mini RAG Engine

A dependency-free retrieval engine that exposes the mechanics behind a simple RAG pipeline.

Instead of hiding retrieval inside a framework, this project implements chunking, tokenization, TF-IDF weighting, cosine similarity, and ranked evidence directly in Python.

## What it demonstrates

- Explainable document retrieval
- Lightweight indexing
- Evidence ranking before an LLM is called
- Separation between retrieval and generation

## Run

```bash
python projects/mini-rag-engine/rag.py
python projects/mini-rag-engine/test_rag.py
```

In a production system, the retriever can be swapped for embeddings / a vector database while keeping the same evidence-first interface.
