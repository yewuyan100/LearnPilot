from app.learning.policies.schemas import PolicyDecision, PolicyRequest


class ContextPolicyEngine:
    """V11B policy Interface: context validity, conflicts, and version checks only."""

    def evaluate(self, policy_request: PolicyRequest) -> PolicyDecision:
        if policy_request.request_conflict:
            return PolicyDecision(
                allowed=False,
                code="request_id_conflict",
                reason="The request id is already bound to different request content.",
            )
        if not policy_request.context.valid:
            return PolicyDecision(
                allowed=False,
                code="context_invalid",
                reason=policy_request.context.invalid_reason or "The learner context is invalid.",
            )
        expected = policy_request.expected_context_version
        if expected is not None and expected != policy_request.context.context_version:
            return PolicyDecision(
                allowed=False,
                code="context_version_conflict",
                reason="The learner context changed after the caller observed it.",
            )
        return PolicyDecision(allowed=True)
