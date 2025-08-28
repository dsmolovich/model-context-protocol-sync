# MCP - weather agent 
Synchronous implementation of MCP server + client, made out of the examples from:
- [MCP server](https://modelcontextprotocol.io/quickstart/server)
- [MCP client](https://modelcontextprotocol.io/quickstart/client)


# MCP client with MCP server over stdio
### Pre-reqs:
Ollama up and running with `llama:3.2` model


Run client `client.py` talking to weather MCP server `weather.py` in a subprocess
```
python client.py weather.py
```
>/!\ Type `quit` to exit


# MCP Server over HTTP
```
python weather-http.py
```
and curl call it:
```
# List tools:
curl -X POST http://localhost:8000/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{
    "jsonrpc": "2.0",
    "id": "1",
    "method": "tools/list",
    "params": {}
  }'

# Get forecast for location:
curl -X POST http://localhost:8000/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{
    "jsonrpc": "2.0",
    "id": "2",
    "method": "tools/call",
    "params": {
      "name": "get_forecast",
      "arguments": {
        "latitude": 40.7128,
        "longitude": -74.0060
      }
    }
  }'

# Get alerts:
curl -X POST http://localhost:8000/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{
    "jsonrpc": "2.0",
    "id": "3",
    "method": "tools/call",
    "params": {
      "name": "get_alerts",
      "arguments": {
        "state": "NY"
      }
    }
  }'
```