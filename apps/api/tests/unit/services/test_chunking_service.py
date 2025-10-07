"""Test chunking service."""

import pytest
from grimoire_api.services.chunking_service import ChunkingService


class TestChunkingService:
    """Test ChunkingService class."""

    @pytest.fixture
    def chunking_service(self):
        """Create ChunkingService instance."""
        return ChunkingService(chunk_size=100)

    def test_chunk_text_simple(self, chunking_service):
        """Test simple text chunking."""
        text = "This is a simple text for testing chunking functionality."
        chunks = chunking_service.chunk_text(text)

        assert isinstance(chunks, list)
        assert len(chunks) >= 1
        assert all(isinstance(chunk, str) for chunk in chunks)

    def test_chunk_markdown(self, chunking_service):
        """Test markdown text chunking."""
        markdown = """# Title

## Section 1
This is the first section with some content.

## Section 2
This is the second section with more content.

### Subsection
More detailed content here.
"""
        chunks = chunking_service.chunk_markdown(markdown)

        assert isinstance(chunks, list)
        assert len(chunks) >= 1
        assert all(isinstance(chunk, str) for chunk in chunks)

    def test_chunk_long_text(self, chunking_service):
        """Test chunking of long text."""
        # Create text longer than chunk_size
        long_text = "This is a sentence. " * 20  # 400+ characters
        chunks = chunking_service.chunk_text(long_text)

        assert len(chunks) >= 1  # Should have at least one chunk

    def test_chunk_empty_text(self, chunking_service):
        """Test chunking empty text."""
        chunks = chunking_service.chunk_text("")

        assert isinstance(chunks, list)

    def test_custom_chunk_size(self):
        """Test custom chunk size configuration."""
        service = ChunkingService(chunk_size=50)
        text = "This is a test text that should be chunked with custom settings."
        chunks = service.chunk_text(text)

        assert isinstance(chunks, list)
        assert len(chunks) >= 1
