# BRSR Real-Report Pattern Brief
**Sources:** Tata Chemicals FY25, Infosys FY24-25, Mahindra Logistics FY24, StepChange BRSR Barometer 2023, GloCert Assurance Guide
**Purpose:** Input for AI system prompt — few-shot patterns for language, structure, and handling gaps

---

## 1. How Companies Handle Missing Data

There are four distinct missing-data situations, each with a different language pattern:

**A. Field is genuinely zero (not N/A):**
Use a hard number with a brief qualifier. Never leave blank.
> *"Zero fatalities reported during FY 2024-25 for both employees and workers."*
> *"Nil complaints received under POSH during the reporting period."*

**B. Field doesn't apply to the business model:**
State the business reason explicitly, not just "NA."
> *"The Company is primarily engaged in IT services and does not have manufacturing operations; accordingly, radioactive waste and bio-medical waste disclosures are not applicable."*
> *"Not Applicable — the Company does not directly source raw materials; this KPI is not material to our business model."*
Bare "NA" in a table cell without explanation fails assurance review. Companies that pass KPMG/EY assurance always have a footnote.

**C. Data tracked but not yet reported to the required granularity:**
Disclose what you have, acknowledge the gap, and commit to a timeline.
> *"Scope 3 emissions are currently under compilation. Disclosures will be included from FY 2025-26 onwards as the Company builds out its value-chain measurement methodology."*
> *"Contract labour welfare data is being systematised across all site contractors. Partial data for captive contractors is provided below; full disclosure expected from Q2 FY26."*

**D. Data genuinely unavailable for a prior year (comparison column):**
> *"Previous year data not available as this indicator was not tracked prior to FY 2023-24."*
> *"— (Not tracked; base year established in FY 2023-24)"*

**AI rule:** For any blank input field, generate language from pattern B, C, or D — never output a blank cell or bare "NA."

---

## 2. Quantitative Disclosure Language Patterns

**Number format rules observed across all three reports:**
- Large numbers in Indian notation: *"47.70 lakh tonnes CO₂e"* not "4,770,000 tonnes"
- Intensity always expressed per INR crore of turnover: *"37 tCO₂e per crore of revenue"*
- Two decimal places for LTIFR: *"LTIFR: 1.53 (employees), 0.54 (workers)"*
- Percentages rounded to two decimal places: *"Gross wages to females: 28.34% of total wages"*
- Always present current year + previous year side by side

**Table header convention:**
| Parameter | Unit | FY 2024-25 | FY 2023-24 |
Every table has this structure. No deviations in any report reviewed.

**Units used in practice (calibrate AI output):**
- GHG: metric tonnes CO₂e (not "tons" — always metric tonnes)
- Energy: GJ (gigajoules) — some companies also show kWh alongside
- Water: KL (kiloliters) or million KL for large extractors like Tata Chemicals (1003 million KL)
- Waste: MT (metric tonnes)
- LTIFR: per million man-hours worked
- Wages to females: % of total gross wages
- MSME sourcing: % of total purchases by value

**The intensity line always appears immediately after the absolute number:**
> *"Total Scope 1+2 emissions: 47.75 lakh MT CO₂e. Emission intensity: 32.06 MT CO₂e per INR crore of turnover."*

---

## 3. Qualitative Governance Responses — Strong vs Minimal

### Principle 1 (Ethics and Governance) — the benchmark principle

**Minimal response (boilerplate — what to avoid generating):**
> *"The Company is committed to conducting business with integrity and transparency. It has adopted policies to ensure ethical conduct across its operations."*
Problems: no named policy, no oversight mechanism, no quantification, untestable claim.

**Strong response (what to aim for):**
> *"The Company's Code of Conduct (approved by the Board on [date], available at [URL]) applies to all directors, employees, and business partners. Compliance training is mandatory for 100% of permanent employees, completed annually on the [platform name]. During FY 2024-25, zero instances of non-compliance with the Code were reported. Complaints are received through the Vigil Mechanism / Whistleblower Policy, overseen by the Audit Committee (Chair: [name]). [X] complaints were received, of which [Y] were resolved and [Z] are under review."*
Distinguishing features: named policy document + named oversight body + quantified compliance rate + quantified outcome.

### Principle 6 (Environment) — the most data-heavy principle

**Minimal:**
> *"The Company is committed to environmental protection and regularly monitors its environmental impact."*

**Strong:**
> *"The Company has a Board-level Safety, Health, Environment & Sustainability (SHES) Committee which reviews environmental KPIs on a quarterly basis. Environment-related capex in FY 2024-25 was ₹XX crore (X% of total capex). The Company has set a science-based target to reduce Scope 1+2 emissions by 25% by FY 2030 against a FY 2020 baseline. Progress: [X]% reduction achieved to date."*
Distinguishing features: committee name + review frequency + capital commitment + quantified target with baseline year + progress reported.

### Pattern across all Principles
Strong responses share three elements: (1) a named mechanism or body, (2) a quantified input (spend, rate, coverage), (3) a quantified outcome (incidents, complaints, % achieved). If any of these three is absent, the response reads as minimal.

---

## 4. Document Structure Patterns

**Section hierarchy (SEBI-mandated, all companies follow exactly):**
- Section A: General Disclosures (company identity, operations, employees)
- Section B: Management and Process Disclosures (policies, committees, grievance mechanisms)
- Section C: Principle-wise Performance Disclosures (Principles 1–9)
  - Each Principle: Essential Indicators (mandatory) → Leadership Indicators (voluntary)
- BRSR Core KPIs: Some companies call these out in a separate index at the end with assurance status marked

**Cover page convention:**
Every BRSR opens with a statement signed by a director: *"Name of Director responsible for BRSR: [Name], DIN: [XXXXXXXX], Designation: [Title]."* The AI should generate a placeholder for this.

**Footnote usage:**
Companies use footnotes for: (1) methodology statements, (2) boundary definitions (consolidated vs standalone), (3) restatements of prior year data. The AI should generate a standard methodology footnote for all intensity KPIs.

**Language register:**
Formal Indian corporate English. Third person: *"The Company has..."*, *"The Board reviews..."*, *"During the reporting period..."*. Never first person. No contractions. Passive voice for policy statements; active voice for outcome statements.

---

## 5. Sector-Specific Baselines (for AI calibration)
From StepChange BRSR Barometer — chemicals sector medians:
- GHG intensity: 37 tCO₂e / INR crore
- Energy intensity: 311 GJ / INR crore
- Water intensity: 194 KL / INR crore
- Waste intensity: 1.15 MT / INR crore
- Female employee ratio: 0.06 (notably low — flag in AI output for manufacturing companies)

For IT/services companies (Infosys profile): GHG intensity ~2–4 tCO₂e/crore, energy mostly electricity, water intensity very low, waste dominated by e-waste.

---

## 6. Red Flags to Catch and Fix in AI Output
1. Bare "NA" without explanation → replace with business-reason language
2. Single-year data without prior year → add prior year column even if "not tracked"
3. Generic policy statement without named mechanism → add committee name placeholder
4. Percentage without denominator definition → always state "as % of total [X]"
5. Scope 3 claims without methodology note → add "to be disclosed" language
6. LTIFR without man-hours denominator context → add denominator in footnote
