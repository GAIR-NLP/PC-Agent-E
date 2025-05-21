# multi-function script for data refinement
# 1. rewrite screenshot path
# 2. clean fail and error record
# 3. check last action finish
# 4. merge press and drag
# 5. remove redundant actions
# 6. remove meaningless actions
# 7. rewrite scroll
# 8. resize screenshot and coordinates to 1080p -> 720p
# 9. clean tracker interface
# 10. mark screenshot with red rect and point
# 11. rewrite markdown file
# 12. statistics
# support interrupt


import os
import json
import sys
import numpy as np
from PIL import Image
from utils import *

OVERWRITE_MARKED = True
REMOVE_FAIL_RECORD = True
DETAIL_OUTPUT = False 


def screenshot_of_tracker(screenshot_path, sample_size=100):
    """
    check if the screenshot is a Tracker interface.
    """
    if get_file_size_kb(screenshot_path) > 83:  # magic number
        return False

    bg_color = "#f0f0f0"
    bg_threshold = 0.8
    top_offset = 40  # top area offset
    bottom_offset = 80  # bottom area offset

    with Image.open(screenshot_path) as img:
        width, height = img.size

        # define the sampling regions
        sample_regions = [
            (0, top_offset, sample_size, sample_size + top_offset),  # top left corner
            (width - sample_size, top_offset, width, sample_size + top_offset),  # top right corner
            (0, height - sample_size - bottom_offset, sample_size, height - bottom_offset),  # bottom left corner
            (width - sample_size, height - sample_size - bottom_offset, width, height - bottom_offset)  # bottom right corner
        ]

        # convert the background color to numpy array
        bg_color_rgb = np.array([int(bg_color[i:i + 2], 16) for i in (1, 3, 5)])

        # check the four regions
        for region in sample_regions:
            sample_region = img.crop(region)
            sample_array = np.array(sample_region)[:, :, :3]
            matches = np.all(sample_array == bg_color_rgb, axis=2)
            bg_ratio = np.sum(matches) / matches.size

            if bg_ratio < bg_threshold:
                return False

    return True


def clean_tracker_interface(file_path):
    """
    clean the action records of the Tracker interface.

    return the number of actions after cleaning, -1 means the file is deleted
    """
    if DETAIL_OUTPUT:
        print(f"Clean tracker interface: {file_path}")
    screenshot_paths = []
    entries = []

    with open(file_path, 'r', encoding='utf-8') as file:
        for line in file:
            entry = json.loads(line)
            full_path = os.path.join(os.path.dirname(file_path), entry['screenshot'])
            screenshot_paths.append(full_path)
            entries.append(entry)

    last_entry_action = entries[-1].get('action')
    markdown_path = file_path.replace('.jsonl', '.md')

    # scan and identify the action of the Tracker interface
    begin = -1
    interval_list = []  # [begin, end)
    for index, screenshot_path in enumerate(screenshot_paths):
        # find the screenshot of the Tracker interface
        if screenshot_of_tracker(screenshot_path):
            if begin == -1:
                begin = index
        else:
            # back to the screenshot of non-Tracker interface, end the interval
            if begin != -1:
                interval_list.append((begin, index))
                begin = -1

    interval_list.append((begin, len(screenshot_paths)))  # the last interval (begin maybe -1)

    # delete the last interval (finish/fail)
    begin, end = interval_list.pop()
    if begin != -1:
        entries = entries[:begin]
        try:
            entries[-1]['action'] = last_entry_action
            entries[-1]['element'] = None
            entries[-1]['rect'] = None
        except Exception as e:  # empty data
            print(f"[ERROR] delete related records (probably empty): {e}")
            # delete the JSONL file
            os.remove(file_path)
            # delete the Markdown file
            os.remove(markdown_path)
            # delete the screenshot files
            for screenshot_path in screenshot_paths:
                remove_screenshot(screenshot_path)
            return -1

        for i in range(begin, end):
            remove_screenshot(screenshot_paths[i])

    # delete other intervals
    to_remove_entry_set = set()
    for begin, end in interval_list:
        for i in range(begin - 1, end):
            remove_screenshot(screenshot_paths[i])
            to_remove_entry_set.add(i)

    entries = [entry for i, entry in enumerate(entries) if i not in to_remove_entry_set]

    # save the updated JSONL file
    with open(file_path, 'w', encoding='utf-8') as file:
        for entry in entries:
            json.dump(entry, file, ensure_ascii=False)
            file.write('\n')

    return len(entries)


