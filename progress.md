# Progress: Advanced Chat History Management

## New Features to Implement

1. ✨ Hamburger button to show/hide chat history
2. 📋 Add 'subject' column to database (default: first user question)
3. 🖊️ Edit subject names
4. 🗑️ Delete chat histories
5. 📜 Replace dropdown with a better component (Accordion or custom list)

---

## Part 1: Database Schema Changes

### Step 1.1: Add Subject Column to Database

You need to add a 'subject' column to your `chat_history` table.

**Option A: Modify existing table (recommended)**

Run this SQL command to add the subject column:

```sql
-- Connect to PostgreSQL
sudo -u postgres psql -d langchain_chat

-- Add subject column (allows NULL for existing records)
ALTER TABLE chat_history ADD COLUMN subject TEXT;

-- Create index for better performance
CREATE INDEX IF NOT EXISTS idx_chat_history_subject ON chat_history (subject);

-- Exit
\q
```

**Option B: Update the table creation code**

In `main.py`, find the table creation code (around line 38-51) and update it:

**Current code:**
```python
cur.execute("""
    CREATE TABLE IF NOT EXISTS chat_history (
            id SERIAL PRIMARY KEY,
            session_id UUID NOT NULL,
            message JSONB NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
    CREATE INDEX IF NOT EXISTS idx_chat_history_session_id ON chat_history (session_id);
""")
```

**Replace with:**
```python
cur.execute("""
    CREATE TABLE IF NOT EXISTS chat_history (
            id SERIAL PRIMARY KEY,
            session_id UUID NOT NULL,
            message JSONB NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            subject TEXT
        );
    CREATE INDEX IF NOT EXISTS idx_chat_history_session_id ON chat_history (session_id);
    CREATE INDEX IF NOT EXISTS idx_chat_history_subject ON chat_history (subject);
""")
```

---

## Part 2: New Database Functions

Add these new functions to `main.py` (after the existing database functions, around line 86):

### Function 1: Get Sessions with Subjects

```python
def get_all_sessions_with_subjects() -> list[dict]:
    """
    Fetch all unique sessions with their subjects and first message timestamp.
    Returns: [{"session_id": "...", "subject": "...", "created_at": "..."}, ...]
    """
    if db_conn is None:
        print("⚠️ No database connection, cannot fetch sessions.")
        return []
    try:
        with db_conn.cursor() as cur:
            # Get unique sessions with their subject and earliest timestamp
            cur.execute("""
                SELECT
                    session_id,
                    subject,
                    MIN(created_at) as created_at
                FROM chat_history
                GROUP BY session_id, subject
                ORDER BY MIN(created_at) DESC;
            """)
            sessions = []
            for row in cur.fetchall():
                sessions.append({
                    "session_id": str(row[0]),
                    "subject": row[1] or "Untitled Chat",  # Default if NULL
                    "created_at": row[2]
                })
            print(f"✅ Found {len(sessions)} sessions with subjects")
            return sessions
    except Exception as e:
        print(f"⚠️ Error fetching sessions: {e}")
        return []
```

### Function 2: Update Session Subject

```python
def update_session_subject(session_id: str, new_subject: str):
    """
    Update the subject for all messages in a session.
    """
    if db_conn is None:
        print("⚠️ No database connection.")
        return False
    try:
        with db_conn.cursor() as cur:
            cur.execute("""
                UPDATE chat_history
                SET subject = %s
                WHERE session_id = %s;
            """, (new_subject, session_id))
        print(f"✅ Updated subject for session {session_id}")
        return True
    except Exception as e:
        print(f"⚠️ Error updating subject: {e}")
        return False
```

### Function 3: Delete Session

```python
def delete_session(session_id: str):
    """
    Delete all messages for a given session.
    """
    if db_conn is None:
        print("⚠️ No database connection.")
        return False
    try:
        with db_conn.cursor() as cur:
            cur.execute("""
                DELETE FROM chat_history
                WHERE session_id = %s;
            """, (session_id,))
        print(f"✅ Deleted session {session_id}")
        return True
    except Exception as e:
        print(f"⚠️ Error deleting session: {e}")
        return False
```

### Function 4: Set Subject for New Message

