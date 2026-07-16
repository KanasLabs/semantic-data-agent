from __future__ import annotations

import os
import hashlib
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from data_agent_improvement.docker_worker import (
    DockerCodexRunner,
    DockerWorkerConfig,
    issue_docker_isolation_receipt,
    resolve_docker_image_id,
    write_isolation_receipt,
    _docker_environment,
)
from data_agent_improvement.isolation import REQUIRED_ISOLATION_PROBES
from data_agent_improvement.models import BoundedCodexTask, JobStatus, JobTargetType


IMAGE_ID = "sha256:" + "a" * 64
HMAC_KEY = "docker-worker-test-key-material-at-least-32-bytes"
HTTPS_PROXY = "http://si2-egress-proxy:3128"


class ImprovementDockerWorkerTest(unittest.TestCase):
    def test_config_requires_immutable_image_and_dedicated_network(self):
        with self.assertRaisesRegex(ValueError, "immutable sha256"):
            DockerWorkerConfig(
                image_id="worker:latest",
                network="si2-egress",
                https_proxy=HTTPS_PROXY,
            )
        with self.assertRaisesRegex(ValueError, "dedicated provider-egress"):
            DockerWorkerConfig(
                image_id=IMAGE_ID,
                network="bridge",
                https_proxy=HTTPS_PROXY,
            )
        with self.assertRaisesRegex(ValueError, "credential-free HTTP"):
            DockerWorkerConfig(
                image_id=IMAGE_ID,
                network="si2-egress",
                https_proxy="http://user:secret@proxy:3128",
            )

    def test_runner_builds_hardened_mount_and_codex_command(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            candidate = root / "candidate"
            evidence = root / "evidence"
            control = root / "control"
            candidate.mkdir()
            evidence.mkdir()
            control.mkdir()
            schema = control / "schema.json"
            schema.write_text("{}\n", encoding="utf-8")
            runner = DockerCodexRunner(
                config=DockerWorkerConfig(
                    image_id=IMAGE_ID,
                    network="si2-provider-egress",
                    https_proxy=HTTPS_PROXY,
                ),
                candidate_root=candidate,
                evidence_root=evidence,
                output_schema_path=schema,
            )
            args = runner.build_args(container_name="si2-test")
            combined = "\n".join(args)
            self.assertIn("--read-only", args)
            self.assertIn("no-new-privileges:true", args)
            self.assertIn("ALL", args)
            self.assertIn("si2-provider-egress", args)
            self.assertIn("sandbox_workspace_write.network_access=false", args)
            self.assertIn("shell_environment_policy.inherit=none", args)
            self.assertIn("check_for_update_on_startup=false", args)
            self.assertIn(f"HTTPS_PROXY={HTTPS_PROXY}", args)
            self.assertIn("--ignore-user-config", args)
            self.assertIn("--ignore-rules", args)
            self.assertIn("--ephemeral", args)
            self.assertIn("target=/workspace", combined)
            self.assertIn("target=/evidence,readonly", combined)
            self.assertIn("target=/control/output.schema.json,readonly", combined)
            self.assertNotIn("probe-only-secret", combined)

    def test_runner_rewrites_host_paths_and_states_container_boundary(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            candidate = root / "candidate"
            evidence = root / "evidence"
            candidate.mkdir()
            evidence.mkdir()
            schema = root / "schema.json"
            schema.write_text("{}\n", encoding="utf-8")
            unmounted = root / "repository"
            runner = DockerCodexRunner(
                config=DockerWorkerConfig(
                    image_id=IMAGE_ID,
                    network="si2-provider-egress",
                    https_proxy=HTTPS_PROXY,
                ),
                candidate_root=candidate,
                evidence_root=evidence,
                output_schema_path=schema,
                path_replacements={unmounted: "/not-mounted/project"},
            )
            prompt = runner.containerize_prompt(
                f"Edit {candidate}. Read {evidence}. Ignore {unmounted}."
            )
            self.assertIn("/workspace", prompt)
            self.assertIn("/evidence", prompt)
            self.assertIn("/not-mounted/project", prompt)
            self.assertNotIn(str(candidate), prompt)
            self.assertIn("repository, Registry, base snapshot", prompt)

    def test_runner_does_not_start_without_auth_environment(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            candidate = root / "candidate"
            evidence = root / "evidence"
            candidate.mkdir()
            evidence.mkdir()
            schema = root / "schema.json"
            schema.write_text("{}\n", encoding="utf-8")
            runner = DockerCodexRunner(
                config=DockerWorkerConfig(
                    image_id=IMAGE_ID,
                    network="si2-provider-egress",
                    https_proxy=HTTPS_PROXY,
                ),
                candidate_root=candidate,
                evidence_root=evidence,
                output_schema_path=schema,
            )
            with patch.dict(os.environ, {}, clear=True):
                result = runner.run("bounded task")
            self.assertEqual(result.returncode, 126)
            self.assertIn("OPENAI_API_KEY", result.stderr)

    def test_docker_process_environment_excludes_unrelated_secrets(self):
        with patch.dict(
            os.environ,
            {
                "PATH": "docker-tools",
                "OPENAI_API_KEY": "openai-parent-secret",
                "DEEPSEEK_API_KEY": "deepseek-secret",
                "CONTEXT_BUILDER_STARROCKS_PASSWORD": "database-secret",
                "DATA_AGENT_ISOLATION_HMAC_KEY": "isolation-secret",
            },
            clear=True,
        ):
            environment = _docker_environment("OPENAI_API_KEY")
        self.assertEqual(environment["PATH"], "docker-tools")
        self.assertEqual(environment["OPENAI_API_KEY"], "openai-parent-secret")
        self.assertNotIn("DEEPSEEK_API_KEY", environment)
        self.assertNotIn("CONTEXT_BUILDER_STARROCKS_PASSWORD", environment)
        self.assertNotIn("DATA_AGENT_ISOLATION_HMAC_KEY", environment)

    def test_probe_issues_receipt_bound_to_immutable_image(self):
        with tempfile.TemporaryDirectory() as temporary_dir:
            root = Path(temporary_dir)
            evidence = root / "registry" / "jobs" / ("job_" + "1" * 32) / "evidence"
            evidence.mkdir(parents=True)
            (evidence / "manifest.json").write_text("{}\n", encoding="utf-8")
            base = root / "base"
            base.mkdir()
            job = _job(evidence=evidence, base=base)
            config = DockerWorkerConfig(
                image_id=IMAGE_ID,
                network="si2-provider-egress",
                https_proxy=HTTPS_PROXY,
            )
            with (
                patch("data_agent_improvement.docker_worker._probe_filesystem") as filesystem,
                patch(
                    "data_agent_improvement.docker_worker._probe_provider_egress"
                ) as provider_egress,
                patch(
                    "data_agent_improvement.docker_worker._probe_tool_network_and_credentials"
                ) as network,
            ):
                receipt = issue_docker_isolation_receipt(
                    job=job,
                    config=config,
                    project_root=root,
                    environment_id="docker-test-environment",
                    issuer="ci-worker",
                    hmac_key=HMAC_KEY,
                )
            filesystem.assert_called_once()
            provider_egress.assert_called_once_with(config=config)
            network.assert_called_once_with(config=config)
            self.assertEqual(
                receipt.backend,
                f"docker:{IMAGE_ID}:network:si2-provider-egress:proxy-sha256:"
                f"{hashlib.sha256(HTTPS_PROXY.encode('utf-8')).hexdigest()}",
            )
            self.assertTrue(all(receipt.probes[name] for name in REQUIRED_ISOLATION_PROBES))
            path = write_isolation_receipt(receipt=receipt, path=root / "receipt.json")
            self.assertTrue(path.is_file())

    def test_resolve_image_returns_docker_content_id(self):
        completed = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=f"{IMAGE_ID}\n", stderr=""
        )
        with patch(
            "data_agent_improvement.docker_worker._run_quiet",
            return_value=completed,
        ):
            self.assertEqual(resolve_docker_image_id(image="worker:tag"), IMAGE_ID)


def _job(*, evidence: Path, base: Path) -> BoundedCodexTask:
    return BoundedCodexTask(
        schema_version=1,
        job_id="job_" + "1" * 32,
        finding_id="finding_" + "2" * 32,
        eval_target_id="evaltarget_" + "3" * 32,
        eval_target_sha256="sha256:" + "4" * 64,
        target_type=JobTargetType.WREN_CONTEXT,
        risk_level="MEDIUM",
        base_candidate_id="candidate_" + "5" * 32,
        read_only_roots=[str(evidence), str(base)],
        evidence_manifest_sha256="sha256:" + "6" * 64,
        data_identity={"schema_fingerprint": "sha256:" + "7" * 64},
        writable_root="context_builder_candidate_workspace",
        allowed_paths=["models/**"],
        forbidden_paths=["src/**"],
        required_suites=["frozen_target"],
        target_eval_repetitions=3,
        timeout_seconds=900,
        max_repair_rounds=2,
        database_access=False,
        network_access=False,
        status=JobStatus.PREPARED,
        created_at="2026-07-16T00:00:00+00:00",
    )


if __name__ == "__main__":
    unittest.main()
