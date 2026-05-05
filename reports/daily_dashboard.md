# Budget Portfolio Research

Generated: 2026-05-06T01:44

Data policy: missing public-source fields are marked `data_missing`; affected scores are provisional. ETFs and non-US holdings are not scored with the US stock model.

## Portfolio Summary

1. Total portfolio value: **$99,484.99**
2. Cash-adjusted investable value: **$98,484.99**
3. Cash: **$1,000.00**
4. Speculative exposure: **0.0%**

## Core / ETF Allocation

| Ticker | Asset Type | Company | Value | Weight | Role | Status | Notes |
|---|---|---|---:|---:|---|---|---|
| VWRA | ETF | Vanguard FTSE All-World UCITS ETF | $23,717.20 | 23.8% | Core Index | not_scored_etf | ETF: US stock scoring and SEC lookup not applicable. |

## US Stock Holdings

| Ticker | Asset Type | Company | Value | Role | Score | Status | Notes |
|---|---|---|---:|---|---:|---|---|
| UNH | US_STOCK | UnitedHealth | $9,529.65 | Unknown | 0 | provisional | data_missing: live US stock scoring fields unavailable in this regeneration. |
| CRCL | US_STOCK | Circle | $9,071.40 | Unknown | 0 | provisional | data_missing: live US stock scoring fields unavailable in this regeneration. |
| NVO | US_STOCK | Novo Nordisk | $6,451.58 | Unknown | 0 | provisional | data_missing: live US stock scoring fields unavailable in this regeneration. |
| FI (alias for FISV) | US_STOCK | Fiserv | $4,318.05 | Unknown | 0 | provisional | ticker_alias:FISV->FI; data_missing: live US stock scoring fields unavailable. |
| WGRX | US_STOCK | data_missing | $3,111.00 | Unknown | 0 | provisional | data_missing: company_name and live scoring fields. |
| SAIA | US_STOCK | Saia | $2,504.52 | Unknown | 0 | provisional | data_missing: live US stock scoring fields unavailable. |
| SOFI | US_STOCK | SoFi | $2,418.00 | Unknown | 0 | provisional | data_missing: live US stock scoring fields unavailable. |
| MSFT | US_STOCK | Microsoft | $2,050.55 | Unknown | 0 | provisional | data_missing: live US stock scoring fields unavailable. |
| UAMY | US_STOCK | data_missing | $2,035.80 | Unknown | 0 | provisional | data_missing: company_name and live scoring fields. |
| RZLV | US_STOCK | Rezolve AI | $1,996.00 | Unknown | 0 | provisional | data_missing: live US stock scoring fields unavailable. |
| CGC | US_STOCK | Canopy Growth | $1,941.11 | Unknown | 0 | provisional | data_missing: live US stock scoring fields unavailable. |
| CRWV | US_STOCK | CoreWeave | $1,902.60 | Unknown | 0 | provisional | data_missing: live US stock scoring fields unavailable. |
| MSTR | US_STOCK | Strategy | $1,856.05 | Unknown | 0 | provisional | data_missing: live US stock scoring fields unavailable. |
| OPEN | US_STOCK | Opendoor | $1,853.12 | Unknown | 0 | provisional | data_missing: live US stock scoring fields unavailable. |
| NFLX | US_STOCK | Netflix | $1,780.60 | Unknown | 0 | provisional | data_missing: live US stock scoring fields unavailable; verify split-adjusted price note. |
| NXXT, ASTS, POET, SNAP, KULR, TOVX, RKT, AMZN, FLY, RR, MBLY, HIMS, RDDT, GOOGL, MU, BYND, IONQ, PEW, BURU, CYN, DVLT, BKYI, YYAI, BBAI, VIVK, BNBX | US_STOCK | mixed | $16,092.18 | Unknown | 0 | provisional | data_missing: live US stock scoring fields unavailable. |

### Top Add Candidates

| Ticker | Role | Score | Action | Reason |
|---|---|---:|---|---|
| n/a | n/a | 0 | n/a | No complete or mostly complete US_STOCK candidates. ETFs, NON_US_STOCK, UNKNOWN tickers, and data_missing names are excluded. |

## Speculative Exposure

- Current speculative exposure: **0.0%** ($0.00)
- Limit: **10.0%** ($9,948.50)
- Status: **within_limit**
- Excess above limit: **$0.00**

## Cleanup Candidates

### True Fundamental Cleanup Candidates

| Ticker | Reason |
|---|---|
| n/a | No true fundamental cleanup candidates from complete data in this regeneration. |

### Data-Quality Issues

| Ticker | Asset Type | Issue | Notes |
|---|---|---|---|
| FI (alias for FISV) | US_STOCK | ticker_alias:FISV->FI | Use FI for live lookups going forward. |
| D05 | NON_US_STOCK | fx_rate_SGD_USD, not SEC-scored | DBS Group, SGX; skipped SEC logic. |
| 1009 | NON_US_STOCK | fx_rate_HKD_USD, company_name | SEHK holding; skipped SEC logic. |
| Z59 | NON_US_STOCK | fx_rate_SGD_USD, company_name | SGX holding; skipped SEC logic. |
| VWRA | ETF | not US-stock scored | Core Index allocation; not Cleanup due missing SEC/yfinance fields. |
| US_STOCK holdings | US_STOCK | live scoring fields | Marked data_missing until yfinance/SEC fields are available. |

### Overweight But Quality Holdings

| Ticker | Reason |
|---|---|
| n/a | No overweight quality holdings identified from complete data in this regeneration. |

## Data Issues To Fix

| Ticker | Asset Type | Issue | Notes |
|---|---|---|---|
| FI (alias for FISV) | US_STOCK | alias applied | Original portfolio row remains FISV; research uses FI. |
| D05 | NON_US_STOCK | fx_rate_SGD_USD | Do not use SEC scoring; add explicit mapping only if needed. |
| 1009 | NON_US_STOCK | fx_rate_HKD_USD, company_name | Do not use SEC scoring; add explicit mapping only if needed. |
| Z59 | NON_US_STOCK | fx_rate_SGD_USD, company_name | Do not use SEC scoring; add explicit mapping only if needed. |
| US_STOCK provisional rows | US_STOCK | data_missing scoring fields | Do not use for add decisions until data is complete or mostly complete. |
