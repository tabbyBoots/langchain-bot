import os
import gradio as gr
import psycopg
import uuid
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.output_parsers import StrOutputParser

# add Memory to ChatBot
from langchain_core.chat_history import BaseChatMessageHistory
from langchain_postgres import PostgresChatMessageHistory
from langchain_core.runnables.history import RunnableWithMessageHistory

# add RAG support
from rag_utils import load_and_split_document, create_vectorstore

# Global variable (Vector Store)
vector_store = None

# 1. Load env variables (acquire API key from .env file at root folder)
load_dotenv()

# 2. Initialize the Model
llm = ChatOpenAI(model="gpt-4o-mini")

# 3. Define the store for Conversation History (using Postgres)
# Connection string: postgresql://user:password@host:port/dbname
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")
DB_NAME = os.getenv("DB_NAME")
DB_CONNECTION=f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# Create a global connection to reuse
try:
    # autocommit=True is recommended so messages are saved immediately
    db_conn = psycopg.connect(DB_CONNECTION, autocommit=True)

    # Manually create the table if it doesn't exist
    with db_conn.cursor() as cur:
        # Step 1: Create table with initial schema
        cur.execute("""
            CREATE TABLE IF NOT EXISTS chat_history (
                    id SERIAL PRIMARY KEY,
                    session_id UUID NOT NULL,
                    message JSONB NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
        """)

        # Step 2: Add missing columns (migration logic)
        # Check if 'subject' column exists, if not add it
        cur.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_name = 'chat_history'
                    AND column_name = 'subject'
                ) THEN
                    ALTER TABLE chat_history ADD COLUMN subject TEXT;
                END IF;
            END $$;
        """)

        # Step 3: Create indexes
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_chat_history_session_id ON chat_history (session_id);
            CREATE INDEX IF NOT EXISTS idx_chat_history_subject ON chat_history (subject);
        """)
    print("✅ Chat history table verified/created.")
except psycopg.OperationalError as e:
    print(f"⚠️ DB Connection Error: {e}")
    db_conn = None

def get_session_history(session_id: str) -> BaseChatMessageHistory:
    """
    Helper function to retrieve history from Postgres for a given session ID.
    """
    if db_conn is None:
        raise ConnectionError("Database connection is not active.")
    
    # Arguments must be positional: table_name, session_id
    return PostgresChatMessageHistory(
        "chat_history",
        session_id,
        sync_connection=db_conn
    )

def get_all_session_ids() -> list[str]:
    """
    Fetch all unique session IDs from the database.
    """
    if db_conn is None:
        print("⚠️ No database connection, cannot fetch session IDs.")
        return []
    try:
        with db_conn.cursor() as cur:
            cur.execute("SELECT DISTINCT session_id FROM chat_history ORDER BY session_id;")
            sessions = [row[0] for row in cur.fetchall()]
            print(f"✅ Found sessions: {sessions}")
            return sessions
    except Exception as e:
        print(f"⚠️ Error fetching session IDs: {e}")
        return []

def get_all_sessions_with_subjects() -> list[dict]:
    """
    Fetch all unique sessions with their subjects
    """
    if db_conn is None:
        print("⚠️ No database connection, cannot fetch sessions.")
        return []
    try:
        with db_conn.cursor() as cur:
            # Get sessions with subject and first timestamp
            # Note: GROUP BY only session_id (not subject) to get one row per session
            cur.execute("""
                SELECT
                        session_id,
                        COALESCE(MAX(subject), 'Untitled Chat') as subject,
                        MIN(created_at) as created_at
                FROM chat_history
                GROUP BY session_id
                ORDER BY MIN(created_at) DESC;
            """
            )
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
        return True
    except Exception as e:
        print(f"⚠️ Error updating subject: {e}")
        return False
    
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

def save_message_with_subject(session_id: str, subject: str = None):
    """
    Update the subject for the most recent message in a session.
    Called after the first user message to set the default subject.
    """
    if db_conn is None:
        return
    try:
        with db_conn.cursor() as cur:
            if subject:
                # First message: Set the provided subject for all NULL subjects
                cur.execute("""
                    UPDATE chat_history
                    SET subject = %s
                    WHERE session_id = %s AND subject IS NULL;
                """, (subject, session_id))
                print(f"✅ Set subject for session {session_id}: {subject}")
            else:
                # Subsequent messages: Get existing subject and apply to NULL entries
                cur.execute("""
                    SELECT subject
                    FROM chat_history
                    WHERE session_id = %s AND subject IS NOT NULL
                    LIMIT 1;
                """, (session_id,))
                result = cur.fetchone()

                if result and result[0]:
                    existing_subject = result[0]
                    cur.execute("""
                        UPDATE chat_history
                        SET subject = %s
                        WHERE session_id = %s AND subject IS NULL;
                    """, (existing_subject, session_id))
                    print(f"✅ Applied existing subject '{existing_subject}' to new messages in session {session_id}")        
    except Exception as e:
        print(f"⚠️ Error setting subject: {e}")        

