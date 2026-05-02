"""Chroma + fastembed wrapper around a multilingual sentence embedder."""
from __future__ import annotations

from pathlib import Path
from typing import Iterable

import chromadb
from chromadb.api.models.Collection import Collection
from fastembed import TextEmbedding

from .config import CHROMA_DIR, COLLECTION_NAME, EMBEDDING_MODEL


class Store:
    def __init__(self, persist_dir: Path = CHROMA_DIR):
        persist_dir.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=str(persist_dir))
        self._embedder = TextEmbedding(model_name=EMBEDDING_MODEL)
        self._collection: Collection = self._client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )

    def _embed_passages(self, texts: list[str]) -> list[list[float]]:
        return [v.tolist() for v in self._embedder.embed(texts)]

    def _embed_query(self, text: str) -> list[float]:
        return next(self._embedder.embed([text])).tolist()

    def upsert(
        self,
        ids: list[str],
        documents: list[str],
        metadatas: list[dict],
    ) -> None:
        if not ids:
            return
        embeddings = self._embed_passages(documents)
        self._collection.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas,
        )

    def delete_by_source(self, source_path: str) -> None:
        self._collection.delete(where={"source_path": source_path})

    def query(
        self,
        text: str,
        limit: int = 10,
        where: dict | None = None,
    ) -> list[dict]:
        emb = self._embed_query(text)
        result = self._collection.query(
            query_embeddings=[emb],
            n_results=limit,
            where=where,
        )
        out = []
        ids = result.get("ids", [[]])[0]
        docs = result.get("documents", [[]])[0]
        metas = result.get("metadatas", [[]])[0]
        dists = result.get("distances", [[]])[0]
        for i, doc, meta, dist in zip(ids, docs, metas, dists):
            out.append(
                {
                    "id": i,
                    "text": doc,
                    "metadata": meta or {},
                    "distance": dist,
                }
            )
        return out

    def count(self) -> int:
        return self._collection.count()
