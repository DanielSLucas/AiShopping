import asyncio
import os
import time
from uuid import uuid4
from typing import Annotated, Literal, TypedDict, List
from enum import StrEnum

from scrapping_agent.scrap import ScrapScriptsManager
from scrapping_agent.scrapper import Scrapper
from scrapping_agent.tools import make_scrapper_tools
from utils.logger import Logger
from utils.utils import extract_domain, get_prompt

from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import StateGraph, END, START
from langgraph.graph.message import add_messages
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage, BaseMessage
from langgraph.types import Command
from langgraph.prebuilt import ToolNode
from langchain_core.tools import BaseTool

class State(TypedDict):
  query: str
  all_results: bool
  messages: Annotated[List[BaseMessage], add_messages]
  actions_history: List[str]
  tokens: int
  input_tokens: int
  output_tokens: int
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

class Tools(StrEnum):
  EXTRACT_ELEMENTS = "extract_elements"
  INTERACT_WITH_ELEMENT = "interact_with_element"
  PAGE_SUMMARY = "page_summary"
  GET_URL = "get_url"
  GO_BACK = "go_back"
  NAVIGATE = "navigate"
  PRINT_PAGE = "print_page"  
  EXECUTE_SCRAP_SCRIPT = "execute_scrap_script"
  GET_SCRAP_SCRIPT = "get_scrap_script"
  SAVE_SCRAP_SCRIPT = "save_scrap_script"


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

    scraping_context = {
      "type": "SITE",
      "content": {
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
      input_tokens=0,
      output_tokens=0,
      scrap_script=scrap_script,
      script_executed=False
    )

    config = {"configurable": {"thread_id": "1"}, "recursion_limit": recursion_limit}

    self.logger.debug(initial_message)

    result = await self.graph.ainvoke(initial_state, config)

    self.logger.debug(f"Input tokens: {result.get('input_tokens', 0)}")
    self.logger.debug(f"Output tokens: {result.get('output_tokens', 0)}")
    self.logger.info(f"Total tokens: {result.get('tokens', 0)}")

    scraping_context["content"]["end_time"] = time.time()
    self.logger.info(scraping_context)

    response = { "type": "RESPONSE", "content": result["messages"][-1].content }
    self.logger.info(response)

    return response


  def _build_graph(self) -> StateGraph:
    graph_builder = StateGraph(State)

    executor_tools = [t for t in self.scrapping_tools.values() if t.get_name() in [Tools.EXECUTE_SCRAP_SCRIPT, Tools.GET_SCRAP_SCRIPT]]
    writter_tools = [self.scrapping_tools[Tools.SAVE_SCRAP_SCRIPT]]
    scrapper_tools = [t for t in self.scrapping_tools.values() if t.get_name() not in executor_tools + writter_tools]

    graph_builder.add_node(Nodes.SCRIPT_EXECUTOR, self._make_script_executor_node(executor_tools))
    graph_builder.add_node(Nodes.SCRIPT_EXECUTOR_TOOLS, ToolNode(executor_tools))
    graph_builder.add_node(Nodes.SCRAPPER, self._make_scrapper_node(scrapper_tools))
    graph_builder.add_node(Nodes.SCRAPPER_TOOLS, ToolNode(scrapper_tools))
    graph_builder.add_node(Nodes.SCRIPT_WRITTER, self._make_script_writter_node(writter_tools))
    graph_builder.add_node(Nodes.SCRIPT_WRITTER_TOOLS, ToolNode(writter_tools))
    graph_builder.add_node(Nodes.RESPONSE, self._response_node)

    graph_builder.add_edge(START, Nodes.SCRIPT_EXECUTOR)
    graph_builder.add_edge(Nodes.SCRIPT_EXECUTOR_TOOLS, Nodes.SCRIPT_EXECUTOR)
    graph_builder.add_edge(Nodes.SCRAPPER_TOOLS, Nodes.SCRAPPER)
    graph_builder.add_edge(Nodes.SCRIPT_WRITTER_TOOLS, Nodes.SCRIPT_WRITTER)
    graph_builder.add_edge(Nodes.RESPONSE, END)

    return graph_builder.compile(checkpointer=MemorySaver())

  def _save_tokens(self, state: State, response: AIMessage) -> dict:
    usage = response.usage_metadata
    input_tokens = usage.get("input_tokens", 0)
    output_tokens = usage.get("output_tokens", 0)
    total_tokens = usage.get("total_tokens", 0)
    
    return {
      "tokens": state["tokens"] + total_tokens,
      "input_tokens": state["input_tokens"] + input_tokens,
      "output_tokens": state["output_tokens"] + output_tokens
    }

  def _trim_history(self, messages: List[BaseMessage]) -> List[BaseMessage]:
    """
    Trims tool responses that are too large or from old get_dom_tree calls to save tokens.
    """
    trimmed = []
    # Identify ToolMessages that are long and might be from get_dom_tree
    # We keep the most recent ones but can truncate older long ones
    for i, msg in enumerate(messages):
      if isinstance(msg, ToolMessage) and len(str(msg.content)) > 2000:
        # Check if it's the last tool message of this type, if so keep it, else truncate
        is_last_of_type = True
        for next_msg in messages[i+1:]:
           if isinstance(next_msg, ToolMessage) and next_msg.name == msg.name:
              is_last_of_type = False
              break
        
        if not is_last_of_type:
           # Truncate older results
           trimmed.append(ToolMessage(
              content=str(msg.content)[:500] + "... [TRUNCATED TO SAVE TOKENS]",
              tool_call_id=msg.tool_call_id,
              name=msg.name
           ))
           continue
      
      trimmed.append(msg)
    return trimmed

  def _make_script_executor_node(self, tools: List[BaseTool] = []) -> Command:
    async def executor_node(state: State) -> Command:
      self.logger.debug(f"{Nodes.SCRIPT_EXECUTOR.upper()} 🤖")
      prompt = self.__get_prompt_template(Nodes.SCRIPT_EXECUTOR)
      model = self.llm.bind_tools(tools)
      
      script_executed = state.get("script_executed", False)
      last_message = state["messages"][-1]
      if isinstance(last_message, ToolMessage) and last_message.name == Tools.EXECUTE_SCRAP_SCRIPT:
        script_executed = False if "Error" in last_message.content else True
        self.logger.debug(f"Script executed with success: {script_executed}")

      # Trim history before calling LLM
      trimmed_state = state.copy()
      trimmed_state["messages"] = self._trim_history(state["messages"])

      response = await (prompt | model).ainvoke(trimmed_state)
      token_updates = self._save_tokens(state, response)
      
      if response.tool_calls:
        self.logger.debug("Executing script")
        return Command(update={"messages": [response], **token_updates}, goto=Nodes.SCRIPT_EXECUTOR_TOOLS)
      
      self.logger.debug(f"Script executed: {script_executed}")
      target = Nodes.RESPONSE if script_executed else Nodes.SCRAPPER
      self.logger.debug(f"Moving to: {target}")
      return Command(update={"messages": [response], "script_executed": script_executed, **token_updates}, goto=target)
    return executor_node
  

  def _make_scrapper_node(self, tools: List[BaseTool] = []) -> Command:
    async def scrapper_node(state: State) -> Command:
      prompt = self.__get_prompt_template(Nodes.SCRAPPER)
      model = self.llm.bind_tools(tools)
      
      last_message = state["messages"][-1]
      if isinstance(last_message, ToolMessage):
        self.logger.debug(f"Tool message: {last_message}")
      
      # Trim history before calling LLM
      trimmed_state = state.copy()
      trimmed_state["messages"] = self._trim_history(state["messages"])

      response = await (prompt | model).ainvoke(trimmed_state)
      token_updates = self._save_tokens(state, response)

      self.logger.debug(f"{Nodes.SCRAPPER.upper()} 🤖")
      self.logger.debug(f"message: {response.content}")
      self.logger.debug(f"tokens: {response.usage_metadata}")

      if response.tool_calls:  
        tool_calls = self._get_formatted_tool_calls(response)
        self.logger.debug(f"tool_calls: {tool_calls}")
        return Command(
          update={"messages": [response], "actions_history": state["actions_history"] + tool_calls, **token_updates}, 
          goto=Nodes.SCRAPPER_TOOLS
        )
      
      return Command(update={"messages": [response], **token_updates}, goto=Nodes.SCRIPT_WRITTER)
    return scrapper_node
  
  def _get_formatted_tool_calls(self, msg: BaseMessage):
    return [
      f"{tc['name']}(" + ", ".join(f"{k}={v!r}" for k, v in tc['args'].items()) + ")"
      for tc in msg.tool_calls
    ]

  def _make_script_writter_node(self, tools: List[BaseTool] = []) -> Command:
    async def script_writter_node(state: State) -> Command:
      self.logger.debug(f"{Nodes.SCRIPT_WRITTER.upper()} 🤖")
      prompt = self.__get_prompt_template(Nodes.SCRIPT_WRITTER)
      model = self.llm.bind_tools(tools)
      
      # Trim history before calling LLM
      trimmed_state = state.copy()
      trimmed_state["messages"] = self._trim_history(state["messages"])

      response = await (prompt | model).ainvoke(trimmed_state)
      token_updates = self._save_tokens(state, response)

      if response.tool_calls:
        self.logger.debug("Saving scrap script")
        return Command(update={"messages": [response], **token_updates}, goto=Nodes.SCRIPT_WRITTER_TOOLS)
      
      self.logger.debug("Moving to: RESPONSE")
      return Command(update={"messages": [response], **token_updates}, goto=Nodes.RESPONSE)
    return script_writter_node

  async def _response_node(self, state: State):
    self.logger.debug(f"{Nodes.RESPONSE.upper()} 🤖")
    prompt = self.__get_prompt_template(Nodes.RESPONSE)
    response = await (prompt | self.llm).ainvoke(state)
    token_updates = self._save_tokens(state, response)
    return {"messages": [response], **token_updates }

  def __get_prompt_template(self, role) -> ChatPromptTemplate:
    prompt_path = os.path.join(os.path.dirname(__file__), "prompts", f"{role}.md")
    return ChatPromptTemplate.from_messages([
      ("system", get_prompt(prompt_path)),
      MessagesPlaceholder("messages")
    ])

