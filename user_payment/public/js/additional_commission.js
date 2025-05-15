frappe.ui.form.on("Additional Salary", {
  refresh(frm) {
    frm.add_custom_button(__("Get Commission"), function () {
      // Get the start date
      let start_date = frm.doc.payroll_date;
      // Calculate end of month
      let end_date = moment(start_date).endOf("month").format("YYYY-MM-DD");

      console.log("end_date", end_date);
      if (start_date && end_date) {
        frappe.call({
          method:
            "user_payment.overrides.salary_slip_commission.get_commission",
          args: {
            employee: frm.doc.employee,
            start_date: start_date,
            end_date: end_date,
          },
          callback: function (r) {
            if (r.message) {
              frm.set_value("amount", r.message);
            }
          },
        });
      } else {
        frappe.msgprint(__("Please select an Employee and Payroll Date."));
      }
    });
  },
});
