frappe.ui.form.on("Payment Entry", {
  refresh: function (frm) {
    if (frm.doc.payment_type === "Receive") {
      let current_user = frappe.session.user;

      frappe.db.get_doc("User Payment").then((doc) => {
        let user_account = null;

        // Iterate over the child table to find the current user
        doc.user_accounts.forEach((row) => {
          if (row.user === current_user) {
            user_account = row.account; // Assuming 'account' holds the associated account
          }
        });

        if (user_account) {
          frm.set_query("paid_to", function () {
            return {
              filters: {
                name: user_account,
              },
            };
          });
        }
      });
    }
  },
});
