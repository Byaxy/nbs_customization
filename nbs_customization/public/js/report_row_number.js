/**
 * NBS Customization: Fix serial numbers in DataTable-based reports.
 */
(function () {
	const patch_datatable = () => {
		if (!window.DataTable) return false;
		if (window.DataTable.prototype._report_rn_patched) return true;

		window.DataTable.prototype._report_rn_patched = true;

		const _init = window.DataTable.prototype.initializeComponents;
		window.DataTable.prototype.initializeComponents = function () {
			_init.apply(this, arguments);

			const dt = this;
			const _bodyRenderer = dt.bodyRenderer;

			const _renderRows = _bodyRenderer.renderRows.bind(_bodyRenderer);
			_bodyRenderer.renderRows = function (rows) {
				if (dt.options.serialNoColumn) {
					const srColIdx = dt.datamanager.getColumnIndexById("_rowIndex");
					if (srColIdx != null) {
						rows.forEach((row, idx) => {
							const cell = row[srColIdx];
							if (cell) {
								cell.content = idx + 1 + "";
							}
						});
					}
				}
				return _renderRows(rows);
			};

			// Use MutationObserver to renumber SR cells after any DOM change
			const mo = new MutationObserver(() => {
				if (!dt.options.serialNoColumn) return;
				const cells = _bodyRenderer.bodyScrollable.querySelectorAll(
					".dt-cell--col-0 .dt-cell__content",
				);
				cells.forEach((el, i) => {
					const val = i + 1 + "";
					if (el.textContent.trim() !== val) {
						el.textContent = val;
					}
				});
			});
			mo.observe(_bodyRenderer.bodyScrollable, { childList: true, subtree: true });
		};

		return true;
	};

	if (!patch_datatable()) {
		const interval = setInterval(() => {
			if (patch_datatable()) clearInterval(interval);
		}, 500);
		setTimeout(() => clearInterval(interval), 30000);
	}
})();
