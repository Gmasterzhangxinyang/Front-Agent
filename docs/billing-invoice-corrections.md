# Billing Invoice Correction Runbook

## Scope

Use this process when a customer asks to change the organization name, Tax ID,
or billing address on an invoice that has already been finalized or paid.

## Policy

- A finalized or paid invoice cannot be modified or reissued with different
  billing details.
- Billing details updated in the billing portal apply to future invoices only.
- A Credit Note may be offered as a supplementary document after manual billing
  review. It does not modify, replace, cancel, or reissue the original invoice.
- The customer's institution decides whether it accepts the supplementary
  document for reimbursement. Support must not guarantee acceptance or tax
  treatment.
- The agent has no billing-provider tool. It must not claim that a Credit Note
  was issued, sent, or attached.

## Automated Flow

| Current condition | Action | Next state |
|---|---|---|
| Required details are missing | Draft a request for only the missing items | `awaiting_invoice_details` |
| Details are complete, but the customer has not accepted a Credit Note | Draft the policy and ask whether the supplementary document is acceptable | `awaiting_credit_note_acceptance` |
| Customer accepts | Add a structured internal Front comment; do not claim issuance to the customer | `manual_review` |
| `manual_review` | Stop automation; leave all further replies for the billing operator | unchanged |

Required details:

- Workspace name or identifier
- Existing invoice number
- Legal organization name
- Tax ID
- Complete billing address
- Customer confirmation that a supplementary Credit Note is acceptable

The internal Front comment should use this structure:

```text
[Billing manual review: Credit Note requested]
Workspace: <workspace>
Invoice: <invoice number>
Organization: <legal organization name>
Tax ID: <tax ID>
Billing address: <complete address>
Customer accepted supplementary Credit Note: yes
Required action: verify the invoice and billing details, then create the Credit Note using the approved billing-provider procedure.
```

## Initial Customer Draft

Use this before the customer has accepted a supplementary Credit Note:

```text
Hi <name>,

Thank you for updating the billing information in the billing portal.

Once an invoice has been finalized, we're unable to modify or reissue it with different billing details. The updated billing information will be reflected on future invoices.

For existing invoice <invoice number>, we can ask our billing team to verify its status and review whether a supplementary Credit Note can be issued with the updated organization name, Tax ID, and billing address. Please note that a Credit Note is a supplementary document and does not replace the original invoice. Acceptance for reimbursement is subject to your institution's review.

Please confirm whether this supplementary document would be acceptable, and we'll pass the request to our billing team for review.

Cheers
```

## Human Billing Checklist

1. Verify the workspace and invoice number in the billing provider.
2. Verify that the invoice is finalized or paid and cannot be edited or
   reissued under the approved policy.
3. Verify that the customer updated the billing portal and that the legal name,
   Tax ID, and address match the internal Front comment.
4. Create the Credit Note using the approved billing-provider procedure.
5. Verify the provider result, delivery status, invoice/payment status, and
   subscription status before making any statement about them.
6. Send the final reply only after successful verification. If the provider
   action fails or the document cannot be issued, explain that outcome instead
   of using the success template.
7. Resolve the Front conversation manually when no further action remains.

## Verified Success Reply

This template is for the human operator only, after successful billing-provider
verification:

```text
Hi <name>,

Thank you for updating the billing information in the billing portal.

As invoice <invoice number> has already been finalized and paid, we're unable to modify or reissue the original invoice.

To support your request, we have issued a Credit Note containing the following updated billing information:

- Organization Name: <legal organization name>
- Tax ID: <tax ID>
- Billing Address: <complete billing address>

The Credit Note will be sent to you separately by our billing system. You may submit it together with the original invoice for your institution's reimbursement review.

Please note that the Credit Note is a supplementary document and does not replace the original invoice. Only include statements about payment and subscription status here after verifying them in the billing provider.

The updated billing information will also be reflected on future invoices.

Cheers
```

## Current Ownership Boundary

The request appears in the Ops priority queue as `billing / invoice /
manual_review`. The system does not currently auto-assign the Front conversation
to Elsie because no trusted Elsie teammate ID is configured. Until a dedicated
billing assignment is configured, the operator taking the queue item owns the
billing-provider action and final response.
