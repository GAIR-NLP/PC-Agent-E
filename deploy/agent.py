# agent.py

import re
import time
from typing import Dict, List
from PIL import Image
from io import BytesIO
from utils import *
from prompt import * 


class PCAgentE:
    def __init__(
        self, client, model, max_steps=30, screenshot_size=(1280, 720), prompt=AGENT_PROMPT
    ):
        self.retry_click_elements = []
        self.history = []
        self.history_cut_off = 10
        self.client = client
        self.model = model
        self.max_steps = max_steps
        self.screenshot_size = screenshot_size
        self.prompt = prompt
        self.steps = 0
        print(f"Using model: {model}")
       
    def predict(self, instruction: str, obs: Dict):
        """
        Predict the next action based on the current observation
        Args:
            instruction: the task description
            obs: the current observation (obs['screenshot'])
        Returns:
            actions: the code of next action
            logs: the logs of next action
        """
        logs = {}
        self.task_description = instruction
        
        # get and process the screenshot
        image_file = BytesIO(obs['screenshot'])
        view_image = Image.open(image_file)

        # call the visual language model for planning
        self.screenshot_size = view_image.size
        try_time = 5
        feedback = ""
        while try_time > 0:
            plan, action = self.get_plan(view_image, self.task_description, feedback)
            action_code = self.get_action_code(action)
            if action_code is None:
                print(f"Invalid action: {action}, Try again.")
                feedback = f"\n\nNote: You have provided an invalid action before: {action}, please try again."
                try_time -= 1
                if try_time == 0:
                    raise ValueError(f"Fail to get valid action after 5 try: {action}")
            else:
                self.add_to_history(f"Plan: {plan}\n\nAction: {action}")
                break

        # check if the steps is greater than the max steps
        self.steps += 1
        if self.steps >= self.max_steps and action_code != "DONE":
            logs['plan_result'] = "Max steps reached"
            actions = ["FAIL"]
        else:
            logs['plan_result'] = f"Plan: {plan}\n\nAction: {action}"
            actions = [action_code]

        return actions, logs

    def reset(self):
        """Reset the agent state"""
        self.history.clear()
        pass

    def get_plan(self, screenshot, task_description, feedback=""):
        """
        get the next plan
        Args:
            screenshot: the screenshot
            task_description: task description
            retry_click_elements: the list of elements that failed to click before
        Returns:
            plan_str: plan description
            action_str: specific action
        """
        base64_image = encode_image(screenshot)
        try_time = 5
        while try_time > 0:
            try:
                instruction = self.get_plan_instruction(task_description, feedback)
                messages = get_mllm_messages(instruction, base64_image)
                
                completion = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    max_tokens=512,
                    temperature=0.8
                )
                output_text = completion.choices[0].message.content
                print(f"Output from agent: {output_text}")

                if not "Action" in output_text:
                    feedback = f"\n\nNote: You should provide an action after 'Action:' in the response."
                
                return self.split_output(output_text)
            
            except Exception as e:
                print(f"Failed to get the plan: {e}, try again.")
                time.sleep(1)
                if try_time == 1:
                    raise f"Failed to get the plan: {e}"

            try_time -= 1   

    def add_to_history(self, output):
        """
        add the output to the history
        """
        self.history.append(output)

    def get_action_history(self):
        if len(self.history) > self.history_cut_off:
            history_str = "\n\n".join(f"[{i+1}] {item}" for i, item in enumerate(self.history[-self.history_cut_off:]))
        else:
            history_str = "\n\n".join(f"[{i+1}] {item}" for i, item in enumerate(self.history))
                
        if history_str == '':
            history_str = "None"
    
        return history_str
    
    def get_plan_instruction(self, task_description, feedback=""):
        """
        generate the planning instruction
        """
        prompt = self.prompt + f"Your task is: {task_description}\n\n"
        history_str = self.get_action_history()
        prompt += f"History of the previous actions and thoughts you have done to reach the current screen: {history_str}\n\n"
        prompt += "--------------------------------------------\n\n"
        prompt += f"Given the screenshot. What's the next step that you will do to help with the task?"
        prompt += feedback
        return prompt
    
    def split_output(self, output):
        """
        split the output into plan and action
        """
        plan_str = output.split("Action:")[0].strip().strip('{}')
        action_str = output.split("Action:")[1].strip().strip('{}')
        return plan_str, action_str
    
    def get_action_code(self, action) -> str:
        screen_width, screen_height = self.screenshot_size
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
            # if key is not in the valid keyboard keys list
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
