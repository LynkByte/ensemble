"""Entry point: python -m ensemble_mcp."""


def main() -> None:
    """Start the ensemble-mcp MCP server."""
    from ensemble_mcp.server import serve

    serve()


if __name__ == "__main__":
    main()
