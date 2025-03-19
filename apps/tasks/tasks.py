import os, time, subprocess
import datetime
import json
from os import listdir
from os.path import isfile, join
from .celery import app
from celery.contrib.abortable import AbortableTask
from django.utils import timezone
from django.contrib.auth.models import User
from django.conf import settings
import logging
import tiktoken
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile

from apps.common.content_loader import ContentLoader
from apps.agents.tools.compression_tool.compression_tool import CompressionTool
from apps.summarizer.models import SummarizerUsage

def get_scripts():
    """
    Returns all scripts from 'ROOT_DIR/celery_scripts'
    """
    raw_scripts = []
    scripts     = []
    ignored_ext = ['db', 'txt']

    try:
        raw_scripts = [f for f in listdir(settings.CELERY_SCRIPTS_DIR) if isfile(join(settings.CELERY_SCRIPTS_DIR, f))]
    except Exception as e:
        return None, 'Error CELERY_SCRIPTS_DIR: ' + str( e ) 

    for filename in raw_scripts:

        ext = filename.split(".")[-1]
        if ext not in ignored_ext:
           scripts.append( filename )

    return scripts, None           

def write_to_log_file(logs, script_name):
    """
    Writes logs to a log file with formatted name in the CELERY_LOGS_DIR directory.
    """
    script_base_name = os.path.splitext(script_name)[0]  # Remove the .py extension
    current_time = datetime.datetime.now().strftime("%y%m%d-%H%M%S")
    log_file_name = f"{script_base_name}-{current_time}.log"
    log_file_path = os.path.join(settings.CELERY_LOGS_DIR, log_file_name)
    
    with default_storage.open(log_file_path, 'w') as log_file:
        log_file.write(logs)
    
    return log_file_path

@app.task(bind=True, base=AbortableTask)
def execute_script(self, data: dict):
    """
    This task executes scripts found in settings.CELERY_SCRIPTS_DIR and logs are later generated and stored in settings.CELERY_LOGS_DIR
    :param data dict: contains data needed for task execution. Example `input` which is the script to be executed.
    :rtype: None
    """
    script = data.get("script")
    args   = data.get("args")

    print( '> EXEC [' + script + '] -> ('+args+')' ) 

    scripts, ErrInfo = get_scripts()

    if script and script in scripts:
        # Executing related script
        script_path = os.path.join(settings.CELERY_SCRIPTS_DIR, script)
        process = subprocess.Popen(
            f"python {script_path} {args}", shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        time.sleep(8)

        exit_code = process.wait()
        error = False
        status = "STARTED"
        if exit_code == 0:  # If script execution successfull
            logs = process.stdout.read().decode()
            status = "SUCCESS"
        else:
            logs = process.stderr.read().decode()
            error = True
            status = "FAILURE"


        log_file = write_to_log_file(logs, script)

        return {"logs": logs, "input": script, "error": error, "output": "", "status": status, "log_file": log_file}
    
@app.task(bind=True, time_limit=3600)
def summarize_content(self_task, query, user_id, model_name=settings.SUMMARIZER, crawl_website=False, max_pages=10):
    """
    Summarize the given content 
    :param self: Celery task instance
    :param query: str, the text/url to be summarized
    :param user_id: int, the user ID
    :param model_name: str, the model to use for summarization
    :param crawl_website: bool, whether to crawl the entire website
    :param max_pages: int, maximum number of pages to crawl
    :return: str, the summary of the input text
    """
    start_time = timezone.now()
    max_tokens = int(settings.SUMMARIZER_MAX_TOKENS)
    
    try:
        user = User.objects.get(id=user_id)
    except Exception as e:
        user_id = 3
        user = User.objects.get(id=user_id)
    
    content_loader = ContentLoader()
    content = content_loader.load_content(
        query, 
        user_id=user_id,
        crawl_website=crawl_website, 
        max_pages=max_pages
    )

    input_tokens = 0
    output_tokens = 0


    # Use CompressionTool for compression with 'comprehensive' setting
    compression_tool = CompressionTool(modelname=model_name)
    compression_result_json = compression_tool.run(
        content=content,
        max_tokens=max_tokens,
        detail_level="comprehensive"
    )
    
    # Parse the result
    compression_result = json.loads(compression_result_json)
    
    if "error" in compression_result:
        logging.error(f"Error compressing content: {compression_result.get('message', 'Unknown error')}")
        return f"Error: {compression_result.get('message', 'Failed to compress content')}"
    
    compressed_content = compression_result.get("processed_content", "")
    comp_input_tokens = compression_result.get("llm_input_tokens", 0)
    comp_output_tokens = compression_result.get("llm_output_tokens", 0)



    input_tokens += comp_input_tokens
    output_tokens += comp_output_tokens
    
    # Use CompressionTool for summarization with 'focused' setting to create a summary
    summarization_tool = CompressionTool(modelname=model_name)
    summarization_result_json = summarization_tool.run(
        content=compressed_content,
        detail_level="focused"  # Using focused for summarization
    )
    
    # Parse the result
    summarization_result = json.loads(summarization_result_json)
    
    if "error" in summarization_result:
        logging.error(f"Error summarizing content: {summarization_result.get('message', 'Unknown error')}")
        return f"Error: {summarization_result.get('message', 'Failed to summarize content')}"
    
    summary = summarization_result.get("processed_content", "")
    sum_input_tokens = summarization_result.get("llm_input_tokens", 0)
    sum_output_tokens = summarization_result.get("llm_output_tokens", 0)
    
    logging.info("finished compressing content")

    logging.info("finished summarizing content")
    input_tokens += sum_input_tokens
    output_tokens += sum_output_tokens

    result = summary + "\n\n--Detail-------------------\n\n" + compressed_content

    # save summarizationusage
    end_time = timezone.now()
    duration = end_time - start_time

    tokenizer = tiktoken.get_encoding("cl100k_base")
    content_tokens = tokenizer.encode(content)

    usage = SummarizerUsage.objects.create(
        user=user,
        query=query,
        compressed_content=compressed_content,
        response=summary,
        duration=duration,
        content_token_size=len(content_tokens),
        content_character_count=len(content),
        total_input_tokens=input_tokens,
        total_output_tokens=output_tokens,
        model_used=model_name
    )
    usage.save()
    logging.info(f"task summarize_content, user_id: {user_id}, model_name: {model_name}, max_tokens: {max_tokens}, content_tokens: {len(content_tokens)}, input_tokens: {input_tokens}, output_tokens: {output_tokens}, total_tokens: {input_tokens+output_tokens}, duration: {duration}")

    return result