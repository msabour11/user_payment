////////////////////////////discount options//////////////////////////////////////////////////////////////////////////////////////////////////
frappe.ui.form.on("Sales Invoice", {
  validate(frm) {
    // Only validate free quantity logic if is_discount is checked
    if (frm.doc.is_discount) {
      validate_free_quantity_logic(frm);
    }
    calculate_discount_amount(frm);
  },

  refresh(frm) {
    // Refresh relevant fields
    refresh_totals_fields(frm);

    // Show/hide discount-related fields based on is_discount
    toggle_discount_fields(frm);
  },

  before_save(frm) {
    // add sales person and fixed rate from sales person doctype

    const current_user = frappe.session.user;
    frm.set_value("sales_person", current_user);
    if (frm.doc.is_cash) {
      // add_payment_row(frm);
      frm.set_value("payment_method", "Cash");
    }

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
    // Calculate discount amount before saving
    calculate_discount_amount(frm);
  },

  // New field handler for is_discount
  is_discount: function (frm) {
    if (!frm.doc.is_discount) {
      // Clear discount-related data when is_discount is unchecked
      clear_discount_data(frm);
    }
    toggle_discount_fields(frm);
  },

  // add payment row to sales invoice based on is_cash field
  is_cash: function (frm) {
    if (frm.doc.is_cash) {
      // Enable POS mode for immediate payment processing
      frm.set_value("is_pos", 1);
      frm.set_value("payment_method", "Cash");
      // add_payment_row(frm);
    } else {
      // Reset fields when "Is Cash" is unchecked
      frm.set_value("is_pos", 0);
      frm.clear_table("payments");
      frm.refresh_field("payments");
      frm.set_value("payment_method", "Not Cash");
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
});

frappe.ui.form.on("Sales Invoice Item", {
  qty(frm, cdt, cdn) {
    const row = locals[cdt][cdn];

    // Only process discount logic if is_discount is checked
    if (frm.doc.is_discount) {
      // Reset free_qty when quantity changes (except for free discount items)
      if (row.is_free_discount !== 1 && row.qty) {
        frappe.model.set_value(cdt, cdn, "free_qty", 0);

        const total_paid_qty = get_total_paid_quantity(frm);
        const expected_free_qty =
          calculate_tiered_free_quantity(total_paid_qty);
        frappe.msgprint(
          __("Total Paid Quantity: {0}, Expected Free Quantity: {1}", [
            total_paid_qty,
            expected_free_qty,
          ])
        );
      }
    } else {
      // For normal sales invoice, ensure free_qty is 0
      if (row.free_qty && row.free_qty > 0) {
        frappe.model.set_value(cdt, cdn, "free_qty", 0);
      }
    }

    // Recalculate totals
    recalculate_totals(frm);
  },

  item_code(frm, cdt, cdn) {
    // Standard ERPNext item code handling will fetch rate, UOM, etc.
    // Additional custom logic can be added here if needed
    recalculate_totals(frm);
  },
});

frappe.ui.form.on("Discount Item", {
  quantity(frm, cdt, cdn) {
    // Only process if is_discount is enabled
    if (!frm.doc.is_discount) {
      frappe.msgprint(__("Please enable 'Is Discount' to add discount items"));
      frappe.model.set_value(cdt, cdn, "quantity", 0);
      return;
    }

    const discount_row = locals[cdt][cdn];

    if (!discount_row.item_code) {
      frappe.msgprint(__("Please select an item code first"));
      return;
    }

    process_discount_item(frm, discount_row);
    refresh_totals_fields(frm);
  },

  item_code(frm, cdt, cdn) {
    // Only process if is_discount is enabled
    if (!frm.doc.is_discount) {
      frappe.msgprint(__("Please enable 'Is Discount' to add discount items"));
      frappe.model.set_value(cdt, cdn, "item_code", "");
      return;
    }

    const discount_row = locals[cdt][cdn];

    if (discount_row.item_code && discount_row.quantity) {
      process_discount_item(frm, discount_row);
    }
  },
});

// Core Functions

// New function to toggle discount-related field visibility
function toggle_discount_fields(frm) {
  const is_discount_enabled = frm.doc.is_discount;

  // Toggle visibility of discount-related fields
  frm.toggle_display("discount_items", is_discount_enabled);
  frm.toggle_display("discount_item", is_discount_enabled); // Alternative field name

  // You can add more fields to show/hide based on is_discount
  // frm.toggle_display("some_discount_field", is_discount_enabled);
}

// New function to clear discount-related data
function clear_discount_data(frm) {
  // Clear discount items table
  frm.clear_table("discount_items");
  frm.clear_table("discount_item"); // Alternative field name
  frm.refresh_field("discount_items");
  frm.refresh_field("discount_item");

  // Reset free quantities in items
  frm.doc.items.forEach((item, index) => {
    if (item.free_qty && item.free_qty > 0) {
      frappe.model.set_value("Sales Invoice Item", item.name, "free_qty", 0);
      // Adjust quantity if it was increased due to free qty
      if (item.qty_without_free && item.qty_without_free >= 0) {
        frappe.model.set_value(
          "Sales Invoice Item",
          item.name,
          "qty",
          item.qty_without_free
        );
        frappe.model.set_value(
          "Sales Invoice Item",
          item.name,
          "qty_without_free",
          null
        );
      }
    }
    // Remove free discount items
    if (item.is_free_discount === 1) {
      frm.get_field("items").grid.grid_rows[index].remove();
    }
  });

  // Reset discount amount
  frm.set_value("discount_amount", 0);
  frm.refresh_field("items");
  recalculate_totals(frm);
}

// Helper function to add payment row based on user cash account or default mode of payment
function add_payment_row(frm) {
  // Clear existing payment rows
  frm.clear_table("payments");
  // Try to get user's cash account
  // frappe.db.get_value(
  //   "Account",
  //   { custom_user: frappe.session.user, account_type: "Cash" },
  //   "name",
  //   function (r) {
  //     const user_cash_account = r && r.name;
  //     if (user_cash_account) {
  //       // Add payment row with user's cash account
  //       frm.add_child("payments", {
  //         mode_of_payment: "نقد", // Standard mode of payment
  //         account: user_cash_account,
  //         amount: frm.doc.rounded_total,
  //       });
  //       frm.refresh_field("payments");
  //     }
  //     else {
  //       // Fallback to default cash mode of payment from Company
  //       frappe.db.get_value(
  //         "Company",
  //         frm.doc.company,
  //         "default_cash_account",
  //         function (r) {
  //           const default_mop = r && r.default_cash_account;
  //           if (default_mop) {
  //             frm.add_child("payments", {
  //               mode_of_payment: "نقد", // Standard mode of payment
  //               account: default_mop,
  //               amount: frm.doc.rounded_total,
  //             });
  //             frm.refresh_field("payments");
  //           } else {
  //             frappe.msgprint(
  //               "Please set a Default Cash Mode of Payment in Company settings or link a cash account to the user."
  //             );
  //           }
  //         }
  //       );
  //     }
  //   }
  // );

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
        frappe.throw(
          "Please set a Default Cash Mode of Payment in Company settings or link a cash account to the user."
        );
      }
    }
  );
}

