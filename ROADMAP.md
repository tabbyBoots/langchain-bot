# LangChain RAG Assistant - Roadmap

> **Last Updated:** 2024-12-12
>
> This roadmap outlines planned features and improvements, organized by priority.

---

## Priority 1: UI/UX Polish (Quick Wins)

### 1. Fix Dark Background Issues ⚠️
- **Status:** In Progress
- **Issue:** Some Gradio components still have dark backgrounds
- **Action:** Review and add CSS overrides for remaining dark components
- **Location:** `main.py:1058-1559` (CSS section)
- **Effort:** Low (1-2 hours)

### 2. Fix Content Visibility Issues ⚠️
- **Status:** In Progress
- **Issue:** Content gets cut off and requires browser resize
- **Action:** Remove fixed height restrictions on sidebar
- **Location:** `main.py:1195-1201` (sidebar CSS)
- **Effort:** Low (30 mins - 1 hour)

### 3. Refine Hamburger Toggle Scope ⚠️
- **Status:** In Progress
- **Issue:** Currently hides entire sidebar including file upload
- **Action:** Modify toggle to only hide session management panel
- **Location:** `main.py:674-687` (hamburger button click handler)
- **Effort:** Medium (2-3 hours)

---

## Priority 2: Data Management & Safety

### 4. Add Backup/Export Functionality
- **Status:** Planned
- **What:** Export chat history and vector store backups
- **Why:** Users may want to backup their data or migrate to another system
- **Suggested Features:**
  - Export conversations to JSON or Markdown
  - Backup Qdrant vector database
  - Import/restore functionality
- **Effort:** Medium (4-6 hours)

### 5. Add File Size/Upload Limits
- **Status:** Planned
- **What:** Set maximum file size and chunk count limits
- **Why:** Prevent performance degradation with very large files
- **Location:** `rag_utils.py:24-42` (load_and_split_document)
- **Suggested Limits:**
  - Max file size: 50MB
  - Max chunks per file: 10,000
  - Warning when approaching limits
- **Effort:** Low (1-2 hours)

---

## Priority 3: Feature Enhancements

### 6. Multi-Document Search with Filtering
- **Status:** Planned
- **What:** Allow users to query specific documents or document sets
- **Current:** Searches all uploaded documents
- **Improvement:** Add document selector or tags to filter sources
- **Location:** `main.py:402-422` (RAG logic in chat_function)
- **Effort:** Medium (4-6 hours)

### 7. Conversation Search
- **Status:** Planned
- **What:** Search within chat history across all sessions
- **Why:** Helps users find previous conversations
- **Implementation:** Add search box in sidebar, query PostgreSQL
- **Effort:** Medium (3-5 hours)

### 8. Enhanced Persona Management
- **Status:** Planned
- **What:** Allow users to create and save custom personas
- **Current:** Fixed dropdown list in code
- **Improvement:** Store personas in database, add UI to create/edit/delete
- **Location:** `main.py:571-581` (persona dropdown)
- **Effort:** High (6-8 hours)

### 9. Token Usage Tracking
- **Status:** Planned
- **What:** Display estimated token usage and costs per session
- **Why:** Users can monitor API costs
- **Implementation:** Use `tiktoken` to count tokens, display in UI
- **Effort:** Medium (3-4 hours)

---

## Priority 4: Performance & Scalability

### 10. Implement Chunk Caching
- **Status:** Planned
- **What:** Cache frequently accessed vector search results
- **Why:** Reduce OpenAI API calls for similar queries
- **Implementation:** Use Redis or simple in-memory LRU cache
- **Effort:** Medium (4-5 hours)

### 11. Add Pagination for Sessions
- **Status:** Planned
- **What:** Load sessions in pages rather than all at once
- **Why:** Better performance with many sessions
- **Current:** `main.py:111-143` loads all sessions
- **Effort:** Medium (3-4 hours)

