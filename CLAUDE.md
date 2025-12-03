# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

LangChain RAG Assistant - A conversational AI chatbot built with LangChain, Gradio, and PostgreSQL that supports:
- Document-based RAG (Retrieval-Augmented Generation) using Chroma vector store
- Persistent chat history stored in PostgreSQL
- Session management with multiple conversation threads
- Customizable AI personas
- Strict mode for document-only responses

**Tech Stack:**
- **Framework:** LangChain (with OpenAI GPT-4o-mini)
- **UI:** Gradio 6.0+
- **Database:** PostgreSQL 15 (via Docker)
- **Vector Store:** Chroma (in-memory)
- **Embeddings:** OpenAI text-embedding-3-small
- **Document Loaders:** PyPDF and TextLoader

## Development Setup

### Initial Setup

```bash
# Install dependencies using uv (Python package installer)
uv sync

# Start PostgreSQL database
docker compose up -d

# Configure environment variables
cp .env.example .env
# Edit .env with your OPENAI_API_KEY and DB credentials
```

### Running the Application

```bash
# Development mode (foreground)
uv run main.py

# Production mode (background with logging)
nohup python main.py > gradio_output.log 2>&1 &
```

The Gradio UI will be available at http://localhost:7860

### Database Management

```bash
# Start database
docker compose up -d

# Stop database
docker compose down

# Access PostgreSQL CLI
docker exec -it langchain_postgres psql -U langchain -d langchain_chat
```

## Architecture

### Core Components

1. **main.py** - Primary application file containing:
   - LangChain chat chain with memory (using `RunnableWithMessageHistory`)
   - Gradio UI definition with two-column layout (controls + conversation)
   - PostgreSQL chat history management
   - RAG integration with file upload processing
   - Session management (create, resume, persist conversations)

2. **rag_utils.py** - RAG utilities:
   - `load_and_split_document()` - Loads PDF/text files and chunks them (1000 chars, 200 overlap)
   - `create_vectorstore()` - Creates in-memory Chroma vector store with OpenAI embeddings

### Database Schema

**Table: chat_history**
```sql
CREATE TABLE chat_history (
    id SERIAL PRIMARY KEY,
    session_id UUID NOT NULL,
    message JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_chat_history_session_id ON chat_history (session_id);
```

The table is automatically created on application startup via psycopg connection.

### LangChain Memory Flow

```
User Input → memory_prompt (system + history + user message)
          → ChatOpenAI (gpt-4o-mini)
          → StrOutputParser
          → RunnableWithMessageHistory (saves to PostgreSQL)
          → Response
```

**Key Configuration:**
- `input_messages_key="input"` - Current user message
- `history_messages_key="history"` - Retrieved chat history
- `session_id` from `gr.State` identifies conversation threads

### RAG Flow

```
File Upload → PyPDFLoader/TextLoader
           → RecursiveCharacterTextSplitter (chunks)
           → Chroma.from_documents (with OpenAI embeddings)
           → vector_store (global variable)

Query → vector_store.similarity_search(k=3)
      → Context injected into system message
      → LLM response with sources
```

### Session Management

- Each chat session has a unique UUID (`session_id`)
- Sessions are stored in `gr.State` and passed to all chat functions
- Users can:
  - Start new chat (generates new UUID)
  - Resume previous chat (from dropdown populated via `get_all_session_ids()`)
  - Messages automatically persist to PostgreSQL

### Persona System

Five predefined personas via dropdown:
- Generic helpful assistant
- UAS drone expert
- C-RAM (Counter-Rocket, Artillery, Mortar) expert
- Anti-UAS drone system expert
- Poetic storyteller

Personas modify the system message passed to the LLM. Custom personas can be added by editing the `persona_dropdown.choices` list in main.py:269-278.

### Strict Mode

When enabled with uploaded document:
- Forces LLM to ONLY answer from document context
- Returns "I cannot find the answer in the uploaded document." if info not present
- Implemented via modified system instruction in `chat_function()` at main.py:167-177

## Environment Variables

Required in `.env`:
```bash
OPENAI_API_KEY='sk-...'      # OpenAI API key
DB_HOST='localhost'          # PostgreSQL host
DB_PORT='5432'               # PostgreSQL port
DB_USER='langchain'          # Database user
DB_PASSWORD='langchain'      # Database password
DB_NAME='langchain_chat'     # Database name
```

**Note:** There's a typo in the current .env where `DB_USER='lnagchain'` (missing 'c'). The docker-compose.yml uses `langchain` as the correct username.

## Key Implementation Details

### Global State
- `vector_store` - In-memory Chroma instance (None until file uploaded)
- `db_conn` - Persistent psycopg connection with `autocommit=True`

### Chat History Conversion
Gradio uses new dict format for messages:
```python
{"role": "user", "content": "..."}
{"role": "assistant", "content": "..."}
```

When loading from PostgreSQL, `load_chat_history()` converts LangChain messages to Gradio format (main.py:335-362).

### File Upload Processing
1. User uploads PDF/text via `gr.File`
2. `process_file()` triggered on file change
3. Document loaded, split into chunks, embedded
4. Global `vector_store` updated
5. Status message returned to UI

### Source Attribution
When RAG is active, responses include:
```
--- Sources Used ---
Source 1: Uploaded File, document.pdf, Page 2
Source 2: Uploaded File, document.pdf, Page 5
```

Metadata extracted from `doc.metadata` includes `source` (file path) and `page` number.

## Known Issues & Future Improvements

See `progress.md` for planned features:
- Hamburger menu for chat history
- Subject column in database (auto-populated from first user message)
- Edit/delete session functionality
- Replace dropdown with Accordion UI

## Testing

Currently no automated tests. Manual testing workflow:
1. Start app and verify database connection (green checkmark in UI)
2. Test new chat creation
3. Test session resumption
4. Upload a PDF and verify RAG responses
5. Test strict mode with and without uploaded files
6. Verify sources are displayed correctly

## Code Style Notes

- Uses f-strings for formatting
- Function docstrings follow Google style (description only, no Args/Returns sections)
- Type hints used for function signatures (e.g., `list[str]`, `list[dict]`)
- Print statements for debugging with emoji indicators (✅, ⚠️, 🔄, ✨)
- Gradio event handlers use lambda functions where appropriate
