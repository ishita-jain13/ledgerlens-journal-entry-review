
import os
import pandas as pd

RAW_FILE = "data/raw/journal_entries_4203.csv"
CORRUPTED_FILE = "data/processed/journal_entries_corrupted.csv"
LATE_DAYS = 30          # entry delay limit (days)
BIG_QUANTILE = 0.99     # top 1% amounts

os.makedirs("data/processed", exist_ok=True)
os.makedirs("outputs", exist_ok=True)

# =====================================================
# 1. LOAD AND PREPARE
# =====================================================
df = pd.read_csv(RAW_FILE, sep=";")

for col in ["document_date", "posting_date", "entered_date"]:
    df[col] = pd.to_datetime(df[col])

df["entry_delay_days"] = (df["entered_date"] - df["posting_date"]).dt.days
df["month"] = df["posting_date"].dt.to_period("M").astype(str)

# =====================================================
# 2. DATA QUALITY SUMMARY (on the original data)
# =====================================================
df["signed"] = df["amount"].where(df["cd_flag"] == "D", -df["amount"])
balance = df.groupby("posting_id")["signed"].sum().round(2)

dq_rows = [
    ["Total rows", len(df)],
    ["Total entries (posting_id)", df["posting_id"].nunique()],
    ["Missing values", int(df.isna().sum().sum())],
    ["Duplicate rows", int(df.duplicated().sum())],
    ["Entered before posting date", int((df["entry_delay_days"] < 0).sum())],
    ["Unbalanced entries (debit != credit)", int((balance.abs() > 0.01).sum())],
]
dq_summary = pd.DataFrame(dq_rows, columns=["check", "count"])
dq_summary.to_csv("outputs/dq_summary.csv", index=False)

# =====================================================
# 3. PROVE THE CHECKS WORK (corrupted copy test)
# =====================================================
bad = pd.read_csv(RAW_FILE, sep=";")   # fresh copy of ALL original columns

idx = bad.sample(n=100, random_state=1).index
missing_idx, baddate_idx, dup_idx = idx[:50], idx[50:70], idx[70:100]

bad.loc[missing_idx, "amount"] = None
bad.loc[baddate_idx, "posting_date"] = "2023-02-31"
bad = pd.concat([bad, bad.loc[dup_idx]], ignore_index=True)
bad.to_csv(CORRUPTED_FILE, sep=";", index=False)

found_missing = int(bad["amount"].isna().sum())
found_dups = int(bad.duplicated().sum())
found_dates = int(pd.to_datetime(bad["posting_date"], errors="coerce").isna().sum())

test_results = pd.DataFrame(
    [
        ["Missing amounts", 50, found_missing],
        ["Duplicate rows", 30, found_dups],
        ["Invalid posting dates", 20, found_dates],
    ],
    columns=["check", "injected", "found"],
)
test_results["passed"] = test_results["injected"] == test_results["found"]
test_results.to_csv("outputs/dq_test_results.csv", index=False)

# =====================================================
# 4. RULES
# =====================================================
df["rule_late"] = df["entry_delay_days"] > LATE_DAYS
df["rule_big"] = df["amount"] > df["amount"].quantile(BIG_QUANTILE)
df["rule_nwh"] = df["nwh"] == 1
df["rule_fred_weekend"] = (df["user"] == "Fred") & (df["weekend"] > 0)
df["rule_fred_promptly"] = (df["user"] == "Fred") & (df["promptly"] == 2)

rule_cols = ["rule_late", "rule_big", "rule_nwh", "rule_fred_weekend", "rule_fred_promptly"]
df["flagged"] = df[rule_cols].any(axis=1)
df["rules_hit"] = df[rule_cols].sum(axis=1)

# =====================================================
# 5. REASONS
# =====================================================
df["reason"] = ""
df.loc[df["rule_late"], "reason"] += f"Entered more than {LATE_DAYS} days after posting. "
df.loc[df["rule_big"], "reason"] += "Amount in top 1%. "
df.loc[df["rule_nwh"], "reason"] += "nwh indicator is 1. "
df.loc[df["rule_fred_weekend"], "reason"] += "User Fred with weekend indicator above 0. "
df.loc[df["rule_fred_promptly"], "reason"] += "User Fred with promptly indicator 2. "

# =====================================================
# 6. FLAGGED ROWS (line level)
# =====================================================
flagged_rows = df[df["flagged"]]
flagged_rows[
    ["posting_id", "posting_date", "user", "gl_account_name", "amount", "cd_flag",
     "rules_hit", "reason", "label", "marking"]
].to_csv("outputs/flagged_rows.csv", index=False)

# =====================================================
# 7. REVIEW LIST (one row per flagged entry, with priority)
# =====================================================
review = flagged_rows.groupby("posting_id").agg(
    posting_date=("posting_date", "first"),
    user=("user", "first"),
    text=("text", "first"),
    max_amount=("amount", "max"),
    rules_hit=("rules_hit", "max"),
    actual_label=("label", "max"),
).reset_index()

