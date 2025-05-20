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
    agent = PCAgentE(client, model)
    env = PCEnv()
    
    # Reset environment to get initial observation
    obs = env.reset()
    
    # Run interaction loop
    steps = 0
    done = False
    
    while not done and steps < max_steps:
        print(f"\nStep {steps+1}/{max_steps}")
        
        # Agent predicts next action based on current observation
        actions, logs = agent.predict(task_description, obs)
        if not actions:
            print("Agent failed to generate valid actions, terminating execution")
            break
            
        # Execute each action
        for action in actions:
            print(f"Executing action: {action}")
            obs, done = env.step(action)
            if done:
                break
                
        steps += 1
    
    if steps >= max_steps:
        print(f"Reached maximum steps {max_steps}, terminating execution")
    else:
        print(f"Task execution finished in {steps} steps")


if __name__ == "__main__":
    task_description = input("Please enter task description: ")
    run(task_description)