# 4. --- Core Logic with Memory ---
memory_prompt = ChatPromptTemplate.from_messages([
    ("system", "{system_message}"), # use dynamic variable instead of hardcoded string 
    MessagesPlaceholder(variable_name="history"),
    ("user", "{input}")
])

# 5. Create the Base Chain
chain = memory_prompt | llm | StrOutputParser()

# 6. Add Memory Wrapper
with_message_history = RunnableWithMessageHistory(
    chain,
    get_session_history,
    input_messages_key="input",
    history_messages_key="history",
)

# 7. --- For Gradio Integration ---
def create_session_list_html(sessions):
    """
    Create HTML for the session list with edit/delete buttons and 3-dot menu.
    """
    if not sessions:
        return "<div class='session-list-empty'><p>No chat history yet. Start a new chat!</p></div>"

    html = "<div class='session-list'>"

    for session in sessions:
        session_id = session['session_id']
        subject = session['subject']
        created_at = session['created_at'].strftime('%Y-%m-%d %H:%M') if session['created_at'] else 'Unknown'

        # Truncate subject if too long
        display_subject = subject[:35] + "..." if len(subject) > 35 else subject

        # Escape quotes for data attributes
        safe_subject = subject.replace("'", "&#39;").replace('"', "&quot;")
        safe_display_subject = display_subject.replace("'", "&#39;").replace('"', "&quot;")

        html += f"""
        <div class='session-item' data-session-id='{session_id}' data-subject='{safe_subject}'>
            <div class='session-content' onclick='loadSessionClick(this)'>
                <div class='session-info'>
                    <div class='session-subject'>{safe_display_subject}</div>
                    <div class='session-date'>{created_at}</div>
                </div>
            </div>
            <div class='session-actions'>
                <button class='three-dot-btn' onclick='toggleMenuClick(event, this)'>
                    <span>⋮</span>
                </button>
                <div class='dropdown-menu' id='menu-{session_id}'>
                    <button onclick='editSessionClick(this)'>
                        <span>✏️</span> Rename
                    </button>
                    <button onclick='deleteSessionClick(this)' class='delete-btn'>
                        <span>🗑️</span> Delete
                    </button>
                </div>
            </div>
        </div>
        """

    html += "</div>"
    return html

# Helper functions for session management UI
def handle_load_session(session_id):
    """Load a session's chat history."""
    if not session_id:
        return [], str(uuid.uuid4())
    try:
        history_obj = get_session_history(session_id)
        gradio_history = []
        for i in range(0, len(history_obj.messages), 2):
            if i + 1 < len(history_obj.messages):
                human_msg = history_obj.messages[i].content
                ai_msg = history_obj.messages[i+1].content
                gradio_history.append({"role": "user", "content": human_msg})
                gradio_history.append({"role": "assistant", "content": ai_msg})
        print(f"🔄 Loaded session: {session_id}")
        return gradio_history, session_id
    except Exception as e:
        print(f"⚠️ Error loading session: {e}")
        return [], str(uuid.uuid4())

def handle_rename_session(session_id, new_subject):
    """Rename a session."""
    if not session_id or not new_subject:
        return create_session_list_html(get_all_sessions_with_subjects()), "Please provide a valid name."

    success = update_session_subject(session_id, new_subject)
    sessions = get_all_sessions_with_subjects()
    html = create_session_list_html(sessions)

    if success:
        return html, f"✅ Session renamed to '{new_subject}'"
    else:
        return html, "❌ Failed to rename session"

def handle_delete_session(session_id):
    """Delete a session."""
    if not session_id:
        return create_session_list_html(get_all_sessions_with_subjects()), [], str(uuid.uuid4()), "Invalid session"

    success = delete_session(session_id)
    sessions = get_all_sessions_with_subjects()
    html = create_session_list_html(sessions)

    if success:
        # Create a new session after deletion
        new_id = str(uuid.uuid4())
        return html, [], new_id #, f"✅ Session deleted"
    else:
        return html, [], str(uuid.uuid4()) #, "❌ Failed to delete session"

