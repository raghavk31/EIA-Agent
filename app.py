import io
import json
import os
import re
import uuid
import markdown as md
from dotenv import load_dotenv
from openai import OpenAI
from flask import Flask, request, send_file, Response, render_template, jsonify

load_dotenv()  # no-op in production where env vars are set directly

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 4 * 1024 * 1024  # 4 MB form limit

# In-memory chat sessions: {session_id: {fields: {}, history: []}}
# Single worker only — see Dockerfile. Switch to Redis for multi-worker.
chat_sessions: dict = {}


def get_client():
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise RuntimeError("OPENROUTER_API_KEY is not set. Add it to your .env file.")
    return OpenAI(base_url="https://openrouter.ai/api/v1", api_key=key)


def load_system_prompt():
    with open("system_prompt_v1.md", encoding="utf-8") as f:
        raw = f.read()
    # Strip the markdown code-fence wrapper — content lives between first ``` and last ```
    start = raw.find("```\n") + 4
    end = raw.rfind("\n```")
    return raw[start:end].strip()


SYSTEM_PROMPT = load_system_prompt()

CHAT_SYSTEM_PROMPT = """You are a BRSR Core data collection assistant. You help Indian listed companies collect the ESG data needed for mandatory BRSR Core disclosure under SEBI regulations (Circular SEBI/HO/CFD/CFD-SEC-2/P/CIR/2023/122).

CONVERSATION ORDER:
1. Company name → Financial year (e.g. "FY 2024-25") → Revenue from operations (INR crore)
2. Then collect data in this sequence: GHG Emissions → Water → Energy → Waste → Safety → Gender Wages → Supply Chain → Customer Data

STYLE RULES:
- Ask 1-2 questions at a time. Never overwhelm.
- After each user reply, confirm what you extracted: "Got it — Scope 1 emissions of 47,70,357 MT CO₂e this year."
- Ask for both current year AND previous year for each metric.
- If user says data isn't available or being compiled, accept it and move on. Note it as unavailable.
- Be concise, professional, and warm. This is a compliance task — respect the user's time.

EXTRACTION RULES:
- Parse Indian number format: 47,70,357 means 4770357 (remove all commas before storing).
- Only extract what the user explicitly provides. Never infer or fill defaults.
- Do not include unavailable fields in "extracted".

FIELD NAMES — use these exact keys in "extracted":
Company: company_name (str), financial_year (str e.g. "FY 2024-25"), prev_financial_year (str), cin (str), sector (str), revenue_current (float INR crore), revenue_prev (float INR crore)
Workforce: perm_emp_male, perm_emp_female, contract_workers_male, contract_workers_female
GHG (MT CO₂e): scope1_current, scope1_prev, scope2_current, scope2_prev, scope1_co2, scope1_ch4, scope1_n2o, scope1_co2_prev, scope1_ch4_prev, scope1_n2o_prev
Water withdrawal (kilolitres): water_surface_fresh_current, water_ground_fresh_current, water_third_fresh_current, water_sea_current, water_other_current, water_withdrawal_prev, water_consumed_current, water_consumed_prev
Water discharge (kilolitres): water_disch_surface, water_disch_ground, water_disch_sea, water_disch_third
Energy (gigajoules): energy_nonrenew_current, energy_nonrenew_prev, energy_renew_current, energy_renew_prev
Waste (metric tonnes): waste_hazardous, waste_nonhazardous, waste_plastic, waste_ewaste, waste_biomedical, waste_construction, waste_battery, waste_other_hazardous, waste_other_nonhazardous, waste_total_prev, waste_recycled, waste_reused, waste_landfill
Safety: ltifr_emp_current, ltifr_emp_prev, fatalities_emp_current, fatalities_emp_prev, highconsequence_emp_current, highconsequence_emp_prev, recordable_emp_current, recordable_emp_prev, manhours_emp_current, ltifr_worker_current, ltifr_worker_prev, fatalities_worker_current, fatalities_worker_prev, highconsequence_worker_current, highconsequence_worker_prev, recordable_worker_current, recordable_worker_prev, wellbeing_emp_pct_current, wellbeing_emp_pct_prev, wellbeing_worker_pct_current, wellbeing_worker_pct_prev
Gender: female_wages_pct_current (%), female_wages_pct_prev (%)
Supply chain: msme_pct_current (%), msme_pct_prev (%), india_sourcing_pct_current (%), india_sourcing_pct_prev (%), smaller_towns_pct_current (%), smaller_towns_pct_prev (%)
Customers: data_breach_pct_current (%), data_breach_count_current, total_cyber_events, ap_days_current, ap_days_prev
Director: director_name (str), director_din (str), director_designation (str)

PROGRESS TRACKING:
Mark a section true when you have collected its primary metrics OR the user has confirmed the data is unavailable.
- company: have company_name + financial_year + revenue_current
- ghg: have scope1_current + scope2_current (or confirmed N/A)
- water: have water_consumed_current (or confirmed N/A)
- energy: have energy_nonrenew_current + energy_renew_current (or confirmed N/A)
- waste: have at least one waste type (or confirmed N/A)
- safety: have ltifr_emp_current + fatalities_emp_current (or confirmed N/A)
- gender: have female_wages_pct_current (or confirmed N/A)
- supply_chain: have msme_pct_current (or confirmed N/A)
- customers: have ap_days_current (or confirmed N/A)

RESPONSE FORMAT — always respond with ONLY valid JSON, no markdown, no code fences, no preamble:
{
  "message": "Your conversational reply and next question (plain text, no markdown formatting)",
  "extracted": {},
  "progress": {
    "company": false,
    "ghg": false,
    "water": false,
    "energy": false,
    "waste": false,
    "safety": false,
    "gender": false,
    "supply_chain": false,
    "customers": false
  },
  "ready": false
}

Set ready=true only when all 9 progress sections are true."""


