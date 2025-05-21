import os
import re
import json
import base64
import cv2
import numpy as np
from PIL import Image, ImageDraw

POINT_RADIUS = 2
CIRCLE_RADIUS = 18
CIRCLE_WIDTH = 2
RECT_WIDTH = 2

KEYBOARD_KEYS = ['\t', '\n', '\r', ' ', '!', '"', '#', '$', '%', '&', "'", '(', ')', '*', '+', ',', '-', '.', '/', '0', '1', '2', '3', '4', '5', '6', '7', '8', '9', ':', ';', '<', '=', '>', '?', '@', '[', '\\', ']', '^', '_', '`', 'a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j', 'k', 'l', 'm', 'n', 'o', 'p', 'q', 'r', 's', 't', 'u', 'v', 'w', 'x', 'y', 'z', '{', '|', '}', '~', 'accept', 'add', 'alt', 'altleft', 'altright', 'apps', 'backspace', 'browserback', 'browserfavorites', 'browserforward', 'browserhome', 'browserrefresh', 'browsersearch', 'browserstop', 'capslock', 'clear', 'convert', 'ctrl', 'ctrlleft', 'ctrlright', 'decimal', 'del', 'delete', 'divide', 'down', 'end', 'enter', 'esc', 'escape', 'execute', 'f1', 'f10', 'f11', 'f12', 'f13', 'f14', 'f15', 'f16', 'f17', 'f18', 'f19', 'f2', 'f20', 'f21', 'f22', 'f23', 'f24', 'f3', 'f4', 'f5', 'f6', 'f7', 'f8', 'f9', 'final', 'fn', 'hanguel', 'hangul', 'hanja', 'help', 'home', 'insert', 'junja', 'kana', 'kanji', 'launchapp1', 'launchapp2', 'launchmail', 'launchmediaselect', 'left', 'modechange', 'multiply', 'nexttrack', 'nonconvert', 'num0', 'num1', 'num2', 'num3', 'num4', 'num5', 'num6', 'num7', 'num8', 'num9', 'numlock', 'pagedown', 'pageup', 'pause', 'pgdn', 'pgup', 'playpause', 'prevtrack', 'print', 'printscreen', 'prntscrn', 'prtsc', 'prtscr', 'return', 'right', 'scrolllock', 'select', 'separator', 'shift', 'shiftleft', 'shiftright', 'sleep', 'space', 'stop', 'subtract', 'tab', 'up', 'volumedown', 'volumemute', 'volumeup', 'win', 'winleft', 'winright', 'yen', 'command', 'option', 'optionleft', 'optionright']


def refine_response(response):
    # Returns: refined response or None
    if response is None:
        return None
    response = response.replace("**Action:**", "Action:").strip()
    response = response.replace("### Action:\nAction:", "Action:").strip()
    thought, action = parse_thought_action_from_response(response)
    thought = refine_thought(thought)
    action = refine_action(action)
    if thought is None or action is None:
        return None
    
    return combine_thought_action_to_response(thought, action)


def refine_action(action):
    # Returns: refined action or None
    if action is None:
        return None
    
    action = remove_comments_from_action(action)
    
    # check if valid
    if get_action_code(action) is None:
        return None
    
    return action


def remove_comments_from_action(action):
    if action is None:
        return None
    # Find '#'
    pos_hash = action.find('#')
    if pos_hash != -1:
        action = action[:pos_hash]
    # Find '//'
    pos_slash = action.find('//')
    if pos_slash != -1:
        action = action[:pos_slash]
    
    return action.strip()


