from __future__ import annotations

import json
import unittest

from data_agent_improvement.codex_executor import _candidate_execution_from_result
from data_agent_improvement.evaluation import (
    CandidateEvaluation,
    CandidateEvaluationReason,
    CandidateEvaluationStatus,
    classify_candidate_evaluation,
)


class CandidateEvaluationTest(unittest.TestCase):
    def test_correct_candidate_passes(self):
        evaluation = classify_candidate_evaluation(
            {
                "ok": True,
                "smoke": {"ok": True},
                "regression": {"ok": True, "suites": []},
            }
        )

        self.assertEqual(evaluation.status, CandidateEvaluationStatus.PASS)
        self.assertEqual(
            evaluation.reason,
            CandidateEvaluationReason.ACCEPTANCE_PASSED,
        )
        self.assertEqual(
            CandidateEvaluation.from_dict(json.loads(json.dumps(evaluation.to_dict()))),
            evaluation,
        )

    def test_wrong_unit_assertion_fails(self):
        evaluation = classify_candidate_evaluation(
            {
                "ok": False,
                "smoke": {"ok": True},
                "regression": {
                    "ok": False,
                    "suites": [
                        {
                            "ok": False,
                            "execution": {
                                "ok": False,
                                "returncode": 0,
                                "summary": {"total": 1, "passed": 0, "failed": 1},
                            },
                        }
                    ],
                },
            }
        )

        self.assertEqual(evaluation.status, CandidateEvaluationStatus.FAIL)
        self.assertEqual(
            evaluation.reason,
            CandidateEvaluationReason.ASSERTION_FAILED,
        )

    def test_starrocks_connection_error_is_blocked(self):
        evaluation = classify_candidate_evaluation(
            {
                "ok": False,
                "smoke": {
                    "ok": False,
                    "execution": {
                        "ok": False,
                        "returncode": 1,
                        "stderr": (
                            "Error: (2002, \"Can't connect to server on "
                            "'127.0.0.1' (10061)\")"
                        ),
                    },
                },
                "regression": {"ok": False, "suites": []},
            }
        )

        self.assertEqual(evaluation.status, CandidateEvaluationStatus.BLOCKED)
        self.assertEqual(
            evaluation.reason,
            CandidateEvaluationReason.INFRASTRUCTURE_UNAVAILABLE,
        )

    def test_missing_regression_suite_invalidates_target(self):
        evaluation = classify_candidate_evaluation(
            {
                "ok": False,
                "smoke": {"ok": True},
                "regression": {
                    "ok": False,
                    "suites": [
                        {
                            "ok": False,
                            "suite_path": "missing_frozen_target.jsonl",
                            "error": "Regression suite not found.",
                        }
                    ],
                },
            }
        )

        self.assertEqual(evaluation.status, CandidateEvaluationStatus.BLOCKED)
        self.assertEqual(
            evaluation.reason,
            CandidateEvaluationReason.EVAL_TARGET_INVALID,
        )

    def test_codex_executor_normalizes_infrastructure_block(self):
        execution = _candidate_execution_from_result(
            {
                "ok": False,
                "revision_status": "SMOKE_FAILED",
                "eval": {
                    "ok": False,
                    "smoke": {
                        "ok": False,
                        "execution": {
                            "ok": False,
                            "returncode": 1,
                            "stderr": "Can't connect to server on '127.0.0.1' (10061)",
                        },
                    },
                    "regression": {"ok": False, "suites": []},
                },
            }
        )

        self.assertFalse(execution.ok)
        self.assertEqual(execution.outcome, "inconclusive")
        self.assertEqual(
            execution.evaluation.reason,
            CandidateEvaluationReason.INFRASTRUCTURE_UNAVAILABLE,
        )

    def test_clarification_does_not_claim_an_evaluation_result(self):
        execution = _candidate_execution_from_result(
            {
                "ok": False,
                "revision_status": "CLARIFICATION_REQUIRED",
                "eval": None,
            }
        )

        self.assertEqual(execution.outcome, "clarification_required")
        self.assertIsNone(execution.evaluation)


if __name__ == "__main__":
    unittest.main()
