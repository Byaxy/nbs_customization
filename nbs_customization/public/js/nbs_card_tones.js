/**
 * NBS Customization — nbs_card_tones.js
 *
 * One semantic palette for every workspace and dashboard card. A card takes a
 * tone from what it reports, never from the module it sits in. An unknown title
 * falls back to neutral.
 */

(function () {
	const COLORS = {
		green: "#10b981",
		blue: "#1d4ed8",
		amber: "#f59e0b",
		red: "#b91c1c",
		steel: "#3b82c4",
		slate: "#475569",
	};

	const TONES = {
		revenue: "green",
		"gross margin": "green",
		"net profit": "green",
		"cash and bank balance": "green",
		"accounts receivable": "blue",
		"accounts payable": "amber",
		"payments received": "green",
		"payments made": "amber",
		"sales invoiced": "green",
		"purchases billed": "amber",
		"purchases to receive": "blue",
		"purchases to bill": "amber",
		"orders to deliver": "blue",
		"orders to bill": "amber",
		"due in next 30 days": "amber",
		overdue: "red",
		"asset value": "green",
		"accumulated depreciation": "amber",
		depreciation: "amber",
		"new assets": "green",
		disposals: "slate",
		"assets with unposted depreciation": "amber",
		"total assets": "blue",
		"purchase amount": "amber",
		"material requests to order": "blue",
		"purchase orders to receive": "blue",
		"purchase orders to bill": "amber",
		"overdue purchase orders": "red",
		"on-time delivery": "steel",
		"annual purchase": "amber",
		"sales order value": "green",
		"sales orders to deliver": "blue",
		"sales orders to bill": "amber",
		"open quotations": "amber",
		"quotation win rate": "steel",
		"annual sales": "green",
		"stock value": "green",
		"total stock value": "green",
		"received from suppliers": "blue",
		"delivered to customers": "blue",
		"items to reorder": "amber",
		"items in shortage": "red",
		"total active items": "blue",
		"total warehouses": "slate",
		"absent days": "red",
		"leave days": "amber",
		"on leave today": "amber",
		"number of employees on leave": "amber",
		"holidays in this month": "slate",
		onboardings: "green",
		separations: "red",
		promotions: "blue",
		transfers: "blue",
		trainings: "blue",
		"sanctioned amount": "amber",
		"awaiting approval": "amber",
		"unpaid claims": "amber",
		"active employees": "blue",
		"new hires": "green",
		"employee exits": "red",
		"employees joining": "green",
		"employees relieving": "red",
		"total employees": "blue",
		"gross pay": "amber",
		"net pay": "amber",
		"employees paid": "blue",
		"average gross pay": "amber",
		"total outgoing salary": "amber",
		"total salary structure": "slate",
		"total incentive given": "amber",
		"open job openings": "blue",
		"job openings": "blue",
		applicants: "blue",
		"total applicants": "blue",
		"job offers": "blue",
		"accepted applicants": "green",
		"rejected applicants": "red",
		"applicant-to-hire": "steel",
		"offer acceptance rate": "steel",
		"average time to fill": "steel",
		"open opportunity": "blue",
		"new lead": "blue",
		"won opportunity": "green",
		"open work orders": "blue",
		"wip work orders": "amber",
		"monthly completed work order": "green",
		"open projects": "blue",
		"non completed tasks": "amber",
		"timesheet working hours": "blue",
		"open quality actions": "blue",
		"open non conformances": "red",
		"open quality reviews": "amber",
		"open issues": "blue",
		"overdue issues": "red",
		"resolved issues": "green",
		"active customers": "slate",
		"active suppliers": "slate",
		users: "slate",
		"error logs": "red",
		"failed scheduled jobs": "red",
		"expense claims": "blue",
		"approved claims": "green",
		"rejected claims": "red",
		"total present": "green",
		"total absent": "red",
		"late entry": "amber",
		"early exit": "amber",
		"total outgoing bills": "green",
		"total incoming bills": "amber",
		"total incoming payment": "green",
		"total outgoing payment": "amber",
		"ongoing appraisal cycles": "blue",
		appraisals: "blue",
		"goals in progress": "blue",
		"total declaration submitted": "blue",
		"benefit claims": "amber",
		"tax exemption proofs": "blue",
	};

	const RULES = [
		{
			tone: "red",
			test: /overdue|delayed|\blate\b|rejected|separation|separating|exit|relieving|shortage|absent|failed|error|non conformance|lost|cancelled/,
		},
		{
			tone: "amber",
			test: /await|approval|unpaid|due in|to bill|payable|purchase amount|annual purchase|gross pay|net pay|salary|incentive|depreciation|disposal|to reorder|leave|open quotation|sanctioned|claim|holiday/,
		},
		{
			tone: "steel",
			test: /win rate|on-time|acceptance|time to fill|applicant-to-hire|\brate\b|percentage/,
		},
		{
			tone: "green",
			test: /revenue|profit|margin|cash|bank|collected|payments received|sales order value|stock value|asset value|new assets|new hire|onboard|accepted|approved|present|resolved|won|completed|incoming payment|outgoing bills/,
		},
		{
			tone: "slate",
			test: /warehouse|user|active customer|active supplier|salary structure|holiday|declaration/,
		},
		{
			tone: "blue",
			test: /open|opening|applicant|offer|employee|order|request|item|delivered|received|promotion|transfer|training|appraisal|goal|project|work order|lead|opportunit|task|hour|proof/,
		},
	];

	function normalize(value) {
		return (value || "")
			.replace(/\s*\([^)]*\)\s*$/, "")
			.replace(/\s+/g, " ")
			.trim()
			.toLowerCase();
	}

	function forTitle(title) {
		const key = normalize(title);
		const matched = TONES[key];
		const tone = matched || RULES.find((rule) => rule.test.test(key))?.tone || "slate";
		const color = COLORS[tone];

		return { tone, color, ink: color };
	}

	window.NBSCardTones = { colors: COLORS, forTitle };
})();
