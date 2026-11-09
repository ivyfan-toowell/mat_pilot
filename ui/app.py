"""加载统一双端界面及五个工作区，通过 FastAPI 访问真实科研服务。"""

import os

from ui import agent_page, document_page, knowledge_page, literature_page, material_page, experimental_knowledge_page
from ui.shared import setup_shell

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
