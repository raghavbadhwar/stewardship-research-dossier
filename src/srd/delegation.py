from .models import DelegationPlan, DelegationRequest, TaskCard

PLAN_RULES = {
    "new_issuer": ["filings-analyst", "competitive-analyst", "thesis-skeptic"],
    "governance": ["governance-analyst", "filings-analyst", "thesis-skeptic"],
    "event": ["event-scout", "filings-analyst", "thesis-skeptic"],
    "refresh": ["delta-analyst"],
    "mixed": ["governance-analyst", "event-scout", "filings-analyst", "thesis-skeptic"],
    "exploration": ["outlier-mind", "polymath", "thesis-skeptic"],
}

ROLE_OBJECTIVES = {
    "competitive-analyst": (
        "Assess competitive context from the assigned evidence only; distinguish disclosed facts "
        "from missing peer or industry context."
    ),
    "delta-analyst": (
        "Assess evidence changes between the supplied baseline and later-run sources; identify "
        "what changed without drawing a decision."
    ),
    "event-scout": (
        "Assess dated events in the assigned evidence, preserving event date, source and "
        "unresolved impact."
    ),
    "filings-analyst": (
        "Assess formal disclosures relevant to the question, retaining stated period, attribution "
        "and material omissions."
    ),
    "governance-analyst": (
        "Assess governance mechanisms, including board oversight, incentives, shareholder rights "
        "and disclosure limits, from assigned evidence only."
    ),
    "outlier-mind": (
        "Form falsifiable hypotheses from non-obvious, source-supported tensions or connections; "
        "label missing evidence rather than turning a hypothesis into a claim."
    ),
    "polymath": (
        "Map cross-domain connections across the assigned governance, risk, event, competitive or "
        "technical evidence, separating direct support from a testable inference."
    ),
    "thesis-skeptic": (
        "Seek disconfirming evidence, weak assumptions and unresolved contradictions in the "
        "assigned evidence; do not manufacture a contrary claim."
    ),
}


def plan_delegation(
    request: DelegationRequest,
    sources: list[str],
    run_id: str = "",
) -> DelegationPlan:
    cap = (
        4
        if request.case_type == "mixed" and request.available_worker_cap == 4
        else min(request.available_worker_cap, 3)
    )
    roles = PLAN_RULES[request.case_type][:cap]
    tasks = [
        TaskCard(
            role=r,
            objective=ROLE_OBJECTIVES[r],
            allowed_source_ids=sources,
            stop_condition="Return when all allowed sources are assessed or no supported finding remains.",
        )
        for r in roles
    ]
    return DelegationPlan(
        run_id=run_id,
        max_workers=len(tasks),
        join_rule="Lead reviews structured handoffs and alone saves the research packet.",
        tasks=tasks,
    )