def refine_thought(thought):
    # Returns: refined thought or None
    
    # rule 0: check None
    if thought is None:
        return None
    
    # rule 1: check 'I can't assist'
    if "sorry, I can\'t assist" in thought:
        return None
    
    thought = thought.replace("**Thought Process:**", "").strip()
    
    # rule 2: check 'Action:' in thought
    if "Action:" in thought:
        thought = thought.split("Action:")[0].strip()
    if "*Action*:" in thought:
        thought = thought.split("*Action*:")[0].strip()
    if "**Action:**" in thought:
        thought = thought.split("**Action:**")[0].strip()
    
    # rule 3: check useless title with #
    if thought.startswith("# Thought Process") or thought.startswith("# My Thought Process"):
        newline_index = thought.find("\n")
        if newline_index != -1:
            thought = thought[newline_index+1:].strip()
        else:
            return None
    
    # rule 4: check if thought is enclosed in {}
    if thought.startswith("{") and thought.endswith("}"):
        thought = thought[1:-1].strip()  # remove the outer {}
        
    # rule 5: check if start with Your thought process
    unwanted_contents = ["{Your thought process}", "Your thought process", "## Thought Process", "# Thought process", "#*# Thought Process", "Thought process:", "Thought process", "My thought process:", "My thought process", "#\n", "#:\n", ":\n"]
    for unwanted in unwanted_contents:
        if unwanted in thought:
            thought = thought.replace(unwanted, "").strip()
    
    # rule 6: check too short thought
    if len(thought)< 15:
        return None
    
    return thought


def rewrite_markdown_file_by_jsonl(jsonl_path):
    """
    rewrite markdown file by jsonl file
    """
    with open(jsonl_path, 'r', encoding='utf-8') as file:
        lines = file.readlines()

    entries = [json.loads(line) for line in lines]
    markdown_path = jsonl_path.replace('.jsonl', '.md')
    rewrite_markdown_file(markdown_path, entries)


def rewrite_markdown_file(markdown_path, entries):
    """
    rewrite markdown file by entries, use marked_screenshot if exists
    """
    prompt = '''Given the screenshot as below. What's the next step that you will do to help with the task?'''
    with open(markdown_path, 'r', encoding='utf-8') as file:
        lines = file.readlines()

    # keep the first 5 lines
    kept_lines = lines[:5]

    # add new lines after the kept lines
    for index, entry in enumerate(entries):
        action = get_full_action(entry)
        screenshot_path = entry['marked_screenshot'] if 'marked_screenshot' in entry else entry['screenshot']
        thought = entry['thought'] if 'thought' in entry else None
        # boost_responses = entry['boost_responses'] if 'boost_responses' in entry else []

        kept_lines.append(f'### Step {index+1}\n')
        kept_lines.append(f'**Input:** \n\n{prompt}\n\n')
        kept_lines.append(
            f'<img src="{screenshot_path}" width="100%" height="100%">\n\n')
        
        if thought:
            kept_lines.append(f'**Thought:** \n\n{thought}\n\n')
        
        kept_lines.append(f'**Output:** \n\n{action}\n\n')
                
    # rewrite the file
    with open(markdown_path, 'w', encoding='utf-8') as file:
        file.writelines(kept_lines)


def remove_screenshot(screenshot_path):
    """
    remove the screenshot file and the possible _marked file
    """
    if os.path.exists(screenshot_path):
        os.remove(screenshot_path)

    # remove the possible _marked file
    marked_screenshot_path = screenshot_path.replace('.png', '_marked.png')
    if os.path.exists(marked_screenshot_path):
        os.remove(marked_screenshot_path)


def get_full_action(entry):
    """
    get the full action string from entry
    """
    action = entry['action']
    element = entry['element']
    if element:
        target = 'click'
        index = action.find(target)
        if index != -1:
            # find the end position of 'click'
            insert_position = index + len(target)
            # insert ':' after 'click'
            action = action[:insert_position] + \
                f' element {element} at' + action[insert_position:]
    return action


def encode_image(image_path):
    """
    encode image to base64
    """
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')


def get_file_size_kb(file_path):
    file_size_bytes = os.path.getsize(file_path)
    file_size_kb = file_size_bytes / 1024  # convert to KB
    return round(file_size_kb, 1)  # keep 1 decimal place