# rebuild reason cleanly: unique sentences per entry
def clean_reason(series):
    parts = set()
    for text in series:
        for p in text.split(". "):
            p = p.strip().rstrip(".")
            if p:
                parts.add(p)
    return ". ".join(sorted(parts)) + "."

review["reason"] = review["posting_id"].map(
    flagged_rows.groupby("posting_id")["reason"].apply(clean_reason)
)

review["priority"] = pd.cut(
    review["rules_hit"], bins=[0, 1, 2, 10], labels=["Low", "Medium", "High"]
)
review["recommended_action"] = review["priority"].map(
    {
        "High": "Review first: several rules flagged this entry. Check source document and approver.",
        "Medium": "Review next: two rules flagged this entry. Check supporting document.",
        "Low": "Review if capacity allows: one rule flagged this entry.",
    }
)
review["detection_method"] = "Rule-based"
review = review.sort_values(["rules_hit", "max_amount"], ascending=False)
review.to_csv("outputs/review_list.csv", index=False)

# =====================================================
# 8. EVALUATION AGAINST THE LABEL (entry level)
# =====================================================
entries = df.groupby("posting_id").agg(
    month=("month", "first"),
    user=("user", "first"),
    text=("text", "first"),
    flagged=("flagged", "max"),
    label=("label", "max"),
    marking=("marking", "max"),
)

caught = int((entries["flagged"] & (entries["label"] == 1)).sum())
false_alarms = int((entries["flagged"] & (entries["label"] == 0)).sum())
missed = int((~entries["flagged"] & (entries["label"] == 1)).sum())
precision = caught / (caught + false_alarms)
recall = caught / (caught + missed)
f1 = 2 * precision * recall / (precision + recall)

results = pd.DataFrame(
    [
        ["Total entries", len(entries)],
        ["Flagged entries", int(entries["flagged"].sum())],
        ["Correctly caught", caught],
        ["False alarms", false_alarms],
        ["Missed anomalies", missed],
        ["Precision", round(precision, 3)],
        ["Recall", round(recall, 3)],
        ["F1 score", round(f1, 3)],
    ],
    columns=["metric", "value"],
)
results.to_csv("outputs/evaluation_results.csv", index=False)

# how well does each anomaly type get caught?
by_type = (
    entries[entries["label"] == 1]
    .groupby("marking")
    .agg(anomalous_entries=("flagged", "size"), caught=("flagged", "sum"))
    .reset_index()
)
by_type["recall"] = (by_type["caught"] / by_type["anomalous_entries"]).round(3)
by_type.to_csv("outputs/recall_by_anomaly_type.csv", index=False)

# precision by priority
prio = review.groupby("priority", observed=True).agg(
    entries=("posting_id", "size"), actual_anomalies=("actual_label", "sum")
).reset_index()
prio["precision"] = (prio["actual_anomalies"] / prio["entries"]).round(3)
prio.to_csv("outputs/precision_by_priority.csv", index=False)

# =====================================================
# 9. SUMMARIES FOR POWER BI
# =====================================================
monthly = entries.groupby("month").agg(
    entries=("flagged", "size"),
    flagged=("flagged", "sum"),
    actual_anomalies=("label", "sum"),
).reset_index()
monthly.to_csv("outputs/monthly_summary.csv", index=False)

by_user = entries.groupby("user").agg(
    entries=("flagged", "size"), flagged=("flagged", "sum")
).reset_index()
by_user["flag_rate"] = (by_user["flagged"] / by_user["entries"]).round(3)
by_user.to_csv("outputs/user_summary.csv", index=False)

by_text = entries.groupby("text").agg(
    entries=("flagged", "size"), flagged=("flagged", "sum")
).reset_index()
by_text["flag_rate"] = (by_text["flagged"] / by_text["entries"]).round(3)
by_text.to_csv("outputs/category_summary.csv", index=False)

# =====================================================
# 10. PRINT RESULTS
# =====================================================
print("\n=== DATA QUALITY (original data) ===")
print(dq_summary.to_string(index=False))
print("\n=== TEST: INJECTED vs FOUND ===")
print(test_results.to_string(index=False))
print("\n=== RULE RESULTS (entry level) ===")
print(results.to_string(index=False))
print("\n=== RECALL BY ANOMALY TYPE ===")
print(by_type.to_string(index=False))
print("\n=== PRECISION BY PRIORITY ===")
print(prio.to_string(index=False))
print("\nTop 5 entries to review:")
print(review[["posting_id", "max_amount", "rules_hit", "priority", "reason"]].head(5).to_string(index=False))
print("\nAll files saved in the outputs folder.")