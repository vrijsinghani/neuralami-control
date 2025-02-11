from .utils import tokenize, get_llm,  TokenCounterCallback
from langchain.text_splitter import TokenTextSplitter
from langchain.prompts.chat import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
import tiktoken
from django.conf import settings
import logging
from langchain.callbacks.manager import CallbackManager

class CompressionManager:
    def __init__(self, model_name:str, task_instance = None):
        self.tokenizer = tiktoken.get_encoding("cl100k_base")
        self.model_name = model_name
        self.task_instance = task_instance
        self.llm, self.token_counter_callback = get_llm(model_name, temperature=0.0)

    def compress_content(self, content: str, max_tokens: int) -> str:
        content_tokens = tokenize(content, self.tokenizer)
        if content_tokens < 20:
            return content,0,0
        else:        
            logging.info(f"Compressing content: {len(content)} chars and {content_tokens} tokens and {max_tokens} max tokens.")
            return self._compress_iteratively(content, max_tokens)

    def _compress_iteratively(self, content: str, max_tokens: int) -> str:
        """ Compress content iteratively until it fits within max_tokens """
        chunk_size = int(max_tokens) // 3
        overlap = 25
        text_splitter = TokenTextSplitter(chunk_size=chunk_size, chunk_overlap=overlap)
        logging.info(f"Chunk size: {chunk_size} tokens")
        compress_prompt = ChatPromptTemplate.from_messages([
            ("human", """
- Carefully read through the text and take detailed notes, do not lose any information, but remove content nonrelated to the main topic like promotions, advertisements, calls to action, etc.
- Focus on including every detail 
- long form outline format
- No preambles, post ambles, summaries, just the notes.
- Write at a 16 year old level.
\n\n```{content}```\n\n""")
        ])

        compress_chain = compress_prompt| self.llm | StrOutputParser()

        compressed_chunks = []
        chunks = text_splitter.split_text(content)
        num_chunks = len(chunks)
        iteration = 1

        last_iteration_size = tokenize(content,self.tokenizer)
        
        while True:
            self.task_instance.update_state(
                state=f'reading content...',
                meta={'current_chunk': 0, 'total_chunks': num_chunks}
            )
            current_chunk = 0
            for chunk in chunks:
                current_chunk += 1
                compressed_chunk = compress_chain.invoke({'content':chunk})
                self.task_instance.update_state(
                    state='processing',
                    meta={'current_chunk': current_chunk, 'total_chunks': num_chunks}
                )
                compressed_chunks.append(compressed_chunk)

            compressed_content = "\n".join(compressed_chunks)
            token_count = tokenize(compressed_content, self.tokenizer)
                
            if token_count <= max_tokens or token_count > .75*last_iteration_size:
                break
            else:
                chunks = text_splitter.split_text(compressed_content)
                compressed_chunks = []
                num_chunks= len(chunks)
                iteration += 1
                last_iteration_size = token_count

        input_tokens = self.token_counter_callback.input_tokens
        output_tokens = self.token_counter_callback.output_tokens
        logging.info(f"Compression Input tokens: {input_tokens}, output tokens: {output_tokens}")
        return compressed_content, input_tokens, output_tokens