def mark_image(is_click_action, image_path, rect, point1, point2=None):
    """
    mark the image and save as a new file, return the new file path
    """
    # open the image
    with Image.open(image_path) as image:
        if is_click_action:
            # create a drawable object
            draw = ImageDraw.Draw(image)

            # draw a rectangle
            draw.rectangle(
                [(rect["left"], rect["top"]), (rect["right"], rect["bottom"])],
                outline="red",
                width=RECT_WIDTH  # line width
            )

            # draw a point
            draw_point(point1["x"], point1["y"], draw)

            # draw a circle
            draw_circle(point1["x"], point1["y"], draw)

            # draw a short arrow
            draw_short_arrow(point1["x"], point1["y"], draw)

        else:
            draw = ImageDraw.Draw(image)

            # draw a point
            draw_point(point1["x"], point1["y"], draw)
            draw_point(point2["x"], point2["y"], draw)

            if (abs(point1["x"] - point2["x"]) + abs(point1["y"] - point2["y"])) > 15:
                # draw a circle
                draw_circle(point1["x"], point1["y"], draw)
                draw_circle(point2["x"], point2["y"], draw)
            else:
                print(f"the distance between point1 and point2 in image {image_path} is too small, skip drawing circles")
                
            # draw a long arrow
            draw_long_arrow(point1["x"], point1["y"], point2["x"], point2["y"], draw)

    # generate the output path, add "_marked" to the original file name
    base, ext = os.path.splitext(image_path)
    output_path = f"{base}_marked{ext}"

    # save the marked image
    image.save(output_path)
    # print(f"marked image saved to: {output_path}")
    return output_path


def mark_image_for_boost(is_click_action, image_path, boost_idx, point1, point2=None):
    """
    mark the image and save as a new file, return the new file path
    """
    # open the image
    with Image.open(image_path) as image:
        if is_click_action:
            # create a drawable object
            draw = ImageDraw.Draw(image)

            # draw a point
            draw_point(point1["x"], point1["y"], draw)

            # draw a circle
            draw_circle(point1["x"], point1["y"], draw)

            # draw a short arrow
            draw_short_arrow(point1["x"], point1["y"], draw)

        else:
            draw = ImageDraw.Draw(image)

            # draw a point
            draw_point(point1["x"], point1["y"], draw)
            draw_point(point2["x"], point2["y"], draw)

            if (abs(point1["x"] - point2["x"]) + abs(point1["y"] - point2["y"])) > 15:
                # draw a circle
                draw_circle(point1["x"], point1["y"], draw)
                draw_circle(point2["x"], point2["y"], draw)
            else:
                print(f"the distance between point1 and point2 in image {image_path} is too small, skip drawing circles")
                
            # draw a long arrow
            draw_long_arrow(point1["x"], point1["y"], point2["x"], point2["y"], draw)

    # generate the output path, add "_marked" to the original file name
    base, ext = os.path.splitext(image_path)
    output_path = f"{base}_marked_boost_{boost_idx}{ext}"

    # save the marked image
    image.save(output_path)
    # print(f"marked image saved to: {output_path}")
    return output_path


def resize_to_720p(image_path):
    """
    check and resize the image to fixed 1280x720 resolution, return whether success
    """
    try:
        with Image.open(image_path) as img:
            img.verify()  # verify the image integrity
    except:
        print(f"[ERROR] image corrupted: {image_path}")
        return False

    # open the image
    with Image.open(image_path) as img:
        if img.size == (1280, 720):
            print(f"image is already 720p, no need to resize: {image_path}")
            return True

        try:
            resized_img = img.resize((1280, 720), Image.LANCZOS)
        except:
            print(f"[ERROR] cannot resize image: {image_path}")
            return False

        # save the resized image, overwrite the original file
        resized_img.save(image_path, optimize=True)
        print(f"image resized to 720p and saved: {image_path}")
        return True


def resize_to_1080p(image_path):
    """
    check and resize the image to fixed 1920x1080 resolution, return whether success
    """
    try:
        with Image.open(image_path) as img:
            img.verify()  # verify the image integrity
    except:
        print(f"[ERROR] image corrupted: {image_path}")
        return False

    # open the image
    with Image.open(image_path) as img:
        # check if the image is already 1080p
        if img.size == (1920, 1080):
            print(f"image is already 1080p, no need to resize: {image_path}")
            return True

        # resize the image to fixed 1920x1080 resolution
        try:
            resized_img = img.resize((1920, 1080), Image.LANCZOS)
        except:
            print(f"[ERROR] cannot resize image: {image_path}")
            return False

        # save the resized image, overwrite the original file
        resized_img.save(image_path, optimize=True)
        print(f"image resized and saved: {image_path}")
        return True


