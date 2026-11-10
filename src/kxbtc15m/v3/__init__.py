"""KXBTC15M V3 first-minute prediction. Read-only public GETs. No orders."""

MODEL_VERSION = "v3-logit-ridge-knn@2026-11-09"
FEATURE_SPEC = "shape-v1-logret-vol-relvol-wick-last10logret"
REPLAY_ASSUMPTION = "prior_print_after_settlement_ts"
SERIES = "KXBTC15M"
KNN_K = 25
LOOKBACK_BARS = 96
CORE_BARS = 16
EMBARGO_MINUTES = 96 + 15
