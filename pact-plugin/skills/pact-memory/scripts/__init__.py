"""
PACT Memory Scripts Package

Location: pact-plugin/skills/pact-memory/scripts/__init__.py

Complete package for the PACT Memory skill including:
- Database layer: SQLite with WAL mode and vector extensions
- Graph layer: File relationships and memory-file links
- Models: Rich memory object dataclasses
- Embeddings: Multi-backend embedding generation
- Search: Semantic and graph-enhanced search
- API: High-level PACTMemory interface
- Setup: Auto-initialization and model download
"""

from __future__ import annotations

# Database layer
from .database import (
    # Connection management
    get_connection,
    db_connection,
    get_db_path,

    # Schema management
    init_schema,
    ensure_initialized,
    initialize_database,

    # Memory CRUD
    create_memory,
    get_memory,
    update_memory,
    delete_memory,
    list_memories,
    search_memories_by_text,

    # Utilities
    generate_id,
    get_memory_count,
    vacuum_database,
    check_integrity,
    quick_save,
)

# Graph layer
from .graph import (
    # File tracking
    track_file,
    get_file_id,
    get_file_by_id,
    list_tracked_files,

    # Memory-file relationships
    link_memory_to_file,
    link_memory_to_files,
    link_memory_to_paths,
    get_files_for_memory,
    get_memories_for_file,
    get_memories_for_files,

    # File-file relationships
    add_file_relation,
    get_file_relations,
    get_related_files,
    get_related_files_via_memories,

    # Analysis
    get_file_context,
    get_graph_stats,

    # Convenience
    track_and_link,
    discover_related,
)

# Models
from .models import (
    MemoryObject,
    TaskItem,
    Decision,
    Entity,
    memory_from_db_row,
)

# Embeddings
from .embeddings import (
    generate_embedding,
    generate_embedding_text,
    check_embedding_availability,
    EmbeddingService,
    get_embedding_service,
)

# Search
from .search import (
    semantic_search,
    graph_enhanced_search,
    search_by_file,
    find_similar_memories,
    get_search_capabilities,
)

# High-level API
from .memory_api import (
    PACTMemory,
    get_memory_instance,
    reset_memory_instance,
    save_memory,
    search_memory,
    list_memories_simple,
)

# Working Memory (CLAUDE.md sync)
from .working_memory import (
    # `sync_to_claude_md` RETURNS one of these, so exporting the function
    # without the type left the export unusable for any caller that wants the
    # reason rather than just the truthiness.
    SyncResult,
    # And it can RAISE this one. An exported function whose exception cannot be
    # named is uncatchable by anything but a bare `except Exception`, which is
    # the handler that swallows everything else too -- so the caller either
    # over-catches or cannot respond to the one outcome that is deliberate
    # rather than broken.
    AmbientSyncRefused,
    sync_to_claude_md,
    sync_retrieved_to_claude_md,
    WORKING_MEMORY_HEADER,
    WORKING_MEMORY_COMMENT,
    MAX_WORKING_MEMORIES,
    RETRIEVED_CONTEXT_HEADER,
    RETRIEVED_CONTEXT_COMMENT,
    MAX_RETRIEVED_MEMORIES,
)

# Embedding Catch-up
from .embedding_catchup import (
    get_available_ram_mb,
    get_unembedded_memories,
    embed_single_memory,
    embed_pending_memories,
)

# Lazy Initialization
from .memory_init import (
    ensure_memory_ready,
    reset_initialization,
    clear_embedding_marker,
    is_initialized,
    check_and_install_dependencies,
    maybe_migrate_embeddings,
    maybe_embed_pending,
)

# Setup utilities
from .setup_memory import (
    check_dependencies,
    ensure_initialized as ensure_system_initialized,
    get_setup_status,
    print_setup_status,
)

__all__ = [
    # Database - Connection
    "get_connection",
    "db_connection",
    "get_db_path",

    # Database - Schema
    "init_schema",
    "ensure_initialized",
    "initialize_database",

    # Database - Memory CRUD
    "create_memory",
    "get_memory",
    "update_memory",
    "delete_memory",
    "list_memories",
    "search_memories_by_text",

    # Database - Utilities
    "generate_id",
    "get_memory_count",
    "vacuum_database",
    "check_integrity",
    "quick_save",

    # Graph - File tracking
    "track_file",
    "get_file_id",
    "get_file_by_id",
    "list_tracked_files",

    # Graph - Memory-file relationships
    "link_memory_to_file",
    "link_memory_to_files",
    "link_memory_to_paths",
    "get_files_for_memory",
    "get_memories_for_file",
    "get_memories_for_files",

    # Graph - File-file relationships
    "add_file_relation",
    "get_file_relations",
    "get_related_files",
    "get_related_files_via_memories",

    # Graph - Analysis
    "get_file_context",
    "get_graph_stats",

    # Graph - Convenience
    "track_and_link",
    "discover_related",

    # Models
    "MemoryObject",
    "TaskItem",
    "Decision",
    "Entity",
    "memory_from_db_row",

    # Embeddings
    "generate_embedding",
    "generate_embedding_text",
    "check_embedding_availability",
    "EmbeddingService",
    "get_embedding_service",

    # Search
    "semantic_search",
    "graph_enhanced_search",
    "search_by_file",
    "find_similar_memories",
    "get_search_capabilities",

    # High-level API
    "PACTMemory",
    "get_memory_instance",
    "reset_memory_instance",
    "save_memory",
    "search_memory",
    "list_memories_simple",

    # Working Memory (CLAUDE.md sync)
    "SyncResult",
    "AmbientSyncRefused",
    "sync_to_claude_md",
    "sync_retrieved_to_claude_md",
    "WORKING_MEMORY_HEADER",
    "WORKING_MEMORY_COMMENT",
    "MAX_WORKING_MEMORIES",
    "RETRIEVED_CONTEXT_HEADER",
    "RETRIEVED_CONTEXT_COMMENT",
    "MAX_RETRIEVED_MEMORIES",

    # Embedding Catch-up
    "get_available_ram_mb",
    "get_unembedded_memories",
    "embed_single_memory",
    "embed_pending_memories",

    # Lazy Initialization
    "ensure_memory_ready",
    "reset_initialization",
    "clear_embedding_marker",
    "is_initialized",
    "check_and_install_dependencies",
    "maybe_migrate_embeddings",
    "maybe_embed_pending",

    # Setup
    "check_dependencies",
    "ensure_system_initialized",
    "get_setup_status",
    "print_setup_status",
]