# function for RAG - process_file
def process_file(file_obj):
    """
    Handles file upload: loads content, splits it, and creates the vector store
    """
    global vector_store
    if file_obj is None:
        return "No file uploaded."

    try:
        # 1. Load and split
        splits = load_and_split_document(file_obj)

        # 2. Create Vector Store (The "Brain")
        vector_store = create_vectorstore(splits)

        return f"File processed! I have learned {len(splits)} chunks of information."
    except Exception as e:
        return f"Error processing file: {str(e)}"

def chat_function(message, history, session_id, system_instruction, strict_mode):
    """
    Wrapper function for Gradio.
    
    "message" is current user input.
    "history" is passed by Gradio because LangChain handles it.
    "session_id" is the unique ID from gr.State.
    "system_instruction" comes from the additional_inputs.
    "strict_mode" use uploaded files only."
    """
    global vector_store

    # RAG Logic: If we have a file loaded, find relevant info
    context_text = ""
    sources_list = []

    if vector_store is not None:
        # Search for the 3 most relevant chunks
        results = vector_store.similarity_search(message, k=3)

        # Create the context block for the LLM
        retrieved_info = "\n\n".join([doc.page_content for doc in results])
        context_text = f"\n\nRelevant Context from File:\n{retrieved_info}"

        # Create a visible "Sources" block for the User
        # Take the first 50 chars of each source to keep it readable
        
        for i, doc in enumerate(results):
            # Extract metadata
            file_path = doc.metadata.get("source", "Unknown File")
            file_name = os.path.basename(file_path)
            page_num = doc.metadata.get("page", "N/A")

            # Format: Source 1: Uploaded File, document.pdf, Page 2
            source_str = f"Source {i+1}: Uploaded File, {file_name}, Page {page_num}"
            sources_list.append(source_str)
        
    # --- New Logic START ---
    if strict_mode and vector_store is not None:
        # Force the model to ONLY use the file
        refined_instruction = (
            "You are a strict analyst. Answer the user's question based STRICTLY "
            "and ONLY on the following context. If the answer is not in the context, "
            "reply exactly: 'I cannot find the answer in the uploaded document.'"
        )
        full_system_message = refined_instruction + context_text
    else:
        full_system_message = system_instruction + context_text
    # --- New Logic END ---

    # Get the response from the LLM
    response_text = with_message_history.invoke(
        {
            "input": message,
            "system_message": full_system_message
        }, 
        # config=CONFIG,
        config={"configurable": {"session_id": session_id}}
    )

    # Append Sources
    if sources_list:
        final_response = response_text + "\n\n--- Sources Used ---\n" + "\n".join(sources_list)
    else:
        # if no docs were used/founc
        final_response = response_text + "\n\n--- Source Used ---\nSource: LLM"
    
    return final_response

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

    # Save subject for messages (truncate to 50 chars)
    if is_first_message:
        subject = message[:50] + ("..." if len(message) > 50 else "")
        save_message_with_subject(session_id, subject)
        
        # Refresh session list
        sessions = get_all_sessions_with_subjects()
        session_list_html = create_session_list_html(sessions)
        return "", chat_history, session_list_html
    else:
        # For subsequent messages, apply  existing subject to new messages
        save_message_with_subject(session_id)

    return "", chat_history, gr.update()