### 12. Optimize Vector Search
- **Status:** Planned
- **What:** Experiment with different retrieval parameters
- **Current:** Fixed k=3 similarity search
- **Improvements:**
  - Make k configurable
  - Add score threshold filtering
  - Implement hybrid search (keyword + semantic)
- **Location:** `main.py:404` (similarity_search call)
- **Effort:** Medium (4-6 hours)

---

## Priority 5: Production Readiness

### 13. Add Comprehensive Error Handling
- **Status:** Planned
- **What:** Graceful handling of database/API failures
- **Current:** Basic try/except in some places
- **Improvements:**
  - User-friendly error messages
  - Automatic retry logic for transient failures
  - Fallback behavior when services are down
- **Effort:** Medium (5-7 hours)

### 14. Add Health Check Endpoint
- **Status:** Planned
- **What:** Monitor database and Qdrant connectivity
- **Why:** Essential for production deployment
- **Implementation:** Add status check API endpoint
- **Effort:** Low (2-3 hours)

### 15. Implement Rate Limiting
- **Status:** Planned
- **What:** Prevent abuse and manage costs
- **Implementation:** Limit requests per session/IP
- **Effort:** Medium (3-4 hours)

### 16. Add Logging and Monitoring
- **Status:** Planned
- **What:** Replace print statements with proper logging
- **Current:** Uses print() for debugging (`main.py`, `rag_utils.py`)
- **Implementation:** Use Python `logging` module, configure levels
- **Effort:** Low (2-3 hours)

---

## Priority 6: Developer Experience

### 17. Add Unit Tests
- **Status:** Planned
- **What:** Test core functionality
- **Focus Areas:**
  - RAG utilities (`rag_utils.py`)
  - Database operations
  - Session management functions
- **Effort:** High (8-12 hours)

### 18. Create Docker Compose for Full Stack
- **Status:** Planned
- **What:** Include the app itself in docker-compose
- **Current:** Only PostgreSQL is containerized
- **Benefits:** Easier deployment, environment consistency
- **Effort:** Medium (3-4 hours)

### 19. Add Environment Configuration Validation
- **Status:** Planned
- **What:** Check required env vars on startup
- **Why:** Better error messages if misconfigured
- **Location:** `main.py:18-35` (environment loading)
- **Effort:** Low (1 hour)

---

## Suggested Implementation Order

If tackling these step-by-step, recommended order:

1. ✅ **Fix UI issues** (Priority 1, items 1-3) - In Progress
2. **Add file size limits** (Priority 2, item 5) - Prevent issues before they occur
3. **Implement logging** (Priority 5, item 16) - Foundation for debugging
4. **Add error handling** (Priority 5, item 13) - Application stability
5. **Token tracking** (Priority 3, item 9) - User-facing value
6. **Backup functionality** (Priority 2, item 4) - Data safety

---

## Completed Features

### Major Milestones
- ✅ **Qdrant Migration**: Switched from Chroma (in-memory) to Qdrant (persistent on disk)
- ✅ **Session Management**: Create, resume, rename, and delete conversation threads
- ✅ **Document Management**: Upload multiple files, view all documents, delete individual files
- ✅ **Database Schema Auto-Migration**: Automatic column additions on startup
- ✅ **Auto-Subject Extraction**: First user message becomes session subject
- ✅ **Persistent Vector Store**: Documents survive server restarts in `./qdrant_data`
- ✅ **Modern UI**: Collapsible sidebar with hamburger menu and 3-dot action menus

### Recent Updates
- ✅ Fixed database name mismatch in .env file
- ✅ Added missing 'subject' column to chat_history table
- ✅ Implemented proper indexes for performance
- ✅ Session list with rename/delete functionality
- ✅ Individual file deletion from vector store
- ✅ Clear all documents functionality

---

## Notes

- Update this file as features are completed (move to "Completed Features")
- Effort estimates are approximate and may vary
- Priority levels may shift based on user feedback
- For detailed implementation guides, check git history or ask for step-by-step instructions