def resize_action(action_str, scale_x, scale_y):
    """
    extract coordinates from the action string, scale them, and replace the coordinate part in the original string.
    supports both single-point actions (e.g. "double click (1415, 741)") and 
    drag actions (e.g. "drag from (1230, 26) to (1209, 26)").

    :param action_str: action string
    :param scale_x: X axis scale factor
    :param scale_y: Y axis scale factor
    :return: the scaled action string
    """
    # use regex to match coordinate pairs
    pattern = r'\((\d+),\s*(\d+)\)'
    
    def scale_coords(match):
        original_x = float(match.group(1))
        original_y = float(match.group(2))
        scaled_x = round(original_x * scale_x)
        scaled_y = round(original_y * scale_y)
        print(f"scale coordinates: ({original_x}, {original_y}) -> ({scaled_x}, {scaled_y})")
        return f"({scaled_x}, {scaled_y})"
    
    # replace all coordinate pairs using the callback function
    new_action_str = re.sub(pattern, scale_coords, action_str)
    return new_action_str


def are_screenshots_identical(screenshot_path1, screenshot_path2):
    """
    check if two screenshots are identical
    """
    # read the images
    img1 = cv2.imread(screenshot_path1)
    img2 = cv2.imread(screenshot_path2)

    # check if the images are successfully read
    if img1 is None or img2 is None:
        print(f"cannot read image: {screenshot_path1} or {screenshot_path2}")
        return False

    # check if the images have the same size
    if img1.shape != img2.shape:
        return False

    # check if the images are identical
    difference = cv2.subtract(img1, img2)
    return not np.any(difference)


def parse_click_action(action):
    pattern = r'((?:double |right )?click)\s*\((\d+),\s*(\d+)\)'
    match = re.match(pattern, action)
    
    if match:
        action = match.group(1)  # extract the action name
        x = int(match.group(2))  # extract x coordinate and convert to integer
        y = int(match.group(3))  # extract y coordinate and convert to integer
        return action, (x, y)
    else:
        return None, None


def parse_drag_action(action):
    assert action.startswith('drag from'), f"error: action '{action}' is not a drag action"
    start1 = action.find('from (') + 6
    end1 = action.find(') to (')
    start2 = action.find('to (') + 4
    end2 = len(action) - 1
    
    # extract two sets of coordinates
    coord1 = action[start1:end1]
    coord2 = action[start2:end2]
    
    # split and convert to integers
    x1, y1 = map(int, coord1.split(', '))
    x2, y2 = map(int, coord2.split(', '))
    
    return (x1, y1), (x2, y2)


def extract_coordinates(text):
    # Pattern for drag/press/scroll coordinates
    coord_pattern_1 = r'(?:drag to|press|scroll) \((\-?\d+), (\-?\d+)\)'
    coord_match = re.search(coord_pattern_1, text)
    if coord_match:
        x, y = map(int, coord_match.groups())
        return x, y
    
    # Pattern for scroll with dx and dy
    coord_pattern_2 = r'scroll dx\s*=\s*(\-?\d+),\s*dy\s*=\s*(\-?\d+)'
    coord_match = re.search(coord_pattern_2, text)
    if coord_match:
        dx, dy = map(int, coord_match.groups())
        return dx, dy
    
    # If no match is found, return None
    return None


def draw_point(x, y, draw):
    radius = POINT_RADIUS
    left = x - radius
    top = y - radius
    right = x + radius
    bottom = y + radius

    draw.ellipse(
        [(left, top), (right, bottom)],
        fill="red"
    )


def draw_circle(x, y, draw):
    radius = CIRCLE_RADIUS
    left = x - radius
    top = y - radius
    right = x + radius
    bottom = y + radius

    draw.ellipse(
        [(left, top), (right, bottom)],
        outline="red",
        width=CIRCLE_WIDTH
    )


