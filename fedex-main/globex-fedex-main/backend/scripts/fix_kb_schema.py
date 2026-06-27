"""Ajoute les colonnes Phase 3 manquantes sur knowledge_chunks / knowledge_documents."""

from sqlalchemy import text

from app.core.database import engine


def main() -> None:
    with engine.begin() as conn:
        before = conn.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'knowledge_chunks' ORDER BY 1"
            )
        ).fetchall()
        print("knowledge_chunks avant:", [r[0] for r in before])

        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS knowledge_documents ("
                "id SERIAL PRIMARY KEY, "
                "collection_id INTEGER NOT NULL REFERENCES knowledge_collections(id) ON DELETE CASCADE, "
                "original_filename VARCHAR(255) NOT NULL, "
                "stored_path VARCHAR(512) NOT NULL, "
                "mime_type VARCHAR(128) NOT NULL DEFAULT 'application/octet-stream', "
                "file_size_bytes INTEGER NOT NULL DEFAULT 0, "
                "status VARCHAR(24) NOT NULL DEFAULT 'pending', "
                "error_message TEXT NOT NULL DEFAULT '', "
                "chunk_count INTEGER NOT NULL DEFAULT 0, "
                "uploaded_by_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL, "
                "created_at TIMESTAMPTZ NOT NULL DEFAULT now()"
                ")"
            )
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_knowledge_documents_collection_id "
                "ON knowledge_documents (collection_id)"
            )
        )
        conn.execute(
            text(
                "ALTER TABLE knowledge_chunks "
                "ADD COLUMN IF NOT EXISTS document_id INTEGER "
                "REFERENCES knowledge_documents(id) ON DELETE CASCADE"
            )
        )
        conn.execute(
            text(
                "ALTER TABLE knowledge_chunks "
                "ADD COLUMN IF NOT EXISTS chunk_index INTEGER NOT NULL DEFAULT 0"
            )
        )
        conn.execute(
            text("ALTER TABLE knowledge_chunks ADD COLUMN IF NOT EXISTS embedding_json TEXT")
        )

        after = conn.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'knowledge_chunks' ORDER BY 1"
            )
        ).fetchall()
        print("knowledge_chunks après:", [r[0] for r in after])

    try:
        with engine.begin() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            conn.execute(
                text("ALTER TABLE knowledge_chunks ADD COLUMN IF NOT EXISTS embedding vector(768)")
            )
        print("PGVector: OK")
    except Exception as exc:
        print("PGVector optionnel ignoré:", exc)


if __name__ == "__main__":
    main()
