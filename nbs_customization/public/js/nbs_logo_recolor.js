class NBSLogoRecolor {
	constructor() {
		this.maxSize = 256;
		this.rasterCache = new Map();
	}

	mapSvgColor(value, primary, accent) {
		if (this.isSkippable(value)) return null;

		const color = this.parseColor(value);
		if (!color) return primary;
		return this.luminance(color) >= 0.85 ? accent : primary;
	}

	async processRaster(url, primary, accent) {
		const key = `${url}|${primary}|${accent}`;
		if (this.rasterCache.has(key)) return this.rasterCache.get(key);

		const response = await fetch(url, { credentials: "same-origin" });
		if (!response.ok) throw new Error(`Desktop logo fetch failed: ${response.status}`);

		const image = await this.loadImage(await response.blob());
		const canvas = this.drawImage(image);
		const context = canvas.getContext("2d", { willReadFrequently: true });
		const pixels = context.getImageData(0, 0, canvas.width, canvas.height);
		const base = this.dominantColor(pixels.data);

		this.recolorPixels(pixels.data, base, primary, accent);
		context.putImageData(pixels, 0, 0);

		const result = canvas.toDataURL("image/png");
		this.rasterCache.set(key, result);
		return result;
	}

	loadImage(blob) {
		return new Promise((resolve, reject) => {
			const url = URL.createObjectURL(blob);
			const image = new Image();

			image.onload = () => {
				URL.revokeObjectURL(url);
				resolve(image);
			};
			image.onerror = () => {
				URL.revokeObjectURL(url);
				reject(new Error("Desktop logo decode failed"));
			};
			image.src = url;
		});
	}

	drawImage(image) {
		const scale = Math.min(1, this.maxSize / Math.max(image.width, image.height));
		const canvas = document.createElement("canvas");
		canvas.width = Math.max(1, Math.round(image.width * scale));
		canvas.height = Math.max(1, Math.round(image.height * scale));

		const context = canvas.getContext("2d", { willReadFrequently: true });
		context.clearRect(0, 0, canvas.width, canvas.height);
		context.drawImage(image, 0, 0, canvas.width, canvas.height);
		return canvas;
	}

	dominantColor(data) {
		const bins = new Map();

		for (let index = 0; index < data.length; index += 4) {
			if (data[index + 3] < 32) continue;

			const key =
				((data[index] >> 4) << 8) | ((data[index + 1] >> 4) << 4) | (data[index + 2] >> 4);
			const bin = bins.get(key) || { count: 0, r: 0, g: 0, b: 0 };
			bin.count += 1;
			bin.r += data[index];
			bin.g += data[index + 1];
			bin.b += data[index + 2];
			bins.set(key, bin);
		}

		let dominant = null;
		bins.forEach((bin) => {
			if (!dominant || bin.count > dominant.count) dominant = bin;
		});
		if (!dominant) return [0, 0, 0];

		return [
			dominant.r / dominant.count,
			dominant.g / dominant.count,
			dominant.b / dominant.count,
		];
	}

	recolorPixels(data, base, primary, accent) {
		const primaryRgb = this.parseColor(primary) || [0, 27, 82];
		const accentRgb = this.parseColor(accent) || [0, 253, 255];
		const baseLum = this.luminance(base);
		const range = Math.max(1 - baseLum, 0.01);

		for (let index = 0; index < data.length; index += 4) {
			if (data[index + 3] === 0) continue;

			const lum = this.luminance([data[index], data[index + 1], data[index + 2]]);
			const ratio = Math.min(1, Math.max(0, (lum - baseLum) / range));

			data[index] = Math.round(primaryRgb[0] + (accentRgb[0] - primaryRgb[0]) * ratio);
			data[index + 1] = Math.round(primaryRgb[1] + (accentRgb[1] - primaryRgb[1]) * ratio);
			data[index + 2] = Math.round(primaryRgb[2] + (accentRgb[2] - primaryRgb[2]) * ratio);
		}
	}

	parseColor(value) {
		const color = String(value || "")
			.trim()
			.toLowerCase();
		if (!color) return null;
		if (color === "white") return [255, 255, 255];
		if (color === "black") return [0, 0, 0];
		if (color.startsWith("#")) return this.parseHex(color);

		const match = color.match(/^rgba?\(([^)]+)\)$/);
		if (!match) return null;

		const channels = match[1]
			.split(/[,\s/]+/)
			.filter(Boolean)
			.slice(0, 4)
			.map(Number);
		if (channels.length < 3 || channels.slice(0, 3).some(Number.isNaN)) return null;
		if (channels.length === 4 && channels[3] <= 0) return null;

		return channels.slice(0, 3).map((channel) => Math.min(255, Math.max(0, channel)));
	}

	parseHex(color) {
		const hex = color.slice(1);
		if (hex.length === 3 || hex.length === 4) {
			return hex
				.slice(0, 3)
				.split("")
				.map((digit) => parseInt(digit + digit, 16));
		}
		if (hex.length !== 6 && hex.length !== 8) return null;

		const channels = [0, 2, 4].map((index) => parseInt(hex.slice(index, index + 2), 16));
		if (channels.some(Number.isNaN)) return null;
		if (hex.length === 8 && parseInt(hex.slice(6, 8), 16) === 0) return null;
		return channels;
	}

	isSkippable(value) {
		const color = String(value || "")
			.trim()
			.toLowerCase();
		if (!color || this.isTransparent(color)) return true;
		if (
			["none", "transparent", "currentcolor", "inherit", "initial", "unset"].includes(color)
		) {
			return true;
		}
		return color.includes("url(");
	}

	isTransparent(color) {
		if (/^#[0-9a-f]{4}$/.test(color)) {
			return parseInt(color[4] + color[4], 16) === 0;
		}
		if (/^#[0-9a-f]{8}$/.test(color)) {
			return parseInt(color.slice(7, 9), 16) === 0;
		}

		const match = color.match(/^rgba\(([^)]+)\)$/);
		if (!match) return false;

		const channels = match[1].split(/[,\s/]+/).filter(Boolean);
		return channels.length === 4 && Number(channels[3]) === 0;
	}

	luminance([r, g, b]) {
		const linear = (channel) => {
			const value = channel / 255;
			return value <= 0.03928 ? value / 12.92 : Math.pow((value + 0.055) / 1.055, 2.4);
		};

		return 0.2126 * linear(r) + 0.7152 * linear(g) + 0.0722 * linear(b);
	}
}

if (!window.NBSLogoRecolor) {
	window.NBSLogoRecolor = new NBSLogoRecolor();
}
