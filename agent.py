import asyncio
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from langchain_core.messages import HumanMessage
from mcp import StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.session import ClientSession
from langchain_mcp_adapters.tools import load_mcp_tools

async def run_langgraph_agent():
    print("🧠 Initializing LangGraph Brain...")
    
    llm = ChatOpenAI(
        model="llama3.2", 
        base_url="http://localhost:11434/v1", 
        api_key="ollama", 
        temperature=0
    )

    server_params = StdioServerParameters(
        command="uv",
        args=["run", "--with", "mcp", "mcp", "run", "mcp_server.py"]
    )

    print("🔌 Connecting to SEC MCP Server...")
    
    # 3. Securely bridge the MCP Server to LangGraph
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            
            tools = await load_mcp_tools(session)
            print(f"✅ Loaded {len(tools)} Skills: {[t.name for t in tools]}")
            
            # 4. Build the Cyclical LangGraph Agent
            agent = create_react_agent(llm, tools)
            
            print("\n" + "="*50)
            print("🌟 ENTERPRISE SEC RAG AGENT ONLINE 🌟")
            print("Type 'exit' to quit.")
            print("="*50)
            
            # 5. The Chat Loop
            while True:
                user_input = input("\n👨‍💼 You: ")
                if user_input.lower() in ['exit', 'quit']:
                    break
                    
                messages = [HumanMessage(content=user_input)]
                
                # Stream the agent's thought process so you can see it working
                async for chunk in agent.astream({"messages": messages}):
                    if "agent" in chunk:
                        response = chunk['agent']['messages'][-1].content
                        if response:
                            print(f"\n Agent Synthesis:\n{response}")
                    elif "tools" in chunk:
                        tool_msg = chunk['tools']['messages'][-1]
                        print(f"\n  Tool Executed [{tool_msg.name}] - Reading raw data behind the scenes...")

if __name__ == "__main__":
    # Required to run async MCP clients
    asyncio.run(run_langgraph_agent())