function process_discount_item(frm, discount_row) {
  // Only process if is_discount is enabled
  if (!frm.doc.is_discount) {
    return;
  }

  let existing_item_result = find_existing_item(frm, discount_row.item_code);

  if (existing_item_result) {
    if (existing_item_result.type === "regular") {
      // Update existing regular item with free quantity
      update_existing_item_with_discount(
        existing_item_result.item,
        discount_row
      );
    } else if (existing_item_result.type === "free") {
      // Update existing free discount item quantity
      update_existing_free_item(existing_item_result.item, discount_row);
    }
  } else {
    // Add new discount item
    add_new_discount_item(frm, discount_row);
  }

  frm.refresh_field("items");
}

function find_existing_item(frm, item_code) {
  // First, try to find a regular item (not free discount)
  let regular_item = frm.doc.items.find(
    (item) => item.item_code === item_code && item.is_free_discount !== 1
  );

  if (regular_item) {
    return { item: regular_item, type: "regular" };
  }

  // If no regular item found, look for existing free discount item
  let free_item = frm.doc.items.find(
    (item) => item.item_code === item_code && item.is_free_discount === 1
  );

  if (free_item) {
    return { item: free_item, type: "free" };
  }

  return null;
}

function update_existing_item_with_discount(item_row, discount_row) {
  // Store original quantity if not already stored
  if (
    typeof item_row.qty_without_free === "undefined" ||
    item_row.qty_without_free === null
  ) {
    item_row.qty_without_free = (item_row.qty || 0) - (item_row.free_qty || 0);
  }

  // Update free quantity and total quantity
  item_row.free_qty = discount_row.quantity || 0;
  item_row.qty = (item_row.qty_without_free || 0) + (item_row.free_qty || 0);
}

