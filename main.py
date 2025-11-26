import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.output_parsers import StrOutputParser

# add memory to ChatBot
from langchain_core.chat_history import BaseChatMessageHistory
from langchain_community.chat_message_histories import ChatMessageHistory
from langchain_core.runnables.history import RunnableWithMessageHistory

# 1. Load env variables (acquire API key in .env file)
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

# --- Core Logic with Memory ---

memory_prompt = ChatPromptTemplate.from_messages([
    ("system", "You are a helpful, witty assistant. Keep your response short."),
    MessagesPlaceholder(variable_name="history"),
    ("user", "{input}")
])

# 4. Create the Base Chain
chain = memory_prompt | llm | StrOutputParser()

# 5. Add Memory Wrapper
with_message_history = RunnableWithMessageHistory(
    chain,
    get_session_history,
    input_messages_key="input",
    history_messages_key="history",
)

# 6. Run the Chain Loop
print("--- AI Chatbot Initialized (Type 'quit' or 'exit' to end) ---")

# use a constant 'session_id' for simplicity in this single user chat.
CONFIG = {"configurable":{"session_id":"chat1"}}

while True:
    user_input = input("You: ")
    if user_input.lower() in ["quit", "exit"]:
        break

    response = with_message_history.invoke(
        {"input": user_input},
        config=CONFIG,
    )

    print(f"AI: {response}")
