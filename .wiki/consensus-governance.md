# Consensus Governance & P-Stack Review Protocol

## 1. Execution Precedence
When resolving conflicts, the system strictly respects the hierarchy:
1. **Frozen Core**: System invariants (no unvetted code, test behavior first, YAGNI, track tasks, hard limits).
2. **Council Decisions**: Approved task decisions and the signed Consensus Manifest.
3. **Task Plan**: Agreed scope and module boundaries.
4. **User Request**: Immediate turn instructions.

## 2. Council of Experts Structure
- **Chair (Principal Enterprise Architect)**: Holds veto power over fundamental structural drift.
- **Seat 1 (QA & Verification Lead)**: Enforces clean-room verification (`docker-test-drive.sh`) and adversarial testing (`/interrogate`).
- **Seat 2 (Principal Systems Engineer)**: Validates hardware offload boundaries and execution latency (`/benchmark-checklist`).
- **Seat 3 (Product & DX Designer)**: Enforces cognitive ergonomics and minimal user friction (`plan-design-review`, `design-consultation`).
- **Seat 4 (Information Security Officer)**: Verifies workspace sandboxing (`policy.allow_all()`) and air-gapped zero-egress operation.

## 3. Deliberation Pass Rule
Requires approval from at least **3 of 4 non-Chair seats** and **zero veto from the Chair**.

## 4. Advisor Approval Loop
The Council Verdict and Consensus Manifest are presented to the Advisor. Re-deliberations occur iteratively until final Advisor approval is signed.
