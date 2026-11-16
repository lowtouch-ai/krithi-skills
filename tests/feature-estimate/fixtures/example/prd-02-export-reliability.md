# PRD-02: Nightly export reliability

## Description
Nightly export reliability (REQ-02). Source: `jobs`

## Business Rules & Logic
1. Behaviour as described by the requirement. `jobs`

## Roles & Permissions
- Unchanged. `jobs`

## Key Data Involved
- Existing entities only. `jobs`

## Notable Constraints
- Must not change existing behaviour for other cases. `jobs`

## Integrations
- None.

## Target design
Built in the existing stack, not on FastAPI or Next.js (deviation recorded in the high-level PRD).

## Source coverage
- `jobs`: code changed by this PRD

## Stories

### PRD-02-S01: export skips orders already sent
As a user, I want export skips orders already sent so that the request is met.

**Acceptance criteria**
- Works as the requirement states
- Existing behaviour unchanged

**Source:** `REQ-02`, `jobs`

### PRD-02-S02: export re-run test
As a user, I want export re-run test so that the request is met.

**Acceptance criteria**
- Works as the requirement states
- Existing behaviour unchanged

**Source:** `REQ-02`, `jobs`
## Dependencies
- None.

## Confidence & Open Questions
- Cause and scope as stated in the register. Confidence: 70%
