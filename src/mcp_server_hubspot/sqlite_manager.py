import os
import logging
import numpy as np
import json
from datetime import datetime, timedelta
from typing import Dict, List, Any, Tuple

import libsql_experimental as libsql

logger = logging.getLogger("mcp_hubspot_sqlite_manager")

_VECTOR_INDEX_NAME = "idx_embedding_vec"


class SqliteManager:
    """Vector store backed by libSQL with native F32_BLOB vector search.

    Uses libSQL's built-in DiskANN index (vector_top_k / vector_distance_cos)
    for approximate nearest-neighbour retrieval, eliminating the need for
    in-process numpy brute-force similarity computation.

    Rolling day-based cleanup keeps storage bounded: rows older than
    max_days are deleted on startup.

    Distances returned by vector_distance_cos are cosine distances in [0, 2],
    so the upstream formula ``similarity_score = 1.0 - distance / 2.0``
    maps them back to a [0, 1] cosine similarity score.
    """

    def __init__(self, storage_dir: str = "/storage", max_days: int = 7, embedding_dimension: int = 384):
        """Initialise the libSQL vector store.

        Args:
            storage_dir: Directory that contains (or will contain) the DB file.
            max_days: Rows older than this many days are removed on startup.
            embedding_dimension: Dimensionality expected by the embedding model.
        """
        self.storage_dir = storage_dir
        self.max_days = max_days
        self.embedding_dimension = embedding_dimension

        os.makedirs(self.storage_dir, exist_ok=True)
        self._init_db()
        self._cleanup_old_data()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_db_path(self) -> str:
        return os.path.join(self.storage_dir, "hubspot_cache.db")

    def _connect(self):
        """Return a new libSQL connection to the local database file."""
        return libsql.connect(self._get_db_path())

    def _init_db(self) -> None:
        """Create the embeddings table and vector index if they don't exist."""
        conn = self._connect()
        try:
            conn.execute(f"""
                CREATE TABLE IF NOT EXISTS embeddings (
                    id        INTEGER PRIMARY KEY AUTOINCREMENT,
                    date      TEXT    NOT NULL,
                    embedding F32_BLOB({self.embedding_dimension}),
                    metadata  TEXT    NOT NULL
                )
            """)
            # DiskANN-based approximate nearest-neighbour index
            conn.execute(
                f"CREATE INDEX IF NOT EXISTS {_VECTOR_INDEX_NAME} "
                f"ON embeddings(libsql_vector_idx(embedding))"
            )
            conn.commit()
        finally:
            conn.close()
        logger.info("libSQL database initialised at %s", self._get_db_path())

    def _get_today_date_str(self) -> str:
        return datetime.now().strftime("%Y-%m-%d")

    def _cleanup_old_data(self) -> None:
        """Delete rows that fall outside the rolling retention window."""
        cutoff = (datetime.now() - timedelta(days=self.max_days)).strftime("%Y-%m-%d")
        conn = self._connect()
        try:
            cursor = conn.execute("DELETE FROM embeddings WHERE date < ?", (cutoff,))
            conn.commit()
            deleted = cursor.rowcount
        finally:
            conn.close()
        if deleted:
            logger.info("Removed %d old embedding rows (before %s)", deleted, cutoff)

    # ------------------------------------------------------------------
    # Public interface (drop-in replacement for the former FaissManager)
    # ------------------------------------------------------------------

    def add_data(self, vectors: np.ndarray, metadata_list: List[Dict[str, Any]]) -> None:
        """Persist embedding vectors and their metadata.

        Args:
            vectors: Float32 NumPy array of shape (n, embedding_dimension).
            metadata_list: One metadata dict per row.
        """
        today = self._get_today_date_str()
        conn = self._connect()
        try:
            for vec, meta in zip(vectors, metadata_list):
                # libSQL expects a JSON array string for the vector() function
                vec_json = json.dumps(vec.astype(np.float32).tolist())
                conn.execute(
                    "INSERT INTO embeddings (date, embedding, metadata) "
                    "VALUES (?, vector(?), ?)",
                    (today, vec_json, json.dumps(meta)),
                )
            conn.commit()
        finally:
            conn.close()
        logger.info("Added %d vectors to libSQL for %s", len(vectors), today)

    def search(self, query_vector: np.ndarray, k: int = 10) -> Tuple[List[Dict[str, Any]], List[float]]:
        """Find the k nearest neighbours using libSQL's DiskANN vector index.

        Distances are cosine distances in [0, 2] as returned by
        ``vector_distance_cos``.  Callers can convert to a similarity score
        with ``1.0 - distance / 2.0``.

        Args:
            query_vector: 1-D or 2-D (1 × dim) float array.
            k: Maximum number of results to return.

        Returns:
            Tuple of (metadata_list, distances).
        """
        query = query_vector.astype(np.float32)
        if query.ndim == 2:
            query = query[0]
        query_json = json.dumps(query.tolist())

        conn = self._connect()
        try:
            rows = conn.execute(
                f"""
                SELECT e.metadata,
                       vector_distance_cos(e.embedding, vector(?)) AS distance
                FROM   vector_top_k('{_VECTOR_INDEX_NAME}', vector(?), ?) AS i
                JOIN   embeddings e ON i.id = e.rowid
                ORDER  BY distance
                """,
                (query_json, query_json, k),
            ).fetchall()
        finally:
            conn.close()

        if not rows:
            return [], []

        metadata_list = [json.loads(row[0]) for row in rows]
        distances = [float(row[1]) for row in rows]
        return metadata_list, distances

    def save_today_index(self) -> None:
        """No-op: libSQL commits are immediately durable."""
        logger.debug("save_today_index called (no-op for libSQL backend)")

    def save_all_indexes(self) -> None:
        """No-op: libSQL commits are immediately durable."""
        logger.debug("save_all_indexes called (no-op for libSQL backend)")
