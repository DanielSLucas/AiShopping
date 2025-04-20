import os
from urllib.parse import urlparse
from typing import Literal

from scrapping_agent.scrapper import Scrapper
from scrapping_agent.scrapper_tools import make_scrapper_tools
from utils.logger import Logger
from utils.utils import get_prompt

from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import StateGraph, END
from langgraph.graph.message import MessagesState
from langchain_core.messages import HumanMessage, ToolMessage

class ScrappingAgent:
  def __init__(
    self,
    llm: BaseChatModel,
    debug: bool = True,
    vision_model = ChatOpenAI(model="gpt-4o")
  ):
    self.debug = debug
    
    self.scrapper = Scrapper()
    self.llm = llm
    self.vision_model = vision_model
    
    self.graph = None
    self.scrapping_tools = None
    self.tools_by_name = None

  async def initialize(self, url:str, headless: bool = True):
    self.url = url
    self.logger = Logger(
      file_name=f"{urlparse(url).netloc}_scrap", 
      show_debug_logs=self.debug
    )

    await self.scrapper.initialize(url, headless=headless)

    self.scrapping_tools = make_scrapper_tools(
      self.scrapper,
      vision_model=self.vision_model
    )
    self.tools_by_name = {tool.name: tool for tool in self.scrapping_tools}
  
  async def close(self):
    if self.scrapper:
      await self.scrapper.close()

  async def run(self, query: str, all_results: bool = True, recursion_limit: int = 100):
    if not self.graph:
      self.graph = self._build_graph()
    
    initial_state = MessagesState(
      messages=[HumanMessage(f"Site: {self.url}\nQuery: {query}\nAll: {all_results}")]
    )
    
    config = {"configurable": {"thread_id": "1"}, "recursion_limit": recursion_limit}
    
    self.logger.debug(f"Site: {self.url}\nQuery: {query}\nAll: {all_results}")

    result = await self.graph.ainvoke(initial_state, config)

    return result["messages"][-1].content
      

  def _build_graph(self) -> StateGraph:
    graph_builder = StateGraph(MessagesState)
    
    plan_node = self.make_default_node("plan")
    act_node = self.make_default_node("act", tools=self.scrapping_tools)
    response_node = self.make_default_node("response")
    tools_node = self.make_tools_node()

    graph_builder.add_node("plan", plan_node)
    graph_builder.add_node("act", act_node)
    graph_builder.add_node("response", response_node)
    graph_builder.add_node("tools", tools_node)
    
    should_end_condition = self.make_should_end_condition()
    
    graph_builder.set_entry_point("plan")
    graph_builder.add_conditional_edges("plan", should_end_condition)
    graph_builder.add_edge("act", "tools")
    graph_builder.add_edge("tools", "plan")
    graph_builder.add_edge("response", END)
    
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
    prompt_path = os.path.join(os.path.dirname(__file__), "prompts", f"{role}.md")
    return ChatPromptTemplate.from_messages([
      ("system", get_prompt(prompt_path)),
      MessagesPlaceholder("messages")
    ])
  
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
  
  def make_should_end_condition(self):
    def should_end_condition(state: MessagesState) -> Literal["act", "response"]:
      """Decides whether to end the navigation or not."""
      last_message = state["messages"][-1]
      result = "act" if "END_NAVIGATION" not in last_message.content else "response"
      self.logger.debug(f"\nSHOULD_END_CONDITION ❓ -> {result}")
      return result
    
    return should_end_condition
