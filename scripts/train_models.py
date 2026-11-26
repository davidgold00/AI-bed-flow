"""Train, select and evaluate the models; score every visit and rounds row.

    python scripts/train_models.py                    # everything
    python scripts/train_models.py --skip-scenarios   # models only (skip impact sweeps)

Steps: rule-based note reader on every note (AI reader scores from its cache); admission model; discharge model; bed
forecast tables and backtest. Writes models/*.joblib, models/*.parquet and
models/metrics.json. Deterministic.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import joblib  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from halvian import config as C  # noqa: E402
from halvian.data.generate import DATA_DIR, ROOT  # noqa: E402
from halvian.models import admission as A  # noqa: E402
from halvian.models import discharge as D  # noqa: E402
from halvian.models import forecast as F  # noqa: E402
from halvian.models.common import binary_metrics, calibration_bins, curve_points, month_start  # noqa: E402
from halvian.models.explain import importance_labels  # noqa: E402
from halvian.models.fairness import case_mix_check, fairness_table  # noqa: E402
from halvian.notes import evaluate as NE  # noqa: E402
from halvian.notes.reader import RuleBasedNoteReader, score_note_reader  # noqa: E402

MODELS_DIR = ROOT / "models"
SELECTION_MARGIN_AUC = 0.02  # boosting must beat logistic by this much to be chosen


def _clean(obj):
    if isinstance(obj, dict):
        return {str(k): _clean(v) for k, v in obj.items()}
    if isinstance(obj, list | tuple):
        return [_clean(v) for v in obj]
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.floating):
        return None if np.isnan(obj) else float(obj)
    if isinstance(obj, float) and np.isnan(obj):
        return None
    return obj


def select_and_fit(cohort: pd.DataFrame, new_model, label: str) -> dict:
    """Select on September, refit on Jan to Sep, evaluate on Oct to Dec."""
    fit, valid = cohort[cohort.split == "fit"], cohort[cohort.split == "valid"]
    train = cohort[cohort.split.isin(["fit", "valid"])]
    test = cohort[cohort.split == "test"]
    selection = {}
    for kind in ("logistic", "boosting"):
        m = new_model(kind).fit(fit, fit.y.to_numpy())
        selection[kind] = binary_metrics(valid.y.to_numpy(), m.predict_proba(valid))
    lr, gb = selection["logistic"], selection["boosting"]
    chosen = "boosting" if (gb["auc"] - lr["auc"] >= SELECTION_MARGIN_AUC and gb["brier"] <= lr["brier"]) else "logistic"
    final = {kind: new_model(kind).fit(train, train.y.to_numpy()) for kind in ("logistic", "boosting")}
    test_metrics = {kind: binary_metrics(test.y.to_numpy(), final[kind].predict_proba(test)) for kind in final}
    print(f"  {label}: validation AUC logistic {lr['auc']:.3f}, boosting {gb['auc']:.3f} -> {chosen}; "
          f"test AUC {test_metrics[chosen]['auc']:.3f}")
    return {"selection": selection, "chosen": chosen, "models": final, "test": test_metrics,
            "train_rows": len(train), "test_rows": len(test)}


def main() -> None:
    t_start = time.time()
    MODELS_DIR.mkdir(exist_ok=True)
    ed = pd.read_parquet(DATA_DIR / "ed_visits.parquet")
    stays = pd.read_parquet(DATA_DIR / "inpatient_stays.parquet")
    days = pd.read_parquet(DATA_DIR / "inpatient_days.parquet")
    notes = pd.read_parquet(DATA_DIR / "notes.parquet")
    labels = pd.read_parquet(DATA_DIR / "note_labels.parquet")
    census = pd.read_parquet(DATA_DIR / "census_hourly.parquet")
    metrics: dict = {"seed": C.SEED, "default_threshold": C.ALERT_THRESHOLD,
                     "discharge_threshold": C.DISCHARGE_LIST_THRESHOLD}

    # ------------------------------------------------------------- note reader
    print("Note reader: rules on every note (the discharge model's feature source)...")
    reader = RuleBasedNoteReader()
    found = D.findings_table(notes, reader.read_many(notes.text.tolist()))
    found.to_parquet(MODELS_DIR / "note_findings.parquet", index=False, compression="zstd")
    notes_p = notes.merge(stays[["stay_id", "payer"]], on="stay_id", how="left")
    metrics["note_reader"] = score_note_reader(notes_p, labels, reader=reader)
    o = metrics["note_reader"]["overall"]
    print(f"  precision {o['precision']:.3f}, recall {o['recall']:.3f}, F1 {o['f1']:.3f}")
    llm_cache = NE.load_cache()  # the AI reader's scores come from its cache; the model need not be running
    if llm_cache is not None:
        metrics["note_reader"].update(NE.evaluate_cache(llm_cache, notes, labels, stays))
        old_path = MODELS_DIR / "metrics.json"
        prev = json.loads(old_path.read_text()).get("note_reader", {}) if old_path.is_file() else {}
        for key in ("llm_run", "history"):
            if key in prev:
                metrics["note_reader"][key] = prev[key]
        o = metrics["note_reader"]["llm"]["overall"]
        print(f"  AI reader on its sample of {metrics['note_reader']['llm']['sample_n']}: precision "
              f"{o['precision']:.3f}, recall {o['recall']:.3f}, F1 {o['f1']:.3f}")

    # ------------------------------------------------------------- admission
    print("Admission model...")
    coh = A.labelled_cohort(ed)
    res = select_and_fit(coh, A.new_model, "admission")
    model = res["models"][res["chosen"]]
    test = coh[coh.split == "test"].copy()
    test["p"] = model.predict_proba(test)
    crowd = A.crowding_series(census)
    train_hours = crowd[(crowd.index >= month_start(1)) & (crowd.index < month_start(10))]
    typical = float(train_hours.median())
    # deployed policy replayed on every triaged test visit (including later walkouts)
    all_test = A.prepare(ed[(ed.triage_end_min >= month_start(10)) & ed.triage_end_min.notna()])
    all_test["p"] = model.predict_proba(all_test)
    pol = A.policy_flags(all_test, all_test.p.to_numpy(), crowd, typical)
    all_test = all_test.join(pol)
    test = test.join(pol)
    test["flag_fixed"] = test.p >= C.ALERT_THRESHOLD
    test["flag"] = test.flagged
    adm_true = test[test.y]
    lead = adm_true.lead_h[adm_true.flagged]
    metrics["admission"] = {
        "prediction_time": A.PREDICTION_TIME, "features": A.FEATURES, "chosen": res["chosen"],
        "selection_margin_auc": SELECTION_MARGIN_AUC, "selection": res["selection"], "test": res["test"],
        "train_rows": res["train_rows"], "test_rows": res["test_rows"],
        "outcome_coverage_test": float(len(test) / max(len(all_test), 1)),
        "calibration_bins": calibration_bins(test.y.to_numpy(), test.p.to_numpy()),
        "roc": curve_points(test.y.to_numpy(), test.p.to_numpy(), "roc"),
        "pr": curve_points(test.y.to_numpy(), test.p.to_numpy(), "pr"),
        "fixed_threshold": binary_metrics(test.y.to_numpy(), test.p.to_numpy(), test.flag_fixed.to_numpy()),
        "deployed_policy": binary_metrics(test.y.to_numpy(), test.p.to_numpy(), test.flag.to_numpy()),
        "typical_crowding": typical,
        "lead_time": {
            "definition": "Hours from the first hourly batch that flagged the patient (at least the staff "
                          "response delay after triage) to the admit decision, true positives only.",
            "admitted_test": int(len(adm_true)), "flagged_before_decision": int(adm_true.flagged.sum()),
            "median_h": float(lead.median()) if len(lead) else None,
            "p25_h": float(lead.quantile(0.25)) if len(lead) else None,
            "p75_h": float(lead.quantile(0.75)) if len(lead) else None,
            "missed": int((~adm_true.flagged).sum()),
            "alerts_per_day": float(all_test.flagged.sum() / 92),
        },
        "importance": {k: importance_labels(res["models"][k].global_importance(test, test.y.to_numpy())).to_dict(orient="records")
                       for k in ("logistic", "boosting")},
        "fairness_fixed": fairness_table(test.assign(flag=test.flag_fixed)).to_dict(orient="records"),
        "fairness_deployed": fairness_table(test).to_dict(orient="records"),
    }
    # pre-launch bias test: are the missed admissions by payer explained by triage level and age?
    metrics["admission"]["fairness_case_mix"] = {
        "definition": "Among true admissions in the test quarter, each payer group's miss rate under the deployed "
                      "policy versus the rate expected if its patients were missed like everyone with the same "
                      "triage level (ESI) and age band. Unexplained points = observed minus expected.",
        "strata": ["esi", "age_band"], "rows": case_mix_check(test)}
    # the same policy at other base thresholds (a Phase 2 decision), all payer-blind
    by_base = {}
    for base in C.POLICY_BASE_THRESHOLDS:
        if base == C.ALERT_THRESHOLD:
            alt_all, alt = all_test, test
        else:
            alt_all = all_test.drop(columns=pol.columns).join(
                A.policy_flags(all_test, all_test.p.to_numpy(), crowd, typical, base_threshold=base))
            alt = test.drop(columns=pol.columns).join(alt_all[pol.columns])
        by_base[f"{base:.2f}"] = {
            "policy": binary_metrics(alt.y.to_numpy(), alt.p.to_numpy(), alt.flagged.to_numpy()),
            "alerts_per_day": float(alt_all.flagged.sum() / 92),
            "fairness": fairness_table(alt.assign(flag=alt.flagged)).to_dict(orient="records"),
            "case_mix": case_mix_check(alt.assign(flag=alt.flagged)),
        }
    metrics["admission"]["policy_by_base_threshold"] = by_base

    # comparison model that sees insurance (never deployed)
    train = coh[coh.split.isin(["fit", "valid"])]
    with_payer = A.new_model(res["chosen"], with_payer=True).fit(train, train.y.to_numpy())
    test["p_with_payer"] = with_payer.predict_proba(test)
    metrics["admission"]["fairness_with_payer"] = fairness_table(
        test.assign(p=test.p_with_payer, flag=test.p_with_payer >= C.ALERT_THRESHOLD)).to_dict(orient="records")
    metrics["admission"]["test_with_payer"] = binary_metrics(test.y.to_numpy(), test.p_with_payer.to_numpy())

    # unit lookup and scores for every visit
    train_adm = train[train.y]
    lookup = A.fit_unit_lookup(train_adm)
    by_c = lookup.attrs["by_complaint"]
    scored = A.prepare(ed)
    scored["p_admit"] = model.predict_proba(scored)
    up = A.unit_probabilities(scored, lookup, by_c)
    out = pd.concat([ed[["visit_id"]], scored[["p_admit"]], up], axis=1)
    out["likely_unit"] = up.idxmax(axis=1)
    out["split"] = A.labelled_cohort(ed).split.reindex(ed.index).fillna("unlabelled")
    out.to_parquet(MODELS_DIR / "admission_scores.parquet", index=False, compression="zstd")
    t_adm = test.join(out[["likely_unit"]])
    metrics["admission"]["likely_unit_accuracy_test"] = float((t_adm.likely_unit == t_adm.admit_unit)[t_adm.y].mean())
    joblib.dump({"model": model, "alternative": res["models"]["boosting" if res["chosen"] == "logistic" else "logistic"],
                 "with_payer": with_payer, "unit_lookup": lookup, "unit_by_complaint": by_c,
                 "typical_crowding": typical}, MODELS_DIR / "admission.joblib", compress=3)

    # ------------------------------------------------------------- discharge
    print("Discharge model...")
    dd = D.add_barrier_flags(days, found)
    dcoh = D.labelled_cohort(dd)
    dres = select_and_fit(dcoh, D.new_model, "discharge")
    dmodel = dres["models"][dres["chosen"]]
    dtest = dcoh[dcoh.split == "test"].copy()
    dtest["p"] = dmodel.predict_proba(dtest)
    dtest["flag"] = dtest.p >= C.DISCHARGE_LIST_THRESHOLD
    dtrain = dcoh[dcoh.split.isin(["fit", "valid"])]
    dwith = D.new_model(dres["chosen"], with_payer=True).fit(dtrain, dtrain.y.to_numpy())
    dtest["p_with_payer"] = dwith.predict_proba(dtest)
    lead_dc = D.lead_metrics(dtest, dtest.p.to_numpy(), C.DISCHARGE_LIST_THRESHOLD, month_start(13))
    metrics["discharge"] = {
        "prediction_time": D.PREDICTION_TIME, "features": D.FEATURES, "chosen": dres["chosen"],
        "selection": dres["selection"], "test": dres["test"], "train_rows": dres["train_rows"],
        "test_rows": dres["test_rows"],
        "calibration_bins": calibration_bins(dtest.y.to_numpy(), dtest.p.to_numpy()),
        "roc": curve_points(dtest.y.to_numpy(), dtest.p.to_numpy(), "roc"),
        "pr": curve_points(dtest.y.to_numpy(), dtest.p.to_numpy(), "pr"),
        "at_threshold": binary_metrics(dtest.y.to_numpy(), dtest.p.to_numpy(), dtest.flag.to_numpy()),
        "lead_time": lead_dc,
        "importance": {k: importance_labels(dres["models"][k].global_importance(dtest, dtest.y.to_numpy())).to_dict(orient="records")
                       for k in ("logistic", "boosting")},
        "fairness": fairness_table(dtest).to_dict(orient="records"),
        "fairness_with_payer": fairness_table(dtest.assign(p=dtest.p_with_payer, flag=dtest.p_with_payer >= C.DISCHARGE_LIST_THRESHOLD)).to_dict(orient="records"),
        "test_with_payer": binary_metrics(dtest.y.to_numpy(), dtest.p_with_payer.to_numpy()),
    }
    profile = D.discharge_time_profile(dtrain)
    dscores = dd[["note_id", "stay_id", "rounds_min", "unit", *D.BARRIER_FEATURES, "note_any_barrier"]].copy()
    dscores["p_discharge_24h"] = dmodel.predict_proba(dd)
    dscores["split"] = dcoh.split.to_numpy()
    dscores.to_parquet(MODELS_DIR / "discharge_scores.parquet", index=False, compression="zstd")
    joblib.dump({"model": dmodel, "with_payer": dwith, "profile": profile}, MODELS_DIR / "discharge.joblib", compress=3)

    # ------------------------------------------------------------- forecast
    print("Bed forecast tables and backtest...")
    tables = F.fit_tables(ed, stays, dtrain, month_start(1), month_start(10), profile)
    joblib.dump(tables, MODELS_DIR / "forecast_tables.joblib", compress=3)
    admit_scores = out.set_index(ed.index)[["p_admit", *C.UNIT_NAMES]]
    times = [d * 1440.0 + hh * 60 for d in range(int(month_start(10) // 1440), int(month_start(13) // 1440) - 1)
             for hh in (7, 15)]
    bt = F.backtest(times, ed, stays, admit_scores, dscores, tables)
    bt.to_parquet(MODELS_DIR / "forecast_backtest.parquet", index=False, compression="zstd")
    summ = F.backtest_summary(bt)
    metrics["forecast"] = {"backtest": summ.to_dict(orient="records"),
                           "backtest_by_unit": bt.groupby(["unit", "horizon_h"]).abs_err.mean().reset_index().to_dict(orient="records"),
                           "clean_lag_min": tables.clean_lag_min, "times": "07:00 and 15:00 on every test day"}
    print(summ.round(3).to_string(index=False))

    (MODELS_DIR / "metrics.json").write_text(json.dumps(_clean(metrics), indent=1))

    if "--skip-scenarios" not in sys.argv:
        print("Impact scenarios (paired runs, 3 synthetic years; a few minutes)...")
        from halvian import impact

        impact.precompute()
    sizes = sum(p.stat().st_size for p in MODELS_DIR.glob("*")) / 1e6
    print(f"Done in {time.time() - t_start:.1f} s; models/ is {sizes:.1f} MB")


if __name__ == "__main__":
    main()