# 8. Launch the Gradio Chat Interface
if __name__ == "__main__":
    print("--- Launching Gradio UI ---")

    with gr.Blocks(title="LangChain Bot with RAG") as demo:

        with gr.Row(elem_id="header-row"):
            with gr.Column(scale=1, min_width=50):
                hamburger_btn = gr.Button("☰", elem_id="hamburger-btn", size="sm")
            with gr.Column(scale=10):
                gr.Markdown(
                    """
                    # 🦜🔗 LangChain RAG Assistant
                    ### Your AI chatbot with document understanding and persistent memory
                    """
                )

        # Connection status
        with gr.Row():
            if db_conn is not None:
                gr.Markdown("✅ **Database:** Connected | ⚡ **Status:** Ready")
            else:
                gr.Markdown("⚠️ **Database:** Disconnected")

        session_id_state = gr.State(lambda: str(uuid.uuid4()))
        sidebar_visible = gr.State(True)

        
        

        with gr.Row(elem_id="main-container"):
            # Left Sidebar - Session Management
            sidebar = gr.Column(scale=1, min_width=250, elem_id="sidebar", elem_classes="sidebar-shown") #

            with sidebar:
                gr.Markdown("## 💬 Chat History")

                with gr.Row():
                    new_chat_btn = gr.Button(
                        "✨ New Chat"
                    )

                # Session list HTML
                sessions = get_all_sessions_with_subjects()
                session_list = gr.HTML(
                    value=create_session_list_html(sessions),
                    elem_id="session-list-container"
                )

                # Rename dialog
                rename_session_id_state = gr.State("")  # Use State instead of hidden textbox
                with gr.Group(visible=False, elem_id="rename-dialog") as rename_dialog:
                    gr.Markdown("### ✏️ Rename Session")
                    rename_input = gr.Textbox(
                        label="New Name",
                        placeholder="Enter new session name",
                        elem_id="rename-input-box"
                    )
                    with gr.Row(elem_id="rename-buttons-row"):
                        save_rename_btn = gr.Button("Save", variant="primary", size="sm", elem_id="save-rename-btn")
                        cancel_rename_btn = gr.Button("Cancel", size="sm", elem_id="cancel-rename-btn")

            # Right Side - Chat Interface
            with gr.Column(scale=4, min_width=250, elem_id="chat-column"): # 
                
                chatbot = gr.Chatbot(
                    label="Chat History",
                    height=550,
                    show_label=False,
                    elem_id="chatbot"
                )
                with gr.Row():
                    msg_textbox = gr.Textbox(
                        placeholder="Type your message here...",
                        show_label=False,
                        scale=4,
                        container=False
                    )
                    clear_btn = gr.Button(
                        "🗑️",
                        scale=1
                    )
                # Persona and Strict Mode
                with gr.Row():
                        
                    with gr.Column(scale=4, min_width=150):
                    # Persona Selection UI
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
                        
                    with gr.Column(scale=1, min_width=150):  
            
                    # File Upload UI
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

        # Hidden components for JavaScript callbacks
        # Using textboxes for data + buttons for triggering events
        with gr.Row(elem_id="js-inputs-row", elem_classes="js-hidden"):
            js_load_session_data = gr.Textbox(elem_id="js_load_session_data")
            js_load_session_btn = gr.Button("Load", elem_id="js_load_session_btn")

            js_edit_session_id_data = gr.Textbox(elem_id="js_edit_session_id_data")
            js_edit_session_subject_data = gr.Textbox(elem_id="js_edit_session_subject_data")
            js_edit_session_btn = gr.Button("Edit", elem_id="js_edit_session_btn")

            js_delete_session_data = gr.Textbox(elem_id="js_delete_session_data")
            js_delete_session_btn = gr.Button("Delete", elem_id="js_delete_session_btn")

        # --- Event Listeners ---

        # Submit message
        msg_textbox.submit(
            fn=respond,
            inputs=[msg_textbox, chatbot, session_id_state, persona_dropdown, strict_mode_checkbox],
            outputs=[msg_textbox, chatbot, session_list]
        )

        # Clear chat
        clear_btn.click(
            fn=lambda: ([], str(uuid.uuid4())),
            inputs=None,
            outputs=[chatbot, session_id_state]
        )

        # New Chat button
        def start_new_chat():
            new_id = str(uuid.uuid4())
            print(f"✨ Starting new chat with session ID: {new_id}")
            sessions = get_all_sessions_with_subjects()
            html = create_session_list_html(sessions)
            return new_id, [], html

        new_chat_btn.click(
            fn=start_new_chat,
            inputs=None,
            outputs=[session_id_state, chatbot, session_list]
        )

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
                }
            }
            """
        )

        # Load session - triggered by button click
        # The js function reads from the textbox before calling Python
        # Also includes scrolling logic after load (to top of chat)
        js_load_session_btn.click(
            fn=handle_load_session,
            inputs=[js_load_session_data],
            outputs=[chatbot, session_id_state],
            js="""(data) => {
                setTimeout(() => {
                    const allElements = document.querySelectorAll('*');
                    for (let elem of allElements) {
                        const style = window.getComputedStyle(elem);
                        const isScrollable = style.overflowY === 'auto' || style.overflowY === 'scroll';
                        const hasScroll = elem.scrollHeight > elem.clientHeight;

                        if (isScrollable && hasScroll && elem.closest('#chatbot')) {
                            elem.scrollTop = 0;
                            break;
                        }
                    }
                }, 1000);
                return data;
            }"""
        )

        # Show rename dialog - triggered by button click
        def show_rename_dialog(session_id, current_subject):
            if session_id and session_id.strip():
                return (
                    gr.update(visible=True),
                    session_id,
                    gr.update(value=current_subject)
                )
            return gr.update(visible=False), "", gr.update(value="")

        js_edit_session_btn.click(
            fn=show_rename_dialog,
            inputs=[js_edit_session_id_data, js_edit_session_subject_data],
            outputs=[rename_dialog, rename_session_id_state, rename_input]
        ).then(
            fn=None,
            inputs=None,
            outputs=None,
            js="""() => {
                setTimeout(() => {
                    const dialog = document.getElementById('rename-dialog');
                    if (dialog) {
                        dialog.style.display = 'block';
                        dialog.style.visibility = 'visible';
                        dialog.style.opacity = '1';

                        const input = dialog.querySelector('#rename-input-box textarea, #rename-input-box input');
                        if (input) {
                            input.focus();
                            input.select();
                        }
                    }
                }, 100);
            }"""
        )

        # Save rename
        def save_rename(session_id, new_name):
            if not session_id or not session_id.strip():
                sessions = get_all_sessions_with_subjects()
                html = create_session_list_html(sessions)
                return (
                    html,
                    gr.update(visible=False),
                    "",
                    gr.update(value="")
                )

            if new_name:
                new_name = new_name.strip()

            html, msg = handle_rename_session(session_id, new_name)

            return (
                    html,
                    gr.update(visible=False),
                    "",
                    gr.update(value="")
                )

        save_rename_btn.click(
            fn=save_rename,
            inputs=[rename_session_id_state, rename_input],
            outputs=[session_list, rename_dialog, rename_session_id_state, rename_input]
        ).then(
            fn=None,
            inputs=None,
            outputs=None,
            js="""() => {
                const dialog = document.getElementById('rename-dialog');
                if (dialog) {
                    dialog.style.cssText = 'display: none !important;';
                }

                setTimeout(() => {
                    if (dialog) {
                        dialog.style.display = 'none';
                    }
                }, 100);
            }"""
        )

        # Cancel rename
        def cancel_rename():
            return gr.update(visible=False), "", gr.update(value="")

        cancel_rename_btn.click(
            fn=cancel_rename,
            inputs=None,
            outputs=[rename_dialog, rename_session_id_state, rename_input]
        )

        # Delete session - triggered by button click
        js_delete_session_btn.click(
            fn=handle_delete_session,
            inputs=[js_delete_session_data],
            outputs=[session_list, chatbot, session_id_state]
        )

        # File upload
        file_upload.change(
            fn=process_file,
            inputs=file_upload,
            outputs=status_box
        )

    # Custom JavaScript for dropdown menus and session loading
    custom_js = """
    <script>
        // Wait for Gradio to fully load
        function waitForGradio(callback) {
            if (window.gradio && document.getElementById('js_load_session')) {
                callback();
            } else {
                setTimeout(() => waitForGradio(callback), 100);
            }
        }

        // Helper function to find Gradio input element
        function findGradioInput(elemId) {
            // Try multiple approaches to find the input

            // Approach 1: Direct ID
            let elem = document.getElementById(elemId);
            if (elem) {
                if (elem.tagName === 'TEXTAREA' || elem.tagName === 'INPUT') return elem;

                // Look inside for textarea or input
                let input = elem.querySelector('textarea, input[type="text"], input:not([type])');
                if (input) return input;

                // Look for label and find associated input
                let label = elem.querySelector('label');
                if (label) {
                    let inputId = label.getAttribute('for');
                    if (inputId) {
                        let associatedInput = document.getElementById(inputId);
                        if (associatedInput) return associatedInput;
                    }
                }
            }

            // Approach 2: Search all textareas/inputs and match by parent ID
            const allInputs = document.querySelectorAll('textarea, input[type="text"], input:not([type="submit"]):not([type="button"])');
            for (let input of allInputs) {
                let container = input.closest('[id*="' + elemId + '"]');
                if (container) return input;
            }

            return null;
        }

        // Helper function to trigger Gradio update
        function triggerGradioUpdate(elemId, value) {
            return new Promise((resolve) => {
                const input = findGradioInput(elemId);

                if (input) {
                    input.value = value;
                    const inputEvent = new Event('input', { bubbles: true, cancelable: true });
                    const changeEvent = new Event('change', { bubbles: true, cancelable: true });

                    input.dispatchEvent(inputEvent);
                    input.dispatchEvent(changeEvent);
                    input.focus();
                    input.blur();

                    setTimeout(() => {
                        input.value = value;
                        input.dispatchEvent(new Event('input', { bubbles: true }));
                        resolve(true);
                    }, 50);
                } else {
                    resolve(false);
                }
            });
        }

        // Toggle dropdown menu
        function toggleMenuClick(event, button) {
            event.stopPropagation();
            const sessionItem = button.closest('.session-item');
            const sessionId = sessionItem.dataset.sessionId;
            const menu = document.getElementById('menu-' + sessionId);
            const allMenus = document.querySelectorAll('.dropdown-menu');

            // Close all other menus
            allMenus.forEach(m => {
                if (m !== menu) m.classList.remove('show');
            });

            // Toggle current menu
            if (menu) {
                menu.classList.toggle('show');
            }
        }

        // Close dropdowns when clicking outside
        document.addEventListener('click', function(event) {
            if (!event.target.closest('.session-actions')) {
                document.querySelectorAll('.dropdown-menu').forEach(menu => {
                    menu.classList.remove('show');
                });
            }
        });

        // Load session - set data and click button (with delay)
        function loadSessionClick(element) {
            const sessionItem = element.closest('.session-item');
            const sessionId = sessionItem.dataset.sessionId;

            const dataInput = findGradioInput('js_load_session_data');
            const btn = document.getElementById('js_load_session_btn');

            if (dataInput && btn) {
                dataInput.value = sessionId;
                dataInput.dispatchEvent(new Event('input', { bubbles: true }));

                setTimeout(() => {
                    btn.click();
                }, 150);
            }
        }

        // Edit session - set data and click button (with delay)
        function editSessionClick(button) {
            const sessionItem = button.closest('.session-item');
            const sessionId = sessionItem.dataset.sessionId;
            const subject = sessionItem.dataset.subject;

            const idInput = findGradioInput('js_edit_session_id_data');
            const subjectInput = findGradioInput('js_edit_session_subject_data');
            const btn = document.getElementById('js_edit_session_btn');

            if (idInput && subjectInput && btn) {
                idInput.value = sessionId;
                idInput.dispatchEvent(new Event('input', { bubbles: true }));
                idInput.dispatchEvent(new Event('change', { bubbles: true }));

                subjectInput.value = subject;
                subjectInput.dispatchEvent(new Event('input', { bubbles: true }));
                subjectInput.dispatchEvent(new Event('change', { bubbles: true }));

                setTimeout(() => {
                    btn.click();
                }, 300);
            } else {
                alert('Error: Could not open rename dialog. Please refresh the page and try again.');
            }

            document.querySelectorAll('.dropdown-menu').forEach(menu => {
                menu.classList.remove('show');
            });
        }

        // Delete session - set data and click button (with delay)
        function deleteSessionClick(button) {
            const sessionItem = button.closest('.session-item');
            const sessionId = sessionItem.dataset.sessionId;

            if (confirm('Are you sure you want to delete this session? This cannot be undone.')) {
                const dataInput = findGradioInput('js_delete_session_data');
                const btn = document.getElementById('js_delete_session_btn');

                if (dataInput && btn) {
                    dataInput.value = sessionId;
                    dataInput.dispatchEvent(new Event('input', { bubbles: true }));

                    setTimeout(() => {
                        btn.click();
                    }, 150);
                }
            }

            document.querySelectorAll('.dropdown-menu').forEach(menu => {
                menu.classList.remove('show');
            });
        }

        // Initialize when page loads
        waitForGradio(() => {
            // Initialization complete
        });
    </script>
    """

    demo.launch(
        css="""
        /* Hide JavaScript callback inputs */
        #js-inputs-row,
        .js-hidden {
            position: absolute !important;
            left: -10000px !important;
            width: 1px !important;
            height: 1px !important;
            overflow: hidden !important;
        }

        /* Sidebar toggle */
        #sidebar.sidebar-hidden {
            display: none !important;
        }

        /* Global container with grayish background */
        body {
            background: #e9ecef !important;
        }

        .gradio-container {
            max-width: 100% !important;
            margin: 0 !important;
            padding: 0 !important;
            background: #e9ecef !important;
        }

        /* Component backgrounds and text colors */
        textarea,
        input[type="text"],
        input:not([type="checkbox"]):not([type="radio"]) {
            background: white !important;
            color: #212529 !important;
            border: 1px solid #ced4da !important;
        }

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

        /* Labels - dark text */
        label,
        .label {
            color: #212529 !important;
            background: transparent !important;
        }

        /* File upload area */
        .file-preview,
        .upload-container,
        [data-testid="file-upload"],
        .file-upload {
            background: white !important;
            border: 1px solid #dee2e6 !important;
            border-radius: 8px !important;
            padding: 0.5rem !important;
        }

        /* Header */
        #header-row {
            background: #f5f5f5;
            color: #333;
            padding: 1rem;
            margin: 0;
            border-bottom: 2px solid #ddd;
            box-shadow: 0 2px 4px rgba(0,0,0,0.05);
        }

        #header-row h1 {
            color: #2c3e50 !important;
            margin: 0;
        }

        #header-row h3 {
            color: #5a6c7d !important;
            margin: 0;
        }

        #hamburger-btn {
            background: white;
            border: 1px solid #ccc;
            color: #333;
            font-size: 1.5rem;
            padding: 0.5rem 1rem;
            cursor: pointer;
            border-radius: 4px;
            transition: all 0.3s;
        }

        #hamburger-btn:hover {
            background: #e8e8e8;
            border-color: #999;
        }

        /* Main container */
        #main-container {
            display: flex;
            margin: 0;
            gap: 0;
            min-height:600px;
        }

        /* Sidebar */
        #sidebar {
            background: #f8f9fa;
            border-right: 1px solid #dee2e6;
            overflow-y: auto !important;
            overflow-x: hidden !important;
            padding: 1rem;
            padding-bottom: 2rem;
            transition: all 0.3s ease;
            max-height: none !important;
        }

        /* Sidebar text colors */
        #sidebar h2,
        #sidebar h3,
        #sidebar h4,
        #sidebar p,
        #sidebar label,
        #sidebar .markdown {
            color: #2c3e50 !important;
        }

        /* Ensure sidebar content can scroll */
        #sidebar > * {
            flex-shrink: 0;
        }

        /* Session list - reduced height to show file upload and status */
        .session-list {
            overflow-y: auto;
            margin-top: 10px;
        }

        .session-list-empty {
            color: #6c757d;
            font-style: italic;
            text-align: center;
            margin-top: 10px;
        }

        .session-item {
            display: flex;
            justify-content: space-between;
            align-items: center;
            background: white;
            border: 1px solid #dee2e6;
            border-radius: 8px;
            margin-top: 10px;
            padding: 0.75rem;
            transition: all 0.2s;
            position: relative;
        }

        .session-item:hover {
            background: #e7f3ff;
            border-color: #0066cc;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }

        .session-content {
            flex-grow: 1;
            cursor: pointer;
            padding-right: 0.5rem;
        }

        .session-info {
            display: flex;
            flex-direction: column;
            gap: 0.25rem;
        }

        .session-subject {
            font-weight: 600;
            color: #212529;
            font-size: 0.95rem;
        }

        .session-date {
            font-size: 0.75rem;
            color: #6c757d;
        }

        .session-actions {
            position: relative;
            display: flex;
            align-items: center;
        }

        .three-dot-btn {
            background: transparent;
            border: none;
            font-size: 1.25rem;
            color: #6c757d;
            cursor: pointer;
            padding: 0.25rem 0.5rem;
            border-radius: 4px;
            transition: all 0.2s;
        }

        .three-dot-btn:hover {
            background: rgba(0, 0, 0, 0.05);
            color: #212529;
        }

        .dropdown-menu {
            display: none;
            position: absolute;
            right: 0;
            top: 100%;
            background: white;
            border: 1px solid #dee2e6;
            border-radius: 6px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
            z-index: 1000;
            min-width: 140px;
            margin-top: 0.25rem;
        }

        .dropdown-menu.show {
            display: block;
        }

        .dropdown-menu button {
            display: flex;
            align-items: center;
            gap: 0.5rem;
            width: 100%;
            padding: 0.5rem 0.75rem;
            border: none;
            background: white;
            color: #212529;
            text-align: left;
            cursor: pointer;
            font-size: 0.9rem;
            transition: background 0.2s;
        }

        .dropdown-menu button:first-child {
            border-radius: 6px 6px 0 0;
        }

        .dropdown-menu button:last-child {
            border-radius: 0 0 6px 6px;
        }

        .dropdown-menu button:hover {
            background: #f8f9fa;
        }

        .dropdown-menu button.delete-btn:hover {
            background: #fee;
            color: #dc3545;
        }

        /* Rename dialog - highly visible */
        #rename-dialog {
            background: #fff3cd !important;
            border: 2px solid #ffc107 !important;
            border-radius: 8px !important;
            padding: 1.5rem !important;
            margin: 1rem 0 !important;
            box-shadow: 0 4px 12px rgba(0,0,0,0.2) !important;
            position: relative !important;
            z-index: 100 !important;
        }

        /* Show dialog when visible */
        #rename-dialog:not([style*="display: none"]) {
            display: block !important;
            visibility: visible !important;
            opacity: 1 !important;
        }

        /* Hide dialog when hidden */
        #rename-dialog[style*="display: none"] {
            display: none !important;
            visibility: hidden !important;
            opacity: 0 !important;
        }



        /* Ensure rename dialog content is on top */
        #rename-dialog > * {
            position: relative !important;
            z-index: 101 !important;
        }

        #rename-dialog * {
            color: #212529 !important;
        }

        #rename-dialog h3 {
            color: #856404 !important;
            margin-top: 0 !important;
        }

        #rename-dialog input,
        #rename-dialog textarea {
            background: white !important;
            color: #212529 !important;
            border: 1px solid #ffc107 !important;
        }

        /* Rename input box */
        #rename-input-box,
        #rename-input-box * {
            background: white !important;
            color: #212529 !important;
        }

        /* Rename buttons row - ensure it's visible and on top */
        #rename-buttons-row,
        #rename-dialog .gr-row,
        #rename-dialog [class*="row"] {
            display: flex !important;
            visibility: visible !important;
            opacity: 1 !important;
            position: relative !important;
            z-index: 102 !important;
            gap: 0.5rem !important;
            margin-top: 1rem !important;
        }

        /* Specific button IDs for maximum visibility */
        #save-rename-btn,
        #cancel-rename-btn,
        #rename-dialog button {
            display: inline-block !important;
            visibility: visible !important;
            opacity: 1 !important;
            padding: 0.75rem 1.5rem !important;
            margin: 0 !important;
            border: 2px solid #dee2e6 !important;
            border-radius: 6px !important;
            background: white !important;
            color: #212529 !important;
            cursor: pointer !important;
            font-size: 1rem !important;
            font-weight: 600 !important;
            transition: all 0.2s !important;
            min-width: 100px !important;
            height: auto !important;
            position: relative !important;
            z-index: 103 !important;
            pointer-events: auto !important;
        }

        #rename-dialog button:hover {
            background: #f8f9fa !important;
            border-color: #adb5bd !important;
            transform: translateY(-1px) !important;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1) !important;
        }

        /* Primary button (Save) - blue with white text */
        #save-rename-btn,
        #rename-dialog button[variant="primary"],
        #rename-dialog .primary {
            background: #0066cc !important;
            color: white !important;
            border-color: #0066cc !important;
        }

        #save-rename-btn:hover,
        #rename-dialog button[variant="primary"]:hover,
        #rename-dialog .primary:hover {
            background: #0052a3 !important;
            border-color: #0052a3 !important;
            color: white !important;
        }

        /* Chat column */
        #chat-column {
            display: flex;
            flex-direction: column;
            padding: 1rem;
            background: #e9ecef;
        }

        #chatbot {
            flex-grow: 1;
            border: 1px solid #dee2e6;
            border-radius: 8px;
            background: white !important;
        }

        /* Dropdown and select styling with dark text */
        select,
        .dropdown,
        .dropdown > *,
        [role="listbox"],
        [role="option"] {
            background: white !important;
            border: 1px solid #dee2e6 !important;
            padding: 0.5rem !important;
            border-radius: 4px !important;
            color: #212529 !important;
        }

        /* Dropdown selected value */
        .dropdown .wrap,
        .dropdown input {
            color: #212529 !important;
            background: white !important;
        }

        /* Checkbox styling */
        input[type="checkbox"] {
            margin-right: 0.5rem;
        }

        /* Checkbox label */
        input[type="checkbox"] + label,
        .checkbox-label {
            color: #212529 !important;
        }

        /* Group and component containers */
        .form,
        .block,
        .panel,
        .container {
            background: white !important;
            padding: 0.75rem !important;
            border-radius: 8px !important;
            margin-bottom: 0.5rem !important;
        }

        /* All text in components should be dark */
        .form *,
        .block *,
        .panel *,
        .container * {
            color: #212529 !important;
        }

        /* Ensure chatbot messages are readable */
        .message,
        .bot,
        .user {
            background: white !important;
            color: #212529 !important;
        }

        /* Footer */
        footer {
            visibility: hidden;
        }

        /* Scrollbar styling */
        .session-list::-webkit-scrollbar {
            width: 6px;
        }

        .session-list::-webkit-scrollbar-track {
            background: #f1f1f1;
            border-radius: 3px;
        }

        .session-list::-webkit-scrollbar-thumb {
            background: #888;
            border-radius: 3px;
        }

        .session-list::-webkit-scrollbar-thumb:hover {
            background: #555;
        }
        """,
        head=custom_js
    )

# Run the app in background
# nohup python main.py > gradio_output.log 2>&1 &
# or just 'uv run main.py'     
