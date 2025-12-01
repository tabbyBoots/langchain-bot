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
        cur.execute("""
            CREATE TABLE IF NOT EXISTS chat_history (
                    id SERIAL PRIMARY KEY,
                    session_id UUID NOT NULL,
                    message JSONB NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
            CREATE INDEX IF NOT EXISTS idx_chat_history_session_id ON chat_history (session_id);
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
    bot_message = chat_function(message, chat_history, session_id, persona, strict_mode)
    
    # Append in new Gradio format
    chat_history.append({"role": "user", "content": message})
    chat_history.append({"role": "assistant", "content": bot_message})
    #chat_history.append((message, bot_message))
    return "", chat_history

# 8. Launch the Gradio Chat Interface
if __name__ == "__main__":
    print("--- Launching Gradio UI ---")

    with gr.Blocks(title="LangChain Bot with RAG") as demo:

        # Header line
        gr.Markdown(
            """
            # 🦜🔗 LangChain RAG Assistant
            ### Your AI chatbot with document understanding and persist memory
            """
        )

        # Connection status
        with gr.Row():
            if db_conn is not None:
                gr.Markdown("✅ **Database:** Connected | ⚡ **Status:** Ready")
            else:
                gr.Markdown("⚠️ **Database:** Disconnected")

        # Get the list of existing sessions for the dropdown
        existing_sessions = get_all_session_ids()

        with gr.Row():
           # Left Sidebar - Controls  
            with gr.Column(scale=1, min_width=300):
                gr.Markdown("## 🎮 Controls")

                # Session Management UI
                with gr.Group():
                    gr.Markdown("---")
                    gr.Markdown("### 💬 Session Management")
                    session_id_state = gr.State(lambda: str(uuid.uuid4()))
                    session_dropdown = gr.Dropdown(
                        label="📋 Resume Previous Chat",
                        choices=get_all_session_ids(),
                        value=None,
                        interactive=True
                    )
                    new_chat_btn = gr.Button(
                        "✨ Start New Chat",
                        variant="primary"
                    )
                
                # Persona Selection UI
                with gr.Group():
                    gr.Markdown("---")
                    gr.Markdown("### 🎭 AI Persona")
                    persona_dropdown = gr.Dropdown(
                        choices=[
                            "You are a helpful assistant.",
                            "You are an export of UAS drone.",
                            "You are an export of Counter-Rocket, Artillery, Mortar(C-RAM)",
                            "You are an export of anti-UAS drone. system",
                            "You are a poetic storyteller.",
                        ],
                        value="You are a helpful assistant.",
                        label="Persona"
                    )
                    strict_mode_checkbox = gr.Checkbox(
                        label="🔒 Strict Mode (Answer from file ONLY)",
                        value=False
                    )
           
                # File Upload UI
                with gr.Group():
                    gr.Markdown("---")
                    gr.Markdown("#### 📄RAG Document")
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
                
            # Right Side -Chat Interface

            with gr.Column(scale=3):
                gr.Markdown("## 💭 Conversation")
                chatbot = gr.Chatbot(
                    label="Chat History", 
                    height=600,
                    show_label=False
                )
                with gr.Row():
                    msg_textbox = gr.Textbox(
                        placeholder="Type your message here...", 
                        show_label=False, 
                        scale=9
                    )
                    #clear_btn = gr.ClearButton([msg_textbox, chatbot])
                    clear_btn = gr.Button(
                        "🗑️ Clear",
                        scale=1
                    )
        
        # --- Event listener ---
     
        # for submitting message
        msg_textbox.submit(
            fn=respond,
            inputs=[msg_textbox, chatbot, session_id_state, persona_dropdown, strict_mode_checkbox],
            outputs=[msg_textbox, chatbot]
        )

        # for New Chat button
        def start_new_chat():
            new_id = str(uuid.uuid4())
            print(f"✨ Starting new chat with session ID: {new_id}")
            # return new session ID, clear chatbot, and resets the dropdown
            return new_id, [], None
        
        new_chat_btn.click(
            fn=start_new_chat,
            inputs=None,
            outputs=[session_id_state, chatbot, session_dropdown]
        )

        # for selecting a session from dropdown
        def load_chat_history(session_id):
            if session_id is None:
                 # If selection is cleared, start a new session
                new_id = str(uuid.uuid4())
                return [], new_id # Return empty history and original session_id
            try:
                history_obj = get_session_history(session_id)
                gradio_history = []
                for i in range(0, len(history_obj.messages), 2):
                    human_msg = history_obj.messages[i].content
                    ai_msg = history_obj.messages[i+1].content
                    # Use new Gradio format
                    gradio_history.append({"role": "user", "content": human_msg})
                    gradio_history.append({"role": "assistant", "content": ai_msg})
                    #gradio_history.append((human_msg, ai_msg))
                print(f"🔄 Resuming chat for session ID: {session_id}")
                return gradio_history, session_id
            except Exception as e:
                print(f"⚠️ Error loading history: {e}")
                # Fallback to new session on error
                new_id = str(uuid.uuid4())
                return [], new_id
        
        session_dropdown.change(
            fn=load_chat_history,
            inputs=[session_dropdown],
            outputs=[chatbot, session_id_state]
        )

        # Connect file upload to processing function
        file_upload.change(
            fn=process_file,
            inputs=file_upload,
            outputs=status_box
        )

    demo.launch(
        css="""
        .gradio-container {
            max-width: 1400px !important;
            margin: 0 auto;
        }
        footer {
            visibility: hidden;
        }
        .main {
            padding: 20px;
        }
        h1 {
            text-align: center;
        }
        """
    )

# Run the app in background
# nohup python main.py > gradio_output.log 2>&1 &
# or just 'uv run main.py'     
