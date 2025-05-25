# env.py

import time
import pyautogui
from io import BytesIO
from PIL import ImageGrab

class PCEnv:
    """
    PC Environment class, encapsulates the local computer environment,
    supports executing pyautogui code and capturing screenshots
    """
    def __init__(self, screenshot_size=(1280, 720)):
        """
        Initialize the environment
        Args:
            screenshot_size: Screenshot dimensions
        """
        self.screenshot_size = screenshot_size
        # Ensure pyautogui has failsafe measures
        pyautogui.FAILSAFE = True
        print("Initializing PC Environment...")
        
    def step(self, action):
        """
        Execute an action and return new observation
        Args:
            action: Action to execute (pyautogui code string)
        Returns:
            obs: Observation containing new screenshot
            done: Whether the task is completed
        """
        done = False
        
        # Handle special actions
        if action == "WAIT":
            time.sleep(3)
        elif action == "DONE":
            print("Task completed, terminating execution")
            done = True
            return {"screenshot": self.get_screenshot()}, done
        elif action == "FAIL":
            print("Task failed, terminating execution")
            done = True
            return {"screenshot": self.get_screenshot()}, done
        else:
            # Execute pyautogui code
            try:
                # Since we've imported pyautogui at the module level,
                # exec can directly execute strings like "pyautogui.click(1, 1)"
                # The pyautogui module is available in the exec's namespace
                exec(action)
                # Wait briefly to let UI respond
                time.sleep(1)
            except Exception as e:
                print(f"Action execution failed: {e}")
        
        # Return new observation (screenshot)
        return {"screenshot": self.get_screenshot()}, done
    
    def get_screenshot(self):
        """
        Capture current screen screenshot
        Returns:
            screenshot: Binary data of the screenshot
        """
        # Take screenshot
        screenshot = ImageGrab.grab()
        
        # Warning if size is not as expected
        if screenshot.size != self.screenshot_size:
            print(f"Warning: Screenshot size is not as expected. Expected {self.screenshot_size}, got {screenshot.size}")
            
        # Convert to binary
        buffer = BytesIO()
        screenshot.save(buffer, format='PNG')
        return buffer.getvalue()
    
    def reset(self):
        """
        Reset the environment
        Returns:
            obs: Observation containing new screenshot
        """
        # Reset only needs to return current screenshot as initial observation
        return {"screenshot": self.get_screenshot()} 