from apps.common.utils import get_llm as utils_get_llm  # Rename the import
from .utils import tokenize
from langchain.text_splitter import TokenTextSplitter
from langchain.prompts.chat import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
import tiktoken
from django.conf import settings
import logging
from langchain.callbacks.manager import CallbackManager
from apps.common.utils import TokenCounterCallback
from django.utils import timezone
import pprint

logger = logging.getLogger(__name__)

class SummarizationManager:
    def __init__(self, model_name:str, task_instance = None):
        self.tokenizer = tiktoken.get_encoding("cl100k_base")
        #self.llm=get_llm(model_name, temperature=0.0)
        self.model_name = model_name
        self.task_instance = task_instance
        self.llm, self.token_counter_callback = utils_get_llm(model_name, temperature=0.0)  # Use the imported function
        
    def summarize_content(self, content: str) -> str:
        
        content_tokens = tokenize(content, self.tokenizer)
        #logging.info(f'summarize_content {content_tokens} tokens: {content[:100]}')

        if content_tokens < 20:
            return f"##### TITLE: {content}",0,0
        todays_date=timezone.now().strftime("%Y-%m-%d")
        summarize_prompt = ChatPromptTemplate.from_messages([
            ("human", 
            """
            You are an AI assistant designed to perform the initial extraction of key information from various types of content. Your task is to identify and select the most important elements from the given text, creating a concise yet comprehensive foundation for further refinement. Follow these guidelines:
Identify Key Information:
Extract main ideas, critical facts, and essential data points
Include relevant statistics, dates, and figures if present
Capture the core argument or thesis of the content
Maintain Original Structure:
Preserve the logical flow of ideas from the source material
Keep extracted sentences in their original order when possible
Focus on Relevance:
Prioritize information that is central to the main topic
Exclude tangential or less important details
Capture Diverse Elements:
Include a mix of introductory, supporting, and concluding information
Ensure representation of different viewpoints if present in the original text
Preserve Context:
Include enough surrounding information to maintain clarity
Ensure extracted portions can be understood without the full original text
Handle Quotations:
Include direct quotes only if they are crucial to the main points
Properly attribute any extracted quotes
Technical Content:
For specialized topics, retain key technical terms and their explanations
Include critical methodologies or processes if relevant
Avoid Bias:
Extract information objectively, without introducing personal interpretation
Maintain the tone and intent of the original content
Formatting:
form of an engaging, easy to read, well marked down long form blog post like the style of Neil Patel.
Input: {content}                   
            """),
        ])
        logging.info(f"summarize_prompt: {summarize_prompt}")
        summarize_chain = summarize_prompt| self.llm | StrOutputParser()

        self.task_instance.update_state(
            state='summarizing content',
            meta={'current_chunk': 0, 'total_chunks': 1}           
        )

        summary = summarize_chain.invoke({'content':content, 'date':todays_date})

        input_tokens = self.token_counter_callback.input_tokens
        output_tokens = self.token_counter_callback.output_tokens
        #logging.info(f"Summarization Input tokens: {input_tokens}, output tokens: {output_tokens}")
        return summary, input_tokens, output_tokens
