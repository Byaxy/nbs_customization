/**
 * NBS Customization Theme - JavaScript Theme Manager
 *
 * Handles dynamic theme application and configuration for Biomedical Solutions
 * Supports full-width layouts, custom colors, and responsive design
 */

class NBSTheme {
	constructor() {
		// Theme configuration with your specific colors
		this.themeConfig = {
			// Brand Colors
			primaryColor: "#001b52",
			primaryHover: "#001540",
			dangerColor: "#dc2626",
			dangerHover: "#b91c1c",

			// Table Colors
			tableHeaderBg: "#001b52",
			tableHeaderText: "#ffffff",
			tableEvenBg: "#eff6ff",
			tableHoverBg: "#eff6ff",

			// Navigation
			navbarBg: "#001b52",
			navbarText: "#ffffff",

			// Login
			loginTitle: "Biomedical Solutions",
			loginTitleColor: "#001b52",
			loginBoxBg: "#ffffff",
			loginBoxWidth: "400px",
		};

		this.cacheKey = "nbs_theme_cache";
		this.init();
	}

	/**
	 * Initialize the theme system
	 */
	init() {
		this.applyTheme();
		this.setupFullWidthLayout();
		this.setupTableStyling();
		this.setupButtonStyling();
		this.setupEventListeners();
	}

	/**
	 * Apply theme configuration as CSS custom properties
	 */
	applyTheme() {
		const root = document.documentElement;
		Object.keys(this.themeConfig).forEach((key) => {
			const cssVar = `--nbs-${key.replace(/([A-Z])/g, "-$1").toLowerCase()}`;
			root.style.setProperty(cssVar, this.themeConfig[key]);
		});
	}

	/**
	 * Setup full-width layout
	 */
	setupFullWidthLayout() {
		// Ensure 100% width for all major containers
		this.addGlobalStyles(`
            .page-container, .content.page-container, .layout-main-section, .form-page {
                max-width: 100% !important;
                width: 100% !important;
            }
            .form-layout, .form-container, .form-view {
                max-width: 100% !important;
                width: 100% !important;
            }
            .list-view-container, .report-view-container {
                max-width: 100% !important;
                width: 100% !important;
            }
            .navbar, .navbar.container {
                max-width: 100% !important;
                width: 100% !important;
            }
        `);
	}

	/**
	 * Setup enhanced table styling
	 */
	setupTableStyling() {
		this.addGlobalStyles(`
            .table tbody tr:nth-child(even) { 
                background-color: ${this.themeConfig.tableEvenBg} !important; 
            }
            .table tbody tr:hover,
            .dataTable tbody tr:hover,
            .list-view-table tbody tr:hover {
                background-color: ${this.themeConfig.tableHoverBg} !important;
                cursor: pointer;
            }
            .table thead th,
            .dataTable thead th,
            .list-view-table thead th {
                background-color: ${this.themeConfig.tableHeaderBg} !important;
                color: ${this.themeConfig.tableHeaderText} !important;
                border-bottom: 2px solid ${this.themeConfig.tableHeaderBg} !important;
            }
        `);
	}

	/**
	 * Setup enhanced button styling
	 */
	setupButtonStyling() {
		this.addGlobalStyles(`
            .btn-primary {
                background-color: ${this.themeConfig.primaryColor} !important;
                border-color: ${this.themeConfig.primaryColor} !important;
                color: #ffffff !important;
                border-radius: 6px;
                font-weight: 500;
                transition: all 0.2s ease;
            }
            .btn-primary:hover,
            .btn-primary:focus {
                background-color: ${this.themeConfig.primaryHover} !important;
                border-color: ${this.themeConfig.primaryHover} !important;
                transform: translateY(-1px);
                box-shadow: 0 4px 8px rgba(0, 27, 82, 0.3);
            }
            .btn-danger, .btn-cancel, [data-action="cancel"], 
            [data-action="no"], [data-response="no"] {
                background-color: ${this.themeConfig.dangerColor} !important;
                border-color: ${this.themeConfig.dangerColor} !important;
                color: #ffffff !important;
                border-radius: 6px;
                font-weight: 500;
                transition: all 0.2s ease;
            }
            .btn-danger:hover, .btn-cancel:hover, [data-action="cancel"]:hover,
            [data-action="no"]:hover, [data-response="no"]:hover {
                background-color: ${this.themeConfig.dangerHover} !important;
                border-color: ${this.themeConfig.dangerHover} !important;
                transform: translateY(-1px);
                box-shadow: 0 4px 8px rgba(220, 38, 38, 0.3);
            }
        `);
	}