def draw_short_arrow(x, y, draw):
    arrow_length = 50  # arrow length
    arrow_gap = CIRCLE_RADIUS + 2  # arrow gap
    arrow_width = 10   # arrow width
    angle = np.radians(30)  # arrow angle
    cos_angle = np.cos(angle)
    sin_angle = np.sin(angle)

    # draw the arrow body
    start_x = x - arrow_length * cos_angle
    start_y = y - arrow_length * sin_angle
    end_x = x - arrow_gap * cos_angle
    end_y = y - arrow_gap * sin_angle
    draw.line([(start_x, start_y), (end_x, end_y)],
              fill="red", width=3)

    # draw the arrow head
    arrow_point1 = (
        int(end_x - arrow_width),
        int(end_y)
    )
    arrow_point2 = (
        int(end_x - arrow_width * sin_angle),
        int(end_y - arrow_width * cos_angle)
    )

    draw.polygon([
        (end_x, end_y),
        arrow_point1,
        arrow_point2
    ], fill="red")


def draw_long_arrow(x1, y1, x2, y2, draw):
    head_length = 18  # arrow head length
    head_angle = np.radians(30)  # arrow head angle

    # calculate the midpoint of the line
    mid_x = (x1 + x2) / 2
    mid_y = (y1 + y2) / 2

    # draw the arrow body
    draw.line([(x1, y1), (x2, y2)], fill="red", width=3)

    # arrow head direction vector
    vector_x = x2 - x1
    vector_y = y2 - y1
    length = np.hypot(vector_x, vector_y)
    unit_vector_x = vector_x / length
    unit_vector_y = vector_y / length

    # calculate the positions of the two points of the arrow head (now based on the midpoint)
    left_x = mid_x - head_length * \
        (unit_vector_x * np.cos(head_angle) +
         unit_vector_y * np.sin(head_angle))
    left_y = mid_y - head_length * \
        (unit_vector_y * np.cos(head_angle) -
         unit_vector_x * np.sin(head_angle))

    right_x = mid_x - head_length * \
        (unit_vector_x * np.cos(head_angle) -
         unit_vector_y * np.sin(head_angle))
    right_y = mid_y - head_length * \
        (unit_vector_y * np.cos(head_angle) +
         unit_vector_x * np.sin(head_angle))

    # use the midpoint as the vertex of the arrow head
    draw.polygon([(mid_x, mid_y), (left_x, left_y),
                  (right_x, right_y)], fill="red")


def parse_thought_action_from_response(response):
    """
    Parse thought, action from response by finding the last occurrence of 'Action:'.
    """
    if response is None:
        return None, None
    
    # Find the last occurrence of 'Action:'
    index = response.rfind("Action:")
    if index == -1:
        return response.strip(), None
    
    # Split the response into thought and action
    thought = response[:index].strip()
    action_start = index + len("Action:")
    action = response[action_start:].strip()
    
    return thought, action


def combine_thought_action_to_response(thought, action):
    return f"{thought}\n\nAction: {action}"


def get_mllm_messages(instruction, base64_image=None):
    messages = [
        {
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{base64_image}"
                    }
                },
                {
                    "type": "text",
                    "text": instruction
                },
            ] if base64_image else [
                {
                    "type": "text",
                    "text": instruction
                }
            ]
        },
    ]
    return messages


def match(action, gt_entry):
    """
    Determine if the predicted action is equivalent to the ground truth entry
    
    Args:
        action (str): Predicted action string
        gt_entry (dict): Dictionary containing ground truth action and related information
    
    Returns:
        bool: Returns True if actions are equivalent, False otherwise
    """
    # Handle edge cases first
    if action is None or gt_entry is None or "action" not in gt_entry:
        return False
    
    gt_action = gt_entry["action"]
    
    # Handle all click-type actions (click, right click, double click)
    click_types = ["click", "right click", "double click"]
    
    for click_type in click_types:
        if action.startswith(click_type) and gt_action.startswith(click_type):
            # After confirming click type match, check coordinates
            try:
                # Extract coordinates from predicted action
                import re
                coord_match = re.search(r'\((\d+),\s*(\d+)\)', action)
                if not coord_match:
                    return False
                
                x, y = int(coord_match.group(1)), int(coord_match.group(2))
                
                # Check if coordinates are within gt_entry's rect range
                if "rect" in gt_entry:
                    rect = gt_entry["rect"]
                    # Check rect format, usually [x1, y1, x2, y2] representing top-left and bottom-right coordinates
                    if isinstance(rect, list) and len(rect) == 4:
                        x1, y1, x2, y2 = rect
                        return x1 <= x <= x2 and y1 <= y <= y2
            except Exception as e:
                print(f"Error in matching click coordinates: {e}")
                return False
    
    # For all other action types, directly compare if strings are identical
    return action == gt_action


