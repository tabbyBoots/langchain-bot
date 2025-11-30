# Progress: Building a Manual UI with Session Management

This guide provides step-by-step instructions to add a feature that allows users to select and resume previous chat sessions from the database.

## Goal

Modify the Gradio UI to include a dropdown for selecting existing chat sessions and a button to start a new chat. The selected session will be used to retrieve and continue the conversation.

---

### Step 1: Create a Function to Fetch Session IDs

First, you need a function to query your `chat_history` table and retrieve a list of all unique `session_id`s. This will populate the session selection dropdown.

Add the following Python code to `main.py`, preferably near your other database functions (like `get_session_history`).

```python
def get_all_session_ids() -> list[str]:
    """Fetch all unique session IDs from the database."""
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
```

### Step 2: Modify the Gradio UI Layout (`gr.Blocks`)

You will now restructure your Gradio interface to accommodate the new session management components. This involves replacing `gr.ChatInterface` with a more manual layout using `gr.Chatbot`, `gr.Textbox`, and `gr.Button`.

Inside your `if __name__ == "__main__":` block, replace the entire `with gr.Blocks() as demo:` section with the following code. This new layout gives you more control.

```python
    with gr.Blocks(title="LangChain Bot with RAG", theme=gr.themes.Default()) as demo:
        gr.Markdown("### 🦜🔗 LangChain Bot with RAG & Memory")

        # Get the list of existing sessions for the dropdown
        existing_sessions = get_all_session_ids()

        with gr.Row():
            with gr.Column(scale=1):
                # Session Management UI
                gr.Markdown("#### Session Management")
                session_id_state = gr.State(lambda: str(uuid.uuid4()))
                session_dropdown = gr.Dropdown(
                    label="Resume a Previous Chat",
                    choices=existing_sessions,
                    value=None,
                    interactive=True
                )
                new_chat_btn = gr.Button("✨ Start New Chat")
                
                # Persona and Strict Mode UI
                gr.Markdown("#### Persona & Settings")
                persona_dropdown = gr.Dropdown(
                    choices=[
                        "You are a helpful assistant.",
                        "You are an expert of UAS drone.",
                        "You are an expert of Counter-Rocket, Artillery, Mortar(C-RAM)",
                        "You are an expert of anti-UAS drone. system",
                        "You are a poetic storyteller."
                    ],
                    value="You are a helpful assistant.",
                    label="Persona"
                )
                strict_mode_checkbox = gr.Checkbox(
                    label="Strict Mode (Answer from File ONLY)",
                    value=False
                )

                # File Upload UI
                gr.Markdown("#### RAG Document")
                file_upload = gr.File(label="Upload PDF or Text File", file_count="single", type="filepath")
                status_box = gr.Textbox(label="Status", interactive=False)

            with gr.Column(scale=4):
                # Main Chatbot UI
                chatbot = gr.Chatbot(label="Chat History", height=600)
                msg_textbox = gr.Textbox(placeholder="Type your message here...", show_label=False, scale=3)
                clear_btn = gr.ClearButton([msg_textbox, chatbot])

        # Connect file upload to processing function
        file_upload.change(
            fn=process_file,
            inputs=file_upload,
            outputs=status_box
        )
```

### Step 3: Create a New Chat Function

The old `chat_function` was designed for `gr.ChatInterface`. You need a new function that works with `gr.Chatbot` and handles the history manually. This function will call your original `chat_function` to get the LLM response.

Add this new function to `main.py`.

```python
def respond(message, chat_history, session_id, persona, strict_mode):
    """
    New function for the manual gr.Chatbot interface.
    It calls the original chat_function to get the LLM response.
    """
    # The original function returns the full response text
    bot_message = chat_function(message, chat_history, session_id, persona, strict_mode)
    # Append the user message and the bot response to the history
    chat_history.append((message, bot_message))
    # Return an empty string to clear the textbox and the updated history
    return "", chat_history
```

### Step 4: Connect UI Components to Functions

Finally, you need to wire up the buttons and text inputs to the correct functions. This involves setting up event listeners for submitting a message, starting a new chat, and selecting an old one.

Add this code at the end of your `with gr.Blocks() as demo:` section in `main.py`.

```python
        # Event listener for submitting a message
        msg_textbox.submit(
            fn=respond,
            inputs=[msg_textbox, chatbot, session_id_state, persona_dropdown, strict_mode_checkbox],
            outputs=[msg_textbox, chatbot]
        )

        # Event listener for the "New Chat" button
        def start_new_chat():
            new_id = str(uuid.uuid4())
            print(f"✨ Starting new chat with session ID: {new_id}")
            # Returns the new ID, clears the chatbot, and resets the dropdown
            return new_id, [], None

        new_chat_btn.click(
            fn=start_new_chat,
            inputs=None,
            outputs=[session_id_state, chatbot, session_dropdown]
        )

        # Event listener for selecting a session from the dropdown
        def load_chat_history(session_id):
            if session_id is None:
                return [] # Do nothing if no session is selected
            
            history_obj = get_session_history(session_id)
            # Convert LangChain history format to Gradio chatbot format
            gradio_history = []
            for i in range(0, len(history_obj.messages), 2):
                human_msg = history_obj.messages[i].content
                ai_msg = history_obj.messages[i+1].content
                gradio_history.append((human_msg, ai_msg))
            
            print(f"🔄 Resuming chat for session ID: {session_id}")
            return gradio_history, session_id

        session_dropdown.change(
            fn=load_chat_history,
            inputs=[session_dropdown],
            outputs=[chatbot, session_id_state]
        )
```

---

After completing these steps, run your `main.py` file. The application will now have the session management features you wanted. You can now select old chats from the dropdown to continue them, or start a new one.