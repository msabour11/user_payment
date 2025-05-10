frappe.ui.form.on("Sales Invoice", {
  before_save(frm) {
    var current_user = frappe.session.user;

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
        if (!r.exc) {
          // let sales_person = r.message[0].name;
          // let fixed_rate = r.message[0].custom_fixed_rate;
          frm.clear_table("sales_team");
          frm.refresh_field("sales_team");
          sales_persons = r.message;
          console.log("sales person is", sales_persons);

          sales_persons.forEach((sales_person) => {
            let sales_person_name = sales_person.name;
            let fixed_rate = sales_person.custom_fixed_rate;
            let commission_rate = frm.doc.commission_rate;

            console.log("sales person name is", sales_person_name);
            console.log("fixed rate is", fixed_rate);

            let row = frm.add_child("sales_team", {
              sales_person: sales_person_name,
              custom_fixed_rate: fixed_rate,
              // commission_rate: commission_rate,
            });

            frm.refresh_field("sales_team");
          });
          // let sales_person = r.message[0].name;
        }
      },
    });
  },
});