def get_action_code(action) -> str:
        screen_width, screen_height = 1280, 720
        # click
        match = re.match(r"click \((-?\d+), (-?\d+)\)", action)
        if match:
            x = int(match.group(1))
            y = int(match.group(2))
            if 0 <= x < screen_width and 0 <= y < screen_height:
                return f"pyautogui.click({x}, {y})"
            else:
                return None

        # right click
        match = re.match(r"right click \((-?\d+), (-?\d+)\)", action)
        if match:
            x = int(match.group(1))
            y = int(match.group(2))
            if 0 <= x < screen_width and 0 <= y < screen_height:
                return f"pyautogui.rightClick({x}, {y})"
            else:
                return None

        # double click
        match = re.match(r"double click \((-?\d+), (-?\d+)\)", action)
        if match:
            x = int(match.group(1))
            y = int(match.group(2))
            if 0 <= x < screen_width and 0 <= y < screen_height:
                return f"pyautogui.doubleClick({x}, {y})"
            else:
                return None

        # drag
        match = re.match(r"drag from \((-?\d+), (-?\d+)\) to \((-?\d+), (-?\d+)\)", action)
        if match:
            x1 = int(match.group(1))  # start x coordinate
            y1 = int(match.group(2))  # start y coordinate
            x2 = int(match.group(3))  # target x coordinate
            y2 = int(match.group(4))  # target y coordinate
            if 0 <= x1 < screen_width and 0 <= y1 < screen_height and 0 <= x2 < screen_width and 0 <= y2 < screen_height:
                return f"pyautogui.mouseDown({x1}, {y1})\npyautogui.dragTo({x2}, {y2}, duration=0.5)"
            else:
                return None
        
        # scroll
        match = re.match(r"scroll \((-?\d+)\)", action)
        if match:
            y = int(match.group(1))  # vertical scroll distance
            return f"pyautogui.scroll({y})"  # positive: scroll up, negative: scroll down

        # press key
        match = re.match(r"press key: (.+)", action)
        if match:
            key_content = match.group(1).lower()
            # Format error
            if 'key' in key_content:
                return None
            # If key is not in the valid key list
            if key_content not in KEYBOARD_KEYS:
                return None
            return f"pyautogui.press('{key_content}')"

        # hotkey
        match = re.match(r"hotkey \((.+), (.+), (.+)\)", action)
        if match:
            key1 = match.group(1).strip("'").lower()
            key2 = match.group(2).strip("'").lower()
            key3 = match.group(3).strip("'").lower()
            # Format error
            if 'key' in key1 or 'key' in key2 or 'key' in key3:
                return None
            return f"pyautogui.hotkey('{key1}', '{key2}', '{key3}')"
        
        match = re.match(r"hotkey \((.+), (.+)\)", action)
        if match:
            key1 = match.group(1).strip("'").lower()
            key2 = match.group(2).strip("'").lower()
            # Format error
            if 'key' in key1 or 'key' in key2:
                return None
            return f"pyautogui.hotkey('{key1}', '{key2}')"
        
        # type text
        match = re.match(r"type text: (.+)", action)
        if match:
            text_content = match.group(1).strip("'").strip("\"")
            text_content = text_content.replace("\"", "\\\"")
            text_content = text_content.replace("\'", "\\\'")
            # Format error
            if "text_content" in text_content:
                return None
            return f"pyautogui.write(\"{text_content}\")"

        # wait
        if action == "wait":
            return "WAIT"
            
        # finish
        if action == "finish":
            return "DONE"

        # fail
        if action == "fail":
            return "FAIL"
        
        return None
    

def get_history_str(history: list):
    history_cut_off = 10
    if len(history) > history_cut_off:
        history_str = "\n\n".join(f"[{i+1}] {item}" for i, item in enumerate(history[-history_cut_off:]))
    else:
        history_str = "\n\n".join(f"[{i+1}] {item}" for i, item in enumerate(history))
            
    if history_str == '':
        history_str = "None"
    
    return history_str