def clean_fail_and_error(file_path):
    """
    clean the records without corresponding Markdown files or the last action is 'fail' or there is None in action.

    return True if the file is deleted, False otherwise.
    """
    markdown_path = file_path.replace('.jsonl', '.md')
    if DETAIL_OUTPUT:
        print(f"Clean fail: {file_path}")
    try:
        with open(file_path, 'r', encoding='utf-8') as infile:
            entries = [json.loads(line) for line in infile]
    except Exception as e:
        print(f"[ERROR] Failed to read file {file_path}: {e}")
        return False

    screenshot_paths = [os.path.join(os.path.dirname(file_path), entry['screenshot']) for entry in entries]
    last_entry_action = entries[-1]['action'] if entries else ''

    # delete the records without corresponding Markdown files
    if not os.path.exists(markdown_path):
        if DETAIL_OUTPUT:
            print(f"File {file_path} has no corresponding Markdown file")
            print("Delete related records...")
        # delete the JSONL file
        os.remove(file_path)
        # delete the screenshot files
        for screenshot_path in screenshot_paths:
            remove_screenshot(screenshot_path)
        return True

    # clean the fail records (optional)
    if REMOVE_FAIL_RECORD and last_entry_action == 'fail':
        if DETAIL_OUTPUT:
            print(f"File {file_path} ends with fail action")
            print("Delete related records...")
        # delete the JSONL file
        os.remove(file_path)
        # delete the Markdown file
        os.remove(markdown_path)
        # delete the screenshot files
        for screenshot_path in screenshot_paths:
            remove_screenshot(screenshot_path)
        return True
    
    # check if there is None in action
    for entry in entries:
        if entry['action'] is None or "None" in entry['action']:
            if DETAIL_OUTPUT:
                print(f"File {file_path} has None in action")
                print("Delete related records...")
            # delete the JSONL file
            os.remove(file_path)
            # delete the Markdown file
            os.remove(markdown_path)
            # delete the screenshot files
            for screenshot_path in screenshot_paths:
                remove_screenshot(screenshot_path)
            return True
    
    return False


def resize(file_path):
    if DETAIL_OUTPUT:
        print(f"Resize file: {file_path}")

    # get the directory of the file
    task_dir = os.path.dirname(file_path)

    # read the screenshot path of the last entry
    try:
        with open(file_path, 'r', encoding='utf-8') as infile:
            lines = infile.readlines()
            last_line = lines[-1]
            last_entry = json.loads(last_line)
            screenshot_path = os.path.join(task_dir, last_entry['screenshot'])
    except Exception as e:
        print(f"[ERROR] Failed to read the screenshot path of the last entry: {e}")
        return

    if not os.path.exists(screenshot_path):
        print(f"[ERROR] The screenshot file does not exist: {screenshot_path}")
        return

    # get the resolution of the screenshot
    try:
        with Image.open(screenshot_path) as img:
            original_width, original_height = img.size
            if DETAIL_OUTPUT:
                print(f"Original resolution: {original_width}x{original_height}")
    except Exception as e:
        print(f"[ERROR] Failed to open the screenshot file {screenshot_path}: {e}")
        return

    # original_width, original_height = 2560, 1440

    # target resolution
    target_width, target_height = 1280, 720
    if original_width == target_width and original_height == target_height:
        if DETAIL_OUTPUT:
            print(f"The screenshot resolution is the same as the target resolution, no need to resize")
        return

    scale_x = target_width / original_width
    scale_y = target_height / original_height
    if DETAIL_OUTPUT:
        print(f"Resize ratio - X: {scale_x:.4f}, Y: {scale_y:.4f}")

    # process the JSONL file
    modified_lines = []
    for line in lines:
        try:
            data = json.loads(line)

            # process the screenshot
            screenshot_path = os.path.join(task_dir, data['screenshot'])
            assert resize_to_720p(screenshot_path), "Error occured!"

            # process the action
            data['action'] = resize_action(data['action'], scale_x, scale_y)

            # process the rect
            if 'rect' in data and isinstance(data['rect'], dict):
                rect = data['rect']
                rect['left'] = round(rect['left'] * scale_x)
                rect['top'] = round(rect['top'] * scale_y)
                rect['right'] = round(rect['right'] * scale_x)
                rect['bottom'] = round(rect['bottom'] * scale_y)
                if DETAIL_OUTPUT:
                    print(f"Resize rect: {rect}")

            modified_lines.append(json.dumps(data, ensure_ascii=False) + '\n')
        except Exception as e:
            print(f"[WARNING] Error when processing the line: {line.strip()} - {e}")
            modified_lines.append(line)

    # directly write the modified content, overwrite the original file
    try:
        with open(file_path, 'w', encoding='utf-8') as outfile:
            outfile.writelines(modified_lines)
        if DETAIL_OUTPUT:
            print(f"Saved the modified file: {file_path}")
    except Exception as e:
        print(f"[ERROR] Failed to write the file {file_path}: {e}")


