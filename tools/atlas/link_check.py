#!/usr/bin/env python3
"""Audit resource links embedded in the research atlas.

This script is intentionally conservative:
- 2xx/3xx responses count as pass
- 403/405/429/5xx responses count as warnings because documentation sites
  and anti-bot defenses sometimes block non-browser requests
- 404/410 and hard network failures count as failures
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import re
import ssl
import sys
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path


RESOURCE_PATTERN = re.compile(
    r'\{\s*id:\s*"(?P<id>[^"]+)",\s*'
    r'title:\s*"(?P<title>(?:[^"\\]|\\.)*)",\s*'
    r'url:\s*"(?P<url>[^"]+)"',
    re.DOTALL,
)

WARNING_STATUSES = {403, 405, 429, 500, 502, 503, 504}
FAIL_STATUSES = {404, 410}
USER_AGENT = (
    "Mozilla/5.0 (compatible; AtlasLinkAudit/1.0; "
    "+https://github.com/Athishsivakumaran/agentic-ai-research-atlas)"
)


@dataclass(frozen=True)
class Resource:
    id: str
    title: str
    url: str


@dataclass(frozen=True)
class Result:
    id: str
    title: str
    url: str
    status: str
    status_code: int | None
    detail: str


def decode_js_string(value: str) -> str:
    return bytes(value, "utf-8").decode("unicode_escape")


def parse_resources(source: Path) -> list[Resource]:
    text = source.read_text(encoding="utf-8")
    resources = []
    for match in RESOURCE_PATTERN.finditer(text):
        resources.append(
            Resource(
                id=match.group("id"),
                title=decode_js_string(match.group("title")),
                url=match.group("url"),
            )
        )
    if not resources:
        raise SystemExit(f"No resources found in {source}")
    return resources


def classify_http_status(code: int) -> tuple[str, str]:
    if 200 <= code < 400:
        return "pass", "reachable"
    if code in FAIL_STATUSES:
        return "fail", "missing"
    if code in WARNING_STATUSES:
        return "warning", "blocked or transient"
    return "warning", "unexpected status"


def fetch_once(url: str, method: str) -> tuple[int, str]:
    request = urllib.request.Request(
        url,
        method=method,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
    )
    context = ssl.create_default_context()
    with urllib.request.urlopen(request, timeout=20, context=context) as response:
        return response.getcode(), response.geturl()


def check_resource(resource: Resource) -> Result:
    methods = ["HEAD", "GET"]
    last_error = ""

    for method in methods:
        try:
            code, final_url = fetch_once(resource.url, method)
            status, detail = classify_http_status(code)
            if status == "warning" and method == "HEAD":
                last_error = f"{method} {code}"
                continue
            if final_url != resource.url:
                detail = f"{detail}; redirected to {final_url}"
            return Result(resource.id, resource.title, resource.url, status, code, detail)
        except urllib.error.HTTPError as error:
            code = error.code
            status, detail = classify_http_status(code)
            if status == "warning" and method == "HEAD":
                last_error = f"{method} {code}"
                continue
            return Result(resource.id, resource.title, resource.url, status, code, detail)
        except urllib.error.URLError as error:
            last_error = str(error.reason)
        except Exception as error:  # pragma: no cover - defensive
            last_error = str(error)

    return Result(resource.id, resource.title, resource.url, "fail", None, last_error or "network failure")


def write_json(path: Path, results: list[Result]) -> None:
    payload = {
        "summary": summarize(results),
        "results": [asdict(result) for result in results],
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def summarize(results: list[Result]) -> dict[str, int]:
    summary = {"pass": 0, "warning": 0, "fail": 0, "total": len(results)}
    for result in results:
        summary[result.status] += 1
    return summary


def write_markdown(path: Path, results: list[Result]) -> None:
    summary = summarize(results)
    lines = [
        "# Atlas Link Audit",
        "",
        f"- Total: {summary['total']}",
        f"- Pass: {summary['pass']}",
        f"- Warning: {summary['warning']}",
        f"- Fail: {summary['fail']}",
        "",
        "| Status | Code | Resource | URL | Detail |",
        "| --- | --- | --- | --- | --- |",
    ]

    for result in results:
        code = str(result.status_code) if result.status_code is not None else "-"
        title = result.title.replace("|", "\\|")
        url = result.url.replace("|", "\\|")
        detail = result.detail.replace("|", "\\|")
        lines.append(f"| {result.status} | {code} | {title} | {url} | {detail} |")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, help="Path to the atlas HTML source")
    parser.add_argument("--json", required=True, help="Path to the JSON audit report")
    parser.add_argument("--markdown", required=True, help="Path to the Markdown audit report")
    args = parser.parse_args()

    source = Path(args.source)
    json_path = Path(args.json)
    markdown_path = Path(args.markdown)

    resources = parse_resources(source)

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        results = list(executor.map(check_resource, resources))

    results.sort(key=lambda result: (result.status, result.title.lower()))
    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    write_json(json_path, results)
    write_markdown(markdown_path, results)

    summary = summarize(results)
    print(
        f"Checked {summary['total']} links: "
        f"{summary['pass']} pass, {summary['warning']} warning, {summary['fail']} fail."
    )

    return 1 if summary["fail"] else 0


if __name__ == "__main__":
    sys.exit(main())