def call_chat_claude(history: list) -> dict:
    model = os.environ.get("OPENROUTER_MODEL", "anthropic/claude-sonnet-4-5")
    response = get_client().chat.completions.create(
        model=model,
        max_tokens=1500,
        messages=[
            {"role": "system", "content": CHAT_SYSTEM_PROMPT},
            *history,
        ],
    )
    text = response.choices[0].message.content.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r'\{[\s\S]*\}', text)
        if match:
            try:
                return json.loads(match.group())
            except Exception:
                pass
    return {"message": text, "extracted": {}, "progress": {}, "ready": False}


def auto_status(form_status, *check_values):
    """Downgrade 'available' to 'compiling' when no data was actually provided."""
    resolved = form_status or "available"
    if resolved == "available" and all(v is None for v in check_values):
        return "compiling"
    return resolved


def build_user_message(data: dict) -> str:
    company = data.get("company", {})
    fy      = company.get("financial_year") or "the current financial year"
    prev_fy = company.get("prev_financial_year") or "previous year"
    name    = company.get("name") or "[Company Name]"

    return f"""Generate a complete BRSR Core disclosure report for {name} for {fy}.

CRITICAL: Use ONLY the numbers in COMPANY DATA below. Do not invent any figure, name, date, or statistic.

Token budget allocation (MUST follow):
- Section A: ≤200 words, factual only
- Section B: ≤300 words, policy names and governance structure only
- Section C: ≤80 words per Principle, cross-reference KPI Index for numbers
- BRSR Core KPI Index: FULL detail, all 40 KPIs, do not truncate

Apply every rule from your instructions:
- Formal Indian corporate English, third person throughout
- All quantitative tables: two columns — {fy} | {prev_fy}
- Intensity metrics: footnote with the revenue denominator (INR crore)
- Missing fields: apply the correct Pattern (A zero / B not-applicable / C compiling / D prior-year) based on each field's "status" value
- Governance responses: named body + quantified input + quantified outcome (or [PLACEHOLDER] if not in data)
- Run the 10-point self-check before finalising

COMPANY DATA:
{json.dumps(data, indent=2, ensure_ascii=False)}

Output the complete report in Markdown. Structure exactly:
# BUSINESS RESPONSIBILITY AND SUSTAINABILITY REPORT
## SECTION A: GENERAL DISCLOSURES
## SECTION B: MANAGEMENT AND PROCESS DISCLOSURES
## SECTION C: PRINCIPLE-WISE PERFORMANCE DISCLOSURES
### Principle 1 … through Principle 9 (one short paragraph each, cross-reference KPI Index)
## BRSR CORE — KPI INDEX
"""


