"""Launch the optional upstream MCP preset with Asteria's active RAG config.

The upstream stdio server normally reads its own config/settings.yaml. We
redirect that default to the same config used by Asteria's in-process bridge,
so the preset never silently queries a different collection or index.
"""
import os
import sys

from backend.knowledge.modular_rag import get_modular_config, get_modular_root


def main() -> int:
    root = get_modular_root()
    config = get_modular_config()
    if not root.is_dir() or not config.is_file():
        raise FileNotFoundError(f"Modular RAG root/config missing: {root} / {config}")
    sys.path.insert(0, str(root))
    os.chdir(root)
    from src.core import settings
    settings.DEFAULT_SETTINGS_PATH = config
    from src.mcp_server.server import main as upstream_main
    return upstream_main()


if __name__ == "__main__":
    raise SystemExit(main())
