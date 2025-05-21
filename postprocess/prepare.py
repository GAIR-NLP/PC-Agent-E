import os
import json
import copy
import traceback
from prompt import AGENT_PROMPT
from utils import refine_response, refine_thought, combine_thought_action_to_response, get_history_str


output_file = f"train/LLaMA-Factory/data/pc-agent-e.json"
all_data = []
BOOST = True
HUMAN = True
REMOVE_NO_FISISH = True
BOOST_CNT = 9


def get_instruction(task_description, action_history):
    prompt = AGENT_PROMPT + f"Your task is: {task_description}\n\n"
    prompt += f"History of the previous actions and thoughts you have done to reach the current screen: {action_history}\n\n"
    prompt += "--------------------------------------------\n\n"
    prompt += f"Given the screenshot. What's the next step that you will do to help with the task?<image>"
    return prompt


def check_boost_response(boost_response, action):
    if boost_response is None:
        return False

    if REMOVE_NO_FISISH and action == "finish" and not "finish" in boost_response:
        # print(f"last action for boost is not finish, remove it!")
        return False
    if "(x, y)" in boost_response or "(x,y)" in boost_response:
        return False
    
    return True


def process_task_jsonl_file(file_path, dir_path, task_description):
    with open(file_path, "r", encoding="utf-8") as file:
        lines = file.readlines()          
    
    response_history = []  # for action history in natural language
        
    for idx, line in enumerate(lines):
        formatted_task = {
            "messages": [],
            "images": "",
        }

        entry = json.loads(line)
        action = entry["action"]
        
        # Reorganize press key action
        if action.startswith("press key"):
            action = action.replace("press key", "press key:")

        screenshot_path = entry["screenshot"]
        screenshot_path = f"{dir_path}/{screenshot_path}"
        # Add image path
        formatted_task["images"] = [screenshot_path]
        
        # Add user message
        action_history = get_history_str(response_history)
            
        query = get_instruction(task_description, action_history)
        formatted_task["messages"].append({"role": "user", "content": query})
        
        # Add boost response
        if BOOST and "boost_responses" in entry:
            for id, boost_response in enumerate(entry["boost_responses"][:BOOST_CNT]):
                if not check_boost_response(boost_response, action):
                    continue
                boost_response_cleaned = refine_response(boost_response)
                if boost_response_cleaned is None:
                    continue
                formatted_task_copy = copy.deepcopy(formatted_task)
                formatted_task_copy["messages"].append({"role": "assistant", "content": boost_response_cleaned})
                all_data.append(formatted_task_copy)

        # Add assistant message
        thought = refine_thought(entry['thought'])
        if thought is not None:
            response = combine_thought_action_to_response(thought, action)
            formatted_task["messages"].append({"role": "assistant", "content": response})
            response_history.append(response)
            if HUMAN:
                all_data.append(formatted_task)


def process_events_directories():
    # Get the parent directory of the current script
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    # Build the path to the data folder
    data_dir = os.path.join(root_dir, 'data')
    if not os.path.exists(data_dir):
        print(f"error: {data_dir} directory does not exist")
        exit()
        
    # Events folder prefix
    events_prefix = "events"

    # Process each subdirectory under /data
    for item in os.listdir(data_dir):
        item_path = os.path.join(data_dir, item)

        # Check if it's a directory and starts with specified name
        if os.path.isdir(item_path) and item.startswith(events_prefix):
            for filename in os.listdir(item_path):
                # Process each jsonl file under the directory
                if filename.endswith(".jsonl") and "task" in filename:
                    file_path = os.path.join(item_path, filename)
                    md_path = os.path.join(item_path, filename.replace(".jsonl", ".md"))
                    with open(md_path, "r", encoding="utf-8") as file:
                        lines = file.readlines()
                    try:
                        task_description = lines[1].replace("**Description:** ", "").strip()
                    except:
                        print(f"Error: Unable to extract task description from {md_path}")
                        continue
                    try:
                        process_task_jsonl_file(file_path, item_path, task_description)
                    except Exception as e:
                        error_traceback = traceback.format_exc()
                        print(f"{file_path} encountered error: {e}")
                        print(f"{error_traceback}")


if __name__ == "__main__":
    process_events_directories()
    print(f"entries: {len(all_data)}")
    with open(output_file, "w", encoding="utf-8") as file:
        json.dump(all_data, file, indent=2, ensure_ascii=False)
    