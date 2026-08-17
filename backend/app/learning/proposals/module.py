from uuid import uuid4

from app.learning.proposals.schemas import ProposalEnvelope


class ProposalModule:
    """Small Interface for creating typed, still-pending proposal envelopes."""

    def create_envelope(self, proposal_type: str, **values) -> ProposalEnvelope:
        return ProposalEnvelope(
            proposal_id=values.pop("proposal_id", uuid4().hex),
            proposal_type=proposal_type,
            status="pending",
            **values,
        )
