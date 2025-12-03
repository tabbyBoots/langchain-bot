# Progress Details: Implementation Guide

This file contains detailed implementation steps for features tracked in `progress.md`.

---

## Future Enhancement: Make Session List Interactive

### Option A: Simplest - Use Dropdown with Subjects (Recommended)

Replace the HTML list with a dropdown that shows subjects:

```python
# Instead of session_list = gr.HTML(...)
session_dropdown = gr.Dropdown(
    label="📋 Select Chat History",
    choices=[(s['subject'], s['session_id']) for s in get_all_sessions_with_subjects()],
    value=None
)
```

Then add Edit/Delete buttons below it.

**Pros:** Easy to implement, uses standard Gradio events
**Cons:** Less visual appeal than a styled list

### Option B: Use Radio with Custom Formatting

```python
session_radio = gr.Radio(
    label="📋 Chat History",
    choices=[(f"{s['subject']} ({s['created_at']})", s['session_id'])
             for s in get_all_sessions_with_subjects()],
    value=None
)
```

**Pros:** Can select and see all at once
**Cons:** Takes more vertical space

### Option C: Use Accordion with Buttons Inside

Create an Accordion with individual buttons for each session.

**Pros:** More control, collapsible sections
**Cons:** More complex to implement

---

## Recommendation

For your use case, **Option A (Dropdown)** is recommended because:
1. Shows meaningful subjects instead of UUIDs ✅
2. Easy to implement with standard events ✅
3. Can add Edit/Delete buttons easily ✅
4. Clean and simple UI ✅

---

## Database Functions Reference

### Function: get_all_sessions_with_subjects()

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
                    "subject": row[1] or "Untitled Chat",
                    "created_at": row[2]
                })
            print(f"✅ Found {len(sessions)} sessions with subjects")
            return sessions
    except Exception as e:
        print(f"⚠️ Error fetching sessions: {e}")
        return []
```

### Function: update_session_subject()

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

### Function: delete_session()

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

### Function: save_message_with_subject()

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

## Database Schema Update

If you need to add the subject column to the database:

```sql
-- Connect to PostgreSQL
docker exec -it langchain_postgres psql -U langchain -d langchain_chat

-- Add subject column (allows NULL for existing records)
ALTER TABLE chat_history ADD COLUMN subject TEXT;

-- Create index for better performance
CREATE INDEX IF NOT EXISTS idx_chat_history_subject ON chat_history (subject);