	/**
	 * Setup event listeners for dynamic content
	 */
	setupEventListeners() {
		// Monitor for DOM changes (for dynamic content)
		const observer = new MutationObserver((mutations) => {
			mutations.forEach((mutation) => {
				if (mutation.type === "childList") {
					mutation.addedNodes.forEach((node) => {
						if (node.nodeType === Node.ELEMENT_NODE) {
							this.applyStylingToNewElements(node);
						}
					});
				}
			});
		});

		observer.observe(document.body, {
			childList: true,
			subtree: true,
		});
	}

	/**
	 * Apply styling to dynamically added elements
	 */
	applyStylingToNewElements(element) {
		// Apply button styling to new buttons
		if (element.classList && element.classList.contains("btn")) {
			if (element.classList.contains("btn-primary")) {
				element.style.backgroundColor = this.themeConfig.primaryColor;
				element.style.borderColor = this.themeConfig.primaryColor;
			}
			if (
				element.classList.contains("btn-danger") ||
				element.classList.contains("btn-cancel")
			) {
				element.style.backgroundColor = this.themeConfig.dangerColor;
				element.style.borderColor = this.themeConfig.dangerColor;
			}
		}

		// Apply styling to tables
		if (element.classList && element.classList.contains("table")) {
			this.styleTable(element);
		}
	}

	/**
	 * Style individual table
	 */
	styleTable(table) {
		const headers = table.querySelectorAll("thead th");
		headers.forEach((header) => {
			header.style.backgroundColor = this.themeConfig.tableHeaderBg;
			header.style.color = this.themeConfig.tableHeaderText;
		});

		const rows = table.querySelectorAll("tbody tr");
		rows.forEach((row, index) => {
			if (index % 2 === 0) {
				row.style.backgroundColor = this.themeConfig.tableEvenBg;
			}

			row.addEventListener("mouseenter", () => {
				row.style.backgroundColor = this.themeConfig.tableHoverBg;
			});

			row.addEventListener("mouseleave", () => {
				if (index % 2 === 0) {
					row.style.backgroundColor = this.themeConfig.tableEvenBg;
				} else {
					row.style.backgroundColor = "";
				}
			});
		});
	}

	/**
	 * Add global CSS styles
	 */
	addGlobalStyles(css) {
		const style = document.createElement("style");
		style.textContent = css;
		style.setAttribute("data-nbs-theme", "true");
		document.head.appendChild(style);
	}

	/**
	 * Update theme configuration
	 */
	updateTheme(newConfig) {
		this.themeConfig = { ...this.themeConfig, ...newConfig };
		this.applyTheme();
		this.setupTableStyling();
		this.setupButtonStyling();
	}

	/**
	 * Get current theme configuration
	 */
	getThemeConfig() {
		return { ...this.themeConfig };
	}
}

// Initialize theme when DOM is ready
document.addEventListener("DOMContentLoaded", () => {
	window.NBSTheme = new NBSTheme();
});

// Also initialize if DOM is already loaded
if (document.readyState === "loading") {
	document.addEventListener("DOMContentLoaded", () => {
		window.NBSTheme = new NBSTheme();
	});
} else {
	window.NBSTheme = new NBSTheme();
}
