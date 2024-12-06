from apps.common.utils import get_llm

from langchain.prompts.chat import (
    ChatPromptTemplate,
    SystemMessagePromptTemplate,
    HumanMessagePromptTemplate,
)
from langchain.schema import AIMessage, HumanMessage, SystemMessage

class ChatModelHandler:
    def __init__(self, model_name: str):
        self.model_name = model_name
        self.chat_model, _ = get_llm(model=model_name, temperature=0.05)
        self.summarize_prompt = self._create_summarize_prompt()

    def _create_summarize_prompt(self) -> ChatPromptTemplate:
        """ Create a prompt template for summarization """
        system_message_prompt = SystemMessagePromptTemplate.from_template(
            "You are an AI assistant that summarizes text while preserving key details, using markdown formatting."
        )
        human_message_prompt = HumanMessagePromptTemplate.from_template("{text}")
        return ChatPromptTemplate.from_messages([system_message_prompt, human_message_prompt])

    def _generate_messages(self, query: str) -> list:
        """ Generate messages for the chat model based on the query """
        human_message = HumanMessage(content=self.summarize_prompt.format_prompt(text=query).to_messages()[1].content)
        return [human_message]

    def generate_response(self, query: str) -> str:
        """ Generate a response from the chat model based on the query """
        messages = self._generate_messages(query)
        response = self.chat_model(messages)
        return response.content
