# PostgreSQL MCP Server

A generic Model Context Protocol (MCP) server for PostgreSQL, allowing AI agents to inspect and query PostgreSQL databases safely.

## Features

- `list_tables`: List all tables in the `public` schema.
- `get_schema`: Get the schema (columns, types, nullability) of a specific table.
- `run_query`: Run a read-only SQL query (only `SELECT`/`WITH` allowed) with a maximum limit of 100 rows to avoid large responses.

## Prerequisites

- Python 3.13+
- [uv](https://github.com/astral-sh/uv)
- PostgreSQL database

## Installation

You can run this directly using `uvx` or `uv run` if you clone the repository.

## Usage

This server requires the `DATABASE_URL` environment variable to be set.

Example connection string:
`postgres://user:password@localhost:5432/mydatabase`

### Running directly

```bash
DATABASE_URL="postgresql://postgres:poggerpogger@localhost:5432/boxboxWeb" uv run main.py
```

### Usage with Claude Desktop / MCP Clients

Add the following to your MCP client configuration (e.g., Claude Desktop's `claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "postgres": {
      "command": "uv",
      "args": [
        "run",
        "/path/to/2025postgresqlmcp/main.py"
      ],
      "env": {
        "DATABASE_URL": "postgres://user:password@localhost:5432/mydatabase"
      }
    }
  }
}
```
