"""Python governance logger with synchronous blocking support."""

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any, Optional

DEFAULT_GOVERNOR_BACKEND = r"C:\Users\msell\OneDrive\AIAlchemy\aiagentgovernance\backend"
_governor_start_attempted = False


def _governor_url() -> str:
    return os.environ.get("GOVERNANCE_URL", "http://localhost:3000")


def _timeout_seconds() -> float:
    return int(os.environ.get("GOVERNANCE_TIMEOUT", "5000")) / 1000


def _governor_backend_dir() -> str:
    return os.environ.get("GOVERNANCE_BACKEND_DIR", DEFAULT_GOVERNOR_BACKEND)


def _http_json(
    method: str,
    url: str,
    payload: Optional[dict[str, Any]] = None,
    timeout: float = 2,
) -> tuple[int, dict[str, Any]]:
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = int(response.status)
            raw = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        status = int(exc.code)
        raw = exc.read().decode("utf-8", errors="replace")
    try:
        body = json.loads(raw) if raw else {}
    except ValueError:
        body = {}
    if not isinstance(body, dict):
        body = {}
    return status, body


def _governor_is_healthy() -> bool:
    try:
        status, _body = _http_json("GET", f"{_governor_url()}/health", timeout=2)
        return status == 200
    except Exception:
        return False


def ensure_governor_running(wait_seconds: int = 45) -> bool:
    """Start the governor if it is not already running."""
    global _governor_start_attempted

    if _governor_is_healthy():
        return True

    if _governor_start_attempted:
        for _ in range(wait_seconds):
            if _governor_is_healthy():
                return True
            time.sleep(1)
        return False

    _governor_start_attempted = True
    backend_dir = _governor_backend_dir()
    if not os.path.isdir(backend_dir):
        print(f"[GovernanceLogger] Governor backend not found: {backend_dir}")
        return False

    print("[GovernanceLogger] Governor not running - starting it now ...")
    command = (
        f"Set-Location '{backend_dir}'; "
        "Write-Host 'GOVERNOR - auto-started by agent' -ForegroundColor Green; "
        "npx tsx src/server.ts"
    )

    popen_kwargs: dict[str, Any] = {}
    if sys.platform == "win32":
        popen_kwargs["creationflags"] = subprocess.CREATE_NEW_CONSOLE

    subprocess.Popen(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
        **popen_kwargs,
    )

    for _ in range(wait_seconds):
        if _governor_is_healthy():
            print("[GovernanceLogger] Governor is ready.")
            return True
        time.sleep(1)

    print("[GovernanceLogger] Governor did not become healthy in time.")
    return False


def _parse_response(status_code: int, body: dict[str, Any]) -> dict[str, Any]:
    return {
        "success": status_code == 200 and body.get("success", True),
        "allowed": body.get("allowed", status_code == 200),
        "violation": body.get("violation"),
        "violatedPolicy": body.get("violatedPolicy"),
        "escalationId": body.get("escalationId"),
        "data": body.get("data"),
    }


def log_success(
    agent_id: str,
    description: str,
    output: Optional[Any] = None,
    confidence: Optional[float] = None,
) -> dict[str, Any]:
    """Log activity and return governor blocking decision."""
    if not ensure_governor_running():
        return {
            "success": False,
            "allowed": False,
            "violation": "Governor is not running and could not be started",
        }

    activity = {
        "agentId": agent_id,
        "actionType": "agent_execution_complete",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "description": description,
        "result": {"success": True, "output": output},
        "confidence": confidence,
    }

    try:
        status, body = _http_json(
            "POST",
            f"{_governor_url()}/agents/{agent_id}/activity",
            payload=activity,
            timeout=_timeout_seconds(),
        )
        return _parse_response(status, body)
    except Exception as exc:
        print(f"[GovernanceLogger] Failed to log activity for {agent_id}: {exc}")
        return {
            "success": False,
            "allowed": False,
            "violation": f"Failed to get governance approval: {exc}",
        }


def log_error(agent_id: str, error: str) -> dict[str, Any]:
    """Log an agent error to the governance governor."""
    if not ensure_governor_running():
        return {
            "success": False,
            "allowed": False,
            "violation": "Governor is not running and could not be started",
        }

    activity = {
        "agentId": agent_id,
        "actionType": "error_occurred",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "description": f"Error: {error}",
        "result": {"success": False, "error": error},
    }

    try:
        status, body = _http_json(
            "POST",
            f"{_governor_url()}/agents/{agent_id}/activity",
            payload=activity,
            timeout=_timeout_seconds(),
        )
        return _parse_response(status, body)
    except Exception as exc:
        print(f"[GovernanceLogger] Failed to log error for {agent_id}: {exc}")
        return {
            "success": False,
            "allowed": False,
            "violation": f"Failed to get governance approval: {exc}",
        }


def require_approval(
    agent_id: str,
    description: str,
    output: Optional[Any] = None,
    confidence: Optional[float] = None,
) -> dict[str, Any]:
    """Log activity and exit if governor blocks the pipeline."""
    approval = log_success(agent_id, description, output, confidence=confidence)
    if not approval.get("allowed", False):
        print(f"BLOCKED: {approval.get('violation', 'Governance violation')}")
        if approval.get("escalationId"):
            print(f"   Escalation: {approval['escalationId']}")
        sys.exit(1)
    return approval
