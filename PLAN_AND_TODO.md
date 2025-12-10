# PinyaBot Project Plan & Todo

## 1. Project Overview
**Goal:** Build "PinyaBot," a self-hosted, high-performance RAG bot for a Project Zomboid server.
**Philosophy:** "Configuration over Code" + "Obsessive UX."
**Key Features:** Fully configurable via Discord, native UX (modals, autocomplete), RAG-based answers, RLHF feedback loop.

## 2. Technology Stack
*   **Language:** Python 3.11+
*   **Framework:** `discord.py` (Slash Commands)
*   **Database:** PostgreSQL 16 with `pgvector` (Dockerized)
*   **ORM/Driver:** `asyncpg` (Direct async driver)
*   **AI/RAG:** LangChain, OpenAI (`gpt-4o-mini`, `text-embedding-3-small`)
*   **Deployment:** Docker Compose

## 3. Database Schema
*   **`config`**: `key` (TEXT PK), `value` (TEXT). Stores role IDs, channel IDs, thresholds.
*   **`pinya_docs`**:
    *   `id` (SERIAL PK)
    *   `topic` (TEXT)
    *   `content` (TEXT)
    *   `embedding` (VECTOR)
    *   `metadata` (JSONB: votes, flags, spoiler_status)
    *   `created_at` (TIMESTAMP)
*   **`aliases`**: `trigger` (TEXT), `replacement` (TEXT).

## 4. Architecture & Modules
*   **`main.py`**: Bot entry point, extension loader.
*   **`core/database.py`**: Connection pool, schema initialization, helper methods.
*   **`core/config_manager.py`**: Caching and retrieving dynamic config.
*   **`cogs/admin.py`**: `/admin` commands for configuring roles, channels, thresholds.
*   **`cogs/knowledge.py`**: `/teach`, `/edit`, `/forget` (Ingestion & Management).
*   **`cogs/query.py`**: Event listener for mentions, RAG logic, Response generation.
*   **`utils/ui.py`**: Reusable Views (Vote buttons), Modals, Color constants.
*   **`utils/ai.py`**: LangChain wrappers, Embedding generation, Vector search logic.

## 5. UX Specifications
*   **Colors**:
    *   Success: `#57F287` (Green)
    *   Error: `#ED4245` (Red)
    *   Warning: `#FEE75C` (Yellow)
    *   AI Answer: `#5865F2` (Blurple)
*   **Interactions**:
    *   Success/Info: `delete_after=10`.
    *   Error: `ephemeral=True`.
    *   RAG Commands: `defer()` immediately (Thinking state).
    *   Autocomplete: Real-time DB query for `/edit`, `/forget`.

## 6. Implementation Steps (Todo List)

### Phase 1: Foundation
- [x] **Setup Project Structure**: Create directories (`core`, `cogs`, `utils`) and `requirements.txt`.
- [x] **Docker Setup**: Create `docker-compose.yml` for PostgreSQL + pgvector.
- [x] **Database Layer**: Implement `core/database.py` with `asyncpg` pool and auto-schema creation.
- [x] **Bot Skeleton**: Create `main.py` and basic environment variable loading (`.env`).

### Phase 2: Configuration System
- [x] **Config Logic**: Implement `core/config_manager.py` to read/write `config` table.
- [x] **Admin Cog**: Implement `/admin config role`, `/admin config channel`, `/admin config threshold`.
- [x] **Decorators**: Create `@is_configured_role` to secure commands.

### Phase 3: Knowledge Management (Ingestion)
- [x] **Teach Modal**: Create UI for `/teach` (Topic, Content, Spoiler).
- [x] **Embedding Logic**: Implement `utils/ai.py` to generate embeddings using OpenAI.
- [x] **Storage**: Save topic, content, and embedding to `pinya_docs`.
- [x] **Duplicate Detection**: Implement cosine similarity check before saving.

### Phase 4: Retrieval & RAG (The Brain)
- [x] **Vector Search**: Implement search query in `pinya_docs`.
- [x] **Query Listener**: Handle `@PinyaBot` mentions.
- [x] **Confidence Logic**: Implement Threshold check.
    -   *If Low Confidence*: Post to Knowledge Gap channel with "Teach This" button.
    -   *If High Confidence*: Generate answer via LLM.
- [x] **Formatting**: Bold map coordinates or link them.

### Phase 5: Refinement & RLHF
- [x] **Voting UI**: Attach "Helpful/Wrong" buttons to answers.
- [x] **Feedback Loop**: Update metadata on vote; alert admins if flagged > 3 times.
- [x] **Autocomplete**: Implement dynamic autocomplete for editing/forgetting topics.