def call_claude(data: dict) -> str:
    model = os.environ.get("OPENROUTER_MODEL", "anthropic/claude-sonnet-4-5")
    response = get_client().chat.completions.create(
        model=model,
        max_tokens=16000,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": build_user_message(data)},
        ],
    )
    return response.choices[0].message.content


def markdown_to_pdf(draft: str, data: dict) -> bytes:
    company = data.get("company", {})
    director = company.get("director", {})

    # Strip the AI's own cover heading — the template provides the cover page
    body = re.sub(r"^#\s+BUSINESS RESPONSIBILITY.*?\n", "", draft, flags=re.IGNORECASE)

    html_body = md.markdown(
        body,
        extensions=["tables", "nl2br", "sane_lists"],
    )

    full_html = render_template(
        "pdf_report.html",
        html_body=html_body,
        company_name=company.get("name") or "[Company Name]",
        fy=company.get("financial_year") or "",
        cin=company.get("cin") or "",
        director_name=director.get("name") or "",
        director_din=director.get("din") or "",
        director_designation=director.get("designation") or "",
    )

    # Try WeasyPrint first (works on Linux/Railway), fall back to xhtml2pdf on Windows
    try:
        from weasyprint import HTML
        return HTML(string=full_html).write_pdf()
    except Exception as wp_err:
        # Fallback for Windows dev where WeasyPrint needs GTK libs.
        # Install xhtml2pdf manually on Windows: pip install xhtml2pdf
        try:
            return _pdf_via_xhtml2pdf(html_body, data)
        except ImportError:
            raise RuntimeError(
                f"WeasyPrint failed ({wp_err}). On Windows, install xhtml2pdf: pip install xhtml2pdf"
            ) from wp_err


def _pdf_via_xhtml2pdf(html_body: str, data: dict) -> bytes:
    """Simplified PDF for local Windows dev — xhtml2pdf doesn't support CSS Paged Media."""
    from xhtml2pdf import pisa

    company = data.get("company", {})
    director = company.get("director", {})
    company_name = company.get("name") or "[Company Name]"
    fy = company.get("financial_year") or ""
    cin = company.get("cin") or "[To be confirmed]"
    director_name = director.get("name") or ""
    director_din = director.get("din") or ""
    director_designation = director.get("designation") or ""

    simple_html = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<style>
