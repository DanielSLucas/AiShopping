import asyncio
import os
import time
from uuid import uuid4
from typing import Annotated, Literal, TypedDict
from enum import StrEnum

from scrapping_agent.scrap import ScrapScriptsManager
from scrapping_agent.scrapper import Scrapper
from scrapping_agent.tools import Tools, make_scrapper_tools
from utils.logger import Logger
from utils.utils import extract_domain, get_prompt

from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage

class State(TypedDict):
  query: str
  all_results: bool
  messages: Annotated[list, add_messages]
  actions_history: list[str]
  tokens: int
  scrap_script: dict
  script_executed: bool

class Nodes(StrEnum):
  SCRIPT_EXECUTOR = "script_executor"
  SCRIPT_EXECUTOR_TOOLS = "script_executor_tools"
  SCRAPPER = "scrapper"
  SCRAPPER_TOOLS = "scrapper_tools"
  SCRIPT_WRITTER = "script_writter"
  SCRIPT_WRITTER_TOOLS = "script_writter_tools"
  RESPONSE = "response"
  END = END

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
    self.current_node = None

  async def initialize(self, url:str, headless: bool = True):
    self.url = url
    
    if not self.logger:
      self.logger = Logger(
        file_name=f"{extract_domain(url)}_scrap",
        show_debug_logs=self.debug
      )
    
    self.scrapping_tools = make_scrapper_tools(
      self.scrapper,
      vision_model=self.vision_model,
      headless=headless
    )

  async def close(self):
    if self.scrapper:
      await self.scrapper.close()

  async def run(self, query: str, all_results: bool = True, recursion_limit: int = 100):
    start_time = time.time()

    # site_data = await self.scrapper.getSiteData()
    scraping_context = {
      "type": "SITE",
      "content": {
        # **site_data,
        "url": self.url,
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

    initial_message = f"Site: {self.url}\nQuery: {query}\nScrap Script:\n{scrap_script}"
      
    initial_state = State(
      query=query,
      all_results=all_results,
      messages=[HumanMessage(initial_message)],
      actions_history=[],
      tokens=0,
      scrap_script=scrap_script,
      script_executed=False
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

    script_executor_tools = [Tools.EXECUTE_SCRAP_SCRIPT]
    script_executor_node = self.__make_default_node(Nodes.SCRIPT_EXECUTOR, tools=script_executor_tools)
    script_executor_tools_node = self.__make_tools_node(Nodes.SCRIPT_EXECUTOR_TOOLS, tools=script_executor_tools)

    scrapper_tools = [Tools.PAGE_SUMMARY, Tools.EXTRACT_ELEMENTS, Tools.INTERACT_WITH_ELEMENT, Tools.NAVIGATE, Tools.GO_BACK, Tools.PRINT_PAGE]
    scrapper_node = self.__make_default_node(Nodes.SCRAPPER, tools=scrapper_tools)
    scrapper_tools_node = self.__make_tools_node(Nodes.SCRAPPER_TOOLS, tools=[])
    
    script_writter_tools = [Tools.SAVE_SCRAP_SCRIPT]
    script_writter_node = self.__make_default_node(Nodes.SCRIPT_WRITTER, tools=script_writter_tools)
    script_writter_tools_node = self.__make_tools_node(Nodes.SCRIPT_WRITTER_TOOLS, tools=script_writter_tools)

    response_node = self.__make_default_node(Nodes.RESPONSE)

    graph_builder.add_node(Nodes.SCRIPT_EXECUTOR, script_executor_node)
    graph_builder.add_node(Nodes.SCRIPT_EXECUTOR_TOOLS, script_executor_tools_node)
    graph_builder.add_node(Nodes.SCRAPPER, scrapper_node)
    graph_builder.add_node(Nodes.SCRAPPER_TOOLS, scrapper_tools_node)
    graph_builder.add_node(Nodes.SCRIPT_WRITTER, script_writter_node)
    graph_builder.add_node(Nodes.SCRIPT_WRITTER_TOOLS, script_writter_tools_node)
    graph_builder.add_node(Nodes.RESPONSE, response_node)


    graph_builder.set_entry_point(Nodes.SCRIPT_EXECUTOR)
    graph_builder.add_conditional_edges(Nodes.SCRIPT_EXECUTOR, self.make_script_executor_conditional_edge()) # [TOOLS, SCRAPPER, RESPONSE]
    graph_builder.add_edge(Nodes.SCRIPT_EXECUTOR_TOOLS, Nodes.SCRIPT_EXECUTOR)
    graph_builder.add_conditional_edges(Nodes.SCRAPPER, self.make_scrapper_conditional_edge()) # [TOOLS, SCRIPT_WRITTER]
    graph_builder.add_edge(Nodes.SCRAPPER_TOOLS, Nodes.SCRAPPER)
    graph_builder.add_conditional_edges(Nodes.SCRIPT_WRITTER, self.make_script_writter_conditional_edge()) # [TOOLS, RESPONSE]
    graph_builder.add_edge(Nodes.SCRIPT_WRITTER_TOOLS, Nodes.SCRIPT_WRITTER)
    graph_builder.add_edge(Nodes.RESPONSE, Nodes.END)

    memory = MemorySaver()
    return graph_builder.compile(checkpointer=memory)

  def __make_default_node(self, name: Nodes, tools: list[Tools] = []):
    async def node(state: State):
      self.current_node = name.upper()
      prompt = self.__get_prompt_template(name)
      tools_impl = [v for k, v in self.scrapping_tools.items() if k in tools]
      llm = self.llm.model_copy()
      llm = llm if len(tools) == 0 else llm.bind_tools(tools_impl)

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

  def __get_prompt_template(self, role) -> ChatPromptTemplate:
    prompt_path = os.path.join(os.path.dirname(__file__), "prompts", f"{role}.md")
    return ChatPromptTemplate.from_messages([
      ("system", get_prompt(prompt_path)),
      MessagesPlaceholder("messages")
    ])
  
  def __make_tools_node(self, name: Nodes, tools: list[Tools]):
    async def tools_node(state: State):
      self.current_node = name.upper()
      tool_msgs = await asyncio.gather(*[
        self.__handle_tool_call(tool_call, state) 
        for tool_call in state["messages"][-1].tool_calls
      ])

      # execute_script_tool_msg = {
      #   msg["tool_name"]:msg 
      #   for msg in tool_msgs 
      #   if msg["tool_name"] == Tools.EXECUTE_SCRAP_SCRIPT
      # }

      # if len(execute_script_tool_msg) > 0:
      #   execute_script_tool_msg = execute_script_tool_msg[0]
      #   script_executed = False if "Error" in execute_script_tool_msg["content"] else True

      # self.logger.debug(f"\nTOOLS 🛠️ -> {tool_msgs}")  
      return {"messages": tool_msgs, "script_executed": state["script_executed"]}
    
    return tools_node
  
  async def __handle_tool_call(self, tool_call, state: State):
    tool_call_id, tool_name, tool_args = tool_call["id"], tool_call["name"], tool_call["args"]
    
    tool = self.scrapping_tools[tool_name]
    result = await tool.ainvoke(tool_args)

    if tool_name == Tools.EXECUTE_SCRAP_SCRIPT:
      state["script_executed"] = False if "Error" in result else True

    return ToolMessage(content=result, tool_call_id=tool_call_id, tool_name=tool_name)
  
  def make_script_executor_conditional_edge(self):
    def conditional_edge(state: State) -> Literal[Nodes.SCRIPT_EXECUTOR_TOOLS, Nodes.SCRAPPER, Nodes.RESPONSE]:
      if self.__has_tool_calls(state["messages"][-1]):
        return Nodes.SCRIPT_EXECUTOR_TOOLS
      if state["script_executed"]:
        return Nodes.RESPONSE

      return Nodes.SCRAPPER
    
    return conditional_edge

  def make_scrapper_conditional_edge(self):
    def conditional_edge(state: State) -> Literal[Nodes.SCRAPPER_TOOLS, Nodes.SCRIPT_WRITTER]:
      return Nodes.SCRAPPER_TOOLS if self.__has_tool_calls(state["messages"][-1]) else Nodes.SCRIPT_WRITTER
    
    return conditional_edge
  
  def make_script_writter_conditional_edge(self):
    def conditional_edge(state: State) -> Literal[Nodes.SCRIPT_WRITTER_TOOLS, Nodes.RESPONSE]:
      return Nodes.SCRIPT_WRITTER_TOOLS if self.__has_tool_calls(state["messages"][-1]) else Nodes.RESPONSE
    
    return conditional_edge

  def __has_tool_calls(self, message):
    return hasattr(message, "tool_calls") and len(message.tool_calls) > 0
