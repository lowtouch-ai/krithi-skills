# High-level PRD: Shop App

## Overview
Three changes requested by the customer's operations lead: tax per invoice line, no duplicate orders when the nightly export is re-run, and an order status filter. Built in the existing stack.

## Use cases and feature areas
- Invoice tax detail (PRD-01). `src/main/java/com/acme/billing`
- Nightly export reliability (PRD-02). `jobs`
- Order list filtering (PRD-03). `web/pages`, `src/main/java/com/acme/orders`

## Detailed PRDs
| ID | Use case / feature area | Scope | Main code paths |
|---|---|---|---|
| PRD-01 | Invoice tax detail | Tax per line | `src/main/java/com/acme/billing` |
| PRD-02 | Nightly export reliability | No duplicate sends on re-run | `jobs` |
| PRD-03 | Order list filtering | Filter by status | `web/pages`, `src/main/java/com/acme/orders` |

## Roles & Permissions Model
Unchanged by this request.

## Data Model Overview
Invoices have lines; orders have a status.

## Non-Functional Requirements
No new requirements stated.

## Release / Versioning Scope
Next release.

## Target architecture
The change is built in the existing Java and Celery stack. Architecture deviation: FastAPI, Next.js, Redis and Airflow are not introduced, because the feature is built in the existing stack and re-platforming is not part of this request. PostgreSQL remains the database. The export fix stays a Celery task rather than an Airflow DAG for the same reason. Tenant handling follows the existing tenant filter.

## Out of scope
- Every other module: none in this sample; all four inventory modules are touched.
- A mobile app (REQ-04): customer said it is for next year.

## Not included in the estimate
QA sign-off, production deployment and data migration are not estimated; they are covered by the approximate go-live allowance in the estimate summary.

## Confidence & Open Questions
- Stripe and RabbitMQ are unchanged integrations. Confidence: 90%
