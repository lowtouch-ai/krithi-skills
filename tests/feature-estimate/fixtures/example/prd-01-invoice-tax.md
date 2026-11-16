# PRD-01: Invoice tax detail

## Description
Invoice tax detail (REQ-01). Source: `src/main/java/com/acme/billing`

## Business Rules & Logic
1. Behaviour as described by the requirement. `src/main/java/com/acme/billing`

## Roles & Permissions
- Unchanged. `src/main/java/com/acme/billing`

## Key Data Involved
- Existing entities only. `src/main/java/com/acme/billing`

## Notable Constraints
- Must not change existing behaviour for other cases. `src/main/java/com/acme/billing`

## Integrations
- None.

## Target design
Built in the existing stack, not on FastAPI or Next.js (deviation recorded in the high-level PRD).

## Source coverage
- `src/main/java/com/acme/billing`: code changed by this PRD

## Stories

### PRD-01-S01: tax shown per invoice line
As a user, I want tax shown per invoice line so that the request is met.

**Acceptance criteria**
- Works as the requirement states
- Existing behaviour unchanged

**Source:** `REQ-01`, `src/main/java/com/acme/billing`

### PRD-01-S02: tax totals reconcile
As a user, I want tax totals reconcile so that the request is met.

**Acceptance criteria**
- Works as the requirement states
- Existing behaviour unchanged

**Source:** `REQ-01`, `src/main/java/com/acme/billing`
## Dependencies
- None.

## Confidence & Open Questions
- Cause and scope as stated in the register. Confidence: 70%
