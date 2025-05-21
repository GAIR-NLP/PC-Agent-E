import os
import json
import sys
import random
import concurrent.futures
import argparse
import traceback
import time
from datetime import datetime
from openai import OpenAI
from concurrent.futures import ThreadPoolExecutor
from prompt import *
from utils import *

THOUGHT = True
BOOST = True
CONCURRENT_NUM = 18
RE_GENERATE = False
MAX_CONTEXT_ENTRIES = 30
DETAILED_OUTPUT = True
BOOST_COUNT = 9


client = OpenAI()
model = "claude-3-7-sonnet-20250219"
print(f"Using model: {model}")


def call_model(query, base64_image=None):
    messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{base64_image}"
                        }
                    } if base64_image else None,
                    {
                        "type": "text",
                        "text": query
                    },
                ],
            },
        ]

    retry_time = 10
    while retry_time > 0:
        try:
            completion = client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=1000
            )
            reply = completion.choices[0].message.content
            
            return reply
        except Exception as e:
            if retry_time == 1:
                raise e
            else:
                pass
        retry_time -= 1
         

def process_concurrently(data_dir, events_prefix, function):
    tasks = []
    
    for item in os.listdir(data_dir):
        item_path = os.path.join(data_dir, item)

        if os.path.isdir(item_path) and item.startswith(events_prefix):
            print(f'Processing directory: {item_path}')
            for filename in os.listdir(item_path):
                if filename.endswith('.jsonl') and 'task' in filename:
                    file_path = os.path.join(item_path, filename)   
                    md_path = os.path.join(item_path, filename.replace('.jsonl', '.md'))
                    try:
                        with open(md_path, 'r', encoding='utf-8') as file:
                            lines = file.readlines()
                        task_description = lines[1].replace('**Description:** ', '').strip()
                        tasks.append((file_path, task_description))
                    except Exception as e:
                        print(f"error: failed to extract task description from {md_path}: {e}")

    random.shuffle(tasks)
    with ThreadPoolExecutor(max_workers=CONCURRENT_NUM) as executor:
        futures = [executor.submit(function, file_path, task_description) 
                  for file_path, task_description in tasks]
        concurrent.futures.wait(futures)
        

def get_history_str_for_boost(history_steps):
    """
    no context limit, extra 
    """
    history_str = ""
    for i, step in enumerate(history_steps):
        step_id, step_content = step
        if i == len(history_steps) - 1:
            history_str += f"**Your Previous Step**: Step {step_id}: {step_content}"
        else:
            history_str += f"Step {step_id}: {step_content}\n\n"
    return history_str


def get_thought(task_description, entry, history_steps, marked_screenshot_path):
    """
    Generate thought for the action.
    """
    base64_image = encode_image(marked_screenshot_path)
    action = entry["action"]
    element_description = entry["element"]
    history_str = get_history_str_for_boost(history_steps)

    query = THOUGHT_COMPLETION_PROMPT \
        + f"The task you are attempting to complete: {task_description}\n\n" \
        + f"Your performing history:\n{history_str}\n\n" \
        + f"The specific action you chose to perform: {action}\n\n"
        
    if element_description and element_description != "Unknown":
        query += f"The element you clicked: {element_description}\n\n"

    while True:
        thought = call_model(query, base64_image)
        thought = refine_thought(thought)
        if thought is not None:
            return thought


def get_boost_responses(task_description, entry, history_steps, screenshot_path, num):
    """
    Generate boost responses
    """
    base64_image = encode_image(screenshot_path)
    history_str = get_history_str_for_boost(history_steps)
    
    query = TRAJECTORY_BOOST_PROMPT \
        + f"The task you are attempting to complete: {task_description}\n\n" \
        + f"Your performing history:\n{history_str}\n\n" \
        + f"Given the screenshot as below. What's the next step that you will do to help with the task?"

    responses = []
    
    # Add more boost responses one by one
    for i in range(num-len(responses)):
        try_time = 5
        while try_time > 0:
            response = call_model(query, base64_image)
            response = refine_response(response)
            if response is not None:
                responses.append(response)
                break
            try_time -= 1
        responses.append(None)
            
    return responses
          
    
