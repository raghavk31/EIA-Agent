import json
from flask import Flask, request, jsonify, send_file

app = Flask(__name__)


@app.route("/")
def index():
    return send_file("form.html")


@app.route("/generate", methods=["POST"])
def generate():
    f = request.form

    def num(key, default=None):
        val = f.get(key, "").strip()
        try:
            return float(val) if val else default
        except ValueError:
            return default

    def txt(key):
        return f.get(key, "").strip() or None

    # ── Revenue (denominator for all intensity calculations) ──────────────
    revenue_current = num("revenue_current")
    revenue_prev = num("revenue_prev")

    # ── Auto-calculate intensity if raw numbers supplied ─────────────────
    scope1 = num("scope1_current")
    scope2 = num("scope2_current")
    ghg_intensity = num("ghg_intensity_current")
    if ghg_intensity is None and scope1 is not None and scope2 is not None and revenue_current:
        ghg_intensity = round((scope1 + scope2) / revenue_current, 2)

    energy_nonrenew = num("energy_nonrenew_current")
    energy_renew = num("energy_renew_current")
    energy_total = None
    energy_intensity = num("energy_intensity_current")
    if energy_nonrenew is not None and energy_renew is not None:
        energy_total = energy_nonrenew + energy_renew
    if energy_intensity is None and energy_total and revenue_current:
        energy_intensity = round(energy_total / revenue_current, 2)

    water_consumed = num("water_consumed_current")
    water_intensity = None
    if water_consumed is not None and revenue_current:
        water_intensity = round(water_consumed / revenue_current, 2)

    waste_types = {
        "plastic":           num("waste_plastic"),
        "ewaste":            num("waste_ewaste"),
        "biomedical":        num("waste_biomedical"),
        "construction":      num("waste_construction"),
        "battery":           num("waste_battery"),
        "radioactive":       num("waste_radioactive"),
        "other_hazardous":   num("waste_other_hazardous"),
        "other_nonhazardous":num("waste_other_nonhazardous"),
    }
    provided = [v for v in waste_types.values() if v is not None]
    waste_total = round(sum(provided), 4) if provided else None
    waste_intensity = None
    if waste_total is not None and revenue_current:
        waste_intensity = round(waste_total / revenue_current, 4)

    # ── Structured payload ────────────────────────────────────────────────
    data = {
        "company": {
            "name":              txt("company_name"),
            "cin":               txt("cin"),
            "financial_year":    txt("financial_year"),
            "prev_financial_year": txt("prev_financial_year") or "Previous year",
            "sector":            txt("sector"),
            "registered_address":txt("registered_address"),
            "revenue_current_cr":revenue_current,
            "revenue_prev_cr":   revenue_prev,
            "workforce": {
                "permanent_employees": {
                    "male":   num("perm_emp_male"),
                    "female": num("perm_emp_female"),
                },
                "contract_workers": {
                    "male":   num("contract_workers_male"),
                    "female": num("contract_workers_female"),
                },
            },
            "director": {
                "name":        txt("director_name"),
                "din":         txt("director_din"),
                "designation": txt("director_designation"),
            },
        },

        "governance": {
            "code_of_conduct": {
                "name":              txt("code_of_conduct_name"),
                "board_approved":    txt("code_of_conduct_date"),
                "training_pct":      num("coc_training_pct"),
                "violations":        num("coc_violations"),
            },
            "esg_committee": {
                "name":              txt("esg_committee_name"),
                "review_frequency":  txt("esg_committee_frequency"),
            },
            "whistleblower": {
                "oversight_body":    txt("whistleblower_oversight"),
                "complaints_received": num("whistleblower_received"),
                "complaints_resolved": num("whistleblower_resolved"),
            },
            "env_policy_name":       txt("env_policy_name"),
            "sustainability_target": txt("sustainability_target"),
        },

        "brsr_core": {

            "ghg": {
                "scope1": {
                    "status":   txt("scope1_status") or "available",
                    "current":  scope1,
                    "prev":     num("scope1_prev"),
                    "na_context": txt("scope1_na_context"),
                    "breakup": {
                        "co2":  num("scope1_co2"),
                        "ch4":  num("scope1_ch4"),
                        "n2o":  num("scope1_n2o"),
                    },
                },
                "scope2": {
                    "status":   txt("scope2_status") or "available",
                    "current":  scope2,
                    "prev":     num("scope2_prev"),
                    "method":   txt("scope2_method") or "location",
                    "na_context": txt("scope2_na_context"),
                },
                "intensity": {
                    "current":  ghg_intensity,
                    "prev":     num("ghg_intensity_prev"),
                },
            },

            "water": {
                "withdrawal": {
                    "status":   txt("water_withdrawal_status") or "available",
                    "sources": {
                        "surface_freshwater":    num("water_surface_fresh_current"),
                        "groundwater_freshwater":num("water_ground_fresh_current"),
                        "third_party_freshwater":num("water_third_fresh_current"),
                        "seawater":              num("water_sea_current"),
                        "other":                 num("water_other_current"),
                    },
                    "prev_total":  num("water_withdrawal_prev"),
                    "na_context":  txt("water_withdrawal_na_context"),
                },
                "consumption": {
                    "current":   water_consumed,
                    "prev":      num("water_consumed_prev"),
                    "intensity": water_intensity,
                },
                "discharge": {
                    "status":    txt("water_discharge_status") or "available",
                    "surface":   num("water_disch_surface"),
                    "groundwater": num("water_disch_ground"),
                    "third_party": num("water_disch_third"),
                    "treatment_level": txt("water_disch_treatment"),
                    "na_context": txt("water_discharge_na_context"),
                },
                "recycled": {
                    "current":   num("water_recycled_current"),
                    "prev":      num("water_recycled_prev"),
                },
            },

            "energy": {
                "non_renewable": {
                    "current":   energy_nonrenew,
                    "prev":      num("energy_nonrenew_prev"),
                },
                "renewable": {
                    "current":   energy_renew,
                    "prev":      num("energy_renew_prev"),
                },
                "total": {
                    "current":   energy_total,
                },
                "intensity": {
                    "current":   energy_intensity,
                    "prev":      num("energy_intensity_prev"),
                },
            },

            "waste": {
                "status":        txt("waste_status") or "available",
                "generated": {
                    **waste_types,
                    "total_current":  waste_total,
                    "total_prev":     num("waste_total_prev"),
                    "intensity":      waste_intensity,
                },
                "recovered": {
                    "recycled":       num("waste_recycled"),
                    "reused":         num("waste_reused"),
                    "other_recovery": num("waste_other_recovery"),
                    "prev_total":     num("waste_recovered_prev"),
                },
                "disposed": {
                    "incineration_with_energy":    num("waste_incineration_energy"),
                    "incineration_without_energy": num("waste_incineration_no_energy"),
                    "landfill":                    num("waste_landfill"),
                    "other":                       num("waste_other_disposal"),
                },
                "na_context": txt("waste_na_context"),
            },

            "safety": {
                "wellbeing_spend": {
                    "employees_pct_current": num("wellbeing_emp_pct_current"),
                    "employees_pct_prev":    num("wellbeing_emp_pct_prev"),
                    "workers_pct_current":   num("wellbeing_worker_pct_current"),
                    "workers_pct_prev":      num("wellbeing_worker_pct_prev"),
                },
                "employees": {
                    "ltifr_current":           num("ltifr_emp_current"),
                    "ltifr_prev":              num("ltifr_emp_prev"),
                    "manhours_millions":       num("manhours_emp_current"),
                    "fatalities_current":      num("fatalities_emp_current"),
                    "fatalities_prev":         num("fatalities_emp_prev"),
                    "high_consequence_current":num("highconsequence_emp_current"),
                    "recordable_current":      num("recordable_emp_current"),
                },
                "workers": {
                    "ltifr_current":           num("ltifr_worker_current"),
                    "ltifr_prev":              num("ltifr_worker_prev"),
                    "fatalities_current":      num("fatalities_worker_current"),
                    "fatalities_prev":         num("fatalities_worker_prev"),
                    "high_consequence_current":num("highconsequence_worker_current"),
                    "recordable_current":      num("recordable_worker_current"),
                },
            },

            "gender": {
                "female_wages_pct": {
                    "current":        num("female_wages_pct_current"),
                    "prev":           num("female_wages_pct_prev"),
                    "wages_definition": txt("wages_definition"),
                },
                "posh": {
                    "filed_current":   num("posh_filed_current"),
                    "filed_prev":      num("posh_filed_prev"),
                    "pending_current": num("posh_pending_current"),
                    "pending_prev":    num("posh_pending_prev"),
                },
            },

            "inclusive": {
                "msme_sourcing": {
                    "status":   txt("msme_status") or "available",
                    "current":  num("msme_pct_current"),
                    "prev":     num("msme_pct_prev"),
                    "na_context": txt("msme_na_context"),
                },
                "india_sourcing": {
                    "status":   txt("india_sourcing_status") or "available",
                    "current":  num("india_sourcing_pct_current"),
                    "prev":     num("india_sourcing_pct_prev"),
                    "na_context": txt("india_sourcing_na_context"),
                },
                "smaller_towns": {
                    "status":         txt("smaller_towns_status") or "available",
                    "current":        num("smaller_towns_pct_current"),
                    "prev":           num("smaller_towns_pct_prev"),
                    "classification": txt("smaller_towns_classification"),
                    "na_context":     txt("smaller_towns_na_context"),
                },
            },

            "fairness": {
                "data_breach": {
                    "count_current":       num("data_breach_count_current"),
                    "count_prev":          num("data_breach_count_prev"),
                    "pct_of_cyber_events": num("data_breach_pct_current"),
                    "total_cyber_events":  num("total_cyber_events"),
                },
                "accounts_payable_days": {
                    "current": num("ap_days_current"),
                    "prev":    num("ap_days_prev"),
                    "formula": txt("ap_days_formula"),
                },
            },

            "openness": {
                "purchase_concentration": {
                    "current": num("purchase_concentration_current"),
                    "prev":    num("purchase_concentration_prev"),
                },
                "sales_concentration": {
                    "current": num("sales_concentration_current"),
                    "prev":    num("sales_concentration_prev"),
                },
                "related_party": {
                    "purchases_pct_current": num("rpt_purchases_pct_current"),
                    "purchases_pct_prev":    num("rpt_purchases_pct_prev"),
                    "sales_pct_current":     num("rpt_sales_pct_current"),
                    "sales_pct_prev":        num("rpt_sales_pct_prev"),
                },
            },
        },
    }

    # ── Temporary: pretty-print the dict so we can verify the plumbing ───
    return app.response_class(
        response=json.dumps(data, indent=2, ensure_ascii=False),
        status=200,
        mimetype="application/json",
    )


if __name__ == "__main__":
    app.run(debug=True, port=5000)
