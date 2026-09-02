"""Collect GitHub preflight facts and optionally attempt authorized setup.

No credential value is ever serialized.  Without an authenticated GitHub CLI
or API token this script records explicit permission gaps and the compare URL.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
REPOSITORY = "csn1985-ship-it/ugas"
BASELINE = "6b956b9299f3a2f75280f17706c38c59e3714034"
BRANCH = "codex/v0.12.3-github-native-review"
API = f"https://api.github.com/repos/{REPOSITORY}"


def git(args: list[str]) -> tuple[int, str, str]:
    result = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def api_call(method: str, path: str, token: str | None, payload: dict[str, Any] | None = None) -> tuple[int, Any, str]:
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "ugas-v0123-preflight"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = Request(f"{API}{path}", data=data, headers=headers, method=method)
    try:
        with urlopen(request, timeout=20) as response:
            body = response.read().decode("utf-8", "replace")
            try:
                return response.status, json.loads(body), ""
            except json.JSONDecodeError:
                return response.status, {}, body[-500:]
    except HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        try:
            value = json.loads(body)
            message = str(value.get("message", "HTTP error"))
        except json.JSONDecodeError:
            message = body[-500:] or str(exc)
        return exc.code, {}, message
    except (OSError, URLError) as exc:
        return 0, {}, str(exc)


def token() -> str | None:
    for name in ("GH_TOKEN", "GITHUB_TOKEN", "GITHUB_PAT"):
        value = os.environ.get(name)
        if value:
            return value
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write-evidence", action="store_true")
    parser.add_argument("--attempt-ruleset", action="store_true")
    parser.add_argument("--attempt-metadata", action="store_true")
    parser.add_argument("--attempt-pr", action="store_true")
    parser.add_argument("--branch", default=BRANCH)
    args = parser.parse_args()
    api_token = token()
    gh_path = shutil.which("gh")
    _, remote, _ = git(["remote", "get-url", "origin"])
    _, remote_head, _ = git(["ls-remote", "--heads", "origin", args.branch])
    compare_url = f"https://github.com/{REPOSITORY}/compare/main...{args.branch}"
    before_workflow = subprocess.run(["git", "cat-file", "-e", f"{BASELINE}:.github/workflows/ugas-ci.yml"], cwd=ROOT, capture_output=True, check=False).returncode == 0
    after_workflow = (ROOT / ".github/workflows/ugas-ci.yml").is_file() and (ROOT / ".github/workflows/ugas-review.yml").is_file()
    repo_status, repo_value, repo_error = api_call("GET", "", api_token)
    ruleset_status, rulesets, ruleset_error = api_call("GET", "/rulesets", api_token)
    existing_ruleset = next((item for item in rulesets if isinstance(item, dict) and item.get("name") == "UGAS main PR protection v0.12.3"), None) if isinstance(rulesets, list) else None
    result: dict[str, Any] = {
        "schema_version": "0.12.3",
        "repository": REPOSITORY,
        "default_branch": "main",
        "remote": remote,
        "baseline_head": BASELINE,
        "feature_branch": args.branch,
        "compare_url": compare_url,
        "remote_branch_present": bool(remote_head),
        "workflow_presence": {"baseline": before_workflow, "working_tree": after_workflow, "required": [".github/workflows/ugas-ci.yml", ".github/workflows/ugas-review.yml"]},
        "ruleset_presence": {"api_status": ruleset_status, "existing_named_ruleset": bool(existing_ruleset), "error": ruleset_error or None},
        "authentication": {"gh_cli_present": bool(gh_path), "api_token_present": bool(api_token), "credential_values_recorded": False},
        "permission_gaps": [],
        "operations": {},
    }
    if repo_status not in (200,):
        result["permission_gaps"].append({"code": "GITHUB_API_READ_GAP", "reason": repo_error or f"GitHub repository API returned HTTP {repo_status}", "remediation": "Verify repository URL and network access."})
    if not api_token and not gh_path:
        result["permission_gaps"].append({"code": "GITHUB_PR_CREATE_GAP", "reason": "No authenticated gh CLI or GH_TOKEN/GITHUB_TOKEN/GITHUB_PAT is available to create the PR.", "remediation": "Install GitHub CLI and run gh auth login, or provide a token with pull-requests:write for csn1985-ship-it/ugas.", "compare_url": compare_url})
        result["permission_gaps"].append({"code": "GITHUB_RULESET_GAP", "reason": "No authenticated GitHub API/CLI credential is available to configure the main ruleset.", "remediation": "Authenticate with repository administration:write and configure a main ruleset requiring PR plus the two stable checks, while blocking deletion and force-push."})
    if not (ROOT / ".github/CODEOWNERS").is_file():
        result["permission_gaps"].append({"code": "CODEOWNERS_GAP", "reason": "No repository-owner/reviewer identity was resolvable without guessing; CODEOWNERS was not created.", "remediation": "Add .github/CODEOWNERS only after a valid repository owner/reviewer account is confirmed."})

    if args.attempt_ruleset:
        if not api_token:
            result["operations"]["ruleset"] = {"status": "GITHUB_RULESET_GAP", "attempted": False, "reason": "no API token available"}
        elif existing_ruleset:
            result["operations"]["ruleset"] = {"status": "ALREADY_CONFIGURED", "attempted": True, "ruleset_id": existing_ruleset.get("id"), "name": existing_ruleset.get("name")}
        else:
            payload = {"name": "UGAS main PR protection v0.12.3", "target": "branch", "enforcement": "active", "conditions": {"ref_name": {"include": ["refs/heads/main"], "exclude": []}}, "rules": [{"type": "pull_request", "parameters": {"dismiss_stale_reviews_on_push": True, "require_code_owner_review": False, "required_approving_review_count": 0, "require_last_push_approval": False, "required_review_thread_resolution": True}}, {"type": "required_status_checks", "parameters": {"required_status_checks": [{"context": "UGAS CI / unit-and-validation", "integration_id": -1}, {"context": "UGAS CI / docker-smoke", "integration_id": -1}], "strict_required_status_checks_policy": True}}, {"type": "deletion"}, {"type": "non_fast_forward"}]}
            status, value, error = api_call("POST", "/rulesets", api_token, payload)
            result["operations"]["ruleset"] = {"status": "CONFIGURED" if status in (200, 201) else "GITHUB_RULESET_GAP", "attempted": True, "http_status": status, "ruleset_id": value.get("id") if isinstance(value, dict) else None, "error": error or None}
            if status not in (200, 201):
                result["permission_gaps"].append({"code": "GITHUB_RULESET_GAP", "reason": error or f"ruleset API returned HTTP {status}", "remediation": "In GitHub Settings -> Rules -> Rulesets, create an active main ruleset requiring Pull Requests and contexts UGAS CI / unit-and-validation plus UGAS CI / docker-smoke; block deletion and force-push without weakening visibility/security."})

    if args.attempt_metadata:
        if not api_token:
            result["operations"]["metadata"] = {"status": "GITHUB_METADATA_GAP", "attempted": False, "reason": "no API token available"}
        else:
            description = "Universal Game Asset Studio - GitHub-native review infrastructure and local always-on observability."
            status, _, error = api_call("PATCH", "", api_token, {"description": description})
            topic_status, _, topic_error = api_call("PUT", "/topics", api_token, {"names": ["game-assets", "python", "docker", "github-actions", "observability", "asset-pipeline"]})
            result["operations"]["metadata"] = {"status": "CONFIGURED" if status == 200 and topic_status == 200 else "GITHUB_METADATA_GAP", "attempted": True, "description_http_status": status, "topics_http_status": topic_status, "error": error or topic_error or None}

    if args.attempt_pr:
        if not api_token:
            result["operations"]["pull_request"] = {"status": "GITHUB_PR_CREATE_GAP", "attempted": False, "compare_url": compare_url, "reason": "no API token available"}
        else:
            status, open_prs, error = api_call("GET", f"/pulls?state=open&head={REPOSITORY.split('/')[0]}:{args.branch}&base=main", api_token)
            existing_pr = open_prs[0] if status == 200 and isinstance(open_prs, list) and open_prs else None
            if existing_pr:
                result["operations"]["pull_request"] = {"status": "ALREADY_OPEN", "attempted": True, "number": existing_pr.get("number"), "url": existing_pr.get("html_url")}
            else:
                body = """## UGAS v0.12.3 GitHub-native review\n\nThis PR implements the bounded review infrastructure slice from the verified baseline.\n\nReview evidence is produced by the [UGAS GitHub review evidence workflow](https://github.com/csn1985-ship-it/ugas/actions/workflows/ugas-review.yml) as `ugas-review-evidence-pr-<N>-<SHA>` after the required checks complete. The artifact contains machine manifests and the v0.12.2 dashboard PNGs; it contains no secrets, model weights, telemetry DB or local credentials.\n\nProduction remains `production_approved=false` and `production_routing=BLOCKED`. The executor does not merge this PR; external review must resolve the final decision.\n"""
                status, value, error = api_call("POST", "/pulls", api_token, {"title": "v0.12.3 GitHub-native review infrastructure", "head": args.branch, "base": "main", "body": body})
                result["operations"]["pull_request"] = {"status": "CREATED" if status == 201 else "GITHUB_PR_CREATE_GAP", "attempted": True, "http_status": status, "number": value.get("number") if isinstance(value, dict) else None, "url": value.get("html_url") if isinstance(value, dict) else compare_url, "error": error or None, "compare_url": compare_url}
                if status != 201:
                    result["permission_gaps"].append({"code": "GITHUB_PR_CREATE_GAP", "reason": error or f"pull request API returned HTTP {status}", "remediation": "Authenticate a token with pull-requests:write for csn1985-ship-it/ugas and create the PR from the compare URL.", "compare_url": compare_url})
    result["status"] = "READY_FOR_EXTERNAL_REVIEW" if not result["permission_gaps"] else "READY_WITH_EXPLICIT_GITHUB_GAPS"
    if args.write_evidence:
        output = ROOT / "docs/evidence/github-review-v0123/github-preflight.json"
        output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
