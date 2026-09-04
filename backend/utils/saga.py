"""
CV. Dewi Aditya ERP — Saga / Compensation Pattern
Batch 2 — E-2: Transaction/Atomicity

Since MongoDB is running in standalone mode (no replica set), native multi-document
transactions are not available. This module implements a Saga pattern with:
  - Sequential execution of steps
  - Automatic compensation (rollback) on failure
  - Structured error reporting

Usage:
    from utils.saga import SagaExecutor, SagaStep

    executor = SagaExecutor()
    executor.add_step(
        name="insert_payslips",
        action=lambda: db.payslips.insert_many(payslips),
        compensate=lambda: db.payslips.delete_many({"run_id": run_id}),
    )
    executor.add_step(
        name="insert_run_header",
        action=lambda: db.payroll_runs.insert_one(run_doc),
        compensate=lambda: db.payroll_runs.delete_one({"id": run_id}),
    )
    result = await executor.execute()
    if not result.success:
        raise HTTPException(500, result.error_detail)
"""
import logging
from dataclasses import dataclass, field
from typing import List, Optional, Any, Callable, Awaitable

log = logging.getLogger(__name__)


@dataclass
class SagaStep:
    name: str
    action: Callable[[], Awaitable[Any]]
    compensate: Optional[Callable[[], Awaitable[None]]] = None
    result: Any = None


@dataclass
class SagaResult:
    success: bool
    failed_step: Optional[str] = None
    error_detail: Optional[str] = None
    step_results: dict = field(default_factory=dict)
    compensated: bool = False
    compensation_errors: List[str] = field(default_factory=list)


class SagaExecutor:
    """
    Executes a series of async steps. On failure, compensates completed steps in reverse order.
    """

    def __init__(self, name: str = "saga"):
        self.name = name
        self._steps: List[SagaStep] = []

    def add_step(
        self,
        name: str,
        action: Callable[[], Awaitable[Any]],
        compensate: Optional[Callable[[], Awaitable[None]]] = None,
    ) -> "SagaExecutor":
        """Add a step to the saga. Returns self for chaining."""
        self._steps.append(SagaStep(name=name, action=action, compensate=compensate))
        return self

    async def execute(self) -> SagaResult:
        """Execute all steps. Compensate in reverse order on failure."""
        completed: List[SagaStep] = []
        result = SagaResult(success=False)

        for step in self._steps:
            try:
                log.debug(f"[Saga:{self.name}] Executing step: {step.name}")
                step.result = await step.action()
                result.step_results[step.name] = step.result
                completed.append(step)
            except Exception as exc:
                log.error(
                    f"[Saga:{self.name}] Step '{step.name}' failed: {type(exc).__name__}: {exc}"
                )
                result.failed_step = step.name
                result.error_detail = f"Step '{step.name}' failed: {exc}"

                # Compensate completed steps in reverse order
                if completed:
                    log.warning(
                        f"[Saga:{self.name}] Compensating {len(completed)} completed step(s)..."
                    )
                    for completed_step in reversed(completed):
                        if completed_step.compensate:
                            try:
                                await completed_step.compensate()
                                log.debug(
                                    f"[Saga:{self.name}] Compensated step: {completed_step.name}"
                                )
                            except Exception as comp_exc:
                                log.error(
                                    f"[Saga:{self.name}] Compensation for '{completed_step.name}' failed: {comp_exc}"
                                )
                                result.compensation_errors.append(
                                    f"{completed_step.name}: {comp_exc}"
                                )
                    result.compensated = True
                return result

        result.success = True
        return result


async def run_saga(
    steps: List[dict],
    saga_name: str = "anonymous",
) -> SagaResult:
    """
    Convenience function for running a saga from a list of step dicts.

    Args:
        steps: List of {"name": str, "action": coroutine_fn, "compensate": coroutine_fn | None}
        saga_name: Name for logging

    Returns:
        SagaResult with success status and details
    """
    executor = SagaExecutor(name=saga_name)
    for step in steps:
        executor.add_step(
            name=step["name"],
            action=step["action"],
            compensate=step.get("compensate"),
        )
    return await executor.execute()