-- Exit
\q
```

Or update the table creation code in main.py (around line 38-51):

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

## Update respond() Function

Modify the `respond` function to save the first message as the subject:

**Find this section (around line 198):**
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

## UI Issues: Black Backgrounds, Hidden Blocks, and Toggle Scope

### Three Problems to Fix:

1. **Black backgrounds on some components** - Some Gradio components have dark backgrounds
2. **Hidden blocks requiring browser resize** - Content gets cut off, need to shrink browser to 60% to see everything
3. **Toggle button controls too much** - Hamburger button hides file upload section too, should only hide session management

---

## Issue 1: Fix Black Backgrounds

### Problem
Gradio might be applying dark theme to some internal components that aren't being overridden by your CSS.

### Solution
Add these CSS rules after line 906 (after the existing input/textarea styles) in the `demo.launch(css="""...)` section:

```css
/* Force light backgrounds on all Gradio internal components */
.svelte-1gfkn6j,
.svelte-1ed2p3z,
.prose,
div[data-testid],
.gr-box,
.gr-input,
.gr-form,
.gr-padded {
    background: white !important;
    color: #212529 !important;
}

/* Force dropdown options to be light */
.dropdown-content,
.options,
[data-testid="dropdown-option"] {
    background: white !important;
    color: #212529 !important;
}

/* Fix any remaining dark components */
* {
    background-color: inherit;
}

/* Override Gradio's dark mode if it's being applied */
:root {
    --body-background-fill: #e9ecef;
    --background-fill-primary: white;
    --background-fill-secondary: #f8f9fa;
    --color-accent: #0066cc;
}
```

---

## Issue 2: Fix Hidden Blocks - Remove Height Restrictions

### Problem
Lines 962-968 set a fixed height on `#main-container` with `height: calc(100vh - 180px)`, and the sidebar has `max-height: calc(100vh - 180px)` which can hide content if there's too much.

### Solution A: Update Main Container CSS

Find the `#main-container` section (around line 962-968) and replace it with:

```css
/* Main container - remove fixed height to show all content */
#main-container {
    display: flex;
    margin: 0;
    gap: 0;
    min-height: 600px;  /* Minimum height instead of fixed */
}
```

### Solution B: Update Sidebar CSS

Find the `#sidebar` section (around line 970-980) and replace it with:

```css
/* Sidebar - allow natural height */
#sidebar {
    background: #f8f9fa;
    border-right: 1px solid #dee2e6;
    overflow-y: auto !important;
    overflow-x: hidden !important;
    padding: 1rem;
    padding-bottom: 2rem;
    transition: all 0.3s ease;
    min-height: 600px;  /* Minimum instead of maximum */
    max-height: none !important;  /* Remove max-height restriction */
}
```

**What changed:**
- `#main-container`: Removed `height: calc(100vh - 180px)`, replaced with `min-height: 600px`
- `#sidebar`: Removed `max-height: calc(100vh - 180px)`, added `max-height: none !important`

This allows the content to naturally expand to show all components without cutting them off.

---

## Issue 3: Toggle Only Session Management (Not File Upload)

### Problem
The hamburger button (lines 570-586) toggles the entire `#sidebar` which includes:
- Session management ✅ (should be toggled)
- Persona selection ❌ (should stay visible)
- Strict mode checkbox ❌ (should stay visible)
- File upload ❌ (should stay visible)

### Solution
Restructure the UI so the toggle only affects the session list panel.

### Step 1: Wrap Session List in a Separate Container

Find the section around lines 438-471 where the sidebar content is defined. Modify it to wrap only the session history in a toggleable panel:

**Current structure:**
```python
with sidebar:
    gr.Markdown("## 💬 Sessions")

    with gr.Row():
        new_chat_btn = gr.Button(...)

    gr.Markdown("#### Chat History")

    # Session list HTML
    sessions = get_all_sessions_with_subjects()
    session_list = gr.HTML(...)

    # Rename dialog
    with gr.Group(visible=False, elem_id="rename-dialog") as rename_dialog:
        # ... rename dialog code ...

    # Persona Selection UI
    gr.Markdown("---")
    gr.Markdown("### 🎭 AI Persona")
    # ... persona code ...

    # File Upload UI
    gr.Markdown("---")
    gr.Markdown("### 📄 RAG Document")
    # ... file upload code ...
```

**Replace with (add session_panel wrapper):**
```python
with sidebar:
    gr.Markdown("## 💬 Sessions")

    with gr.Row():
        new_chat_btn = gr.Button(
            "✨ New Chat",
            variant="primary",
            size="sm",
            scale=1
        )

    # NEW: Wrap session list in a toggleable container
    session_panel = gr.Column(visible=True, elem_id="session-panel")

    with session_panel:
        gr.Markdown("#### Chat History")

        # Session list HTML
        sessions = get_all_sessions_with_subjects()
        session_list = gr.HTML(
            value=create_session_list_html(sessions),
            elem_id="session-list-container"
        )

        # Rename dialog (keep inside session panel)
        with gr.Group(visible=False, elem_id="rename-dialog") as rename_dialog:
            gr.Markdown("### ✏️ Rename Session")
            rename_session_id = gr.Textbox(visible=False)
            rename_input = gr.Textbox(
                label="New Name",
                placeholder="Enter new session name"
            )
            with gr.Row():
                save_rename_btn = gr.Button("Save", variant="primary", size="sm")
                cancel_rename_btn = gr.Button("Cancel", size="sm")

    # END of session_panel - everything below is OUTSIDE and always visible

    # Persona Selection UI (outside session panel, always visible)
    gr.Markdown("---")
    gr.Markdown("### 🎭 AI Persona")
    persona_dropdown = gr.Dropdown(
        choices=[
            "You are a helpful assistant.",
            "You are an expert of UAS drone.",
            "You are an expert of Counter-Rocket, Artillery, Mortar(C-RAM)",
            "You are an expert of anti-UAS drone system",
            "You are a poetic storyteller.",
        ],
        value="You are a helpful assistant.",
        label="Select Persona"
    )
    strict_mode_checkbox = gr.Checkbox(
        label="🔒 Strict Mode (Answer from file ONLY)",
        value=False
    )

    # File Upload UI (outside session panel, always visible)
    gr.Markdown("---")
    gr.Markdown("### 📄 RAG Document")
    file_upload = gr.File(
        label="Upload PDF or Text File",
        file_count="single",
        type="filepath"
    )
    status_box = gr.Textbox(
        label="Upload Status",
        interactive=False,
        placeholder="No file uploaded yet...",
        lines=2
    )
```

### Step 2: Update Hamburger Button Click Handler

Find the hamburger button click handler (lines 570-586) and replace it with:

**Current code (toggles entire sidebar):**
```python
# Hamburger button - toggle sidebar using JavaScript
hamburger_btn.click(
    fn=None,
    inputs=None,
    outputs=None,
    js="""
    () => {
        const sidebar = document.getElementById('sidebar');
        if (sidebar) {
            sidebar.classList.toggle('sidebar-hidden');
            console.log('Toggled sidebar, hidden:', sidebar.classList.contains('sidebar-hidden'));
        } else {
            console.error('Sidebar element not found!');
        }
    }
    """
)
```

**Replace with (toggles only session panel):**
```python
# Hamburger button - toggle session panel only (not file upload)
session_panel_visible = gr.State(True)

def toggle_session_panel(is_visible):
    """Toggle only the session history panel."""
    new_visible = not is_visible
    return new_visible, gr.update(visible=new_visible)

hamburger_btn.click(
    fn=toggle_session_panel,
    inputs=[session_panel_visible],
    outputs=[session_panel_visible, session_panel]
)
```

**Important:** Make sure to define `session_panel_visible` state after line 434 where `sidebar_visible` is defined:

```python
session_id_state = gr.State(lambda: str(uuid.uuid4()))
sidebar_visible = gr.State(True)
session_panel_visible = gr.State(True)  # Add this line
```

### Step 3: Add CSS for Session Panel

Add this CSS after line 1001 (after the session-list styles):

```css
/* Session panel toggle */
#session-panel {
    transition: all 0.3s ease;
}
```

### Step 4: Remove Old Sidebar Toggle CSS (Optional)

Since you're no longer toggling the entire sidebar with JavaScript, you can remove or comment out these CSS lines (around 882-885):

```css
/* Sidebar toggle */
#sidebar.sidebar-hidden {
    display: none !important;
}
```

---

## Summary of Changes

### Issue 1: Black Backgrounds
- Add CSS to force light backgrounds on Gradio internal classes
- Override CSS variables for dark mode

### Issue 2: Hidden Blocks
- Change `#main-container` from fixed `height` to `min-height`
- Change `#sidebar` from `max-height: calc(100vh - 180px)` to `max-height: none`
- This allows natural expansion to show all content

### Issue 3: Toggle Scope
- Create `session_panel` container that wraps only session list and rename dialog
- Move Persona and File Upload outside the session panel
- Update hamburger button to toggle `session_panel` instead of entire sidebar
- Add `session_panel_visible` state

---

## Testing After Changes

1. **Black backgrounds**: Check all dropdowns, inputs, and file upload areas - should all be white/light gray
2. **Hidden blocks**: Verify all sections (Sessions, Persona, File Upload) are visible without resizing browser
3. **Toggle behavior**: Click hamburger button - only "Chat History" section should hide/show, Persona and File Upload should remain visible
