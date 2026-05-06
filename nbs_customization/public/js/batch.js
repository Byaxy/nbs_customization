frappe.ui.form.on("Batch", {
     item: function (frm) {
          if (!frm.doc.item) return;

          frappe.db.get_value("Item", frm.doc.item, "has_expiry_date", (r) => {
               const requires_expiry = r && r.has_expiry_date;

               // Make expiry_date mandatory/optional dynamically
               frm.set_df_property("expiry_date", "reqd", requires_expiry ? 1 : 0);

               if (requires_expiry) {
                    frm.set_df_property(
                         "expiry_date",
                         "description",
                         "Required — this item is configured with expiry date tracking."
                    );
               } else {
                    frm.set_df_property("expiry_date", "description", "");
               }

               frm.refresh_field("expiry_date");
          });
     },
     batch_id: function (frm) {
          if (!frm.doc.batch_id) return;

          frm.set_value("custom_batch_no", frm.doc.batch_id);
          frm.refresh_field("custom_batch_no");
     },

     validate: function (frm) {
          if (!frm.doc.item) return;

          frappe.db.get_value("Item", frm.doc.item, "has_expiry_date", (r) => {
               if (r && r.has_expiry_date && !frm.doc.expiry_date) {
                    frappe.throw(
                         __("Expiry Date is mandatory for {0} before a batch can be created.", [
                              frappe.bold(frm.doc.item),
                         ])
                    );
               }
          });
     },
});