from langchain.chat_models import ChatOllama
from langchain.prompts.chat import (
    ChatPromptTemplate,
    SystemMessagePromptTemplate,
    HumanMessagePromptTemplate,
)
from langchain_core.output_parsers import StrOutputParser

def summarize(query, base_url="http://192.168.30.100:11434"):
    """
    Generate a response to a user's query using the ChatOllama model.

    Args:
        query (str): The user's query.
        base_url (str, optional): The base URL for the API endpoint. Defaults to "https://api.example.com/v1/chat".

    Returns:
        str: The response to the user's query, formatted in Markdown.
    """
    
    # Initialize the ChatOllama model with the base_url parameter
    llm = ChatOllama(model="mistral", base_url=base_url)

    # Define a chat prompt template
    prompt = ChatPromptTemplate.from_messages([
    ("system", "Extract all relevant facts from the text."),
    ("human", "{query}"),
    ])

    # prompt = ChatPromptTemplate(
    #     messages=[
    #         SystemMessagePromptTemplate(
    #             prompt=("You are a helpful AI assistant for summarization. "
    #                     "Provide a concise summary of the users input, just the summary, no extra commentary.")
    #         ),
    #         HumanMessagePromptTemplate(input_variables=["query"]),
    #     ]
    # )
    chain = prompt | llm | StrOutputParser()
    # Define an output parser to handle Markdown responses
    # Generate a response to the user's query
    response = chain.invoke({'query':query})
    result = response

    return result