```python
def save_message_with_subject(session_id: str, subject: str = None):
    """
    Update the subject for the most recent message in a session.
    Called after the first user message to set the default subject.
    """
    if db_conn is None or subject is None:
        return
    try:
        with db_conn.cursor() as cur:
            cur.execute("""
                UPDATE chat_history
                SET subject = %s
                WHERE session_id = %s AND subject IS NULL;
            """, (subject, session_id))
        print(f"✅ Set subject for session {session_id}: {subject}")
    except Exception as e:
        print(f"⚠️ Error setting subject: {e}")
```

---

## Part 3: Update the respond Function

Modify the `respond` function (around line 198) to save the first message as the subject:

**Find this section:**
```python
def respond(message, chat_history, session_id, persona, strict_mode):
    """
    Call chat_function to get the LLM response.
    """
    bot_message = chat_function(message, chat_history, session_id, persona, strict_mode)

    # Append in new Gradio format
    chat_history.append({"role": "user", "content": message})
    chat_history.append({"role": "assistant", "content": bot_message})
    return "", chat_history
```

**Replace with:**
```python
def respond(message, chat_history, session_id, persona, strict_mode):
    """
    Call chat_function to get the LLM response.
    """
    # Check if this is the first message (empty history)
    is_first_message = len(chat_history) == 0

    bot_message = chat_function(message, chat_history, session_id, persona, strict_mode)

    # Append in new Gradio format
    chat_history.append({"role": "user", "content": message})
    chat_history.append({"role": "assistant", "content": bot_message})

    # If first message, save it as the subject (truncate to 50 chars)
    if is_first_message:
        subject = message[:50] + ("..." if len(message) > 50 else "")
        save_message_with_subject(session_id, subject)

    return "", chat_history
```

---

## Part 4: New UI Design with Accordion

Replace the dropdown with an Accordion that shows a list of chat histories with edit/delete buttons.

### Step 4.1: Find the UI Section

In `main.py`, find the section with the session management UI (around line 254-267).

### Step 4.2: Replace with New Design

**Remove the old dropdown section:**
```python
# Remove this entire section:
with gr.Group():
    gr.Markdown("---")
    gr.Markdown("### 💬 Session Management")
    session_id_state = gr.State(lambda: str(uuid.uuid4()))
    session_dropdown = gr.Dropdown(...)
    new_chat_btn = gr.Button(...)
```

**Replace with this new Accordion design:**
```python
# Session Management with Accordion
gr.Markdown("---")
gr.Markdown("### 💬 Session Management")
session_id_state = gr.State(lambda: str(uuid.uuid4()))

with gr.Row():
    new_chat_btn = gr.Button(
        "✨ Start New Chat",
        variant="primary",
        scale=3
    )
    toggle_history_btn = gr.Button(
        "☰ History",
        variant="secondary",
        scale=1
    )

# History panel (initially visible, but can be toggled)
history_panel = gr.Column(visible=True)

with history_panel:
    gr.Markdown("#### 📜 Chat History")

    # This will hold the list of sessions
    sessions_data = gr.State(get_all_sessions_with_subjects())

    # Create a dynamic list of session buttons
    session_list = gr.HTML(value="<p>Loading sessions...</p>")

    # Selected session state
    selected_session = gr.State(None)

    # Edit subject interface (hidden by default)
    with gr.Row(visible=False) as edit_subject_row:
        subject_input = gr.Textbox(
            label="Edit Subject",
            placeholder="Enter new subject name",
            scale=3
        )
        save_subject_btn = gr.Button("💾 Save", scale=1, size="sm")
        cancel_edit_btn = gr.Button("❌ Cancel", scale=1, size="sm")
```

---

## Part 5: Create HTML for Session List

Add this helper function (before the Gradio UI section, around line 200):

