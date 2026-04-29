/**
 * NBS Customization: Add row number ("Sr") column to all List Views.
 * Patches the ListView prototype for seamless integration.
 */

(function () {
     const patch_list_view = () => {
          if (!window.frappe || !frappe.views || !frappe.views.ListView) return false;
          if (frappe.views.ListView.prototype._row_number_patched) return true;

          frappe.views.ListView.prototype._row_number_patched = true;

          // 1. Patch get_header_html to inject "Sr" header
          const _get_header_html = frappe.views.ListView.prototype.get_header_html;
          frappe.views.ListView.prototype.get_header_html = function () {
               let html = _get_header_html.apply(this, arguments);
               if (html && html.includes("list-header-checkbox")) {
                    const sr_html = `<span class="nbs-row-no nbs-row-no-header">${__("Sr")}</span>`;
                    // Inject right after the checkbox span (first </span>)
                    html = html.replace("</span>", "</span>" + sr_html);
               }
               return html;
          };

          // 2. Patch get_subject_element to inject row numbers
          const _get_subject_element = frappe.views.ListView.prototype.get_subject_element;
          frappe.views.ListView.prototype.get_subject_element = function (doc, title) {
               const div = _get_subject_element.apply(this, arguments);
               if (!div) return div;

               const row_no = (doc._idx !== undefined ? doc._idx : 0) + 1;
               const sr_span = document.createElement("span");
               sr_span.className = "nbs-row-no";
               sr_span.innerHTML = row_no;

               // The div has checkboxspan as the first child. We insert SR after it.
               if (div.firstChild) {
                    div.insertBefore(sr_span, div.firstChild.nextSibling);
               } else {
                    div.appendChild(sr_span);
               }

               return div;
          };

          return true;
     };

     // Initialize patch
     if (!patch_list_view()) {
          // ListView might be in a bundle loaded later
          const interval = setInterval(() => {
               if (patch_list_view()) {
                    clearInterval(interval);
               }
          }, 500);
          // Stop trying after 30 seconds
          setTimeout(() => clearInterval(interval), 30000);
     }
})();