# GitHub 使用说明

仓库保存应用源码、界面、测试、依赖锁文件、任务书和开发文档。默认使用私有仓库。

## 不上传的本地文件

- `.env`、其他真实环境配置、Streamlit 密钥、证书与私钥。
- `data/` 下的论文、解析结果、实验记录、查询快照、运行轨迹和验收报告。
- 数据库文件、备份、日志、虚拟环境、依赖缓存和编辑器配置。
- 本机 Codex 沙箱修复脚本、ACL 备份、诊断文档与聊天续做记录。

这些文件由 `.gitignore` 排除，仍保留在本地。GitHub 仓库不能代替论文和数据库备份；
Docker 具名卷也不会随代码上传。`.env.example` 仅包含变量名和无密钥的默认设置。

## 克隆后运行

1. 安装 Python 3.13、uv、Docker Desktop 和 Git。
2. 克隆仓库并进入项目根目录，执行 `uv sync --locked --all-extras`。
3. 将 `.env.example` 复制为 `.env`，在本地填写密钥，不要提交 `.env`。
4. 按 README「配置服务 / 迁移顺序」执行：`setup_database` →（可选）`migrate_tenant_local`
   → `docker compose up -d --wait db` → schema（`SCHEMA_AUTO_APPLY` 或 `apply_schema` /
   `alembic upgrade head`）→（可选）`migrate_docs_to_postgres`。
5. 启动 API 与 Streamlit。共享部署时设置 `AUTH_MODE=api_key`、`AUTH_API_KEYS`，
   并为界面配置同值 `MATPILOT_API_KEY`；建议 `RATE_LIMIT_PER_MINUTE>0`、`LOG_JSON=true`。
6. 运行检索评测时，通过 `--document-id` 传入自己导入的文献 UUID；脚本会核对
   `eval/retrieval_pilot.json` 中的 PDF 哈希和原文标注，下载到不同版本的全文时需重新核对标注。

新数据库为空；样例论文可用 `scripts.download_sample_paper` 重新下载和解析。

## 后续提交

在项目根目录执行，提交前检查暂存区：

```powershell
git status --short
git add app ui scripts tests docs eval alembic .streamlit .env.example .gitignore .gitattributes .python-version README.md CHANGELOG.md pyproject.toml uv.lock docker-compose.yml alembic.ini
git diff --cached --stat
git diff --cached
git commit -m "Describe the change"
git push
```

不要使用 `git add -f` 强行加入被忽略的配置或数据。切换为公开仓库前，应再次检查代码、
文档和完整提交历史，确认拥有发布权限且没有凭据及私有科研资料。
