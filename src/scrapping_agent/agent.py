import os
from uuid import uuid4
from typing import Annotated, TypedDict

from scrapping_agent.scrap import ScrapScriptsManager
from scrapping_agent.scrapper import Scrapper
from scrapping_agent.tools import make_scrapper_tools
from utils.logger import Logger
from utils.utils import extract_domain, get_prompt

from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
import time

class State(TypedDict):
  query: str
  all_results: bool
  messages: Annotated[list, add_messages]
  actions_history: list[str]
  tokens: int

class ScrappingAgent:
  def __init__(
    self,
    llm: BaseChatModel,
    debug: bool = True,
    vision_model = ChatOpenAI(model="gpt-4o"),
    logger: Logger = None
  ):
    self.debug = debug
    self.logger = logger

    self.scrapper = Scrapper()
    self.llm = llm
    self.vision_model = vision_model

    self.graph = None
    self.scrapping_tools = None
    self.tools_by_name = None
    self.current_node = None

  async def initialize(self, url:str, headless: bool = True):
    self.url = url
    
    if not self.logger:
      self.logger = Logger(
        file_name=f"{extract_domain(url)}_scrap",
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
    start_time = time.time()

    site_data = await self.scrapper.getSiteData()
    scraping_context = {
      "type": "SITE",
      "content": {
        **site_data,
        "id": str(uuid4()),
        "start_time": start_time,
        "end_time": None
      }
    }
    self.logger.info(scraping_context)

    if not self.graph:
      self.graph = self._build_graph()

    ssm = ScrapScriptsManager()

    scrap_script_exists = ssm.exists(extract_domain(self.url))
    scrap_script = ssm.get(extract_domain(self.url)) if scrap_script_exists else "None"

    initial_message = f"Site: {self.url}\n" \
      + f"Query: {query}\n"\
      + f"All: {all_results}\n"\
      + f"SCRIPT: {scrap_script}\n\n"\
      + f"IMPORTANTE: Se o campo SCRIPT acima não for 'None', sua PRIMEIRA e ÚNICA ação deve ser usar a ferramenta 'execute_scrap_script' adaptando a Query para os inputs do script."

    initial_state = State(
      query=query,
      all_results=all_results,
      messages=[HumanMessage(initial_message)],
      actions_history=[],
      tokens=0
    )

    config = {"configurable": {"thread_id": "1"}, "recursion_limit": recursion_limit}

    self.logger.debug(initial_message)

    result = await self.graph.ainvoke(initial_state, config)

    ai_messages = [msg for msg in result["messages"] if isinstance(msg, AIMessage)]
    total_tokens = sum(msg.usage_metadata.get("total_tokens", 0) for msg in ai_messages)
    self.logger.debug(f"Total tokens: {total_tokens}")

    scraping_context["content"]["end_time"] = time.time()
    self.logger.info(scraping_context)

    return { "type": "RESPONSE", "content": result["messages"][-1].content }


  def _build_graph(self) -> StateGraph:
    graph_builder = StateGraph(State)

    navigator_node = self.make_default_node("navigator", tools=self.scrapping_tools)
    tools_node = ToolNode(self.scrapping_tools)

    graph_builder.add_node("navigator", navigator_node)
    graph_builder.add_node("tools", tools_node)

    graph_builder.set_entry_point("navigator")
    graph_builder.add_conditional_edges("navigator", tools_condition)
    graph_builder.add_edge("tools", "navigator")

    memory = MemorySaver()
    return graph_builder.compile(checkpointer=memory)

  def make_default_node(self, name: str, tools: list = []):
    async def node(state: State):
      self.current_node = name.upper()
      prompt = self._get_prompt_template(name)
      llm = self.llm.model_copy()
      llm = llm if len(tools) == 0 else llm.bind_tools(tools)

      message = await (prompt | llm).ainvoke(state)
      tool_calls = [
        f"{tc['name']}(" + ", ".join(f"{k}={v!r}" for k, v in tc['args'].items()) + ")"
        for tc in message.tool_calls
      ]

      state["actions_history"].extend(tool_calls)
      state["tokens"] += message.usage_metadata.get('total_tokens', 0)

      self.logger.debug(f"\n{name.upper()} 🤖")
      self.logger.debug(f"message: {message.content}")
      self.logger.debug(f"tool_calls: {tool_calls}")
      self.logger.debug(f"tokens: {message.usage_metadata['total_tokens']}")

      return {"messages": [message], "actions_history": state["actions_history"], "tokens": state["tokens"]}

    return node

  def _get_prompt_template(self, role) -> ChatPromptTemplate:
    prompt_path = os.path.join(os.path.dirname(__file__), "prompts", f"{role}.md")
    return ChatPromptTemplate.from_messages([
      ("system", get_prompt(prompt_path)),
      MessagesPlaceholder("messages")
    ])