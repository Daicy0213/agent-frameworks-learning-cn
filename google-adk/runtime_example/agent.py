from google.adk.agents import Agent
from .verify import DemoModel

root_agent = Agent(name="answer", model=DemoModel())
