# Seed Contract Templates for instrument placement (CPT / RRA / RLO).
# Idempotent: only inserts when the title is absent, never overwrites a
# customized template. Per-customer variance lives on the contract's own
# contract_terms copy, fetched via get_contract_template at selection time.

import frappe

_COMMON_HEAD = """<h3>CONTRACT FOR THE PLACEMENT OF MEDICAL EQUIPMENT</h3>
<p><b>{{ contract_title }}</b><br>Contract Type: {{ contract_type }}<br>
Customer: {{ customer_name }}<br>Analyzer: {{ analyzer_pid }} — {{ analyzer_description }}<br>
Serial No: {{ serial_no }}<br>Term: {{ start_date }} to {{ end_date }}
({{ contract_duration_months }} months)</p>
<h4>RECITALS</h4>
<p>WHEREAS the Supplier places the Instrument at the Customer laboratory and
retains ownership; WHEREAS the Customer operates a diagnostic laboratory and
requires the Instrument to improve diagnostic capacity; NOW the Parties agree:</p>
<h4>ARTICLE 1 - DEFINITIONS</h4>
<p>“Instrument” means {{ analyzer_pid }} (S/N {{ serial_no }}) with modules,
software and accessories. “Reportable Test” means a validated result released
for clinical use, excluding QC, calibration and operator-error repeats.
“Commencement Date” means the last signature date. “Term” means
{{ contract_duration_months }} months from the Commencement Date.</p>
<h4>ARTICLE 2 - SUBJECT</h4>
<p>The Supplier places the Instrument at the Customer laboratory; brochures
spelling out specifications and functionality are attached.</p>
<h4>ARTICLE 3 - SCOPE AND EXCLUSIVITY</h4>
<p>The Instrument is for the Customer's own diagnostic testing only. The
Customer obtains 100% of the Instrument reagent requirements from the Supplier
and introduces no third-party reagents, refurbished consumables or
non-authorized parts; breach voids warranty and service obligations.</p>
"""

_COMMON_TAIL = """<h4>ARTICLE 6 - ORDERS</h4>
<p>Written purchase orders at least 14 business days before the required date;
acknowledgement within 48 hours; delivery within 10 business days. The Customer
keeps at least 4 weeks safety stock.</p>
<h4>ARTICLE 7 - STORAGE AND SHELF LIFE</h4>
<p>Store per manufacturer instructions (e.g. 2°C - 30°C); daily temperature log
on request. Delivered consumables carry at least 75% remaining shelf life.
Spoilage from improper storage, power outage beyond 4 consecutive hours or
negligence is the Customer's account.</p>
<h4>ARTICLE 8 - WARRANTY</h4>
<p>Instrument free from defects in material and workmanship for the Term;
Supplier repairs or replaces defective components (parts, labour, travel)
except for misuse, unauthorized consumables, accident, power surge or force
majeure. Defective consumables are replaced free.</p>
<h4>ARTICLE 9 - OWNERSHIP</h4>
<p>The Instrument remains the Supplier's sole property. No sale, pledge, lease
or encumbrance. On termination/expiry the Customer ceases use and makes the
Instrument with accessories, software and documentation available for
collection within 7 days during business hours.</p>
<h4>ARTICLE 10 - RISK</h4>
<p>Risk of loss, theft, damage or destruction passes to the Customer on
delivery and installation.</p>
<h4>ARTICLE 11 - INSTALLATION AND TRAINING</h4>
<p>Delivery and installation within 15 business days of Commencement (site
prepared per Schedule D); 5 business days acceptance testing with a joint
Installation &amp; Acceptance Report; on-site training for up to 6 staff;
refresher training twice per year on reasonable request.</p>
<h4>ARTICLE 12 - FORCE MAJEURE</h4>
<p>Neither Party is liable for delay from events beyond reasonable control;
7 days written notice with updates and mitigation; termination on 14 days
notice after 90 consecutive days.</p>
<h4>ARTICLE 13 - ACCEPTANCE AND USE</h4>
<p>Joint acceptance test; signature of the Installation &amp; Acceptance
Report, deemed accepted after 5 business days without valid technical
objection. Trained personnel only; no relocation without written consent.</p>
<h4>ARTICLE 14 - MAINTENANCE AND SLA</h4>
<p>Preventive maintenance quarterly at no extra cost. Breakdown response:
acknowledge within 2 working hours, on site within 48 hours for critical
failures, restore within 5 business days. Downtime beyond 7 consecutive
business days attributable to the Supplier credits 10% of the average monthly
value per extra week. Signed maintenance log after each visit.</p>
<h4>ARTICLE 15 - CUSTOMER OBLIGATIONS</h4>
<p>Suitable secure environment with surge protection and adequate UPS; trained
operators; daily QC with supplied controls; compliance with applicable health
laboratory policy and data protection law. No modification, reverse
engineering or unauthorized repair.</p>
<h4>ARTICLE 16 - LIABILITY</h4>
<p>No indirect or consequential damages. Aggregate liability capped at payments
made in the 12 months preceding the claim.</p>
<h4>ARTICLE 17 - TERMINATION</h4>
<p>No termination without cause or material breach. Material breach: 30 days
cure notice; insolvency: immediate. Non-payment: 14 days notice after 60 days
overdue. Accrued payments, return, confidentiality, arbitration and governing
law survive.</p>
<h4>ARTICLE 18 - NOTICES</h4>
<p>In writing: personal delivery, registered post or confirmed email.</p>
<h4>ARTICLE 19 - DATA PROTECTION</h4>
<p>Customer owns all patient data. Supplier sees usage data (counts, error
logs) for billing and maintenance only, no patient-identifiable processing.</p>
<h4>ARTICLE 20 - VARIATION</h4>
<p>Only by written amendment signed by both Parties (Contract Amendment).</p>
<h4>ARTICLE 21 - DISPUTES</h4>
<p>Good-faith negotiation within 15 business days, then arbitration under the
Arbitration Act 2010 (Act 798), seat Accra, in English; interim relief from
the High Court preserved.</p>
<h4>ARTICLE 22 - CONFIDENTIALITY</h4>
<p>Mutual confidentiality for 5 years after termination; pricing, volumes and
performance data are proprietary.</p>
<h4>ARTICLE 23 - GOVERNING LAW</h4>
<p>Laws of the Republic of Ghana.</p>
<h4>ARTICLE 24 - SEVERABILITY / ARTICLE 25 - WAIVER</h4>
<p>Invalid provisions do not affect the remainder; no waiver by delay.</p>
<h4>ARTICLE 26 - SCHEDULES</h4>
<p>A: Authorized Consumables. B: Price Matrix. C: SLA. D: Site Preparation.
E: Acceptance Certificate. F: Monthly Count Confirmation.</p>
"""