def mark(file_path):
    if DETAIL_OUTPUT:
        print(f"Mark file: {file_path}")
    
    # get the directory of the file
    task_dir = os.path.dirname(file_path)
    
    # process the JSONL file
    modified_lines = []
    with open(file_path, 'r', encoding='utf-8') as infile:
        for line in infile:
            entry = json.loads(line)

            if not OVERWRITE_MARKED and 'marked_screenshot' in entry:
                if DETAIL_OUTPUT:
                    print(f"Already marked: {entry['marked_screenshot']}")
                modified_lines.append(line)
                continue

            screenshot = os.path.join(task_dir, entry.get('screenshot'))
            action = entry.get('action')
            rect = entry.get('rect')

            if rect is not None and action != "finish": # click or drag
                click_action_name, coordinates = parse_click_action(action)
                if click_action_name != None: # click related action
                    x, y = coordinates
                    marked_screenshot = mark_image(is_click_action=True, image_path=screenshot, rect=rect, point1={'x': x, 'y': y})
                    entry['marked_screenshot'] = marked_screenshot
                else: # drag related action
                    (x1, y1), (x2, y2) = parse_drag_action(action)
                    marked_screenshot = mark_image(is_click_action=False, image_path=screenshot, rect=rect, point1={'x': x1, 'y': y1}, point2={'x': x2, 'y': y2})
                    entry['marked_screenshot'] = marked_screenshot
            else:
                # rect is None, copy the original screenshot path
                entry['marked_screenshot'] = screenshot

            # remove the task_dir prefix of marked_screenshot
            entry['marked_screenshot'] = entry['marked_screenshot'].replace(
                task_dir + '/', '')

            modified_lines.append(json.dumps(entry, ensure_ascii=False) + '\n')

    # write the modified content, overwrite the original file
    with open(file_path, 'w', encoding='utf-8') as outfile:
        outfile.writelines(modified_lines)


def rewrite_screenshot_path(file_path):
    if DETAIL_OUTPUT:
        print(f"Rewrite screenshot path: {file_path}")

    modified_lines = []
    with open(file_path, 'r', encoding='utf-8') as file:
        for line in file:
            entry = json.loads(line)

            # process the screenshot field, remove the possible prefix 'events\\'
            if entry['screenshot'].startswith('events\\'):
                entry['screenshot'] = entry['screenshot'][7:]  # remove the 'events\\' prefix

            # replace the backslash with the forward slash (Linux format)
            if "\\" in entry['screenshot']:
                entry['screenshot'] = entry['screenshot'].replace("\\", "/")

            modified_lines.append(json.dumps(entry, ensure_ascii=False) + '\n')

    with open(file_path, 'w', encoding='utf-8') as outfile:
        outfile.writelines(modified_lines)


