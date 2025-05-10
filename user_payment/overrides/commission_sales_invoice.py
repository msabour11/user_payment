# from erpnext.accounts.doctype.sales_invoice.sales_invoice import SalesInvoice

# # # work fine
# from erpnext.controllers.selling_controller import SellingController
# import frappe
# from frappe import _, bold, throw
# from frappe.utils import cint, flt, get_link_to_form, nowtime


# class CustomSellingController(SalesInvoice):
#     def calculate_contribution(self):
#         if not self.meta.get_field("sales_team"):
#             return

#         sales_team = self.get("sales_team")

#         self.validate_sales_team(sales_team)

#         # Calculate total quantity of items once
#         total_quantity = sum(item.qty for item in self.items)

#         for sales_person in sales_team:
#             self.round_floats_in(sales_person)

#             # Fetch the custom fixed rate from the Sales Person
#             custom_fixed_rate = frappe.db.get_value(
#                 "Sales Person", sales_person.sales_person, "custom_fixed_rate"
#             )

#             if not custom_fixed_rate:
#                 frappe.throw(
#                     _("Custom Fixed Rate is not set for Sales Person {0}").format(
#                         sales_person.sales_person
#                     )
#                 )

#             # Calculate incentives as custom_fixed_rate * total_quantity
#             sales_person.incentives = flt(
#                 custom_fixed_rate * total_quantity,
#                 self.precision("incentives", sales_person),
#             )

#         # Calculate total allocated amount
#         total_allocated_amount = sum(
#             sales_person.incentives for sales_person in sales_team
#         )

#         # Adjust allocated_percentage
#         for sales_person in sales_team:
#             if total_allocated_amount != 0:
#                 allocated_percentage = (
#                     sales_person.incentives / total_allocated_amount
#                 ) * 100
#                 sales_person.allocated_percentage = flt(
#                     allocated_percentage,
#                     self.precision("allocated_percentage", sales_person),
#                 )
#             else:
#                 sales_person.allocated_percentage = 0

#         # Recalculate allocated_amount based on allocated_percentage and total invoice amount
#         total_invoice_amount = self.total
#         for sales_person in sales_team:
#             sales_person.allocated_amount = flt(
#                 (sales_person.allocated_percentage / 100) * total_invoice_amount,
#                 self.precision("allocated_amount", sales_person),
#             )

#         # Set commission_rate
#         for sales_person in sales_team:
#             # sales_person.commission_rate = 100
#             sales_person.commission_rate = flt(
#                 sales_person.incentives / sales_person.allocated_amount * 100,
#                 self.precision("commission_rate", sales_person),
#             )

# grok
from erpnext.accounts.doctype.sales_invoice.sales_invoice import SalesInvoice
from erpnext.controllers.selling_controller import SellingController
import frappe
from frappe import _, bold, throw
from frappe.utils import cint, flt, get_link_to_form, nowtime


class CustomSellingController(SalesInvoice):
    def calculate_contribution(self):
        if not self.meta.get_field("sales_team"):
            return

        sales_team = self.get("sales_team")
        self.validate_sales_team(sales_team)

        # Calculate total quantity of items once
        total_quantity = sum(item.qty for item in self.items)
        total_invoice_amount = self.total

        # Calculate average unit price
        average_unit_price = (
            flt(total_invoice_amount / total_quantity) if total_quantity else 0
        )

        # Step 1: Calculate incentives and set commission_rate based on custom_fixed_rate
        for sales_person in sales_team:
            self.round_floats_in(sales_person)

            # Fetch the custom fixed rate from the Sales Person
            custom_fixed_rate = frappe.db.get_value(
                "Sales Person", sales_person.sales_person, "custom_fixed_rate"
            )

            if not custom_fixed_rate:
                frappe.throw(
                    _("Custom Fixed Rate is not set for Sales Person {0}").format(
                        sales_person.sales_person
                    )
                )

            # Calculate incentives as custom_fixed_rate * total_quantity
            sales_person.incentives = flt(
                custom_fixed_rate * total_quantity,
                self.precision("incentives", sales_person),
            )

            # Set commission_rate as a percentage of average unit price
            # This makes commission_rate vary based on custom_fixed_rate
            sales_person.commission_rate = flt(
                (
                    (custom_fixed_rate / average_unit_price) * 100
                    if average_unit_price
                    else 0
                ),
                self.precision("commission_rate", sales_person),
            )

        # Step 2: Calculate total incentives
        total_incentives = sum(sales_person.incentives for sales_person in sales_team)

        # Step 3: Calculate allocated_percentage based on proportion of incentives
        for sales_person in sales_team:
            if total_incentives != 0:
                allocated_percentage = (
                    sales_person.incentives / total_incentives
                ) * 100
                sales_person.allocated_percentage = flt(
                    allocated_percentage,
                    self.precision("allocated_percentage", sales_person),
                )
            else:
                sales_person.allocated_percentage = 0

        # Step 4: Calculate allocated_amount based on allocated_percentage and total invoice amount
        for sales_person in sales_team:
            sales_person.allocated_amount = flt(
                (sales_person.allocated_percentage / 100) * total_invoice_amount,
                self.precision("allocated_amount", sales_person),
            )

        # Verification: Incentives should equal allocated_amount * (commission_rate / 100)
        # Note: Due to the independent setting of commission_rate, this equality may not hold exactly
        # If exact equality is required, commission_rate could be recalculated as (incentives / allocated_amount) * 100
        # after allocated_amount is set, but that would revert to uniform rates

    def validate_sales_team(self, sales_team):
        sales_persons = [d.sales_person for d in sales_team]
        print("Sales Persons:", sales_persons)

        if not sales_persons:
            return

        sales_person_status = frappe.db.get_all(
            "Sales Person",
            filters={"name": ["in", sales_persons]},
            fields=["name", "enabled"],
        )

        for row in sales_person_status:
            if not row.enabled:
                frappe.throw(_("Sales Person <b>{0}</b> is disabled.").format(row.name))
