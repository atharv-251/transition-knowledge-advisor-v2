from agentic_blueprint import wrap
from agentic_blueprint.governance.policies import (
    BudgetPolicy,
    MaxStepsPolicy,
    TimeoutPolicy,
)


AGENT_NAME = "kt-scheduler-bot"
AGENT_VERSION = "0.1.0"
AGENT_ID = "urn:vw:agent:kt-scheduler-bot"


def govern(graph):
    """Apply Agentic Blueprint governance to a scheduler workflow graph."""

    return wrap(
        graph,
        name=AGENT_NAME,
        risk_class="medium",
        autonomy="a2_collaborative",
        impact="d2_operational",
        data_sensitivity="internal",
        exposure="level_1_internal",
        identity_mode="service_account",
        agent_id=AGENT_ID,
        agent_version=AGENT_VERSION,
        lifecycle="active",
        guards=[
            MaxStepsPolicy(max_steps=8),
            TimeoutPolicy(timeout_seconds=120),
            BudgetPolicy(max_tokens=50000),
        ],
        block_responses={
            "PromptInjectionGuardrail": (
                "Security concern detected. Rephrase as a KT scheduling request."
            ),
            "InputPIIGuardrail": (
                "The request could not be completed because personal "
                "information or an identifier-like value was detected in the "
                "question, recent conversation, or retrieved evidence."
            ),
            "ToxicityGuardrail": "Rephrase the request professionally.",
        },
    )

