  Implement a PayLoan webhook feature.

  Context: An external payment provider calls our API to notify that a loan payment was received. We don't call the provider — they call us.

  Business rules:
  - Only loans with status disbursed or partially_paid can receive payments
  - The webhook payload contains: loan_id, amount_paid, provider_reference, provider_name
  - If amount_paid covers the full remaining balance → status becomes paid
  - If amount_paid is less than the remaining balance → status becomes partially_paid
  - If amount_paid exceeds the remaining balance → reject with error
  - The same provider_reference cannot be processed twice (idempotency)

  What needs to change:
  - Loan entity: add amount_paid field (default 0.0), add ensure_can_pay() and apply_payment() methods
  - Loan model: add amount_paid column + migration
  - New endpoint: POST /api/v1/webhooks/payments
  - Follow all existing patterns in the codebase

  Follow all rules in CLAUDE.md.

  DO NOT MAKE MISTAKES.