```python
def create_session_list_html(sessions):
    """
    Create HTML for the session list with edit/delete buttons.
    """
    if not sessions:
        return "<p style='color: gray; font-style: italic;'>No chat history yet. Start a new chat!</p>"

    html = "<div style='max-height: 400px; overflow-y: auto;'>"

    for session in sessions:
        session_id = session['session_id']
        subject = session['subject']
        created_at = session['created_at'].strftime('%Y-%m-%d %H:%M') if session['created_at'] else 'Unknown'

        # Truncate subject if too long
        display_subject = subject[:40] + "..." if len(subject) > 40 else subject

        html += f"""
        <div style='
            border: 1px solid #ddd;
            border-radius: 8px;
            padding: 10px;
            margin: 8px 0;
            background: #f9f9f9;
            transition: background 0.2s;
        '
        onmouseover="this.style.background='#e8f4f8'"
        onmouseout="this.style.background='#f9f9f9'">
            <div style='display: flex; justify-content: space-between; align-items: center;'>
                <div style='flex-grow: 1; cursor: pointer;' onclick='alert("Load session: {session_id}")'>
                    <strong>{display_subject}</strong><br>
                    <small style='color: #666;'>{created_at}</small>
                </div>
                <div style='display: flex; gap: 5px;'>
                    <button onclick='alert("Edit: {session_id}")'
                            style='background: #4CAF50; color: white; border: none;
                                   padding: 5px 10px; border-radius: 4px; cursor: pointer;'>
                        ✏️
                    </button>
                    <button onclick='alert("Delete: {session_id}")'
                            style='background: #f44336; color: white; border: none;
                                   padding: 5px 10px; border-radius: 4px; cursor: pointer;'>
                        🗑️
                    </button>
                </div>
            </div>
        </div>
        """

    html += "</div>"
    return html
```

---

## Part 6: Event Handlers

Add these event handlers in the Gradio UI section (after defining the components):

### Handler 1: Toggle History Panel

```python
def toggle_history_visibility(current_visible):
    """Toggle the history panel visibility."""
    return not current_visible

toggle_history_btn.click(
    fn=lambda visible: gr.Column(visible=not visible),
    inputs=[history_panel],
    outputs=[history_panel]
)
```

### Handler 2: Load Session List

```python
def refresh_session_list():
    """Refresh the session list HTML."""
    sessions = get_all_sessions_with_subjects()
    html = create_session_list_html(sessions)
    return html, sessions

# Call this when the page loads and after actions
session_list.change(
    fn=refresh_session_list,
    inputs=None,
    outputs=[session_list, sessions_data]
)
```

### Handler 3: Update New Chat Button

Update the new chat button handler to refresh the session list:

```python
def start_new_chat():
    new_id = str(uuid.uuid4())
    print(f"✨ Starting new chat with session ID: {new_id}")
    # Refresh session list
    sessions = get_all_sessions_with_subjects()
    html = create_session_list_html(sessions)
    return new_id, [], html

new_chat_btn.click(
    fn=start_new_chat,
    inputs=None,
    outputs=[session_id_state, chatbot, session_list]
)
```

---

## Summary of Architecture

```
┌─────────────────────────────────────────┐
│  🦜🔗 LangChain RAG Assistant           │
├──────────────┬──────────────────────────┤
│  🎮 Controls │  💭 Conversation         │
│              │                          │
│  [✨ New]    │  [Chat messages]         │
│  [☰ History] │                          │
│              │                          │
│  ┌─────────┐│                          │
│  │📜 History││                          │
│  │         ││                          │
│  │ Chat 1  ││                          │
│  │  ✏️ 🗑️  ││                          │
│  │ Chat 2  ││                          │
│  │  ✏️ 🗑️  ││                          │
│  └─────────┘│                          │
└──────────────┴──────────────────────────┘
```

---

## Implementation Order

**Do these in order:**

1. ✅ Add 'subject' column to database (SQL command)
2. ✅ Add new database functions (4 functions)
3. ✅ Update `respond` function to save first message as subject
4. ✅ Add `create_session_list_html` helper function
5. ✅ Replace dropdown UI with new Accordion design
6. ✅ Add event handlers for toggle, refresh, load, edit, delete
7. ✅ Test each feature one by one

---

## Alternative: Simpler Approach

If the above seems too complex, here's a simpler approach:

**Use Gradio's built-in components:**
- Keep using Dropdown but populate it with subjects instead of session_ids
- Add separate buttons for "Edit Subject" and "Delete Session"
- Use Modal/Dialog for editing (if available in your Gradio version)

Let me know which approach you prefer, and I can provide more specific instructions!
