"""
ResultAggregator: combines all step outputs into a final task result.

MVP default: concatenate summaries (zero extra LLM cost).
Optional: LLM summarization when config.summarize_with_llm = true.
"""

import logging
from typing import Dict, Any, List

from app.employee.runtime.context import EmployeeContext

logger = logging.getLogger(__name__)


class ResultAggregator:
    """Aggregates step results into a final Task result."""

    async def aggregate(
        self,
        ctx: EmployeeContext,
        snapshot: dict,
        skipped_steps: List[str] = None,
    ) -> dict:
        """Produce the final result dict for a completed task.

        Args:
            ctx: EmployeeContext with all artifacts.
            snapshot: Employee config snapshot.
            skipped_steps: Step keys that were skipped (for partial flag).

        Returns:
            {summary: str, steps: [...], partial: bool}
        """
        skipped = skipped_steps or []

        # Build steps view
        steps_view = []
        for key, art in ctx.artifacts.items():
            steps_view.append({
                "step_key": key,
                "success": art.get("success", False),
                "summary": (art.get("summary") or "")[:500],
                "trace_id": (art.get("metadata") or {}).get("trace_id"),
            })

        # Determine if any steps were skipped
        partial = len(skipped) > 0

        # Summarize
        config = snapshot.get("config", {})
        if config.get("summarize_with_llm"):
            summary = await self._llm_summarize(ctx, snapshot)
        else:
            summary = self._concat_summarize(ctx)

        result = {
            "summary": summary,
            "steps": steps_view,
            "partial": partial,
        }
        if partial:
            result["skipped_steps"] = skipped

        return result

    def _concat_summarize(self, ctx: EmployeeContext) -> str:
        """Default: concatenate all step summaries with separators."""
        summaries = [
            (art.get("summary") or "")
            for art in ctx.artifacts.values()
        ]
        summaries = [s for s in summaries if s]
        if not summaries:
            return "(no output from any step)"
        return "\n\n---\n\n".join(summaries)

    async def _llm_summarize(self, ctx: EmployeeContext, snapshot: dict) -> str:
        """Optional: use default chat model to summarize all outputs."""
        try:
            from app.models_center.service import ModelService
            model_service = ModelService()

            parts = []
            for key, art in ctx.artifacts.items():
                summary = (art.get("summary") or "")[:1000]
                parts.append(f"[{key}] {summary}")

            combined = "\n\n".join(parts)
            prompt = (
                f"请总结以下多个 Agent 的执行结果，"
                f"给出简洁的最终结论：\n\n{combined}"
            )

            result = await model_service.chat(prompt)
            return result.get("answer") or result.get("response") or self._concat_summarize(ctx)
        except Exception as e:
            logger.warning(f"LLM summarize failed, falling back to concat: {e}")
            return self._concat_summarize(ctx)
