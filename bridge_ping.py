from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    "model-bridge-test",
    host="127.0.0.1",
    port=8081,
    stateless_http=True,
    json_response=True,
)

@mcp.tool()
def bridge_ping(message: str) -> dict:
    """Test connectivity by returning the supplied message unchanged."""
    return {"status": "ok", "echo": message}

if __name__ == "__main__":
    mcp.run(transport="streamable-http")
