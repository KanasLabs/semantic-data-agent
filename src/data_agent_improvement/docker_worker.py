from __future__ import annotations

import json
import hashlib
import os
import re
import shutil
import subprocess
import tempfile
import uuid
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from data_subagent_context_builder.codex_runtime import (
    CodexCommandResult,
    _terminate_process_tree,
)

from .isolation import REQUIRED_ISOLATION_PROBES, create_isolation_receipt
from .models import BoundedCodexTask, IsolationReceipt


_IMAGE_ID_PATTERN = re.compile(r"sha256:[0-9a-f]{64}")
_NETWORK_NAME_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,62}")
_NETWORK_ERROR_MARKERS = (
    "could not resolve host",
    "failed to connect",
    "network is unreachable",
    "operation not permitted",
    "permission denied",
)


@dataclass(frozen=True)
class DockerWorkerConfig:
    image_id: str
    network: str
    https_proxy: str
    docker_bin: str = "docker"
    codex_model: str | None = None
    timeout_seconds: int = 900
    memory: str = "2g"
    cpus: str = "2"
    pids_limit: int = 128
    auth_env_name: str = "OPENAI_API_KEY"

    def __post_init__(self) -> None:
        if not _IMAGE_ID_PATTERN.fullmatch(self.image_id):
            raise ValueError("Docker SI2 worker requires an immutable sha256 image ID.")
        if (
            not _NETWORK_NAME_PATTERN.fullmatch(self.network)
            or self.network in {"bridge", "default", "host", "none"}
        ):
            raise ValueError(
                "Docker SI2 worker requires a dedicated provider-egress network."
            )
        if self.auth_env_name != "OPENAI_API_KEY":
            raise ValueError("Docker SI2 worker supports only OPENAI_API_KEY authentication.")
        proxy = urlsplit(self.https_proxy)
        if (
            proxy.scheme != "http"
            or not proxy.hostname
            or proxy.username is not None
            or proxy.password is not None
        ):
            raise ValueError(
                "Docker SI2 worker requires a credential-free HTTP egress proxy URL."
            )
        if self.timeout_seconds < 1 or self.pids_limit < 1:
            raise ValueError("Docker SI2 worker limits must be positive.")

    @property
    def backend(self) -> str:
        proxy_hash = hashlib.sha256(self.https_proxy.encode("utf-8")).hexdigest()
        return (
            f"docker:{self.image_id}:network:{self.network}:"
            f"proxy-sha256:{proxy_hash}"
        )


