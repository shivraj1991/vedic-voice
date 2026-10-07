"""Client for the scoring service (separate Lambda container image).

The backend depends on scoring only through this request/response contract
(CLAUDE.md: no imports of vv_scoring internals). The scoring Lambda is not
publicly invokable; the API calls it with IAM (boto3 `lambda.invoke`).

Request:
    {"recording": {"bucket": "recordings", "key": "rec/tmp/..."},
     "reference": {"bucket": "reference", "key": "ref/..."},
     "text_iast": "tat savitur ...",
     "words": [{"position": 0, "surface_iast": "tat"}, ...]}
Response:
    {"overall": 0-100, "match_confidence": 0-1, "scorer_version": "vv-gop-0.1.0",
     "duration_ms": int,
     "words": [{"position": 0, "score": 0-100, "issue_code": str|null,
                "issue_text": str|null, "start_ms": int, "end_ms": int}, ...]}
    or {"error": "audio_invalid" | "audio_too_long" | ..., "message": "..."}
"""

from __future__ import annotations

import json
from typing import Any, Protocol


class ScoringError(Exception):
    def __init__(self, code: str, message: str = ""):
        super().__init__(message or code)
        self.code = code


class Scorer(Protocol):
    def score(self, request: dict[str, Any]) -> dict[str, Any]: ...


class LambdaScorer:
    def __init__(self, function_name: str, region: str | None):
        import boto3
        from botocore.config import Config

        cfg = Config(read_timeout=60, connect_timeout=5, retries={"max_attempts": 1})
        self._client = boto3.client("lambda", region_name=region, config=cfg)
        self._fn = function_name

    def score(self, request: dict[str, Any]) -> dict[str, Any]:
        resp = self._client.invoke(FunctionName=self._fn, Payload=json.dumps(request).encode())
        body = json.loads(resp["Payload"].read() or b"{}")
        if resp.get("FunctionError"):
            raise ScoringError("scoring_failed")
        if "error" in body:
            raise ScoringError(body["error"], body.get("message", ""))
        return body


class FakeScorer:
    """Deterministic stand-in: every word scores `score`; optional issue on one word."""

    def __init__(self, score: int = 90, weak_position: int | None = None, match: float = 0.95):
        self.calls: list[dict[str, Any]] = []
        self._score, self._weak, self._match = score, weak_position, match

    def score(self, request: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(request)
        words = []
        for w in request["words"]:
            weak = w["position"] == self._weak
            words.append(
                {
                    "position": w["position"],
                    "score": 50 if weak else self._score,
                    "issue_code": "aspiration_missing" if weak else None,
                    "issue_text": f'In "{w["surface_iast"]}": add a breath' if weak else None,
                    "start_ms": 500 * w["position"],
                    "end_ms": 500 * w["position"] + 450,
                }
            )
        overall = round(sum(w["score"] for w in words) / max(len(words), 1))
        return {"overall": overall, "match_confidence": self._match, "scorer_version": "fake-1",
                "duration_ms": 500 * len(words), "words": words}  # fmt: skip