duplicate_clicks = 0
adjacent_clicks = 0


def remove_redundant_actions(file_path):
    if DETAIL_OUTPUT:
        print(f"Remove redundant actions: {file_path}")
    ctrl_cnt = 0
    shift_cnt = 0
    wait_cnt = 0
    caps_lock_cnt = 0
    all_entries = []
    kept_entries = []
    screenshot_paths = []
    continuous_wait_at_begin = False

    with open(file_path, 'r', encoding='utf-8') as file:
        for line in file:
            entry = json.loads(line)
            all_entries.append(entry)
            
    total_cnt = len(all_entries)
    skip = False
    for id, entry in enumerate(all_entries):
        if skip:
            skip = False
            continue
        # check the continuous adjacent clicks
        screenshot_path = os.path.join(os.path.dirname(file_path), entry['screenshot'])
        if entry != all_entries[-1] and 'click' in entry['action'] and 'click' in all_entries[id+1]['action']:
            _, (x1, y1) = parse_click_action(entry['action'])
            _, (x2, y2) = parse_click_action(all_entries[id+1]['action'])
            global adjacent_clicks
            global duplicate_clicks
            if entry['action'] == all_entries[id+1]['action']:
                duplicate_clicks += 1;
            elif abs(x1-x2) + abs(y1-y2) < 5:
                adjacent_clicks += 1;
        
        # delete the continuous wait at the beginning
        if entry['action'] != 'wait':
            continuous_wait_at_begin = False
        if entry['action'] == 'wait' and (id == 0 or continuous_wait_at_begin):
            wait_cnt += 1
            screenshot_paths.append(screenshot_path)
            continuous_wait_at_begin = True
        # delete the redundant ctrl and shift
        elif entry['action'] == 'press key ctrl' and (entry == all_entries[-1] or all_entries[id+1]['action'] == 'press key ctrl' or all_entries[id+1]['action'].startswith("hotkey (Ctrl,")):
            ctrl_cnt += 1
            screenshot_paths.append(screenshot_path)
        elif entry['action'] == 'press key shift' and (entry == all_entries[-1] or all_entries[id+1]['action'] == 'press key shift' or all_entries[id+1]['action'].startswith('type')):
            shift_cnt += 1
            screenshot_paths.append(screenshot_path)
        elif entry['action'] == 'press key ctrl' and all_entries[id+1]['action'] == 'press key shift':
            # this action and the next action should be deleted
            ctrl_cnt += 1
            shift_cnt += 1
            screenshot_paths.append(screenshot_path)
            screenshot_paths.append(os.path.join(os.path.dirname(file_path), all_entries[id+1]['screenshot']))
            if DETAIL_OUTPUT:
                print(f"remove ctrl + shift in {file_path} action {id}")
            skip = True
        elif entry['action'] == 'press key caps_lock':
            caps_lock_cnt += 1
            screenshot_paths.append(screenshot_path)
        else:
            kept_entries.append(entry)
                
    with open(file_path, 'w', encoding='utf-8') as file:
        for entry in kept_entries:
            json.dump(entry, file, ensure_ascii=False)
            file.write('\n')
                
    if len(kept_entries) == len(all_entries):
        if DETAIL_OUTPUT:
            print(f"File {file_path} has no redundant actions")
        return
    if DETAIL_OUTPUT:
        if wait_cnt != 0:
            print(f"File {file_path} has {wait_cnt}/{total_cnt} redundant wait, removed")
        if ctrl_cnt != 0:
            print(f"File {file_path} has {ctrl_cnt}/{total_cnt} redundant ctrl, removed")
        if shift_cnt != 0:
            print(f"File {file_path} has {shift_cnt}/{total_cnt} redundant shift, removed")
        if caps_lock_cnt != 0:
            print(f"File {file_path} has {caps_lock_cnt}/{total_cnt} redundant caps_lock, removed")
    
    # delete the screenshot files
    for screenshot_path in screenshot_paths:
        os.remove(screenshot_path)


