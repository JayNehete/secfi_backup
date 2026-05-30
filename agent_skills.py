import os
import glob
import asyncio
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_mcp_adapters.tools import load_mcp_tools
from langgraph.prebuilt import create_react_agent
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# ==========================================
# 1. DYNAMIC SKILL LOADER
# ==========================================
def load_agent_skills(skills_dir="skills"):
    """
    Reads all markdown files from the skills directory and compiles them
    into a structured system instruction block for the agent.
    """
    compiled_skills = []
    
    if not os.path.exists(skills_dir):
        print(f"⚠️ Warning: '{skills_dir}' directory not found. Proceeding without custom skills.")
        return ""
        
    search_path = os.path.join(skills_dir, "*.md")
    for filepath in glob.glob(search_path):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
                filename = os.path.basename(filepath)
                compiled_skills.append(f"--- START SKILL: {filename} ---\n{content}\n--- END SKILL: {filename} ---")
        except Exception as e:
            print(f"⚠️ Failed to load skill file {filepath}: {e}")
            
    if compiled_skills:
        print(f"🧠 Successfully loaded {len(compiled_skills)} custom agent skills!")
        return "\n\n### AVAILABLE AGENT SKILLS & ROUTING RULES\n" + "\n\n".join(compiled_skills)
    
    return ""

# ==========================================
# 2. RUNNABLE LANGGRAPH AGENT ENGINE
# ==========================================
async def run_langgraph_agent():
    # Define connection parameters to existing local MCP server
    server_params = StdioServerParameters(
        command="python",
        args=["mcp_server.py"]
    )
    
    print("🚀 Connecting to MCP Server and initializing pipeline...")
    
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            # Initialize the session and discover tools automatically
            await session.initialize()
            mcp_tools = await load_mcp_tools(session)
            
            # Load the Markdown skills
            skills_context = load_agent_skills("skills")
            
            # Construct a rigorous system instruction prompt
            base_system_prompt = (
                "You are an advanced Multi-Engine SEC Financial Intelligence Agent.\n"
                "You have access to specialized local tools and structural operational instructions called 'Skills'.\n\n"
                "CRITICAL OPERATIONAL RULES:\n"
                "1. Before executing any tool call, evaluate the user's intent against the AVAILABLE AGENT SKILLS listed below.\n"
                "2. Adopt the specific Persona, Constraints, and Tool Routing specified by the matching skill.\n"
                "3. If a request spans multiple skills, execute them sequentially to build a complete response.\n"
                "4. Stick to the absolute boundaries of each skill to avoid hallucination."
            )
            
            full_system_instruction = f"{base_system_prompt}\n{skills_context}"
            
            from langchain_openai import ChatOpenAI
            llm = ChatOpenAI(
                model="llama3.2", 
                base_url="http://localhost:11434/v1", 
                api_key="ollama", 
                temperature=0
            ) 
            
            # Create the managed ReAct agent graph with integrated tools and system instructions
            agent = create_react_agent(
                model=llm,
                tools=mcp_tools,
                state_modifier=full_system_instruction
            )
            
            print("\n🤖 SEC Intelligence Agent Online with Custom Skills.")
            print("Type 'exit' or 'quit' to stop.\n")
            
            while True:
                user_input = input("👨‍💼 You: ")
                if user_input.strip().lower() in ["exit", "quit"]:
                    break
                    
                if not user_input.strip():
                    continue
                    
                messages = [HumanMessage(content=user_input)]
                
                try:
                    async for chunk in agent.astream({"messages": messages}):
                        if "agent" in chunk:
                            message = chunk["agent"]["messages"][-1]
                            if message.content:
                                print(f"\n🤖 Agent Synthesis:\n{message.content}\n")
                        elif "tools" in chunk:
                            message = chunk["tools"]["messages"][-1]
                            print(f"\n⚙️ Tool Executed [{message.name}] - Processing raw payload...\n")
                except Exception as e:
                    print(f"\n❌ Execution Error encountered: {e}\n")

if __name__ == "__main__":
    asyncio.run(run_langgraph_agent())