_CPT_TERM = """<h4>ARTICLE 4 - DURATION AND VOLUME</h4>
<p>Initial term {{ contract_duration_months }} months with successive one-year
renewals unless 120 days non-renewal notice. Minimum volume: about
{{ avg_samples_per_day }} samples/day ({{ operational_days_per_month }}
operational days/month). Three consecutive shortfalls allow price
renegotiation or termination on 30 days notice.</p>
<h4>ARTICLE 5 - COST PER TEST PRICING AND PAYMENT</h4>
<p>CPT price per reportable test as per Schedule B; the Supplier share is
{{ revenue_share_pct }}% (about {{ fixed_monthly_share_amount }} per month on
a declared {{ fixed_monthly_gross_revenue }} gross). Invoices on resupply
notice; payment within 14 days by transfer, cash or cheque. Late payment
interest 6% per month or the legal maximum. Price fixed 12 months, then annual
CPI revision capped at 10%.</p>
"""

_RRA_TERM = """<h4>ARTICLE 4 - DURATION AND VOLUME</h4>
<p>Initial term {{ contract_duration_months }} months with successive one-year
renewals unless 120 days non-renewal notice. Minimum monthly purchase value
{{ min_monthly_value }}; grace period {{ grace_period_days }} days; breach
after {{ breach_threshold }} consecutive shortfall months.</p>
<h4>ARTICLE 5 - REAGENT RENTAL PRICING AND PAYMENT</h4>
<p>Reagent prices per Schedule B (cost plus uniform markup recovering analyzer,
interest, maintenance and profit: total recovery target
{{ total_recovery_target }}). Invoices per delivery; payment within 14 days.
Late payment interest 6% per month or the legal maximum. Shortfall penalties
per the contract penalty type. Annual price review capped at 10%.</p>
"""

_RLO_TERM = """<h4>ARTICLE 4 - DURATION AND VOLUME</h4>
<p>Initial term {{ contract_duration_months }} months with successive one-year
renewals unless 120 days non-renewal notice. Minimum monthly purchase value
{{ min_monthly_value }}; grace period {{ grace_period_days }} days; breach
after {{ breach_threshold }} consecutive shortfall months.</p>
<h4>ARTICLE 5 - RENT-TO-OWN PRICING, PAYMENT AND TRANSFER</h4>
<p>Reagent prices per Schedule B (cost plus uniform markup recovering analyzer,
cost of capital, maintenance and profit: total recovery target
{{ total_recovery_target }}). Invoices per delivery; payment within 14 days.
On full recovery the Supplier transfers ownership via Ownership Transfer
Request with certificate and transfer invoice. Annual price review capped
at 10%.</p>
"""

TEMPLATES = {
	"CPT-Placement-v1": _COMMON_HEAD + _CPT_TERM + _COMMON_TAIL,
	"RRA-Placement-v1": _COMMON_HEAD + _RRA_TERM + _COMMON_TAIL,
	"RLO-Placement-v1": _COMMON_HEAD + _RLO_TERM + _COMMON_TAIL,
}


def ensure_placement_contract_templates():
	"""Idempotent: seed CPT/RRA/RLO Contract Templates if absent."""
	for title, terms in TEMPLATES.items():
		if frappe.db.exists("Contract Template", title):
			continue
		try:
			frappe.get_doc({"doctype": "Contract Template", "title": title, "contract_terms": terms}).insert(
				ignore_permissions=True
			)
		except Exception:
			frappe.log_error(frappe.get_traceback(), f"ensure template failed: {title}")
