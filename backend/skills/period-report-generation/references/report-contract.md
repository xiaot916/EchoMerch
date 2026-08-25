# Period Report Contract

## Date Ranges

- `daily`: the selected business day.
- `weekly`: the selected day and the preceding six days.
- `monthly`: first day of the selected month through the selected day.
- `mtd`: first day of the selected month through the latest available business day.

## Core Formulas

- GMV: sum of store paid amount.
- Net GMV: GMV minus refund amount measured on the store overview's payment-time refund basis.
- Conversion rate: paid buyers divided by visitors, expressed as a percentage.
- Customer unit price: GMV divided by paid buyers.
- New paid buyers: paid buyers minus older paid buyers, only when both source values exist.
- New-customer buyer share: new paid buyers divided by paid buyers. This is a buyer-count share, not the old template's new-customer paid-amount share.
- Channel sales share: channel attributed paid amount divided by store GMV.
- Promotion ROI: attributed paid amount divided by spend. The report labels the configured attribution window.

## Data States

- `available`: data is present and can be reported.
- `partial`: some expected days or companion tables are absent; qualify the conclusion.
- `missing`: collection has not produced data; never display it as zero.
- `no_data`: the platform confirmed no data; this is not a collection failure.

## Legacy Report Reuse

The previous pandas notebook is a useful source of business definitions, but it is not an execution dependency. SQL access, date normalization, joins, pivots, and string rendering must be implemented behind normalized repository/MCP APIs. Skills consume MCP JSON only.

Keep raw and normalized promotion scene names together. Do not merge parent and child traffic rows into one denominator, because platform attribution levels overlap.