function update_existing_free_item(item_row, discount_row) {
  // Update the quantity and free_qty for existing free discount item
  item_row.qty = discount_row.quantity || 0;
  item_row.free_qty = discount_row.quantity || 0;

  // Recalculate amount (should remain 0 for free items)
  item_row.amount = 0;
}

function add_new_discount_item(frm, discount_row) {
  // Fetch item details and price from server to get standard ERPNext data
  frappe.call({
    method: "erpnext.stock.get_item_details.get_item_details",
    args: {
      args: {
        item_code: discount_row.item_code,
        company: frm.doc.company,
        customer: frm.doc.customer,
        currency: frm.doc.currency,
        selling_price_list: frm.doc.selling_price_list,
        price_list_currency: frm.doc.price_list_currency,
        plc_conversion_rate: frm.doc.plc_conversion_rate,
        conversion_rate: frm.doc.conversion_rate,
        doctype: frm.doc.doctype,
        name: frm.doc.name,
        transaction_date: frm.doc.posting_date || frappe.datetime.get_today(),
      },
    },
    callback: function (r) {
      if (r.message) {
        const item_details = r.message;
        const new_row = frm.add_child("items", {
          item_code: discount_row.item_code,
          item_name: item_details.item_name || discount_row.item_code,
          description: item_details.description || item_details.item_name,
          uom: item_details.uom || item_details.stock_uom || "Nos",
          qty: discount_row.quantity || 0,
          free_qty: discount_row.quantity || 0,
          rate: item_details.price_list_rate || item_details.rate || 0,
          // amount: 0, // Amount will be 0 since qty - free_qty = 0 for free items
          is_free_discount: 1,
          item_group: item_details.item_group,
          brand: item_details.brand,
          item_tax_template: item_details.item_tax_template,
          warehouse: frm.doc.set_warehouse,
          income_account: item_details.income_account,
          expense_account: item_details.expense_account,
          cost_center: item_details.cost_center || frm.doc.cost_center,
          tax_category: item_details.tax_category,
          weight_per_unit: item_details.weight_per_unit,
          weight_uom: item_details.weight_uom,
          conversion_factor: item_details.conversion_factor || 1,
        });

        frm.refresh_field("items");
        recalculate_totals(frm);
      }
    },
    error: function (err) {
      frappe.msgprint(
        __("Error fetching item details: {0}", [err.message || "Unknown error"])
      );
    },
  });
}

function calculate_tiered_free_quantity(total_qty) {
  if (total_qty < 10) return 0;

  let remaining = total_qty;
  let free_qty = 0;

  // Tier calculation logic - from highest to lowest
  const tiers = [
    { threshold: 100, rate: 0.35 },
    { threshold: 50, rate: 0.34 },
    { threshold: 10, rate: 0.3 },
  ];

  for (const tier of tiers) {
    if (remaining >= tier.threshold) {
      const blocks = Math.floor(remaining / tier.threshold);
      free_qty += Math.floor(blocks * tier.threshold * tier.rate);
      remaining %= tier.threshold;
    }
  }

  return free_qty;
}

