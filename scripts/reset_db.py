"""Utility script to reset chat history database and optionally vector store."""

import argparse
import os
import shutil
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from app.config import settings


def reset_chat_db(chat_db_path: str):
    """Deletes SQLite chat database and WAL journal files."""
    for ext in ["", "-wal", "-shm"]:
        p = chat_db_path + ext
        if os.path.exists(p):
            try:
                os.remove(p)
                print(f"Removed: {p}")
            except Exception as e:
                print(f"Failed to remove {p}: {e}")
    print("Chat database reset complete.")


def reset_vectorstore(vectorstore_path: str):
    """Deletes indexed vectorstore directory."""
    if os.path.exists(vectorstore_path):
        try:
            shutil.rmtree(vectorstore_path)
            os.makedirs(vectorstore_path, exist_ok=True)
            print(f"Vector store cleared: {vectorstore_path}")
        except Exception as e:
            print(f"Failed to clear vector store: {e}")


def main():
    parser = argparse.ArgumentParser(description="Reset application data stores.")
    parser.add_argument(
        "--all",
        action="store_true",
        help="Reset both chat DB and vectorstore index",
    )
    args = parser.parse_args()

    print("Resetting chat database...")
    reset_chat_db(settings.chat_db_path)

    if args.all:
        print("Resetting vector store index...")
        reset_vectorstore(settings.vectorstore_path)
        print("Run 'python scripts/ingest.py' to re-populate the vector store.")


if __name__ == "__main__":
    main()
