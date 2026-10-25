"""Document chunking module for mutual fund corpus."""

import re
from typing import Any, Dict, List
from app.ingestion.scraper import ScrapedDocument


class DocumentChunk:
    """Represents a text chunk with complete citation metadata."""

    def __init__(
        self,
        chunk_id: str,
        scheme_id: str,
        scheme_name: str,
        category: str,
        source_url: str,
        document_type: str,
        section_heading: str,
        scrape_date: str,
        text: str,
    ):
        self.chunk_id = chunk_id
        self.scheme_id = scheme_id
        self.scheme_name = scheme_name
        self.category = category
        self.source_url = source_url
        self.document_type = document_type
        self.section_heading = section_heading
        self.scrape_date = scrape_date
        self.text = text

    def to_dict(self) -> Dict[str, Any]:
        return {
            "chunk_id": self.chunk_id,
            "scheme_id": self.scheme_id,
            "scheme_name": self.scheme_name,
            "category": self.category,
            "source_url": self.source_url,
            "document_type": self.document_type,
            "section_heading": self.section_heading,
            "scrape_date": self.scrape_date,
            "text": self.text,
        }


class DocumentChunker:
    """Chunks scraped scheme documents using recursive character splitting with metadata preservation."""

    def __init__(self, chunk_size: int = 700, chunk_overlap: int = 120):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def _split_text(self, text: str) -> List[str]:
        """
        Recursively splits text on natural boundaries: double newlines, single newlines,
        sentence boundaries, and spaces.
        """
        text = text.strip()
        if not text:
            return []

        if len(text) <= self.chunk_size:
            return [text]

        # Splitting delimiters in order of priority
        delimiters = ["\n\n", "\n", ". ", "; ", ", ", " "]

        def recursive_split(chunk: str, delim_idx: int) -> List[str]:
            if len(chunk) <= self.chunk_size or delim_idx >= len(delimiters):
                return [chunk]

            delim = delimiters[delim_idx]
            sub_chunks = chunk.split(delim)
            results = []
            current = ""

            for sub in sub_chunks:
                candidate = (current + delim + sub).strip() if current else sub.strip()
                if len(candidate) <= self.chunk_size:
                    current = candidate
                else:
                    if current:
                        results.append(current)
                    if len(sub) > self.chunk_size:
                        results.extend(recursive_split(sub, delim_idx + 1))
                        current = ""
                    else:
                        current = sub.strip()

            if current:
                results.append(current)

            return results

        raw_chunks = recursive_split(text, 0)

        # Apply overlap where appropriate
        overlapped_chunks = []
        for i, c in enumerate(raw_chunks):
            c_clean = re.sub(r"\s+", " ", c).strip()
            if len(c_clean) >= 40:  # Minimum meaningful chunk length
                overlapped_chunks.append(c_clean)

        return overlapped_chunks

    def chunk_document(self, doc: ScrapedDocument) -> List[DocumentChunk]:
        """Splits a single ScrapedDocument into DocumentChunk instances with metadata."""
        chunks: List[DocumentChunk] = []
        chunk_idx = 0

        # Chunk each section individually to keep heading context
        for sec in doc.sections:
            section_name = sec["section"]
            section_text = sec["text"]

            sub_chunks = self._split_text(section_text)
            for sub_text in sub_chunks:
                # Prepend scheme and section context for high retrieval precision
                contextualized_text = f"[{doc.scheme_name} - {section_name}]\n{sub_text}"

                chunk_id = f"{doc.scheme_id}-chunk-{chunk_idx:03d}"
                chunk = DocumentChunk(
                    chunk_id=chunk_id,
                    scheme_id=doc.scheme_id,
                    scheme_name=doc.scheme_name,
                    category=doc.category,
                    source_url=doc.url,
                    document_type="groww",
                    section_heading=section_name,
                    scrape_date=doc.scrape_date,
                    text=contextualized_text,
                )
                chunks.append(chunk)
                chunk_idx += 1

        return chunks

    def chunk_documents(self, documents: List[ScrapedDocument]) -> List[DocumentChunk]:
        """Processes all documents and returns a flat list of all chunks."""
        all_chunks: List[DocumentChunk] = []
        for doc in documents:
            doc_chunks = self.chunk_document(doc)
            all_chunks.extend(doc_chunks)

        return all_chunks