class DockerCodexRunner:
    def __init__(
        self,
        *,
        config: DockerWorkerConfig,
        candidate_root: Path,
        evidence_root: Path,
        output_schema_path: Path,
        path_replacements: dict[Path, str] | None = None,
    ) -> None:
        self.config = config
        self.candidate_root = candidate_root.resolve()
        self.evidence_root = evidence_root.resolve()
        self.output_schema_path = output_schema_path.resolve()
        self.path_replacements = {
            path.resolve(): replacement
            for path, replacement in (path_replacements or {}).items()
        }

    def run(self, prompt: str, *, last_message_path: Path | None = None) -> CodexCommandResult:
        if not os.environ.get(self.config.auth_env_name):
            return CodexCommandResult(
                args=[],
                returncode=126,
                stdout="",
                stderr=f"Required Docker Codex auth is missing: {self.config.auth_env_name}",
                last_message_path=str(last_message_path) if last_message_path else None,
            )
        container_name = f"si2-codex-{uuid.uuid4().hex[:20]}"
        args = self.build_args(container_name=container_name, last_message_path=last_message_path)
        resolved_docker = shutil.which(self.config.docker_bin) or self.config.docker_bin
        command = [resolved_docker, *args]
        creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
        with tempfile.TemporaryFile() as stdout_file, tempfile.TemporaryFile() as stderr_file:
            try:
                process = subprocess.Popen(
                    command,
                    stdin=subprocess.PIPE,
                    stdout=stdout_file,
                    stderr=stderr_file,
                    creationflags=creation_flags,
                    start_new_session=os.name != "nt",
                    env=_docker_environment(self.config.auth_env_name),
                )
            except OSError as exc:
                return CodexCommandResult(
                    args=args,
                    returncode=127,
                    stdout="",
                    stderr=f"Failed to start Docker executable {resolved_docker!r}: {exc}",
                    last_message_path=str(last_message_path) if last_message_path else None,
                )
            timed_out = False
            try:
                process.communicate(
                    input=self.containerize_prompt(prompt).encode("utf-8"),
                    timeout=self.config.timeout_seconds,
                )
            except subprocess.TimeoutExpired:
                timed_out = True
                _terminate_process_tree(process)
                _run_quiet(
                    [resolved_docker, "rm", "--force", container_name],
                    timeout_seconds=20,
                )
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            stdout_file.seek(0)
            stderr_file.seek(0)
            stdout = stdout_file.read().decode("utf-8", errors="replace")
            stderr = stderr_file.read().decode("utf-8", errors="replace")
        if timed_out:
            stderr = (
                f"{stderr.rstrip()}\nDocker Codex worker timed out after "
                f"{self.config.timeout_seconds} seconds."
            ).strip()
        return CodexCommandResult(
            args=args,
            returncode=124 if timed_out else process.returncode,
            stdout=stdout,
            stderr=stderr,
            last_message_path=str(last_message_path) if last_message_path else None,
        )

    def build_args(
        self,
        *,
        container_name: str,
        last_message_path: Path | None = None,
    ) -> list[str]:
        _require_mountable(self.candidate_root, directory=True)
        _require_mountable(self.evidence_root, directory=True)
        _require_mountable(self.output_schema_path, directory=False)
        args = [
            "run",
            "--rm",
            "--interactive",
            "--name",
            container_name,
            "--hostname",
            "si2-codex-worker",
            "--pull",
            "never",
            "--read-only",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges:true",
            "--pids-limit",
            str(self.config.pids_limit),
            "--memory",
            self.config.memory,
            "--cpus",
            self.config.cpus,
            "--network",
            self.config.network,
            "--user",
            "10001:10001",
            "--tmpfs",
            "/tmp:rw,nosuid,nodev,size=268435456,uid=10001,gid=10001",
            "--mount",
            _mount(self.candidate_root, "/workspace", read_only=False),
            "--mount",
            _mount(self.evidence_root, "/evidence", read_only=True),
            "--mount",
            _mount(self.output_schema_path, "/control/output.schema.json", read_only=True),
            "--env",
            self.config.auth_env_name,
            "--env",
            "CODEX_HOME=/tmp/codex-home",
            "--env",
            "HOME=/tmp/home",
            "--env",
            f"HTTPS_PROXY={self.config.https_proxy}",
            "--env",
            f"HTTP_PROXY={self.config.https_proxy}",
            "--env",
            "NO_PROXY=",
            "--workdir",
            "/workspace",
            self.config.image_id,
            "-c",
            "sandbox_workspace_write.network_access=false",
            "-c",
            "shell_environment_policy.inherit=none",
            "-c",
            "check_for_update_on_startup=false",
            "--ask-for-approval",
            "never",
            "exec",
            "--strict-config",
            "--cd",
            "/workspace",
            "--sandbox",
            "workspace-write",
            "--color",
            "never",
            "--ephemeral",
            "--ignore-user-config",
            "--ignore-rules",
            "--skip-git-repo-check",
            "--output-schema",
            "/control/output.schema.json",
        ]
        if self.config.codex_model:
            args.extend(["--model", self.config.codex_model])
        if last_message_path is not None:
            relative = last_message_path.resolve().relative_to(self.candidate_root)
            args.extend(["--output-last-message", f"/workspace/{relative.as_posix()}"])
        args.append("-")
        return args

    def containerize_prompt(self, prompt: str) -> str:
        replacements = dict(self.path_replacements)
        replacements[self.candidate_root] = "/workspace"
        replacements[self.evidence_root] = "/evidence"
        replacements[self.output_schema_path.parent] = "/control"
        rewritten = prompt
        for path, replacement in sorted(
            replacements.items(), key=lambda item: len(str(item[0])), reverse=True
        ):
            rewritten = rewritten.replace(str(path), replacement)
        boundary = "\n".join(
            [
                "Docker SI2 execution boundary:",
                "- /workspace is the only writable host mount.",
                "- /evidence is the only business-evidence mount and is read-only.",
                "- The repository, Registry, base snapshot, database, and host credentials are not mounted.",
                "- Do not attempt unavailable host paths or Wren commands; the outer controller runs Wren validation and evals.",
                "- Model-generated tools have network disabled; only the Codex provider control plane is reachable.",
                "",
            ]
        )
        return boundary + rewritten


