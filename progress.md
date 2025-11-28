# Project Progress & Roadmap

## Current Status
- **Date:** 2025-11-28
- **State:** Functional Basic Chatbot
- **Features:**
  - UI: Gradio `ChatInterface` with Persona selection.
  - LLM: OpenAI `gpt-4o-mini`.
  - Memory: In-memory `ChatMessageHistory` (resets on restart).
  - Framework: LangChain (LCEL syntax).

## Roadmap (Suggested)

### Phase 1: Fundamentals & Persistence
- [ ] **Persist Chat History:** Save chat logs to a local PostgreSQL database so conversations aren't lost on restart. (Next Step)
- [ ] **Environment Safety:** Ensure `.env` is properly handled and keys are secure.

### Phase 2: Retrieval Augmented Generation (RAG)
- [x] **Document Loading:** functionality to upload text/PDF files.
- [x] **Vector Store:** Set up a local vector store (ChromaDB).
- [x] **Q&A Chain:** Bot answers questions based on uploaded documents with source citations.
- [x] **Strict Mode:** Checkbox to force answers only from documents.

### Phase 3: Agents & Tools
- [ ] **Web Search:** Add a tool (like Tavily or DuckDuckGo) for real-time info.
- [ ] **Agentic Workflow:** Convert the simple chain into an Agent that can decide when to use tools.

### Phase 4: Production Readiness
- [ ] **Refactoring:** Split `main.py` into modular files (UI, Logic, Config).
- [ ] **Logging:** Better logging for debugging.
- [ ] **Testing:** Add unit tests for chains.

## Next Steps
Waiting for user selection on which Phase to tackle first.