def remove_meaningless_actions(file_path):
    if DETAIL_OUTPUT:
        print(f"Remove meaningless actions: {file_path}")
    all_entries = []
    kept_entries = []
    screenshot_paths = []

    with open(file_path, 'r', encoding='utf-8') as file:
        for line in file:
            entry = json.loads(line)
            all_entries.append(entry)
            
    for id, entry in enumerate(all_entries):
        # check the similarity of two continuous screenshots
        if entry != all_entries[-1] and (entry['action'] == 'wait' or 'click' in entry['action']):
            screenshot_path1 = os.path.join(os.path.dirname(file_path), entry['screenshot'])
            screenshot_path2 = os.path.join(os.path.dirname(file_path), all_entries[id+1]['screenshot'])
            if are_screenshots_identical(screenshot_path1, screenshot_path2):
                screenshot_paths.append(screenshot_path1)
                if DETAIL_OUTPUT:
                    print(f"action {id}: {entry['action']} in {file_path} is a meaningless action, it has been removed")
            else:
                kept_entries.append(entry)
        else:
            kept_entries.append(entry)
            
    if len(kept_entries) == len(all_entries):
        if DETAIL_OUTPUT:
            print(f"File {file_path} has no meaningless actions")
        return
    
    # rewrite the JSON file       
    with open(file_path, 'w', encoding='utf-8') as file:
        for entry in kept_entries:
            json.dump(entry, file, ensure_ascii=False)
            file.write('\n')

    # delete the screenshot files
    for screenshot_path in screenshot_paths:
        os.remove(screenshot_path)

     
def merge_press_drag(file_path):
    if DETAIL_OUTPUT:
        print(f"Merge press and drag: {file_path}")
    
    all_entries = []
    kept_entries = []
    screenshot_paths = []

    with open(file_path, 'r', encoding='utf-8') as file:
        for line in file:
            entry = json.loads(line)
            all_entries.append(entry)
    
    id = 0       
    while id < len(all_entries):
        # check the press action
        if id != len(all_entries) - 1 and all_entries[id]['action'].startswith("press ("):
            if id == len(all_entries) - 2 and all_entries[id+1]['action'] == "finish":
                # delete this press action
                id += 1
                continue
            # the next action must be drag to
            assert all_entries[id+1]['action'].startswith("drag"), f"Error: In file {file_path}, action {id+1} should start with 'drag', but it's {all_entries[id+1]['action']}"
            x1, y1 = extract_coordinates(all_entries[id]['action'])
            x2, y2 = extract_coordinates(all_entries[id+1]['action'])
            if abs(x1-x2) + abs(y1-y2) <= 10:
                if DETAIL_OUTPUT:
                    print(f"delta: {abs(x1-x2) + abs(y1-y2)} in {file_path} action {id} is too small, it's merged into a single click")
                all_entries[id]['action'] = f"click ({x2}, {y2})"
            else:
                if DETAIL_OUTPUT:
                    print(f"action {id}: {all_entries[id]['action']} in {file_path} has been merged with action {id+1}: {all_entries[id+1]['action']}")
                all_entries[id]['action'] = f"drag from ({x1}, {y1}) to ({x2}, {y2})"
            screenshot_paths.append(os.path.join(os.path.dirname(file_path), all_entries[id+1]['screenshot']))
            kept_entries.append(all_entries[id])
            id += 1 # skip the next action
        else:
            kept_entries.append(all_entries[id])
        
        id += 1
        
    if len(kept_entries) == len(all_entries):
        if DETAIL_OUTPUT:
            print(f"File {file_path} has no press and drag to be merged")
        return
    
    # rewrite the JSON file       
    with open(file_path, 'w', encoding='utf-8') as file:
        for entry in kept_entries:
            json.dump(entry, file, ensure_ascii=False)
            file.write('\n')

    # delete the screenshot files
    for screenshot_path in screenshot_paths:
        os.remove(screenshot_path)

