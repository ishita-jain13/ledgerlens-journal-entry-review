# Data Dictionary: journal_entries_4203.csv

Source: Gronewald, Stephan, Rombach, Fettke. *Generating synthetic journal entries for audit analytics: Method and dataset.* Data in Brief (2026). Dataset DOI: 10.5281/zenodo.22014653
The data is **synthetic** (a fictional company). It is not real accounting data.

Size (checked by us): 256,232 rows (journal entry lines), 102,429 journal entries (`posting_id`), posting dates 2023-01-02 to 2024-12-30.
One row = one account posting line. One journal entry = all rows with the same `posting_id`.

## Columns (descriptions from the paper's Table 1)

| Column | Type | Meaning |
|---|---|---|
| posting_id | text | Unique ID that groups account postings (lines) of one journal entry |
| document_date | date | Date of the document being posted (e.g. invoice date), set by the user |
| posting_date | date | Date used to assign the posting to a posting period (service date), set by the user |
| entered_date | date-time | Actual date and time the document was entered, assigned by the system |
| gl_account | number | Account number |
| gl_account_name | text | Name of the account |
| amount | number | Net amount (currency EUR, per the high_cash description) |
| cd_flag | text | Debit ("D") or credit ("C") side of the account |
| user | text | Name of the user who posted |
| tax_rate | number | Tax rate applied to the amount |
| ref_id | text | Refers to the posting which this posting clears |
| text | text | Posting text (item description) |
| promptly | number | Labels whether the posting was entered promptly, delayed or very delayed |
| weekend | number | Labels whether the posting was made on a weekend |
| nwh | number | "Non-working hours": posting outside regular working hours |
| label | number | 1 = artificially inserted anomaly, 0 = normal |
| marking | number | ID of the anomaly type (0 = normal) |
| top_n | number | Audit scope flag: among the 1,000 highest postings per fiscal year |
| high_cash | number | Audit scope flag: cash postings above EUR 1,500 |

## Anomaly types (`marking`)

| marking | Type |
|---|---|
| 0 | Normal posting |
| 1 | High amount |
| 2 | High cash disbursement |
| 3 | Delayed entry (10 to 29 days) |
| 4 | Very delayed entry (more than 29 days) |
| 5 | Non-working-hours entry |
| 6 | Weekend entry |
| 7 | Shadow bank account (rarely used second bank account) |
| 8 | Cross-linked clearing (clearing reference points to an unrelated transaction) |

## Notes from our own checks (not from the paper)

- Missing values: 0. Exact duplicate rows: 0. Unbalanced entries (debit total != credit total): 0.
- `promptly` has values 1, 2, 3 in the data. In our data, every type-3 (delayed) anomaly has promptly = 2, so we read 1 = prompt, 2 = delayed, 3 = very delayed. This reading is our inference from the data.
- `weekend` has values 0, 1, 2. The paper's Table 1 only says it labels weekend postings. What 1 versus 2 means is **not stated** there; we only use "greater than 0".
- Anomalies are injected by a generator, so results on this data are a best case and may not carry over to real ledgers.
