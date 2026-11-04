"""调用 OpenAlex 检索论文元数据，处理认证、重试并保存查询快照。"""

import math
import re
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID, uuid4

import httpx
from pydantic import ValidationError

from app.core.config import Settings
from app.core.errors import ServiceError
from app.schemas.literature import AcademicPaper, LiteratureQuery, LiteratureResult

OPENALEX_WORKS = "https://api.openalex.org/works"
SELECT = (
    "id,title,doi,authorships,publication_year,publication_date,primary_location,"
    "best_oa_location,open_access,cited_by_count,is_retracted,type"
)


def normalize_doi(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    value = re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", value.strip(), flags=re.I)
    return value.lower() if re.fullmatch(r"10\.\d{4,9}/[^\s]+", value) else None


def safe_url(value) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        url = urlsplit(value)
        if url.scheme in {"https", "http"} and url.hostname and not (url.username or url.password):
            return value
    except ValueError:
        pass
    return None


def paper_from_work(work: dict) -> AcademicPaper:
    primary = work.get("primary_location") or {}
    best = work.get("best_oa_location") or {}
    access = work.get("open_access") or {}
    # The license and PDF must belong to the same location, never to a different copy.
    location = best if best.get("is_oa") is True else primary
    doi = normalize_doi(work.get("doi"))
    names = [
        item["author"]["display_name"]
        for item in (work.get("authorships") or [])
        if isinstance(item, dict)
        and isinstance(item.get("author"), dict)
        and isinstance(item["author"].get("display_name"), str)
    ]
    return AcademicPaper(
        openalex_id=work["id"],
        title=work.get("title"),
        doi=doi,
        doi_url=f"https://doi.org/{doi}" if doi else None,
        authors=names[:30],
        authors_truncated=len(names) > 30,
        publication_year=work.get("publication_year"),
        publication_date=work.get("publication_date"),
        venue=(primary.get("source") or {}).get("display_name"),
        work_type=work.get("type"),
        cited_by_count=work.get("cited_by_count"),
        is_retracted=work.get("is_retracted"),
        is_oa=access.get("is_oa"),
        oa_status=access.get("oa_status"),
        landing_page_url=safe_url(location.get("landing_page_url")),
        pdf_url=safe_url(location.get("pdf_url")) if location.get("is_oa") is True else None,
        license=location.get("license"),
        version=location.get("version"),
    )


class LiteratureStore:
    def __init__(self, data_dir: Path):
        self.directory = data_dir / "literature_queries"

    def save(self, result: LiteratureResult) -> None:
        temporary = self.directory / f".{uuid4()}.tmp"
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            temporary.write_text(result.model_dump_json(indent=2), encoding="utf-8")
            temporary.replace(self.directory / f"{result.query_id}.json")
        except OSError:
            raise ServiceError("storage_unavailable", "论文检索快照保存失败。", 503) from None
        finally:
            temporary.unlink(missing_ok=True)

    def load(self, query_id: UUID) -> LiteratureResult:
        try:
            return LiteratureResult.model_validate_json(
                (self.directory / f"{query_id}.json").read_text(encoding="utf-8")
            )
        except FileNotFoundError:
            raise ServiceError(
                "literature_query_not_found", "未找到该论文检索记录。", 404
            ) from None
        except (OSError, ValidationError):
            raise ServiceError(
                "literature_snapshot_invalid", "论文检索记录无法读取。", 409
            ) from None


class LiteratureService:
    def __init__(self, settings: Settings):
        self.settings = settings

    def search(self, query: LiteratureQuery) -> LiteratureResult:
        if not self.settings.openalex_api_key:
            raise ServiceError(
                "openalex_not_configured", "请在后端 .env 配置 OPENALEX_API_KEY。", 503
            )
        filters = []
        params = {"per_page": query.limit, "select": SELECT}
        if doi := normalize_doi(query.query):
            filters.append(f"doi:{doi}")
        else:
            params["search"] = query.query
        if query.open_access_only:
            filters.append("is_oa:true")
        if query.year_from is not None:
            filters.append(f"from_publication_date:{query.year_from}-01-01")
        if query.year_to is not None:
            filters.append(f"to_publication_date:{query.year_to}-12-31")
        if filters:
            params["filter"] = ",".join(filters)
        if query.sort != "relevance":
            params["sort"] = (
                "publication_date:desc" if query.sort == "newest" else "cited_by_count:desc"
            )
        url = str(httpx.URL(OPENALEX_WORKS, params=params))
        if len(url.encode("utf-8")) > 4000:
            raise ServiceError("openalex_bad_query", "检索表达式过长，请缩短关键词。", 422)
        started = time.perf_counter()
        # Bearer auth keeps credentials out of URLs, HTTP request logs and stored query links.
        with httpx.Client(
            timeout=self.settings.openalex_timeout_seconds, follow_redirects=False
        ) as client:
            for attempt in range(1, 4):
                try:
                    response = client.get(
                        OPENALEX_WORKS,
                        params=params,
                        headers={
                            "Authorization": "Bearer "
                            + self.settings.openalex_api_key.get_secret_value(),
                            "User-Agent": "MatPilot/0.1 (materials research metadata)",
                        },
                    )
                except httpx.TransportError:
                    if attempt == 3:
                        raise ServiceError(
                            "openalex_unavailable", "OpenAlex 连接失败，请稍后重试。", 503
                        ) from None
                    time.sleep(0.5 * 2 ** (attempt - 1))
                    continue
                if response.status_code in {401, 403}:
                    raise ServiceError(
                        "openalex_auth_failed", "OpenAlex 密钥未通过验证，请检查本地配置。", 503
                    )
                if response.status_code in {429, 500, 502, 503, 504}:
                    delay = 0.5 * 2 ** (attempt - 1)
                    try:
                        delay = float(response.headers.get("Retry-After", delay))
                    except ValueError:
                        pass
                    if attempt < 3 and math.isfinite(delay) and 0 <= delay <= 2:
                        time.sleep(delay)
                        continue
                    code = (
                        "openalex_rate_limited"
                        if response.status_code == 429
                        else "openalex_unavailable"
                    )
                    raise ServiceError(
                        code,
                        "OpenAlex 限流、额度不足或服务暂不可用，请稍后重试。",
                        429 if response.status_code == 429 else 503,
                    )
                if response.status_code == 400:
                    raise ServiceError(
                        "openalex_bad_query",
                        "OpenAlex 不接受此检索表达式，请调整关键词或筛选条件。",
                        422,
                    )
                if not response.is_success:
                    raise ServiceError(
                        "openalex_failed", "OpenAlex 请求失败，未返回未经校验的元数据。", 502
                    )
                try:
                    payload = response.json()
                    works = payload["results"]
                    if not isinstance(works, list) or len(works) > query.limit:
                        raise ValueError("invalid result count")
                    papers = []
                    ids, dois = set(), set()
                    for work in works:
                        paper = paper_from_work(work)
                        if query.open_access_only and paper.is_oa is not True:
                            raise ValueError("provider did not preserve OA filter")
                        if query.year_from is not None and (
                            paper.publication_year is None
                            or paper.publication_year < query.year_from
                        ):
                            raise ValueError("provider did not preserve start year")
                        if query.year_to is not None and (
                            paper.publication_year is None or paper.publication_year > query.year_to
                        ):
                            raise ValueError("provider did not preserve end year")
                        if paper.openalex_id in ids or (paper.doi and paper.doi in dois):
                            continue
                        papers.append(paper)
                        ids.add(paper.openalex_id)
                        if paper.doi:
                            dois.add(paper.doi)
                    meta = payload["meta"]
                    count = meta["count"]
                    if type(count) is not int or count < len(works):
                        raise ValueError("invalid total count")
                    result = LiteratureResult(
                        query_id=uuid4(),
                        query=query,
                        retrieved_at=datetime.now(UTC),
                        api_url=url,
                        matched_count=count,
                        papers=papers,
                        possibly_truncated=count > len(papers),
                        attempts=attempt,
                        elapsed_ms=(time.perf_counter() - started) * 1000,
                        provider_cost_usd=meta.get("cost_usd"),
                    )
                except (ValueError, KeyError, TypeError, AttributeError):
                    raise ServiceError(
                        "openalex_invalid_response", "OpenAlex 元数据格式无效，未保存结果。", 502
                    ) from None
                if len(papers) < len(works):
                    result.warnings.append("本页重复 DOI 或 OpenAlex ID 已去重；未继续翻页补齐。")
                if result.possibly_truncated:
                    result.warnings.append("仅返回第一页的有限结果，不代表完整文献集合。")
                LiteratureStore(self.settings.data_dir).save(result)
                return result
        raise RuntimeError("OpenAlex retry loop exhausted")
