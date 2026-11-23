"""Check the built service image locally, without credentials or Azure access.

Usage: python3 tools/check_image.py <image>

Verifies the non-root UID/GID and the single exposed port, renders the migrations offline inside the
image and checks that the service becomes live with platform authentication settings and stops
cleanly on SIGTERM within the approved 60-second grace period.
"""

import json
import subprocess
import sys
import time
import urllib.request
import uuid

SMOKE_ENV = {
    "PIPESOR_ENVIRONMENT": "azure",
    "SERVER_ADDRESS": "0.0.0.0",
    "SERVER_PORT": "8080",
    "PIPESOR_RAG_STORAGE_BACKEND": "postgresql",
    "PIPESOR_DATABASE_URL": "postgresql+psycopg://rag@app.postgres.database.azure.com/pipesor",
    "PIPESOR_RAG_EMBEDDING_BACKEND": "azure_openai",
    "PIPESOR_RAG_EMBEDDING_MODEL_VERSION": "ci-smoke",
    "PIPESOR_RAG_AZURE_OPENAI_ENDPOINT": "https://ai-pipesor-dev-04f339b7.services.ai.azure.com",
    "PIPESOR_RAG_AZURE_OPENAI_DEPLOYMENT": "pipesor-dev-embeddings",
    "PIPESOR_RAG_AUTHENTICATION_MODE": "platform",
    "PIPESOR_TENANT_ID": "11111111-1111-4111-8111-111111111111",
    "PIPESOR_SECURITY_AUDIENCE": "urn:pipesor:api:rag",
    "PIPESOR_SECURITY_TRUSTEDWORKLOADS_0_ID": "recommendation",
    "PIPESOR_SECURITY_TRUSTEDWORKLOADS_0_JWKSURI": "https://recommendation.invalid/.well-known/jwks.json",
    "PIPESOR_SECURITY_TRUSTEDWORKLOADS_0_ROLES": "Rag.Query",
}


def docker(*args, check=True):
    return subprocess.run(["docker", *args], text=True, capture_output=True, check=check)


def require(condition, message):
    if not condition:
        raise SystemExit(f"Image check failed: {message}")


def check_image(image):
    config = json.loads(docker("image", "inspect", image, "--format", "{{json .Config}}").stdout)
    require(config.get("User") == "10001:10001", f"expected user 10001:10001, found {config.get('User')!r}")
    require(config.get("ExposedPorts") == {"8080/tcp": {}}, f"expected only 8080/tcp, found {config.get('ExposedPorts')}")

    migration = docker("run", "--rm", "--network", "none", "--entrypoint", "alembic", image,
                       "upgrade", "head", "--sql", check=False)
    require(migration.returncode == 0 and "CREATE TABLE" in migration.stdout,
            "offline migration rendering failed inside the image")

    name = f"pipesor-rag-check-{uuid.uuid4().hex[:12]}"
    env_args = [arg for key, value in SMOKE_ENV.items() for arg in ("--env", f"{key}={value}")]
    try:
        docker("run", "--detach", "--name", name, "--publish", "127.0.0.1::8080", *env_args, image)
        port = docker("port", name, "8080/tcp").stdout.splitlines()[0].rsplit(":", 1)[1]
        live = False
        for _ in range(30):
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/health/live", timeout=2) as response:
                    live = response.status == 200
            except OSError:
                live = False
            if live:
                break
            time.sleep(1)
        require(live, "service did not report /health/live")
        docker("stop", "--timeout", "60", name)
        exit_code = docker("inspect", name, "--format", "{{.State.ExitCode}}").stdout.strip()
        require(exit_code == "0", f"SIGTERM must stop the service cleanly, exit code {exit_code}")
    finally:
        docker("rm", "--force", name, check=False)
    print("Image checks passed: non-root 10001, port 8080, offline migrations, liveness, graceful SIGTERM")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    check_image(sys.argv[1])
