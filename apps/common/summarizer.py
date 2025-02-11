from langchain_community.chat_models import ChatOllama
from langchain.prompts.chat import (
    ChatPromptTemplate,
)
from langchain_core.output_parsers import StrOutputParser
import re
import tiktoken

from langchain_community.document_loaders import YoutubeLoader
from apps.agents.tools.crawl_website_tool.crawl_website_tool import CrawlWebsiteTool
from django.utils import timezone
from apps.seo_manager.models import SummarizerUsage
from langchain.text_splitter import TokenTextSplitter
import json

class Summarizer:
    def __init__(self):
        self.llm_tokens_sent=0
        self.llm_tokens_r=0
        self.encoder=tiktoken.get_encoding("gpt2")
        self.crawl_tool = CrawlWebsiteTool()

def is_pdf_url(url: str) -> bool:
    """
    Returns True if the URL points to a PDF, False otherwise.
    """
    try:
        # 1. Check if the URL has a .pdf extension
        parsed_url = urllib.parse.urlparse(url)
        if parsed_url.path.endswith('.pdf'):
            return True

        # 2. Send a HEAD request to the URL to get the Content-Type header
        response = requests.head(url, allow_redirects=True, timeout=5)

        # 3. Check if the Content-Type header is application/pdf
        content_type = response.headers.get('Content-Type')
        if content_type and content_type.startswith('application/pdf'):
            return True

        # 4. Check if the URL returns a PDF MIME type
        mime_type, _ = mimetypes.guess_type(url)
        if mime_type and mime_type.startswith('application/pdf'):
            return True

        # 5. If all else fails, try to download a small chunk of the file and check its magic number
        response = requests.get(url, stream=True, timeout=5)
        chunk = response.raw.read(1024)
        if chunk.startswith(b'%PDF-'):
            return True

        # If none of the above checks pass, it's likely not a PDF
        return False

    except requests.exceptions.RequestException as e:
        # Handle requests exceptions (e.g. connection errors, timeouts)
        print(f"Error checking URL: {e}")
        return False

    except Exception as e:
        # Handle any other unexpected exceptions
        print(f"Error checking URL: {e}")
        return False



    def compress_content(self, content, llm , task_instance, max_tokens):
        """
        Compress the given content using the provided compression chain.
        The content is split into chunks with an overlap of 100 characters, and each chunk is compressed.
        The compressed chunks are then combined, and the process is repeated if the total token count is still greater than the max_tokens.

        Args:
            content (str): The content to be compressed.
            compression_chain: The chain to use for compressing the content.
            max_tokens (int): The maximum number of tokens allowed for the compressed content.

        Returns:
            str: The compressed content.
        """
        tokenizer = tiktoken.get_encoding("gpt2")
        
        chunk_size = max_tokens*3
        overlap = round(chunk_size*.1)

        compressed_content = ""

        compress_prompt = ChatPromptTemplate.from_messages([
            ("system",
            """
            <INSTRUCTION>
            Process the text in the following guidelines, no preamble or postamble:
            <GUIDELINES>
            - preserve all details
            - use markdown
            - do not summarize
            - remove redundancies, fluff, filler content, advertisements, sponsors, and other distracting elements    
            </GUIDELINES>
            """),
            ("human", "<TEXT>{query}</TEXT>"),
        ])

        text_splitter = TokenTextSplitter(chunk_size=chunk_size, chunk_overlap=overlap)

        chunks = text_splitter.split_text(content)
        compress_chain = compress_prompt | llm | StrOutputParser()
        i=0
        chunks = [content[i:i+chunk_size] for i in range(0, len(content), chunk_size-overlap)]
        continue_compression = True
        last_chunk_size=len(chunks)
        while continue_compression:
            i+=1
            compressed_chunks = []
            last_token_size=0
            num_chunks = len(chunks)
            last_chunk_size=num_chunks
            print(f"Compressing iteration {i} with {num_chunks} chunks...")
            j=0
            task_instance.update_state(
                state='start compressing',
                meta={'current_chunk': j, 'total_chunks': num_chunks}
            )
            for chunk in chunks:
                j+=1
                print(f"Compressing chunk {j} of {num_chunks}...")
                compressed_chunk = compress_chain.invoke({'query': chunk})
                compressed_chunks.append(compressed_chunk)
                self.llm_tokens_sent += len(self.encoder.encode(compress_prompt.format(query=chunk), disallowed_special=()))
                self.llm_tokens_r += len(self.encoder.encode(compressed_chunk))
                print (f"LLM tokens received: {len(self.encoder.encode(compressed_chunk))}")
                # Send progress update
                task_instance.update_state(
                    state='compressing',
                    meta={'current_chunk': j, 'total_chunks': num_chunks}
                )

            compressed_content = "\n".join(compressed_chunks)
            print(compressed_content)
            compressed_tokens = tokenizer.encode(compressed_content, disallowed_special=())
            compressed_token_count = len(compressed_tokens)
            print(f"The compressed content has {compressed_token_count} tokens.")

            if compressed_token_count <= max_tokens:
                continue_compression = False
            else:
                chunks = text_splitter.split_text(compressed_content)
                print(f"Splitting into {len(chunks)} chunks. Last chunk size: {last_chunk_size}")
                if len(chunks) >= last_chunk_size: # if compression isn't getting much smaller then stop
                    continue_compression= False 

        return compressed_content

    def summarize(self, query, user, task_instance, base_url="http://192.168.30.100:11434"):
        """
        Generate a response to a user's query using the ChatOllama model.

        Args:
            query (str): The user's query (text or URL).
            base_url (str, optional): The base URL for the API endpoint. Defaults to "https://api.example.com/v1/chat".

        Returns:
            str: The response to the user's query, formatted in Markdown.
        """
        
        max_tokens=8192

        start_time = timezone.now()
        model = 'wizardlm2:7b-q8_0' # very very good
        #model = 'qwen:1.8b'        # bad
        #model = 'phi:latest'        # bad
        #model = 'openhermes:latest' # bad
        #model = 'mistral:7b-instruct-v0.2-q6_K' # ok
        #model = 'nous-hermes2-mixtral:8x7b-dpo-q4_K_M' # good
        #model = 'gemma:7b-instruct-v1.1-q8_0'  # worth investigating more, but not bad
        #model = 'adrienbrault/nous-hermes2pro:Q8_0' # not good
        #model = 'command-r:latest'
        #model = 'eramax/senku:latest' # bad
        #model = 'yi:6b-200k-fp16' # not enough vram
        #model = 'yi:6b-chat-fp16' # only outputted chinese -> didn't pursue
        #model = 'qwen:32b' # not great
        #model = 'dolphin-llama3:8b-v2.9-q8_0'
        #model = 'phi3:3.8b-mini-instruct-4k-fp16' # not that good
        #model = 'llama3:8b-instruct-fp16' # broken
        #model = 'dolphin-llama3:latest' # not that good
        #model = 'mixtral:8x7b-instruct-v0.1-q4_K_M'
        #model = 'herald/phi3-128k'


        # Initialize the ChatOllama model with the base_url parameter
        llm = ChatOllama(model=model, base_url=base_url, temperature=0.4, num_ctx=max_tokens)
        #    llm = ChatOllama(model="llama3:latest", base_url=base_url, num_ctx="8000",)

        # Define the prompt templates
        summarize_prompt = ChatPromptTemplate.from_messages([
            ("system",
            """
            <INSTRUCTION>
            Process the text in the following guidelines, no preamble or postamble:
            <GUIDELINES>
            - preserve all details
            - use markdown
            - do not summarize
            - remove redundancies, fluff, filler content, advertisements, sponsors, and other distracting elements    
            </GUIDELINES>
            </INSTRUCTION>
            """),
            ("human", """<TEXT>{query}\n</TEXT>
            <EXPECTED OUTPUT>
            "##### Title: create a pithy and insightful title\n
            ##### Date: provide the date if cited in source material, else 'not indicated'\n
            ##### Author(s): list the author(s) of the content(if available), else 'not indicated'\n
            ###### TLDR: write a concise, pithy summary of the content and it's conclusions\n\n

            """),
        ])

        summarize_chain = summarize_prompt | llm | StrOutputParser()

        # Check if the input is a URL
        url_pattern = r'^https?://\S+$'
        if re.match(url_pattern, query):
            # Scrape the website content
            youtube_regex = r"(?:https?:\/\/)?(?:www\.)?youtu(?:\.be|be\.com)\/(?:watch\?v=)?([\w-]{11})"
            match = re.match(youtube_regex, query)
            if match:
                # Use langchain YoutubeLoader to get the transcription
                loader = YoutubeLoader.from_youtube_url(query)
                docs = loader.load()

                content = ""
                for doc in docs:
                    content += doc.page_content + "\n"  # Combine page contents

            else: 
                if self.is_pdf_url(query):
                    pdfloader = PDFDocumentLoad()
                    docs = pdfloader.load_from_url(query)
                    content = ""
                    for doc in docs:
                        content += doc.page_content + "\n"  # Combine page contents
                else:
                    # Use CrawlWebsiteTool to get the content
                    try:
                        result = self.crawl_tool._run(
                            website_url=query,
                            user_id=user.id,
                            max_pages=1,  # Only get the main page
                            max_depth=0,  # No recursive crawling
                            output_type="markdown"  # Get markdown formatted content
                        )
                        
                        # Parse the result
                        result_data = json.loads(result)
                        if result_data.get("status") != "success" or not result_data.get("results"):
                            raise Exception("Failed to get content from URL")
                            
                        content = result_data["results"][0].get("content", "")
                        if not content:
                            raise Exception("No content found in the crawl result")
                            
                    except Exception as e:
                        print(f"Error crawling website: {str(e)}")
                        content = "Error: Failed to retrieve content from the URL"

            #print("scraped content: ", content)
        else:
            # Summarize the provided text
            content = query

        tokenizer = tiktoken.get_encoding("gpt2")
        print(f"The content precompression has {len(tokenizer.encode(content,disallowed_special=()))} tokens.")
        cleaned_content=""
        cleaned_content = self.summarize_nlp(content)
        if cleaned_content:
            content = cleaned_content
        #print(f"cleaned content: {content}")
#        print(f"The content is:\n{content}")
        # Count the tokens in the content using tiktoken
        tokens = tokenizer.encode(content, disallowed_special=())
        token_count = len(tokens)

        print(f"The content now has {len(tokenizer.encode(content,disallowed_special=()))} tokens.")

        # Compress the content if it's greater than max tokens
        if token_count > max_tokens:
            compressed_content = self.compress_content(content, llm, task_instance, max_tokens)

            token_count = len(tokenizer.encode(compressed_content,disallowed_special=()))
            print(f"The compressed_content has {token_count} tokens.")
            # Update state to indicate summarization
            content=compressed_content

        task_instance.update_state(
            state='summarizing',
            meta={'current_chunk': 1,  'total_chunks': 1}
        )

        response = summarize_chain.invoke({'query': content})

        result = response

        end_time = timezone.now()
        duration = end_time - start_time
        
        #save the usage data to the database
        usage = SummarizerUsage.objects.create(
            user=user,
            query=query,
            response=result,
            duration = duration,
            content_token_size=token_count,
            content_character_count=len(content),
            total_input_tokens=self.llm_tokens_sent,
            total_output_tokens=self.llm_tokens_r,
            model_used = model
        )
        usage.save()
        return result

 