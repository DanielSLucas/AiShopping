import os
from urllib.parse import urlparse
from typing import Annotated, Literal, TypedDict

from scrapping_agent.scrap import ScrapScriptsManager
from scrapping_agent.scrapper import Scrapper
from scrapping_agent.tools import make_scrapper_tools
from utils.logger import Logger
from utils.utils import get_prompt

from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langchain_core.messages import HumanMessage, ToolMessage

class State(TypedDict):
  messages: Annotated[list, add_messages]
  should_end: bool

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
    self.current_node = None

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

    ssm = ScrapScriptsManager()

    scrap_script_exists = ssm.exists(urlparse(self.url).netloc)
    scrap_script = ssm.get(urlparse(self.url).netloc) if scrap_script_exists else "None"

    initial_message = f"Site: {self.url}\n" \
      + f"Query: {query}\n"\
      + f"All: {all_results}\n"\
      + f"Script: {scrap_script}"

    initial_state = State(
      messages=[HumanMessage(initial_message)],
      should_end=False
    )

    config = {"configurable": {"thread_id": "1"}, "recursion_limit": recursion_limit}

    self.logger.debug(initial_message)

    result = await self.graph.ainvoke(initial_state, config)

    return result["messages"][-1].content


  def _build_graph(self) -> StateGraph:
    graph_builder = StateGraph(State)

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
    async def node(state: State):
      self.current_node = name.upper()
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
    async def tools_node(state: State):
      self.current_node = "TOOLS"
      tool_msgs = [
        await self.handle_tool_call(tool_call, state)
        for tool_call in state["messages"][-1].tool_calls
      ]
      self.logger.debug(f"\nTOOLS 🛠️ -> {tool_msgs}")
      return {"messages": tool_msgs, "should_end": state["should_end"]}

    return tools_node

  async def handle_tool_call(self, tool_call, state: State):
    tool_call_id, tool_name, tool_args = tool_call["id"], tool_call["name"], tool_call["args"]

    tool = self.tools_by_name[tool_name]
    result = await tool.ainvoke(tool_args)

    if tool_name == "end_navigation":
      state["should_end"] = True

    return ToolMessage(content=result, tool_call_id=tool_call_id)

  def make_should_end_condition(self):
    def should_end_condition(state: State) -> Literal["act", "response"]:
      """Decides whether to end the navigation or not."""
      self.logger.debug(f"\nSHOULD_END_STATE ❓ -> {state['should_end']}")
      result = "response" if state["should_end"] else "act"
      self.logger.debug(f"\nSHOULD_END_CONDITION ❓ -> {result}")
      return result

    return should_end_condition
