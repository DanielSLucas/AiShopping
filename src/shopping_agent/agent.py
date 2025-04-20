import os
from typing import Literal

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, ToolMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import MessagesState
from langgraph.prebuilt import tools_condition
from langgraph.types import interrupt, Command

from shopping_agent.tools import make_receptionist_tools, make_shopping_tools
from utils.logger import Logger
from utils.utils import get_prompt

class ShoppingAgent:
  def __init__(
    self,
    llm: BaseChatModel,
    debug: bool = True,
  ):
    self.debug = debug
    
    self.llm = llm
    
    self.graph = None
    self.graph_config = None
    self.logger = Logger(show_debug_logs=debug)

    self.shopping_tools = make_shopping_tools(self.logger)
    self.receptionist_tools = make_receptionist_tools(self.logger)
    self.tools_by_name = {tool.name: tool for tool in self.shopping_tools + self.receptionist_tools}

  async def run(self, run_input, recursion_limit: int = 100):
    if not self.graph:
      self.graph = self._build_graph()
    
    state = MessagesState(messages=[HumanMessage(content=run_input)]) if isinstance(run_input, str) else run_input
    
    if not self.graph_config:
      self.graph_config = {"configurable": {"thread_id": "1"}, "recursion_limit": recursion_limit}
    
    events = self.graph.astream(
      state ,
      self.graph_config,
      stream_mode="values"
    )

    last_message = ""
    async for event in events:
      if "messages" in event:
        last_message = event["messages"][-1]

    self.logger.debug(last_message.content)
    
    if hasattr(last_message, "tool_calls") \
      and last_message.tool_calls\
      and last_message.tool_calls[0]["name"] == "ask_more_details":
      question = last_message.tool_calls[0]["args"]["question"]
      return f"ASK_HUMAN:{question}"
    
    return last_message.content

  async def continue_from_input(self, user_input: str):
    command = Command(resume=user_input)
    await self.run(command)

  def _build_graph(self) -> StateGraph:
    """Build and return the state graph for navigation."""
    graph_builder = StateGraph(MessagesState)
    
    receptionist_node = self.make_default_node("receptionist", tools=self.receptionist_tools)
    ask_human_node = self.make_ask_human_node()
    researcher_node = self.make_default_node("researcher", tools=self.shopping_tools)
    tools_node = self.make_tools_node()
    analyst_node = self.make_default_node("analyst")
    product_reviewer_node = self.make_default_node("product_reviewer")

    graph_builder.add_node("receptionist", receptionist_node)
    graph_builder.add_node("ask_human", ask_human_node)
    graph_builder.add_node("researcher", researcher_node)
    graph_builder.add_node("tools", tools_node)
    graph_builder.add_node("analyst", analyst_node)
    graph_builder.add_node("product_reviewer", product_reviewer_node)
    
    ask_human_condition = self.make_ask_human_condition()

    graph_builder.add_edge(START, "receptionist")
    graph_builder.add_conditional_edges("receptionist", ask_human_condition)
    graph_builder.add_edge("ask_human", "researcher")
    graph_builder.add_conditional_edges("researcher", tools_condition)
    graph_builder.add_edge("tools", "analyst")
    graph_builder.add_edge("analyst",  "product_reviewer")
    graph_builder.add_edge("product_reviewer", END)
    
    memory = MemorySaver()
    return graph_builder.compile(checkpointer=memory)

  def make_default_node(self, name: str, tools: list = []):
    async def node(state: MessagesState):
      prompt = self._get_prompt_template(name)
      llm = self.llm.model_copy()
      llm = llm if len(tools) == 0 else llm.bind_tools(tools)
      message = await (prompt | llm).ainvoke(state["messages"])
      self.logger.debug(f"\n{name.upper()} 🤖 -> {message.content}")
      return {"messages": [message]}
    
    return node
  
  def _get_prompt_template(self, role) -> ChatPromptTemplate:
    """Return the prompt template for the receptionist role."""
    prompt_path = os.path.join(os.path.dirname(__file__), "prompts", f"{role}.md")
    return ChatPromptTemplate.from_messages([
      ("system", get_prompt(prompt_path)),
      MessagesPlaceholder("messages")
    ])
  
  def make_ask_human_node(self):
    async def ask_human_node(state):
      self.logger.debug("ASK_HUMAN")
      tool_call = state["messages"][-1].tool_calls[0]
      
      tool_call_id = tool_call["id"]
      question = tool_call["args"]["question"]
      self.logger.debug(f"question {question}")

      human_response = interrupt(question)
      tool_message = {"tool_call_id": tool_call_id, "type": "tool", "content": human_response}
      self.logger.debug(f"tool_message {tool_message}")

      return {"messages": [tool_message]}
    
    return ask_human_node
  
  def make_tools_node(self):
    async def tools_node(state: dict):
      result = []
      for tool_call in state["messages"][-1].tool_calls:
        tool = self.tools_by_name[tool_call["name"]]
        observation = await tool.ainvoke(tool_call["args"])
        result.append(ToolMessage(content=observation, tool_call_id=tool_call["id"]))
      self.logger.debug(f"\nTOOLS 🛠️ -> {result}")  
      return {"messages": result}
    
    return tools_node

  def make_ask_human_condition(self):
    def ask_human_condition(state: MessagesState) -> Literal["ask_human", "researcher"]:
      """Determine whether more details are needed based on the last message."""
      self.logger.debug("ASK_HUMAN_CONDITION")
      last_message = state["messages"][-1]
      return "ask_human" if last_message.tool_calls else "researcher"
    
    return ask_human_condition

