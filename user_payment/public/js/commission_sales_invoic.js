// Helper function to add payment row based on user cash account or default mode of payment
function add_payment_row(frm) {
  // Clear existing payment rows
  frm.clear_table("payments");
  // Try to get user's cash account
  frappe.db.get_value(
    "Account",
    { custom_user: frappe.session.user, account_type: "Cash" },
    "name",
    function (r) {
      const user_cash_account = r && r.name;
      if (user_cash_account) {
        // Add payment row with user's cash account
        frm.add_child("payments", {
          mode_of_payment: "نقد", // Standard mode of payment
          account: user_cash_account,
          amount: frm.doc.rounded_total,
        });
        frm.refresh_field("payments");
      } else {
        // Fallback to default cash mode of payment from Company
        frappe.db.get_value(
          "Company",
          frm.doc.company,
          "default_cash_account",
          function (r) {
            const default_mop = r && r.default_cash_account;
            if (default_mop) {
              frm.add_child("payments", {
                mode_of_payment: "نقد", // Standard mode of payment
                account: default_mop,
                amount: frm.doc.rounded_total,
              });
              frm.refresh_field("payments");
            } else {
              frappe.msgprint(
                "Please set a Default Cash Mode of Payment in Company settings or link a cash account to the user."
              );
            }
          }
        );
      }
    }
  );
}

frappe.ui.form.on("Sales Invoice", {
  Validite(frm) {
    frm.refresh_field("items");
    frm.refresh_field("total_qty");
    frm.refresh_field("net_total");
    frm.refresh_field("grand_total");
    frm.refresh_field("rounded_total");
    frm.refresh_field("total_taxes_and_charges");
    frm.refresh_field("total_additional_discount_amount");
    frm.refresh_field("total_additional_discount_percentage");
  },
  // get sales person and fixed rate from sales person doctype
  before_save(frm) {
    const current_user = frappe.session.user;

    frappe.call({
      method: "frappe.client.get_list",

      args: {
        doctype: "Sales Person",

        or_filters: [
          ["custom_user", "=", current_user],

          ["custom_is_commission_manager", "=", 1],
        ],
        fields: ["name", "custom_fixed_rate"],
      },

      callback: function (r) {
        if (!r.exc && Array.isArray(r.message)) {
          frm.clear_table("sales_team");
          const sales_persons = r.message;
          sales_persons.forEach((sales_person) => {
            frm.add_child("sales_team", {
              sales_person: sales_person.name,
              custom_fixed_rate: sales_person.custom_fixed_rate,
            });
          });
          frm.refresh_field("sales_team");
        }
      },
    });
  },

  // add payment row to sales invoice based on is_cash field
  is_cash: function (frm) {
    if (frm.doc.is_cash) {
      // Enable POS mode for immediate payment processing
      frm.set_value("is_pos", 1);
      add_payment_row(frm);
    } else {
      // Reset fields when "Is Cash" is unchecked
      frm.set_value("is_pos", 0);
      frm.clear_table("payments");
      frm.refresh_field("payments");
    }
  },
  grand_total(frm) {
    // Update payment amount if grand_total changes while "Is Cash" is checked
    if (frm.doc.is_cash && frm.doc.payments.length > 0) {
      frm.doc.payments[0].amount = frm.doc.grand_total;
      frm.refresh_field("payments");
    }
  },
  before_submit(frm) {
    if (frm.doc.is_cash) {
      // Enable POS mode for immediate payment processing
      frm.set_value("is_pos", 1);
      add_payment_row(frm);
    }
  },

  // total_qty(frm) {
  //   frappe.msgprint("Total Quantity: " + frm.doc.total_qty);
  //   calculate_addittion_qty(frm);
  //   // Get the total number of items in the Sales Invoice
  // },
});

frappe.ui.form.on("Sales Invoice Item", {
  qty(frm) {
    let total_qty = 0;
    // Recalculate total quantity when item quantity changes
    frm.doc.items.forEach((item) => {
      total_qty += item.qty || 0;
    });

    // Calculate and set the free quantity based on tiered logic
    const free_qty = calculate_tiered_free_quantity(frm, total_qty);
    frappe.msgprint(`Total Quantity: ${total_qty}, Free Quantity: ${free_qty}`);
  },
});

function calculate_tiered_free_quantity(frm, total_qty) {
  if (total_qty < 10) return 0;

  let remaining = total_qty;
  let free_qty = 0;

  // Tier calculation logic
  const tiers = [
    { threshold: 100, rate: 0.35 },
    { threshold: 50, rate: 0.34 },
    { threshold: 10, rate: 0.3 },
  ];

  tiers.forEach((tier) => {
    if (remaining >= tier.threshold) {
      const blocks = Math.floor(remaining / tier.threshold);
      free_qty += Math.floor(blocks * tier.threshold * tier.rate);
      remaining %= tier.threshold;
    }
  });

  return free_qty;
}
