class NBSDeskIcons {
	constructor() {
		this.selector = ".desktop-icon .icon-container:not(.folder-icon) img.app-icon";
		this.primaryColors = new Set(["#0289f7", "#004880", "#0e7159", "#06b58b", "#7b808a"]);
		this.accentColors = new Set([
			"#0981e3",
			"#ffffff",
			"#fff",
			"#e7e5f9",
			"#048f6e",
			"#1f876c",
			"#6b6f78",
			"white",
		]);
		this.colorProperties = new Set(["fill", "stroke", "stop-color", "color"]);
		this.cache = new Map();
		this.pending = new WeakSet();
		this.roots = new Set();
		this.scheduled = false;
		this.generation = 0;
		this.paletteKey = "";
	}

	refresh(root = document) {
		const { primary, accent } = this.themeColors();
		const paletteKey = `${primary}|${accent}`;

		if (paletteKey !== this.paletteKey) {
			this.paletteKey = paletteKey;
			this.generation += 1;
			this.restore(root);
		}

		this.recolor(root, primary, accent, paletteKey, this.generation);
	}

	scheduleRefresh(root = document) {
		this.roots.add(root);
		if (this.scheduled) return;

		this.scheduled = true;
		requestAnimationFrame(() => {
			this.scheduled = false;
			const roots = [...this.roots];
			this.roots.clear();
			roots.forEach((item) => this.refresh(item));
		});
	}

	themeColors() {
		const style = getComputedStyle(document.documentElement);
		return {
			primary: style.getPropertyValue("--nbs-primary").trim() || "#001b52",
			accent: style.getPropertyValue("--nbs-accent-color").trim() || "#00fdff",
		};
	}

	restore(root) {
		this.query(root, "[data-nbs-themed], [data-nbs-theme-failed]").forEach((img) => {
			const original = img.dataset.nbsOriginalSrc;
			if (original) img.setAttribute("src", original);
			delete img.dataset.nbsThemed;
			delete img.dataset.nbsThemeFailed;
		});
	}

	recolor(root, primary, accent, paletteKey, generation) {
		this.query(root, this.selector).forEach((img) => {
			if (
				img.dataset.nbsThemed === paletteKey ||
				img.dataset.nbsThemeFailed === paletteKey ||
				this.pending.has(img)
			) {
				return;
			}

			const source = img.getAttribute("src") || "";
			if (!source || source.startsWith("data:")) return;

			let url;
			try {
				url = new URL(source, window.location.href);
			} catch {
				return;
			}

			if (url.origin !== window.location.origin) return;

			const path = url.pathname.toLowerCase();
			const generated = path.includes("/icons/desktop_icons/");
			const logo = path.startsWith("/assets/") && !generated;
			if (!generated && !logo) return;

			img.dataset.nbsOriginalSrc = source;
			this.recolorImage(
				img,
				url,
				primary,
				accent,
				paletteKey,
				generation,
				generated ? "generated" : "logo"
			);
		});
	}

	recolorImage(img, url, primary, accent, paletteKey, generation, mode) {
		this.pending.add(img);

		this.loadThemedImage(url, primary, accent, mode)
			.then((source) => {
				if (generation !== this.generation) return;

				img.src = source;
				img.dataset.nbsThemed = paletteKey;
				delete img.dataset.nbsThemeFailed;
			})
			.catch(() => {
				if (generation === this.generation) {
					img.dataset.nbsThemeFailed = paletteKey;
				}
			})
			.finally(() => {
				this.pending.delete(img);
				if (generation !== this.generation) this.scheduleRefresh(img);
			});
	}

	loadThemedImage(url, primary, accent, mode) {
		const logoRecolor = window.NBSLogoRecolor;
		if (mode === "logo" && !logoRecolor) {
			return Promise.reject(new Error("Logo recolor helper is not loaded"));
		}
		if (mode === "logo" && !url.pathname.toLowerCase().endsWith(".svg")) {
			return logoRecolor.processRaster(url.href, primary, accent);
		}

		const colorMapper =
			mode === "logo"
				? (value) => logoRecolor.mapSvgColor(value, primary, accent)
				: (value) => this.mapColor(value, primary, accent);

		return this.loadSvg(url.href).then((svg) => {
			const rewritten = this.rewriteSvg(svg, colorMapper);
			if (!rewritten) throw new Error("Could not parse desktop icon SVG");
			return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(rewritten)}`;
		});
	}

	loadSvg(url) {
		if (this.cache.has(url)) return Promise.resolve(this.cache.get(url));

		return fetch(url, { credentials: "same-origin" })
			.then((response) => {
				if (!response.ok)
					throw new Error(`Desktop image fetch failed: ${response.status}`);
				return response.text();
			})
			.then((text) => {
				if (!text.includes("<svg")) throw new Error("Desktop image is not SVG");
				this.cache.set(url, text);
				return text;
			});
	}

	rewriteSvg(svg, colorMapper) {
		const doc = new DOMParser().parseFromString(svg, "image/svg+xml");
		if (doc.querySelector("parsererror")) return null;

		doc.querySelectorAll("*").forEach((element) => {
			this.colorProperties.forEach((property) => {
				const value = element.getAttribute(property);
				if (!value) return;

				const color = colorMapper(value);
				if (color) element.setAttribute(property, color);
			});

			const style = element.getAttribute("style");
			if (style) {
				element.setAttribute("style", this.rewriteStyle(style, colorMapper));
			}
		});

		const root = doc.documentElement;
		if (!root || root.nodeName.toLowerCase() !== "svg") return null;
		return new XMLSerializer().serializeToString(root);
	}

	rewriteStyle(style, colorMapper) {
		return style
			.split(";")
			.map((declaration) => {
				const separator = declaration.indexOf(":");
				if (separator === -1) return declaration;

				const property = declaration.slice(0, separator).trim().toLowerCase();
				if (!this.colorProperties.has(property)) return declaration;

				const value = declaration.slice(separator + 1).trim();
				const color = colorMapper(value);
				return color ? `${property}: ${color}` : declaration;
			})
			.join(";");
	}

	mapColor(value, primary, accent) {
		const color = value.trim().toLowerCase();
		if (this.primaryColors.has(color)) return primary;
		if (this.accentColors.has(color)) return accent;
		return null;
	}

	query(root, selector) {
		const nodes = [];
		if (root.nodeType === Node.ELEMENT_NODE && root.matches(selector)) {
			nodes.push(root);
		}
		if (root.querySelectorAll) {
			nodes.push(...root.querySelectorAll(selector));
		}
		return nodes;
	}
}

if (!window.NBSDeskIcons) {
	window.NBSDeskIcons = new NBSDeskIcons();
}