def add_entry_for_file(file_path, task_description):
    print(f"begin add entry for {file_path}")
    entries = []

    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            entries = [json.loads(line) for line in file]
    except Exception as e:
        print(f"error: failed to read file {file_path}: {e}")
        return
        
    try:
        for id, entry in enumerate(entries):
            # check marked screenshot available
            if 'marked_screenshot' not in entry:
                print(f"error: marked_screenshot field not found: {file_path}")
                continue
            
            marked_screenshot_path = os.path.join(os.path.dirname(file_path), entry['marked_screenshot'])
            screenshot_path = os.path.join(os.path.dirname(file_path), entry['screenshot'])
            if not os.path.isfile(marked_screenshot_path):
                print(f"error: screenshot file not found: {marked_screenshot_path}")
                continue
            
            # build history steps
            history_steps = []
            start_idx = max(0, id - MAX_CONTEXT_ENTRIES)
            for hist_id in range(start_idx, id):
                hist_entry = entries[hist_id]
                if 'thought' in hist_entry:
                    history_steps.append((hist_id+1, combine_thought_action_to_response(hist_entry['thought'], hist_entry['action'])))
            
            # get thought completion
            if THOUGHT:
                try:
                    field = "thought"
                    if field in entry:
                        if RE_GENERATE:
                            entry[field] = get_thought(task_description, entry, history_steps, marked_screenshot_path)
                        else:
                            # try refine thought
                            thought = refine_thought(entry[field])
                            # re-generate if not qualified
                            if thought is None:
                                entry[field] = get_thought(task_description, entry, history_steps, marked_screenshot_path)
                    else:
                        entry[field] = get_thought(task_description, entry, history_steps, marked_screenshot_path)
                except Exception as e:
                    print(f"error: failed to add thought file {file_path}: {e}")  
            
            # get boost responses
            if BOOST:
                try:
                    field = "boost_responses"
                    if field in entry:
                        if RE_GENERATE:
                            entry[field] = get_boost_responses(task_description, entry, history_steps, screenshot_path, BOOST_COUNT)
                        else:
                            responses = []
                            # append existing reponse after refinement
                            for response in entry[field]:
                                # remove empty response
                                if response is None:
                                    continue
                                response = refine_response(response)
                                responses.append(response)
                            # add new reponses if not enough
                            if len(responses) < BOOST_COUNT:
                                print(f"append new boost response\n")
                                new_reponses = get_boost_responses(task_description, entry, history_steps, screenshot_path, BOOST_COUNT - len(responses))
                                responses.extend(new_reponses)
                                
                            entry[field] = responses
                    else:
                        entry[field] = get_boost_responses(task_description, entry, history_steps, screenshot_path, BOOST_COUNT)    
                except Exception as e:
                    print(f"error: failed to boost file {file_path}: {e}") 
                    raise 
                
            if DETAILED_OUTPUT:
                print(f"boost finished for entry {id} in file {file_path}")
         
            with open(file_path, 'w', encoding='utf-8') as file:
                for entry in entries:
                    json.dump(entry, file, ensure_ascii=False)
                    file.write('\n')

        rewrite_markdown_file_by_jsonl(file_path)
        print(f"finished adding thought for {file_path}")

    except Exception as e:
        traceback.print_exc()
        print(f"error: failed to process file {file_path}: {e}")
        if "Expecting" in str(e) or "Invalid control character" in str(e):
            print(f"file {file_path} is corrupted, deleting...")
            try:
                os.remove(file_path)
                print(f"deleted corrupted file: {file_path}")
            except OSError as delete_error:
                print(f"error: failed to delete corrupted file: {delete_error}")


if __name__ == "__main__": 
    parser = argparse.ArgumentParser(description="Choose which model to use.")
    parser.add_argument(
        "--specific_data_dir",
        type=str,
        default=None,
        help="Optional path to a specific data directory.",
    )
    parser.add_argument(
        "--events_prefix",
        type=str,
        default=None,
        help="Events prefix",
    )
    parser.add_argument(
        "--boost_count",
        type=int,
        default=None,
        help="Optional number of items to boost. If None, boost all."
    )
    
    args = parser.parse_args()
    
    start_time = datetime.now()
    print(f"start time: {start_time}")

    # Get parent directory of current script
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    # Build total data folder path
    data_dir = os.path.join(root_dir, 'data')
    if not os.path.exists(data_dir):
        print(f"error: {data_dir} directory does not exist")
        exit()
    
    # Events folder prefix
    events_prefix = "events" if args.events_prefix is None else args.events_prefix
    
    process_concurrently(data_dir, events_prefix, add_entry_for_file)
    
    print("process events finished!")
    
    end_time = datetime.now()
    print(f"end time: {end_time}")
    print(f"Total time: {end_time - start_time}")
