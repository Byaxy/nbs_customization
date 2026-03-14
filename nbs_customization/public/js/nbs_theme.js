/**
 * NBS Customization — nbs_theme.js
 *
 * Dynamic theme engine for ERPNext v16 desk.
 *
 * Responsibilities:
 *  1. Replace the page loader logo as early as possible (before DOMContentLoaded)
 *  2. Apply cached theme config instantly on load (no flash)
 *  3. Fetch fresh config from Desk Theme API in the background
 *  4. Listen for real-time theme updates and re-apply without full reload
 *  5. Observe DOM mutations for dynamically added elements
 */

// ---------------------------------------------------------------------------
// 1. LOADER LOGO SWAP — runs immediately, before anything else
// ---------------------------------------------------------------------------
(function replaceLoaderLogo() {
	/**
	 * Resolve the logo URL from Frappe's own boot data.
	 * frappe.boot.app_logo_url is populated from Navbar Settings → Logo.
	 * Falls back to the login page logo img src if boot isn't ready yet,
	 * then to the standard Frappe/ERPNext logo path as a last resort.
	 */
	function getLogoSrc() {
		// Best source — set once in Navbar Settings, available after boot
		if (window.frappe && frappe.boot && frappe.boot.app_logo_url) {
			return frappe.boot.app_logo_url;
		}

		// Fallback — the login page already has the logo rendered as an <img>
		// in .page-card-head; borrow its src before boot is ready
		const loginLogo = document.querySelector(".page-card-head img");
		if (loginLogo && loginLogo.src) {
			return loginLogo.src;
		}

		// Last resort — Frappe's own website logo setting path
		return "/files/app-logo.png";
	}

	function swapLogo() {
		const freeze =
			document.getElementById("freeze") || document.querySelector(".page-loading-indicator");

		if (!freeze) return;

		const logoSrc = getLogoSrc();

		// Hide inline SVG (ERPNext default loader uses an inline SVG logo)
		freeze.querySelectorAll("svg").forEach((svg) => {
			svg.style.display = "none";
		});

		// Replace an existing <img> or inject a new one
		let img = freeze.querySelector("img");
		if (!img) {
			img = document.createElement("img");
			img.alt = "Loading";
			freeze.insertBefore(img, freeze.firstChild);
		}
		img.src = logoSrc;
		img.style.cssText =
			"width:110px;height:110px;object-fit:contain;display:block;margin:0 auto 20px;";
	}

	// Try immediately — catches the freeze div if it's already in the DOM
	swapLogo();

	// Re-run on DOMContentLoaded in case the freeze div is injected after
	// the script executes but before the DOM is fully parsed
	if (document.readyState === "loading") {
		document.addEventListener("DOMContentLoaded", swapLogo);
	}
})();

// ---------------------------------------------------------------------------
// 2. MAIN THEME CLASS
// ---------------------------------------------------------------------------
class NBSTheme {
	constructor() {
		this.CACHE_KEY = "nbs_theme_v1";
		this.CSS_VAR_MAP = {
			// Brand
			"--nbs-primary": "primaryColor",
			"--nbs-primary-hover": "primaryHover",
			"--nbs-danger": "dangerColor",
			"--nbs-danger-hover": "dangerHover",

			// Sidebar
			"--nbs-sidebar-bg": "sidebarBg",
			"--nbs-sidebar-text": "sidebarText",
			"--nbs-sidebar-active-bg": "sidebarActiveItemBg",
			"--nbs-sidebar-active-text": "sidebarActiveText",

			// Navbar
			"--nbs-navbar-bg": "navbarBg",
			"--nbs-navbar-text": "navbarText",
			"--nbs-navbar-icon": "navbarIcon",

			// Tables & lists
			"--nbs-table-header-bg": "tableHeaderBg",
			"--nbs-table-header-text": "tableHeaderText",
			"--nbs-table-even-bg": "tableEvenBg",
			"--nbs-table-row-hover-bg": "tableRowHoverBg",
			"--nbs-select-row-hover-bg": "selectRowHoverBg",

			// Child tables
			"--nbs-child-header-bg": "childHeaderBg",
			"--nbs-child-header-text": "childHeaderText",

			// Buttons
			"--nbs-btn-primary-bg": "btnPrimaryBg",
			"--nbs-btn-primary-hover": "btnPrimaryHover",
			"--nbs-btn-primary-text": "btnPrimaryText",
			"--nbs-btn-danger-bg": "btnDangerBg",
			"--nbs-btn-danger-hover": "btnDangerHover",

			// Login
			"--nbs-login-bg": "loginBg",
			"--nbs-login-box-bg": "loginBoxBg",
			"--nbs-login-title-color": "loginTitleColor",
			"--nbs-login-btn-color": "loginBtnColor",
		};
	}

	// -------------------------------------------------------------------------
	// Initialise — called once when the page is ready
	// -------------------------------------------------------------------------
	async init() {
		// Apply cached config immediately to prevent any color flash
		const cached = this.loadCache();
		if (cached) {
			this.applyConfig(cached);
		}

		// Fetch fresh config from the server in the background
		await this.fetchAndApply();

		// Subscribe to real-time updates from other sessions
		this.subscribeRealtime();

		// Handle login page separately
		this.setupLoginPage();

		// Watch for dynamically added elements
		this.setupMutationObserver();
	}