function get_total_paid_quantity(frm) {
  let total_qty = 0;

  frm.doc.items.forEach((item) => {
    if (item.is_free_discount !== 1) {
      total_qty += (item.qty || 0) - (item.free_qty || 0);
    }
  });

  return total_qty;
}

function get_total_free_quantity_from_discount_items(frm) {
  let total_free_qty = 0;

  // Check both possible child table names
  const discount_table = frm.doc.discount_items || frm.doc.discount_item || [];

  discount_table.forEach((discount_item) => {
    if (discount_item.quantity && discount_item.item_code) {
      total_free_qty += discount_item.quantity || 0;
    }
  });

  return total_free_qty;
}

function validate_free_quantity_logic(frm) {
  // Only validate if is_discount is enabled
  if (!frm.doc.is_discount) {
    return true;
  }

  const total_paid_qty = get_total_paid_quantity(frm);
  const expected_free_qty = calculate_tiered_free_quantity(total_paid_qty);
  const actual_free_qty = get_total_free_quantity_from_discount_items(frm);

  console.log(`Validation Details:`);
  console.log(`- Paid Qty: ${total_paid_qty}`);
  console.log(`- Expected Free: ${expected_free_qty}`);
  console.log(`- Actual Free: ${actual_free_qty}`);
  console.log(
    `- Discount Items:`,
    frm.doc.discount_item || frm.doc.discount_items || []
  );

  if (Math.abs(actual_free_qty - expected_free_qty) > 0.001) {
    // Use small tolerance for floating point comparison
    frappe.throw(
      __(
        "Free quantity validation failed.<br>" +
          "Paid Quantity: <strong>{0}</strong><br>" +
          "Expected Free Quantity: <strong>{1}</strong><br>" +
          "Actual Free Quantity: <strong>{2}</strong><br>" +
          "Please adjust the discount items accordingly.",
        [total_paid_qty, expected_free_qty, actual_free_qty]
      )
    );
    return false;
  }

  return true;
}

function calculate_discount_amount(frm) {
  let total_discount_amount = 0;

  // Only calculate discount amount if is_discount is enabled
  if (frm.doc.is_discount) {
    frm.doc.items.forEach((item) => {
      if (item.free_qty && item.free_qty > 0 && item.rate) {
        // For free discount items, the discount is the full rate * free_qty
        if (item.is_free_discount === 1) {
          total_discount_amount += (item.qty || 0) * (item.rate || 0);
        } else {
          // For regular items with free_qty, discount is rate * free_qty
          total_discount_amount += (item.free_qty || 0) * (item.rate || 0);
        }
      }
    });
    frm.set_value("discount_amount", total_discount_amount);
    frm.refresh_field("discount_amount");
  }
}

function recalculate_totals(frm) {
  // Only calculate free quantities if is_discount is enabled
  if (frm.doc.is_discount) {
    const total_paid_qty = get_total_paid_quantity(frm);
    const expected_free_qty = calculate_tiered_free_quantity(total_paid_qty);

    // Show calculation info (optional - can be removed in production)
    console.log(
      `Recalculation - Total Paid Qty: ${total_paid_qty}, Expected Free Qty: ${expected_free_qty}`
    );
  }

  calculate_discount_amount(frm);
  refresh_totals_fields(frm);
}

function refresh_totals_fields(frm) {
  const fields_to_refresh = [
    "items",
    "total_qty",
    "net_total",
    "grand_total",
    "rounded_total",
    "total_taxes_and_charges",
    "total_additional_discount_amount",
    "total_additional_discount_percentage",
    "discount_amount",
  ];

  fields_to_refresh.forEach((field) => {
    frm.refresh_field(field);
  });
}
