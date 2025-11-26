import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

# 1. Load env variables (acquire my API key)
load_dotenv()

# 2. Initialize the Model
llm = ChatOpenAI(model="gpt-4o-mini")

# 3. Create a Prompt Template
prompt = ChatPromptTemplate.from_messages([
    ("system", "You are a helpful assistant that explains concepts like I am 5 years old."),
    ("user", "Tell me about {topic}.")
])

# 4. Create the Chain
chain = prompt | llm | StrOutputParser()

# 5. Run it
topic = input("What topic do you want explained? ")
print(f"\n--- Explaining {topic} ---\n")

# .invoke() sends the data through the chain
response = chain.invoke({"topic": topic})
print(response)

