frappe.ui.form.on("Payment Entry", {
  // refresh: function (frm) {
  //   if (frm.doc.payment_type === "Receive") {
  //     let current_user = frappe.session.user;

  //     frappe.db
  //       .get_value("Account", { custom_user: current_user }, "name")
  //       .then((r) => {
  //         if (r.message && r.message.name) {
  //           // User has a linked account, apply query filter
  //           frm.set_query("paid_to", function () {
  //             return {
  //               filters: {
  //                 custom_user: current_user, // Only fetch linked account
  //               },
  //             };
  //           });

  //           // Store the linked account for later use
  //           frm.user_account = r.message.name;
  //         } else {
  //           // No linked account found, avoid setting query
  //           frm.user_account = null;
  //         }
  //       });
  //   }
  // },

  mode_of_payment: function (frm) {
    if (
      frm.user_account && // Only apply if user has a linked account
      (frm.doc.mode_of_payment === "Cash" ||
        frm.doc.mode_of_payment === "نقد" ||
        frm.doc.mode_of_payment === "حوالة مصرفية الراجحي662" ||
        frm.doc.mode_of_payment === "حوالة  مصرفية الراجحي 665")
    ) {
      frm.set_value("paid_to", frm.user_account);
    }
  },
});
