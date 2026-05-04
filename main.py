import os
import sys
import asyncio
import asyncpg
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from mcp.server import Server
from mcp.server.sse import SseServerTransport
from mcp.types import Tool, TextContent
import uvicorn

# MCP Server definition
mcp_server = Server("postgres-mcp-server")

DATABASE_URL = os.environ.get("DATABASE_URL")
pool: asyncpg.Pool | None = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global pool
    if not DATABASE_URL:
        print("DATABASE_URL environment variable is required.", file=sys.stderr)
    else:
        try:
            print(f"Connecting to database: {DATABASE_URL}", file=sys.stderr)
            pool = await asyncpg.create_pool(DATABASE_URL)
            print("Database connection pool initialized successfully.", file=sys.stderr)
        except Exception as e:
            print(f"Failed to initialize database pool: {e}", file=sys.stderr)
    
    yield
    
    if pool:
        print("Closing database connection pool.", file=sys.stderr)
        await pool.close()

# FastAPI App definition
app = FastAPI(title="Postgres MCP Server", lifespan=lifespan)
sse = SseServerTransport("/messages")

@mcp_server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="list_tables",
            description="List all tables in the current database schema",
            inputSchema={
                "type": "object",
                "properties": {},
            }
        ),
        Tool(
            name="get_schema",
            description="Get the schema (columns, types) of a specific table",
            inputSchema={
                "type": "object",
                "properties": {
                    "table_name": {
                        "type": "string",
                        "description": "Name of the table"
                    }
                },
                "required": ["table_name"]
            }
        ),
        Tool(
            name="run_query",
            description="Run a read-only SQL query against the database. ONLY SELECT queries are allowed for safety.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The read-only SQL query to execute"
                    }
                },
                "required": ["query"]
            }
        )
    ]

@mcp_server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    if not pool:
        return [TextContent(type="text", text="Error: Database connection pool not initialized. DATABASE_URL may be missing or invalid.")]

    if name == "list_tables":
        async with pool.acquire() as conn:
            records = await conn.fetch("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public' 
                  AND table_type = 'BASE TABLE'
            """)
            tables = [record["table_name"] for record in records]
            if not tables:
                return [TextContent(type="text", text="No tables found in public schema.")]
            return [TextContent(type="text", text=f"Tables in public schema:\n" + "\n".join(f"- {t}" for t in tables))]

    elif name == "get_schema":
        table_name = arguments.get("table_name")
        if not table_name:
            return [TextContent(type="text", text="Error: table_name is required")]
            
        async with pool.acquire() as conn:
            records = await conn.fetch("""
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = $1
                ORDER BY ordinal_position
            """, table_name)
            
            if not records:
                return [TextContent(type="text", text=f"Table '{table_name}' not found or has no columns.")]
                
            schema_info = [f"Schema for {table_name}:"]
            for r in records:
                schema_info.append(f"- {r['column_name']} ({r['data_type']}, nullable: {r['is_nullable']})")
                
            return [TextContent(type="text", text="\n".join(schema_info))]

    elif name == "run_query":
        query = arguments.get("query")
        if not query:
            return [TextContent(type="text", text="Error: query is required")]
            
        if not query.strip().upper().startswith("SELECT") and not query.strip().upper().startswith("WITH"):
             return [TextContent(type="text", text="Error: Only SELECT/WITH queries are permitted via this tool.")]
             
        try:
            async with pool.acquire() as conn:
                async with conn.transaction(readonly=True):
                    stmt = await conn.prepare(query)
                    records = await stmt.fetch(100)
                    
                    if not records:
                        return [TextContent(type="text", text="Query returned 0 rows.")]
                    
                    keys = records[0].keys()
                    header = " | ".join(keys)
                    separator = "-" * len(header)
                    
                    rows = []
                    for record in records:
                        rows.append(" | ".join(str(record[k]) for k in keys))
                        
                    result_text = f"{header}\n{separator}\n" + "\n".join(rows) + "\n\n(Limited to 100 rows max)"
                    return [TextContent(type="text", text=result_text)]
                
        except Exception as e:
             return [TextContent(type="text", text=f"Error executing query: {str(e)}")]

    else:
        raise ValueError(f"Unknown tool: {name}")

@app.get("/sse")
async def handle_sse(request: Request):
    async with sse.connect_sse(
        request.scope, request.receive, request._send
    ) as (read_stream, write_stream):
        await mcp_server.run(
            read_stream,
            write_stream,
            mcp_server.create_initialization_options(),
        )

@app.post("/messages")
async def handle_messages(request: Request):
    await sse.handle_post_message(request.scope, request.receive, request._send)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)