@page {{ size: A4; margin: 22mm 20mm 22mm 25mm; }}
body {{ font-family: Georgia, serif; font-size: 10pt; line-height: 1.6; color: #111827; }}
h1 {{ font-family: Arial, sans-serif; font-size: 14pt; font-weight: bold; color: #1e3a5f;
      text-transform: uppercase; border-bottom: 2pt solid #1e3a5f; padding-bottom: 3pt;
      margin-top: 14pt; page-break-after: avoid; }}
h2 {{ font-family: Arial, sans-serif; font-size: 12pt; font-weight: bold; color: #1e3a5f;
      border-bottom: 1pt solid #93c5fd; padding-bottom: 2pt; margin-top: 12pt; page-break-after: avoid; }}
h3 {{ font-family: Arial, sans-serif; font-size: 10.5pt; font-weight: bold; color: #1e40af;
      margin-top: 10pt; page-break-after: avoid; }}
h4 {{ font-family: Arial, sans-serif; font-size: 10pt; font-weight: bold; color: #374151; margin-top: 8pt; }}
p  {{ margin-bottom: 6pt; text-align: justify; }}
table {{ width: 100%; border-collapse: collapse; margin: 6pt 0 10pt 0; font-size: 9pt; }}
th {{ background-color: #1e3a5f; color: white; font-family: Arial, sans-serif;
      font-size: 8.5pt; padding: 5pt 7pt; text-align: left; border: 0.5pt solid #1e3a5f; }}
td {{ padding: 4pt 7pt; border: 0.5pt solid #d1d5db; font-size: 9pt; vertical-align: top; }}
ul, ol {{ padding-left: 14pt; margin-bottom: 6pt; }}
li {{ margin-bottom: 2pt; }}
hr {{ border: none; border-top: 1pt solid #e5e7eb; margin: 10pt 0; }}
.cover {{ page-break-after: always; padding: 10mm 0; }}
.cover-band {{ background-color: #1e3a5f; height: 10mm; width: 100%; }}
.cover-inner {{ padding: 12mm 0; }}
.cover-title {{ font-family: Arial, sans-serif; font-size: 12pt; font-weight: bold;
                color: #1e3a5f; text-transform: uppercase; margin-bottom: 2mm; }}
.cover-name  {{ font-family: Arial, sans-serif; font-size: 22pt; font-weight: bold;
                color: #111827; margin: 4mm 0; }}
.cover-meta  {{ font-family: Arial, sans-serif; font-size: 10pt; color: #374151;
                margin-bottom: 2mm; }}
.note-box {{ border: 1pt solid #d1d5db; padding: 5mm; margin-top: 8mm;
             background-color: #f9fafb; font-family: Arial, sans-serif;
             font-size: 9pt; color: #374151; }}
</style>
</head><body>

<div class="cover">
  <div class="cover-band"></div>
  <div class="cover-inner">
    <p class="cover-title">Business Responsibility &amp; Sustainability Report</p>
    <p class="cover-title" style="font-size:9pt;color:#6b7280;font-weight:normal;">
      BRSR Core &mdash; For Independent Assurance
    </p>
    <p class="cover-name">{company_name}</p>
    <p class="cover-meta"><b>Financial Year:</b> {fy}</p>
    <p class="cover-meta"><b>CIN:</b> {cin}</p>
    {"<p class='cover-meta'><b>Director Responsible:</b> " + director_name + (", DIN: " + director_din if director_din else "") + (", " + director_designation if director_designation else "") + "</p>" if director_name else ""}
    <p class="cover-meta"><b>Regulatory Reference:</b> SEBI Circular SEBI/HO/CFD/CFD-SEC-2/P/CIR/2023/122 dated July 12, 2023</p>
    <div class="note-box">
      <b>Note:</b> This is a first draft for internal review. All figures must be
      verified against source data before filing. Qualitative disclosures require
      sign-off from the responsible team.
    </div>
  </div>
  <div class="cover-band"></div>
</div>

{html_body}

</body></html>"""

    buf = io.BytesIO()
    pisa.CreatePDF(simple_html, dest=buf)
    return buf.getvalue()


def build_payload(get_str) -> dict:
    """Build the structured data payload for Claude. get_str(key) returns a string."""

    def num(key, default=None):
        val = str(get_str(key)).strip().replace(",", "")
        try:
            return float(val) if val else default
        except ValueError:
            return default

    def txt(key):
        v = str(get_str(key)).strip()
        return v if v else None

    # ── Revenue ───────────────────────────────────────────────────────────
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

    # ── Helpers for auto_status detection ────────────────────────────────
    _water_sources = [
        num("water_surface_fresh_current"), num("water_ground_fresh_current"),
        num("water_third_fresh_current"), num("water_sea_current"), num("water_other_current"),
    ]
    _water_any_source = next((v for v in _water_sources if v is not None), None)
    _discharge_any = next(
        (v for v in [num("water_disch_surface"), num("water_disch_ground"), num("water_disch_sea"), num("water_disch_third")]
         if v is not None), None
    )

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
                    "status":   auto_status(txt("scope1_status"), scope1),
                    "current":  scope1,
                    "prev":     num("scope1_prev"),
                    "na_context": txt("scope1_na_context"),
                    "breakup": {
                        "co2":  num("scope1_co2"),
                        "ch4":  num("scope1_ch4"),
                        "n2o":  num("scope1_n2o"),
                        "co2_prev": num("scope1_co2_prev"),
                        "ch4_prev": num("scope1_ch4_prev"),
                        "n2o_prev": num("scope1_n2o_prev"),
                    },
                },
                "scope2": {
                    "status":   auto_status(txt("scope2_status"), scope2),
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
                    "status":   auto_status(txt("water_withdrawal_status"), _water_any_source),
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
                    "status":    auto_status(txt("water_discharge_status"), _discharge_any),
                    "surface":   num("water_disch_surface"),
                    "groundwater": num("water_disch_ground"),
                    "seawater":  num("water_disch_sea"),
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
                "status":        auto_status(txt("waste_status"), waste_total),
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
                    "high_consequence_prev":   num("highconsequence_emp_prev"),
                    "recordable_current":      num("recordable_emp_current"),
                    "recordable_prev":         num("recordable_emp_prev"),
                },
                "workers": {
                    "ltifr_current":           num("ltifr_worker_current"),
                    "ltifr_prev":              num("ltifr_worker_prev"),
                    "fatalities_current":      num("fatalities_worker_current"),
                    "fatalities_prev":         num("fatalities_worker_prev"),
                    "high_consequence_current":num("highconsequence_worker_current"),
                    "high_consequence_prev":   num("highconsequence_worker_prev"),
                    "recordable_current":      num("recordable_worker_current"),
                    "recordable_prev":         num("recordable_worker_prev"),
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
                    "status":   auto_status(txt("msme_status"), num("msme_pct_current")),
                    "current":  num("msme_pct_current"),
                    "prev":     num("msme_pct_prev"),
                    "na_context": txt("msme_na_context"),
                },
                "india_sourcing": {
                    "status":   auto_status(txt("india_sourcing_status"), num("india_sourcing_pct_current")),
                    "current":  num("india_sourcing_pct_current"),
                    "prev":     num("india_sourcing_pct_prev"),
                    "na_context": txt("india_sourcing_na_context"),
                },
                "smaller_towns": {
                    "status":         auto_status(txt("smaller_towns_status"), num("smaller_towns_pct_current")),
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

    return data


# ── PDF helper ────────────────────────────────────────────────────────────────

def _generate_pdf_response(data: dict):
    draft = call_claude(data)
    pdf_bytes = markdown_to_pdf(draft, data)
    company_name = (data.get("company", {}).get("name") or "Company").replace(" ", "_")
    fy = (data.get("company", {}).get("financial_year") or "FY").replace(" ", "_")
    filename = f"BRSR_Core_{company_name}_{fy}.pdf"
    return send_file(
        io.BytesIO(pdf_bytes),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=filename,
    )


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_file("chat.html")


@app.route("/form")
def legacy_form():
    return send_file("form.html")


@app.route("/chat", methods=["POST"])
def chat():
    body = request.json or {}
    session_id = body.get("session_id")
    message = body.get("message", "")

    if not session_id or session_id not in chat_sessions:
        session_id = str(uuid.uuid4())
        chat_sessions[session_id] = {"fields": {}, "history": []}

    session = chat_sessions[session_id]

    if message and message != "__start__":
        session["history"].append({"role": "user", "content": message})

    result = call_chat_claude(session["history"])

    extracted = result.get("extracted") or {}
    if extracted:
        session["fields"].update(extracted)

    reply = result.get("message") or "I'm ready to help with your BRSR report. What is your company name?"
    session["history"].append({"role": "assistant", "content": reply})

    return jsonify({
        "session_id": session_id,
        "message": reply,
        "progress": result.get("progress") or {},
        "ready": result.get("ready", False),
    })


@app.route("/generate_chat", methods=["POST"])
def generate_chat():
    body = request.json or {}
    session_id = body.get("session_id")

    if not session_id or session_id not in chat_sessions:
        return jsonify({"error": "Session not found. Please refresh and start again."}), 400

    fields = chat_sessions[session_id]["fields"]

    if not fields.get("company_name"):
        return jsonify({"error": "Company name is required before generating the report."}), 400

    data = build_payload(lambda key: str(fields.get(key, "")))
    return _generate_pdf_response(data)


@app.route("/generate", methods=["POST"])
def generate():
    f = request.form
    missing = []
    if not f.get("company_name", "").strip():
        missing.append("Company Name")
    if not f.get("financial_year", "").strip():
        missing.append("Financial Year")
    if not f.get("revenue_current", "").strip():
        missing.append("Current Year Revenue")
    if missing:
        items = "".join(f"<li>{m}</li>" for m in missing)
        return f"""<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><title>Missing Fields</title>
<style>body{{font-family:-apple-system,sans-serif;max-width:600px;margin:60px auto;padding:0 24px}}
h2{{color:#dc2626}}ul{{margin:12px 0 24px;padding-left:20px;line-height:1.8}}
a{{display:inline-block;padding:10px 20px;background:#0ea5e9;color:#fff;border-radius:6px;text-decoration:none}}
</style></head><body><h2>Required fields missing</h2><ul>{items}</ul>
<a href="/form">← Back to form</a></body></html>""", 400

    data = build_payload(lambda key: f.get(key, ""))
    return _generate_pdf_response(data)


if __name__ == "__main__":
    app.run(debug=True, port=5000)
