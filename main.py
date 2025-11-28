import os
import gradio as gr
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.output_parsers import StrOutputParser

# add Memory to ChatBot
from langchain_core.chat_history import BaseChatMessageHistory
from langchain_community.chat_message_histories import ChatMessageHistory
from langchain_core.runnables.history import RunnableWithMessageHistory

# add RAG support
from rag_utils import load_and_split_document, create_vectorstore

# Global variable (Vector Store)
vector_store = None

# 1. Load env variables (acquire API key from .env file at root folder)
load_dotenv()

# 2. Initialize the Model
llm = ChatOpenAI(model="gpt-4o-mini")

# 3. Define the store for Conversation History
store = {}
def get_session_history(session_id: str) -> BaseChatMessageHistory:
    """Helper function to retrieve history for a given seession ID."""
    if session_id not in store:
        store[session_id] = ChatMessageHistory()
    return store[session_id]

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

# constant session_id for DEMO only
# simplicity in this single user chat.
CONFIG = {"configurable":{"session_id":"chat1"}}

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

def chat_function(message, history, system_instruction, strict_mode):
    """
    Wrapper function for Gradio.
    
    "message" is current user input.
    "history" is passed by Gradio because LangChain handles it.
    "system_instruction" comes from the additional_inputs.
    "strict_mode" use uploaded files only."
    """
    global vector_store

    # RAG Logic: If we have a file loaded, find relevant info
    context_text = ""
    sources_list = []
    #sources_text = ""

    if vector_store is not None:
        # Search for the 3 most relevant chunks
        results = vector_store.similarity_search(message, k=3)

        # Create the context block for the LLM
        retrieved_info = "\n\n".join([doc.page_content for doc in results])
        context_text = f"\n\nRelevant Context from File:\n{retrieved_info}"

        # Create a visible "Sources" block for the User
        # Take the first 50 chars of each source to keep it readable
        # sources_text = "\n\n--- Sources Used ---\n"
        
        for i, doc in enumerate(results):
            # Extract metadata
            file_path = doc.metadata.get("source", "Unknown File")
            file_name = os.path.basename(file_path)
            page_num = doc.metadata.get("page", "N/A")

            # Format: Source 1: Uploaded File, document.pdf, Page 2
            source_str = f"Source {i+1}: Uploaded File, {file_name}, Page {page_num}"
            sources_list.append(source_str)

            #sources_text += f"Source {i+1}: {doc.page_content[:100]}...\n"
        
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

    # Combine original system instruction with the new context
    # full_system_message = system_instruction + context_text

    # Get the response from the LLM
    response_text = with_message_history.invoke(
        {
            "input": message,
            "system_message": full_system_message
        }, 
        config=CONFIG,
    )

    # Append Sources
    if sources_list:
        final_response = response_text + "\n\n--- Sources Used ---\n" + "\n".join(sources_list)
    else:
        # if no docs were used/founc
        final_response = response_text + "\n\n--- Source Used ---\nSource: LLM"

    # combine the final answer with source text.
    #return response_text + sources_text
    
    return final_response


# 8. Launch the Gradio Chat Interface
if __name__ == "__main__":
    print("--- Launching Gradio UI ---")

    with gr.Blocks() as demo:
        gr.Markdown("### 🦜🔗 LangChain Bot with RAG")

        # Chat Interface
        gr.ChatInterface(
            fn=chat_function, 
            title="LangChain Bot",
            additional_inputs=[
                gr.Dropdown(
                    choices=[
                        "You are a helpful assistant.",
                        "You are an export of UAS drone.",
                        "You are an export of Counter-Rocket, Artillery, Mortar(C-RAM)",
                        "You are an export of anti-UAS drone. system",
                        "You are a poetic storyteller." 
                        ],
                    value="You are a helpful assistant.",
                    label="Persona"
                ),
                gr.Checkbox(
                    label="Strict Mode (Answer from File ONLY)",
                    value=False
                )
            ]
        )

        with gr.Row():
            # File Upload Component
            file_upload = gr.File(label="Upload PDF or Text File", file_count="single", type="filepath")
            status_box = gr.Textbox(label="Status", interactive=False)

        # Connect file upload to processing function
        file_upload.change(
            fn=process_file,
            inputs=file_upload,
            outputs=status_box
        )

    demo.launch()

# Run the app in background
# nohup python main.py > gradio_output.log 2>&1 &
# or just 'uv run main.py'     
