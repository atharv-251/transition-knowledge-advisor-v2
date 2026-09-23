from agentic_blueprint import wrap
from agentic_blueprint.governance.policies import (
    BudgetPolicy,
    MaxStepsPolicy,
    TimeoutPolicy,
)


AGENT_NAME = "kt-tracker-bot"
AGENT_VERSION = "0.1.0"
AGENT_ID = (
    "urn:vw:agent:"
    "kt-tracker-bot"
)


def govern(graph):
    """Apply Agentic Blueprint governance to the graph."""

    return wrap(
        graph,
        name=AGENT_NAME,
        risk_class="medium",
        autonomy="a2_collaborative",
        impact="d1_advisory",
        data_sensitivity="internal",
        exposure="level_1_internal",
        identity_mode="service_account",
        agent_id=AGENT_ID,
        agent_version=AGENT_VERSION,
        lifecycle="active",
        guards=[
            MaxStepsPolicy(
                max_steps=8
            ),
            TimeoutPolicy(
                timeout_seconds=120
            ),
            BudgetPolicy(
                max_tokens=50000
            ),
        ],
        block_responses={
            "PromptInjectionGuardrail": (
                "Security concern detected. "
                "Rephrase as a transition knowledge question."
            ),
            "InputPIIGuardrail": (
                "The request could not be completed because "
                "personal information or an identifier-like "
                "value was detected in the question, recent "
                "conversation, or retrieved evidence. The source "
                "records must be sanitized before the request "
                "can continue."
            ),
            "ToxicityGuardrail": (
                "Rephrase the request professionally."
            ),
        },
    )