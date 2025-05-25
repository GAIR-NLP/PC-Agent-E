# main.py

from openai import OpenAI
from agent import PCAgentE
from env import PCEnv

client = OpenAI(
    api_key="EMPTY",
    base_url="http://localhost:8030/v1",
)
model = "henryhe0123/PC-Agent-E"


def run(task_description, max_steps=30):
    # Initialize agent and environment
    agent = PCAgentE(client, model, max_steps)
    env = PCEnv()
    
    # Reset environment to get initial observation
    obs = env.reset()
    
    # Run interaction loop
    while True:
        # Agent predicts next action based on current observation
        actions, logs = agent.predict(task_description, obs)
        if not actions:
            print("Agent failed to generate valid actions, terminating execution")
            return
            
        # Execute each action
        for action in actions:
            print(f"Executing action: {action}")
            obs, done = env.step(action)
            if done:
                return


if __name__ == "__main__":
    task_description = input("Please enter task description: ")
    run(task_description)