	// -------------------------------------------------------------------------
	// Fetch fresh config from Desk Theme API
	// -------------------------------------------------------------------------
	async fetchAndApply() {
		try {
			const result = await frappe.call({
				method: "nbs_customization.api.get_desk_theme",
				args: {},
			});

			if (result && result.message) {
				this.applyConfig(result.message);
				this.saveCache(result.message);
			}
		} catch (err) {
			// Non-fatal — CSS defaults in :root still apply
			console.warn("[NBSTheme] Could not load theme config from server.", err);
		}
	}

	// -------------------------------------------------------------------------
	// Apply config — write all CSS variables onto :root
	// -------------------------------------------------------------------------
	applyConfig(config) {
		const root = document.documentElement;

		Object.entries(this.CSS_VAR_MAP).forEach(([cssVar, configKey]) => {
			const value = config[configKey];
			if (value) {
				root.style.setProperty(cssVar, value);
			}
		});
	}

	// -------------------------------------------------------------------------
	// Real-time subscription — re-apply when admin saves Desk Theme
	// -------------------------------------------------------------------------
	subscribeRealtime() {
		if (!window.frappe || !frappe.realtime) return;

		frappe.realtime.on("nbs_theme_updated", () => {
			this.clearCache();
			this.fetchAndApply();
		});
	}

	// -------------------------------------------------------------------------
	// Login page — update the "Sign in to ..." text with the company name
	// -------------------------------------------------------------------------
	setupLoginPage() {
		const loginText = document.querySelector(".page-card-head h4");
		if (!loginText) return;

		frappe
			.call({
				method: "nbs_customization.api.get_default_company",
				args: {},
			})
			.then((r) => {
				if (r && r.message && r.message.company_name) {
					loginText.textContent = `Sign in to ${r.message.company_name}`;
				}
			})
			.catch(() => {
				// Fallback — leave default text as-is
			});
	}

	// -------------------------------------------------------------------------
	// MutationObserver — re-apply inline styles to dynamically injected elements
	// -------------------------------------------------------------------------
	setupMutationObserver() {
		if (!window.MutationObserver) return;

		const observer = new MutationObserver((mutations) => {
			mutations.forEach((mutation) => {
				mutation.addedNodes.forEach((node) => {
					if (node.nodeType !== Node.ELEMENT_NODE) return;
					this.styleNewElement(node);
				});
			});
		});

		observer.observe(document.body, { childList: true, subtree: true });
	}

	styleNewElement(el) {
		// Re-swap loader logo when the freeze div is re-injected (SPA navigations)
		if (el.id === "freeze" || el.classList.contains("page-loading-indicator")) {
			// At this point frappe.boot is available (SPA navigation),
			// so app_logo_url will resolve correctly
			const logoSrc =
				(window.frappe && frappe.boot && frappe.boot.app_logo_url) ||
				"/files/app-logo.png";

			el.querySelectorAll("svg").forEach((s) => (s.style.display = "none"));

			let img = el.querySelector("img");
			if (!img) {
				img = document.createElement("img");
				img.alt = "Loading";
				el.insertBefore(img, el.firstChild);
			}
			img.src = logoSrc;
			img.style.cssText =
				"width:110px;height:110px;object-fit:contain;display:block;margin:0 auto 20px;";
		}
	}

	// -------------------------------------------------------------------------
	// Cache helpers
	// -------------------------------------------------------------------------
	loadCache() {
		// Skip cache entirely in developer mode so changes are instant
		if (frappe.boot && frappe.boot.developer_mode) return null;

		try {
			const raw = localStorage.getItem(this.CACHE_KEY);
			return raw ? JSON.parse(raw) : null;
		} catch {
			return null;
		}
	}

	saveCache(config) {
		try {
			localStorage.setItem(this.CACHE_KEY, JSON.stringify(config));
		} catch {
			// localStorage unavailable — silently ignore
		}
	}

	clearCache() {
		try {
			localStorage.removeItem(this.CACHE_KEY);
		} catch {
			// ignore
		}
	}

	// Public helper — called from desk_theme.js Apply Theme button
	applyAndReload() {
		this.clearCache();
		window.location.reload();
	}
}

// ---------------------------------------------------------------------------
// 3. INITIALISE
// ---------------------------------------------------------------------------

function initNBSTheme() {
	window.NBSTheme = new NBSTheme();
	window.NBSTheme.init();
}

// Guard against double-init
if (!window.NBSTheme) {
	if (document.readyState === "loading") {
		document.addEventListener("DOMContentLoaded", initNBSTheme);
	} else {
		// DOM already ready (common in Frappe SPA after first load)
		initNBSTheme();
	}
}

// Frappe framework hook — also fire after frappe.boot completes
if (window.frappe) {
	$(document).ready(() => {
		if (window.NBSTheme) {
			// Re-run login page setup in case frappe.call wasn't ready earlier
			window.NBSTheme.setupLoginPage();
		}
	});
}
