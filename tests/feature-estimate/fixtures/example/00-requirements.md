# Customer requirements: Shop App

## Customer inputs
| ID | Input | Kind | Date | File |
|---|---|---|---|---|
| IN-01 | Email from the customer's operations lead | email | 2026-11-10 | `inputs/01-email.md` |

## Requirements
| ID | Requirement | Type | Source | Status |
|---|---|---|---|---|
| REQ-01 | Invoices show the tax amount on every line | Enhancement | IN-01: "tax amount on every line" | Clear |
| REQ-02 | Re-running the nightly export on the same day must not send orders twice | Bug | IN-01: "sends every order twice" | Assumption: the cause is the export having no record of what it already sent |
| REQ-03 | The order list can be filtered by order status | Enhancement | IN-01: "filter by order status" | Clear |
| REQ-04 | A mobile app | Feature | IN-01: "a mobile app, but that is for next year" | Out of scope: customer said it is for next year |

## Assumptions
- The export cause is not visible in the supplied input and is assumed to be missing duplicate protection. Confidence: 60%

## Missing information
- Which status values the filter must offer. Affects: REQ-03. Confidence: 70%

## Conflicts and duplicates
- None.
