import json
import sys
import subprocess
from typing import Optional, Dict, Any, List

import requests

class MCPClient:
    def __init__(self, ollama_host: str = "http://localhost:11434", model: str = "llama3.2"):
        self.ollama_host = ollama_host
        self.model = model
        self.server_process = None
        self.tools = []

    def connect_to_server(self, server_script_path: str):
        """Connect to an MCP server
        
        Args:
            server_script_path: Path to the server script (.py or .js)
        """
        is_python = server_script_path.endswith('.py')
        is_js = server_script_path.endswith('.js')
        if not (is_python or is_js):
            raise ValueError("Server script must be a .py or .js file")
            
        command = ["python", server_script_path] if is_python else ["node", server_script_path]
        
        self.server_process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=0
        )
        
        # Initialize the MCP session
        self._send_message({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "roots": {
                        "listChanged": True
                    },
                    "sampling": {}
                },
                "clientInfo": {
                    "name": "sync-mcp-client",
                    "version": "1.0.0"
                }
            }
        })
        
        init_response = self._read_message()
        if "error" in init_response:
            raise Exception(f"Failed to initialize: {init_response['error']}")
        
        # Send initialized notification
        self._send_message({
            "jsonrpc": "2.0",
            "method": "notifications/initialized"
        })
        
        # List available tools
        self._send_message({
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/list"
        })
        
        tools_response = self._read_message()
        if "result" in tools_response and "tools" in tools_response["result"]:
            self.tools = tools_response["result"]["tools"]
            print("\nConnected to server with tools:", [tool["name"] for tool in self.tools])
        else:
            print("No tools found or error listing tools")

    def _send_message(self, message: dict):
        """Send a JSON-RPC message to the server"""
        if not self.server_process:
            raise Exception("Not connected to server")
        
        json_str = json.dumps(message) + "\n"
        self.server_process.stdin.write(json_str)
        self.server_process.stdin.flush()

    def _read_message(self) -> dict:
        """Read a JSON-RPC message from the server"""
        if not self.server_process:
            raise Exception("Not connected to server")
        
        line = self.server_process.stdout.readline()
        if not line:
            raise Exception("Server connection closed")
        
        try:
            return json.loads(line.strip())
        except json.JSONDecodeError as e:
            raise Exception(f"Invalid JSON from server: {e}")

    def call_ollama(self, messages: List[Dict[str, str]], tools: Optional[List[Dict]] = None) -> Dict[str, Any]:
        """Call Ollama API with messages and optional tools"""
        url = f"{self.ollama_host}/api/chat"
        
        # Create system message with tool information
        system_content = "You are a helpful assistant."
        if tools:
            system_content += "\n\nYou have access to the following tools:\n"
            for tool in tools:
                system_content += f"- {tool['name']}: {tool['description']}\n"
                system_content += f"  Input schema: {json.dumps(tool['inputSchema'])}\n"
            system_content += "\nTo use a tool, respond with JSON in this format: {\"tool_call\": {\"name\": \"tool_name\", \"arguments\": {\"arg1\": \"value1\"}}}"
        
        # Prepare messages for Ollama
        ollama_messages = [{"role": "system", "content": system_content}]
        ollama_messages.extend(messages)
        
        payload = {
            "model": self.model,
            "messages": ollama_messages,
            "stream": False
        }
        
        response = requests.post(url, json=payload, timeout=180.0)
        response.raise_for_status()
        return response.json()

    def call_tool(self, tool_name: str, arguments: dict) -> str:
        """Call an MCP tool"""
        self._send_message({
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments
            }
        })
        
        response = self._read_message()
        if "error" in response:
            return f"Error calling tool: {response['error']}"
        
        if "result" in response and "content" in response["result"]:
            content = response["result"]["content"]
            if isinstance(content, list) and len(content) > 0:
                return content[0].get("text", str(content[0]))
            return str(content)
        
        return str(response.get("result", "No result"))

    def process_query(self, query: str) -> str:
        """Process a query using Ollama and available tools"""
        messages = [
            {
                "role": "user",
                "content": query
            }
        ]

        available_tools = [{ 
            "name": tool["name"],
            "description": tool["description"],
            "inputSchema": tool["inputSchema"]
        } for tool in self.tools]

        # Initial Ollama API call
        response = self.call_ollama(messages, available_tools)
        response_text = response['message']['content']
        
        # Check if response contains tool call
        try:
            # Try to parse tool call from response
            if "tool_call" in response_text and "{" in response_text:
                # Extract JSON from response
                start_idx = response_text.find("{")
                end_idx = response_text.rfind("}") + 1
                tool_json = response_text[start_idx:end_idx]
                tool_call = json.loads(tool_json)
                
                if "tool_call" in tool_call:
                    tool_info = tool_call["tool_call"]
                    tool_name = tool_info["name"]
                    tool_args = tool_info["arguments"]
                    
                    # Execute tool call
                    result = self.call_tool(tool_name, tool_args)
                    
                    # Add tool result to conversation
                    messages.append({
                        "role": "assistant",
                        "content": f"I'll use the {tool_name} tool to help answer your question."
                    })
                    
                    messages.append({
                        "role": "user",
                        "content": f"Tool result: {result}"
                    })
                    
                    # Get final response from Ollama
                    final_response = self.call_ollama(messages)
                    return final_response['message']['content']
                    
        except (json.JSONDecodeError, KeyError, IndexError):
            # If no valid tool call found, return original response
            pass
        
        return response_text

    def chat_loop(self):
        """Run an interactive chat loop"""
        print("\nMCP Client Started!")
        print("Type your queries or 'quit' to exit.")
        
        while True:
            try:
                query = input("\nQuery: ").strip()
                
                if query.lower() == 'quit':
                    break
                    
                response = self.process_query(query)
                print("\n" + response)
                    
            except EOFError:
                print("\nEOF encountered. Exiting...")
                break
            except KeyboardInterrupt:
                print("\nInterrupted. Exiting...")
                break
            except Exception as e:
                print(f"\nError: {str(e)}")
    
    def cleanup(self):
        """Clean up resources"""
        if self.server_process:
            self.server_process.terminate()
            self.server_process.wait()

def main():
    if len(sys.argv) < 2:
        print("Usage: python client_sync.py <path_to_server_script> [ollama_host] [model]")
        print("  ollama_host: Ollama server URL (default: http://localhost:11434)")
        print("  model: Ollama model name (default: llama3.2)")
        sys.exit(1)
        
    server_script = sys.argv[1]
    ollama_host = sys.argv[2] if len(sys.argv) > 2 else "http://localhost:11434"
    model = sys.argv[3] if len(sys.argv) > 3 else "llama3.2"
    
    client = MCPClient(ollama_host=ollama_host, model=model)
    try:
        client.connect_to_server(server_script)
        print(f"Using Ollama at {ollama_host} with model {model}")
        client.chat_loop()
    finally:
        client.cleanup()

if __name__ == "__main__":
    main()