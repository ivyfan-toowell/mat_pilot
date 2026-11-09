"""加载统一双端界面及五个工作区，通过 FastAPI 访问真实科研服务。"""

import os
import sys
from pathlib import Path

# Streamlit executes the selected script with its directory on sys.path. Ensure
# the repository root is importable even for the legacy "streamlit run ui/app.py"
# entrypoint, without depending on a session-scoped PYTHONPATH.
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from ui import (  # noqa: E402
    agent_page,
    document_page,
    experimental_knowledge_page,
    knowledge_page,
    literature_page,
    material_page,
)
from ui.shared import setup_shell  # noqa: E402

backend_url = os.getenv("BACKEND_URL", "http://127.0.0.1:8000").rstrip("/")
workspace = setup_shell(backend_url)
{
    "材料筛选": material_page.render,
    "论文发现": literature_page.render,
    "论文解析": document_page.render,
    "文献知识库": knowledge_page.render,
    "科研助手": agent_page.render,
    "实验知识库": experimental_knowledge_page.render,
}[workspace](backend_url)
