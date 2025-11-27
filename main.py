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
    ("system", "You are a helpful, witty assistant. Keep your response short."),
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

def chat_function(message, history):
    """
    Wrapper function for Gradio.
    
    "message" is current user input.
    "history" is passed by Gradio because LangChain handles it.
    """
    response = with_message_history.invoke(
        {"input": message}, 
        config=CONFIG,
    )
    return response

# 8. Launch the Gradio Chat Interface
if __name__ == "__main__":
    print("--- Launching Gradio UI ---")
    demo = gr.ChatInterface(fn=chat_function, title="LangChain Bot")
    demo.launch()

# Run the app in background
# nohup python main.py > gradio_output.log 2>&1 &
# or just 'uv run main.py'
