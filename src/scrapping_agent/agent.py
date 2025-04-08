import os
from urllib.parse import urlparse
from typing import Annotated, Literal

from scrapping_agent.scrapper import Scrapper
from scrapping_agent.scrapper_tools import make_scrapper_tools
from utils.logger import Logger
from utils.utils import get_prompt

from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from typing_extensions import TypedDict
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langchain_core.messages import HumanMessage, ToolMessage

class State(TypedDict):
  messages: Annotated[list, add_messages]

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
    """Initialize the scrapper and set up tools."""
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
    """Close the scrapper."""
    if self.scrapper:
      await self.scrapper.close()

  async def run(self, query: str, all_results: bool = True, recursion_limit: int = 100):
    """
    Run the navigation flow.
    Args:
      query: The query to search for.
      recursion_limit: Maximum number of recursion steps.
    """
    if not self.graph:
      self.graph = self._build_graph()
    
    initial_state = {
      "messages": [
        HumanMessage(
          content=f"Site: {self.url}\nQuery: {query}\nAll: {all_results}"
        )
      ]
    }
    
    config = {"configurable": {"thread_id": "1"}, "recursion_limit": recursion_limit}
    
    result = await self.graph.ainvoke(initial_state, config)

    return result["messages"][-1].content
      

  def _build_graph(self) -> StateGraph:
    """Build and return the state graph for navigation."""
    graph_builder = StateGraph(State)
    
    async def plan_node(state: State):
      plan_prompt = self._get_prompt_template("plan")
      llm_plan = self.llm.model_copy()
      message = await (plan_prompt | llm_plan).ainvoke(state["messages"])
      self.logger.debug(f"\nPLAN 🗺️ -> {message.content}")
      return {"messages": [message]}

    async def act_node(state: State):
      act_prompt = self._get_prompt_template("act")
      llm_act = self.llm.model_copy()
      message = await (act_prompt | llm_act.bind_tools(self.scrapping_tools)).ainvoke(state["messages"])
      self.logger.debug(f"\nACT 🦾 -> '{message.content}' ferramentas: {message.tool_calls}")
      return {"messages": [message]}

    async def response_node(state: State):
      response_prompt = self._get_prompt_template("response")
      llm_response = self.llm.model_copy()
      message = await (response_prompt | llm_response).ainvoke(state["messages"])
      self.logger.debug(f"\nRESPONSE 🔭 -> {message.content}")
      return {"messages": [message]}

    async def tools_node(state: dict):
      result = []
      for tool_call in state["messages"][-1].tool_calls:
        tool = self.tools_by_name[tool_call["name"]]
        observation = await tool.ainvoke(tool_call["args"])
        result.append(ToolMessage(content=observation, tool_call_id=tool_call["id"]))
      self.logger.debug(f"\nTOOLS 🛠️ -> {result}")  
      return {"messages": result}

    graph_builder.add_node("plan", plan_node)
    graph_builder.add_node("act", act_node)
    graph_builder.add_node("response", response_node)
    graph_builder.add_node("tools", tools_node)
    
    def should_end(state: State) -> Literal["act", "response"]:
      """Decides whether to end the navigation or not."""
      last_message = state["messages"][-1]
      result = "act" if "END_NAVIGATION" not in last_message.content else "response"
      self.logger.debug(f"\nSHOULD_END ❓ -> {result}")
      return result
    
    graph_builder.set_entry_point("plan")
    graph_builder.add_conditional_edges("plan", should_end)
    graph_builder.add_edge("act", "tools")
    graph_builder.add_edge("tools", "plan")
    graph_builder.add_edge("response", END)
    
    memory = MemorySaver()
    return graph_builder.compile(checkpointer=memory)
  
  def _get_prompt_template(self, role) -> ChatPromptTemplate:
    """Return the prompt template for the plan role."""
    prompt_path = os.path.join(os.path.dirname(__file__), "prompts", f"{role}.md")
    return ChatPromptTemplate.from_messages([
      ("system", get_prompt(prompt_path)),
      MessagesPlaceholder("messages")
    ])