def resolve_docker_image_id(*, image: str, docker_bin: str = "docker") -> str:
    result = _run_quiet(
        [docker_bin, "image", "inspect", "--format", "{{.Id}}", image],
        timeout_seconds=30,
    )
    image_id = result.stdout.strip()
    if result.returncode != 0 or not _IMAGE_ID_PATTERN.fullmatch(image_id):
        raise RuntimeError(
            f"Docker worker image is unavailable or not immutable: {result.stderr.strip()}"
        )
    return image_id


def issue_docker_isolation_receipt(
    *,
    job: BoundedCodexTask,
    config: DockerWorkerConfig,
    project_root: Path,
    environment_id: str,
    issuer: str,
    hmac_key: str,
) -> IsolationReceipt:
    evidence_root = Path(job.read_only_roots[0]).resolve()
    if not (evidence_root / "manifest.json").is_file():
        raise FileNotFoundError("Docker isolation probe requires the packaged evidence manifest.")
    temporary_root = project_root.resolve() / "data" / "tmp"
    temporary_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="si2-docker-probe-", dir=temporary_root) as name:
        candidate_probe = Path(name) / "candidate"
        candidate_probe.mkdir()
        _probe_filesystem(
            config=config,
            candidate_root=candidate_probe,
            evidence_root=evidence_root,
        )
        _probe_provider_egress(config=config)
        _probe_tool_network_and_credentials(config=config)
    probes = {name: True for name in REQUIRED_ISOLATION_PROBES}
    return create_isolation_receipt(
        job=job,
        environment_id=environment_id,
        issuer=issuer,
        backend=config.backend,
        hmac_key=hmac_key,
        probes=probes,
        ttl=timedelta(minutes=10),
    )


def write_isolation_receipt(*, receipt: IsolationReceipt, path: Path) -> Path:
    resolved = path.resolve()
    resolved.parent.mkdir(parents=True, exist_ok=True)
    if resolved.exists():
        raise FileExistsError(f"Isolation receipt already exists: {resolved}")
    payload = json.dumps(receipt.to_dict(), ensure_ascii=False, indent=2) + "\n"
    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{resolved.name}.", suffix=".tmp", dir=resolved.parent
    )
    try:
        with os.fdopen(file_descriptor, "w", encoding="utf-8") as temporary_file:
            temporary_file.write(payload)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        os.replace(temporary_name, resolved)
    except BaseException:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise
    return resolved


