from __future__ import annotations

import json
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def test_cloudflare_worker_delivery_contract() -> None:
    package = json.loads((REPOSITORY_ROOT / "package.json").read_text(encoding="utf-8"))
    wrangler = (REPOSITORY_ROOT / "wrangler.jsonc").read_text(encoding="utf-8")
    worker = (REPOSITORY_ROOT / "cloudflare/worker.ts").read_text(encoding="utf-8")
    headers = (REPOSITORY_ROOT / "apps/web/public/_headers").read_text(encoding="utf-8")
    validator = (REPOSITORY_ROOT / "packages/contracts/src/validator.generated.ts").read_text(
        encoding="utf-8"
    )

    scripts = package["scripts"]
    assert "wrangler deploy --dry-run" in scripts["cf:check"]
    assert scripts["cf:deploy"].endswith("wrangler deploy")
    assert '"compatibility_date": "2026-07-12"' in wrangler
    assert '"compatibility_flags": ["nodejs_compat"]' in wrangler
    assert '"not_found_handling": "single-page-application"' in wrangler
    assert '"binding": "ASSETS"' in wrangler
    assert '"MESH2PARAM_API_ORIGIN": ""' in wrangler
    assert "new Response(upstreamResponse.body" in worker
    assert "return env.ASSETS.fetch(request)" in worker
    assert "api_origin_not_configured" in worker
    assert 'url.protocol === "https:"' in worker
    assert 'url.protocol === "http:" && isLoopbackHostname(url.hostname)' in worker
    assert 'normalized === "localhost"' in worker
    assert 'normalized === "127.0.0.1"' in worker
    assert 'normalized === "[::1]"' in worker
    assert "valid HTTPS or loopback HTTP origin" in worker
    assert "Content-Security-Policy: default-src 'self'" in headers
    document_policy = headers.split("/assets/*", 1)[0]
    assert "'unsafe-eval'" not in document_policy
    # The Rust WASM worker no longer needs Emscripten's JavaScript eval exception.
    # Require WASM compilation while forbidding JavaScript eval on every route.
    assert "'unsafe-eval'" not in headers
    assert "script-src 'self' 'wasm-unsafe-eval'" in document_policy
    assert "Cache-Control: public, max-age=31536000, immutable" in headers
    assert "ajv.compile" not in validator
    assert 'from "ajv/dist/2020.js"' not in validator
