from langchain_postgres import PostgresChatMessageHistory
import inspect

print(inspect.signature(PostgresChatMessageHistory.__init__))