def _probe_filesystem(
    *,
    config: DockerWorkerConfig,
    candidate_root: Path,
    evidence_root: Path,
) -> None:
    script = " && ".join(
        [
            "set -eu",
            "test -r /evidence/manifest.json",
            "touch /workspace/.si2-write-probe",
            "rm /workspace/.si2-write-probe",
            "if touch /evidence/.si2-write-probe 2>/dev/null; then exit 21; fi",
            "test ! -e /base",
            "if touch /outside-si2-probe 2>/dev/null; then exit 22; fi",
        ]
    )
    result = _run_quiet(
        [
            config.docker_bin,
            "run",
            "--rm",
            "--pull",
            "never",
            "--read-only",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges:true",
            "--network",
            "none",
            "--user",
            "10001:10001",
            "--tmpfs",
            "/tmp:rw,nosuid,nodev,size=67108864,uid=10001,gid=10001",
            "--mount",
            _mount(candidate_root, "/workspace", read_only=False),
            "--mount",
            _mount(evidence_root, "/evidence", read_only=True),
            "--entrypoint",
            "sh",
            config.image_id,
            "-c",
            script,
        ],
        timeout_seconds=60,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Docker filesystem isolation probe failed: {result.stderr.strip()}")


def _probe_tool_network_and_credentials(*, config: DockerWorkerConfig) -> None:
    suffix = uuid.uuid4().hex[:16]
    network_name = f"si2-probe-{suffix}"
    server_name = f"si2-probe-server-{suffix}"
    network_created = False
    server_created = False
    try:
        created = _run_quiet(
            [config.docker_bin, "network", "create", network_name],
            timeout_seconds=30,
        )
        if created.returncode != 0:
            raise RuntimeError(f"Docker probe network creation failed: {created.stderr.strip()}")
        network_created = True
        server = _run_quiet(
            [
                config.docker_bin,
                "run",
                "--detach",
                "--rm",
                "--name",
                server_name,
                "--network",
                network_name,
                "--read-only",
                "--cap-drop",
                "ALL",
                "--security-opt",
                "no-new-privileges:true",
                "--entrypoint",
                "node",
                config.image_id,
                "-e",
                "require('http').createServer((q,r)=>r.end('ok')).listen(8080,'0.0.0.0')",
            ],
            timeout_seconds=30,
        )
        if server.returncode != 0:
            raise RuntimeError(f"Docker probe server failed: {server.stderr.strip()}")
        server_created = True
        ready = _run_quiet(
            [
                config.docker_bin,
                "run",
                "--rm",
                "--network",
                network_name,
                "--entrypoint",
                "curl",
                config.image_id,
                "--silent",
                "--show-error",
                "--retry",
                "10",
                "--retry-connrefused",
                "--retry-delay",
                "1",
                f"http://{server_name}:8080/",
            ],
            timeout_seconds=30,
        )
        if ready.returncode != 0 or ready.stdout.strip() != "ok":
            raise RuntimeError("Docker network canary was not reachable before sandboxing.")
        denied = _run_quiet(
            [
                config.docker_bin,
                "run",
                "--rm",
                "--network",
                network_name,
                "--read-only",
                "--tmpfs",
                "/tmp:rw,nosuid,nodev,size=67108864,uid=10001,gid=10001",
                "--env",
                "HOME=/tmp/home",
                "--entrypoint",
                "codex",
                config.image_id,
                "-c",
                "sandbox_workspace_write.network_access=false",
                "sandbox",
                "--sandbox-state-disable-network",
                "--",
                "curl",
                "--silent",
                "--show-error",
                "--connect-timeout",
                "3",
                f"http://{server_name}:8080/",
            ],
            timeout_seconds=30,
        )
        denial_text = f"{denied.stdout}\n{denied.stderr}".lower()
        if denied.returncode == 0 or not any(
            marker in denial_text for marker in _NETWORK_ERROR_MARKERS
        ):
            raise RuntimeError("Codex tool-network denial probe did not produce a verified denial.")
        credentials = _run_quiet(
            [
                config.docker_bin,
                "run",
                "--rm",
                "--network",
                "none",
                "--read-only",
                "--tmpfs",
                "/tmp:rw,nosuid,nodev,size=67108864,uid=10001,gid=10001",
                "--env",
                "HOME=/tmp/home",
                "--env",
                "OPENAI_API_KEY=probe-only-secret",
                "--entrypoint",
                "codex",
                config.image_id,
                "-c",
                "shell_environment_policy.inherit=none",
                "sandbox",
                "--",
                "sh",
                "-c",
                "test -z \"${OPENAI_API_KEY:-}\"",
            ],
            timeout_seconds=30,
        )
        if credentials.returncode != 0:
            raise RuntimeError("Codex child credential-minimization probe failed.")
    finally:
        if server_created:
            _run_quiet(
                [config.docker_bin, "rm", "--force", server_name],
                timeout_seconds=20,
            )
        if network_created:
            _run_quiet(
                [config.docker_bin, "network", "rm", network_name],
                timeout_seconds=20,
            )


def _probe_provider_egress(*, config: DockerWorkerConfig) -> None:
    inspected = _run_quiet(
        [
            config.docker_bin,
            "network",
            "inspect",
            "--format",
            "{{.Internal}}",
            config.network,
        ],
        timeout_seconds=30,
    )
    if inspected.returncode != 0 or inspected.stdout.strip().lower() != "true":
        raise RuntimeError("Docker provider-egress network must exist and be internal.")
    common = [
        config.docker_bin,
        "run",
        "--rm",
        "--network",
        config.network,
        "--read-only",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges:true",
        "--env",
        f"HTTPS_PROXY={config.https_proxy}",
        "--env",
        f"HTTP_PROXY={config.https_proxy}",
        "--entrypoint",
        "curl",
        config.image_id,
    ]
    openai = _run_quiet(
        [
            *common,
            "--silent",
            "--show-error",
            "--output",
            "/dev/null",
            "--write-out",
            "%{http_code}",
            "--connect-timeout",
            "10",
            "https://api.openai.com/v1/models",
        ],
        timeout_seconds=30,
    )
    if openai.returncode != 0 or openai.stdout.strip() not in {"200", "401", "403", "429"}:
        raise RuntimeError("Docker egress proxy cannot reach the OpenAI API control plane.")
    blocked = _run_quiet(
        [
            *common,
            "--silent",
            "--show-error",
            "--fail",
            "--connect-timeout",
            "10",
            "https://example.com/",
        ],
        timeout_seconds=30,
    )
    if blocked.returncode == 0:
        raise RuntimeError("Docker egress proxy allowed a non-OpenAI destination.")
    direct = _run_quiet(
        [
            *common,
            "--noproxy",
            "*",
            "--silent",
            "--show-error",
            "--connect-timeout",
            "3",
            "https://api.openai.com/v1/models",
        ],
        timeout_seconds=15,
    )
    if direct.returncode == 0:
        raise RuntimeError("Docker internal network unexpectedly allowed direct internet egress.")


def _mount(source: Path, target: str, *, read_only: bool) -> str:
    source_text = str(source.resolve())
    if "," in source_text:
        raise ValueError("Docker bind-mount source paths must not contain commas.")
    mode = ",readonly" if read_only else ""
    return f"type=bind,source={source_text},target={target}{mode}"


def _require_mountable(path: Path, *, directory: bool) -> None:
    exists = path.is_dir() if directory else path.is_file()
    if not exists:
        kind = "directory" if directory else "file"
        raise FileNotFoundError(f"Docker bind-mount {kind} not found: {path}")


def _docker_environment(auth_env_name: str | None = None) -> dict[str, str]:
    allowed = {
        "APPDATA",
        "COMSPEC",
        "DOCKER_CONFIG",
        "DOCKER_CONTEXT",
        "DOCKER_HOST",
        "HOME",
        "LOCALAPPDATA",
        "PATH",
        "PATHEXT",
        "SYSTEMROOT",
        "TEMP",
        "TMP",
        "USERPROFILE",
        "WINDIR",
    }
    if auth_env_name:
        allowed.add(auth_env_name)
    return {key: value for key, value in os.environ.items() if key.upper() in allowed}


def _run_quiet(args: list[str], *, timeout_seconds: int) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            args,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
            check=False,
            env=_docker_environment(),
        )
    except subprocess.TimeoutExpired as exc:
        return subprocess.CompletedProcess(
            args=args,
            returncode=124,
            stdout=str(exc.stdout or ""),
            stderr=f"Docker command timed out after {timeout_seconds} seconds.",
        )
