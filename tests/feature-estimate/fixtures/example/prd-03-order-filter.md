# PRD-03: Order list filtering

## Description
Order list filtering (REQ-03). Source: `web/pages`

## Business Rules & Logic
1. Behaviour as described by the requirement. `web/pages`

## Roles & Permissions
- Unchanged. `web/pages`

## Key Data Involved
- Existing entities only. `web/pages`

## Notable Constraints
- Must not change existing behaviour for other cases. `web/pages`

## Integrations
- None.

## Target design
Built in the existing stack, not on FastAPI or Next.js (deviation recorded in the high-level PRD).

## Source coverage
- `web/pages`: order list page changed by this PRD
- `src/main/java/com/acme/orders`: order query endpoint changed by this PRD

## Stories

### PRD-03-S01: status filter on order list
As a user, I want status filter on order list so that the request is met.

**Acceptance criteria**
- Works as the requirement states
- Existing behaviour unchanged

**Source:** `REQ-03`, `web/pages`

### PRD-03-S02: status filter endpoint
As a user, I want status filter endpoint so that the request is met.

**Acceptance criteria**
- Works as the requirement states
- Existing behaviour unchanged

**Source:** `REQ-03`, `src/main/java/com/acme/orders`
## Dependencies
- None.

## Confidence & Open Questions
- Cause and scope as stated in the register. Confidence: 70%
