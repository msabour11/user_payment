// frappe.ui.form.on("Payment Entry", {
//   refresh: function (frm) {
//     if (frm.doc.payment_type === "Receive") {
//       let current_user = frappe.session.user;

//       frappe.db.get_doc("User Payment").then((doc) => {
//         var user_account = null;

//         // Iterate over the child table to find the current user
//         doc.user_accounts.forEach((row) => {
//           if (row.user === current_user) {
//             user_account = row.account; // 'account' holds the associated account
//           }
//         });

//         if (user_account) {
//           frm.set_query("paid_to", function () {
//             return {
//               filters: {
//                 name: user_account,
//               },
//             };
//           });

//           // Store `user_account` in frm for use in other events
//           frm.user_account = user_account;
//         }
//       });
//     }
//   },

//   mode_of_payment: function (frm) {
//     if (
//       frm.user_account && // Now accessing `user_account` from frm
//       (frm.doc.mode_of_payment === "Cash" ||
//         frm.doc.mode_of_payment === "نقد" ||
//         frm.doc.mode_of_payment === "حوالة مصرفية" ||
//         frm.doc.mode_of_payment === "Wire Transfer")
//     ) {
//       frm.set_value("paid_to", frm.user_account);
//     }
//   },
// });

//////////////// new way

frappe.ui.form.on("Payment Entry", {
  refresh: function (frm) {
    if (frm.doc.payment_type === "Receive") {
      let current_user = frappe.session.user;

      frappe.db
        .get_value("Account", { custom_user: current_user }, "name")
        .then((r) => {
          if (r.message && r.message.name) {
            // User has a linked account, apply query filter
            frm.set_query("paid_to", function () {
              return {
                filters: {
                  custom_user: current_user, // Only fetch linked account
                },
              };
            });

            // Store the linked account for later use
            frm.user_account = r.message.name;
          } else {
            // No linked account found, avoid setting query
            frm.user_account = null;
          }
        });
    }
  },

  mode_of_payment: function (frm) {
    if (
      frm.user_account && // Only apply if user has a linked account
      (frm.doc.mode_of_payment === "Cash" ||
        frm.doc.mode_of_payment === "نقد" ||
        frm.doc.mode_of_payment === "حوالة مصرفية" ||
        frm.doc.mode_of_payment === "Wire Transfer")
    ) {
      frm.set_value("paid_to", frm.user_account);
    }
  },
});