def rewrite_scroll(file_path):
    if DETAIL_OUTPUT:
        print(f"Rewrite Scroll: {file_path}")
    
    all_entries = []
    kept_entries = []

    with open(file_path, 'r', encoding='utf-8') as file:
        for line in file:
            entry = json.loads(line)
            all_entries.append(entry)
    
    for entry in all_entries:
        if entry['action'].startswith("scroll"):
            new_pattern = r'^scroll \(-?\d+\)$'
            match = re.match(new_pattern, entry['action'])
            if match: # already in the new pattern
                kept_entries.append(entry)
            else:
                dx, dy = extract_coordinates(entry['action'])
                if dy != 0:
                    action = f"scroll ({dy})"
                    entry['action'] = action
                    kept_entries.append(entry)
        else:
            kept_entries.append(entry)
                
    
    # rewrite the JSON file       
    with open(file_path, 'w', encoding='utf-8') as file:
        for entry in kept_entries:
            json.dump(entry, file, ensure_ascii=False)
            file.write('\n')

    
def check_finish(file_path):
    if DETAIL_OUTPUT:
        print(f"Check finish: {file_path}")
    
    # read all lines
    try:
        with open(file_path, 'r', encoding='utf-8') as infile:
            lines = infile.readlines()
            last_line = lines[-1]
            last_entry = json.loads(last_line)
    except Exception as e:
        print(f"[ERROR] Failed to read the file content: {e}")
        return

    # replace the last action with finish
    if last_entry.get('action') == 'finish':
        if DETAIL_OUTPUT:
            print("The last entry is already 'finish'")
        return
    else:
        if DETAIL_OUTPUT:
            print("The last entry is ", last_entry.get('action'))
            print("Modify the last entry to 'finish'")
        last_entry['action'] = 'finish'

    # update the last line
    lines[-1] = json.dumps(last_entry, ensure_ascii=False) + '\n'

    # write back to file
    try:
        with open(file_path, 'w', encoding='utf-8') as outfile:
            outfile.writelines(lines)
        if DETAIL_OUTPUT:
            print(f"Saved the modified file: {file_path}")
    except Exception as e:
        print(f"[ERROR] Failed to write the file {file_path}: {e}")
        

def process_task_jsonl_file(file_path):
    if DETAIL_OUTPUT:
        print(f"Process task jsonl file: {file_path}")
    rewrite_screenshot_path(file_path)
    if clean_fail_and_error(file_path):
        return -1  # the file is deleted
    check_finish(file_path)
    merge_press_drag(file_path)
    remove_redundant_actions(file_path)
    remove_meaningless_actions(file_path)
    rewrite_scroll(file_path)
    resize(file_path)
    cnt = clean_tracker_interface(file_path)
    if cnt != -1:
        mark(file_path)
        rewrite_markdown_file_by_jsonl(file_path)
    return cnt


def process_events_directories():
    # Get parent directory of current script
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    # Build the path to the data folder
    data_dir = os.path.join(root_dir, 'data')
    if not os.path.exists(data_dir):
        print(f"error: {data_dir} directory does not exist")
        exit()
        
    # Events folder prefix
    events_prefix = "events_"

    total_action_cnt = 0
    total_record_cnt = 0
    max_action_cnt = 0

    # traverse all subdirectories of the data folder
    for item in os.listdir(data_dir):
        item_path = os.path.join(data_dir, item)

        # check if it's a directory and starts with the specified name
        if os.path.isdir(item_path) and item.startswith(events_prefix):
            print(f'Processing directory: {item_path}')
            for filename in os.listdir(item_path):
                # task jsonl file
                if filename.endswith('.jsonl') and 'task' in filename:
                    file_path = os.path.join(item_path, filename)
                    cnt = process_task_jsonl_file(file_path)
                    if cnt != -1:
                        total_action_cnt += cnt
                        total_record_cnt += 1
                        max_action_cnt = max(max_action_cnt, cnt)
    
    average_action_cnt = total_action_cnt / total_record_cnt
    print(f"Total records: {total_record_cnt}")
    print(f"Average actions per record: {average_action_cnt:.2f}")
    print(f"Maximum actions: {max_action_cnt}")
    

if __name__ == "__main__":
    process_events_directories()