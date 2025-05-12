import frappe
from hrms.payroll.doctype.salary_slip.salary_slip import (
    SalarySlip as OriginalSalarySlip,
)

from frappe.utils import flt, money_in_words


###################3 last work ing code ######################

# import frappe
# from frappe.utils import flt


# def before_save(doc, method):
#     """
#     Update the commission amount in the salary slip before saving
#     """
#     update_salary_slip_commission(doc, method)


# def before_submit(doc, method):
#     """
#     Update the commission amount in the salary slip before submitting
#     """
#     update_salary_slip_commission(doc, method)


# def update_salary_slip_commission(doc, method):
#     """
#     Update the commission amount in the salary slip based on the commission percentage
#     and the total sales amount.
#     """
#     # Get the commission component
#     commission_component = frappe.db.get_value(
#         "Salary Component",
#         {"custom_is_commission_component": 1},
#         ["name"],
#     )

#     # Get the sales person linked to the employee
#     sales_person = frappe.db.get_value(
#         "Sales Person",
#         {"employee": doc.employee},
#         ["name"],
#     )

#     if commission_component and sales_person:
#         # Calculate total incentives for the period
#         total_incentives = flt(
#             frappe.db.sql(
#                 """
#                 SELECT SUM(te.incentives)
#                 FROM `tabSales Invoice` si
#                 INNER JOIN `tabSales Team` te ON si.name = te.parent
#                 WHERE
#                     si.docstatus = 1
#                     AND si.posting_date BETWEEN %s AND %s
#                     AND te.sales_person = %s
#                 """,
#                 (doc.start_date, doc.end_date, sales_person),
#             )[0][0]
#             or 0
#         )

#         # Update the Salary Component with new amount
#         if total_incentives > 0:
#             salary_component = frappe.get_doc("Salary Component", commission_component)
#             salary_component.amount = total_incentives
#             salary_component.save()

#         if doc.salary_structure:
#             # Get the salary structure and its components
#             salary_structure = frappe.get_doc("Salary Structure", doc.salary_structure)
#             for component in salary_structure.earnings:
#                 if component.salary_component == commission_component:
#                     # Update the amount in the Salary Structure
#                     component.amount = total_incentives
#                     break

#             salary_structure.flags.ignore_validate_update_after_submit = True
#             salary_structure.flags.ignore_permissions = True

#             # Save and update after submit
#             salary_structure.save()
#             # salary_structure.update_after_submit()

#         # Check if commission component exists in earnings
#         commission_exists = False
#         for row in doc.earnings:
#             if row.salary_component == commission_component:
#                 # Get the updated amount from Salary Component
#                 updated_amount = frappe.db.get_value(
#                     "Salary Component", commission_component, "amount"
#                 )
#                 row.amount = updated_amount
#                 commission_exists = True
#                 break

#         # If commission component doesn't exist in earnings, add it
#         if not commission_exists and total_incentives > 0:
#             doc.append(
#                 "earnings",
#                 {"salary_component": commission_component, "amount": total_incentives},
#             )


###################


class CustomSalarySlip(OriginalSalarySlip):
    def calculate_total_incentives(self):
        """
        Dynamically calculate total incentives for the employee based on sales data.
        """
        sales_person = frappe.db.get_value(
            "Sales Person", {"employee": self.employee}, "name"
        )
        if not sales_person:
            return 0

        total_incentives = (
            frappe.db.sql(
                """
            SELECT SUM(te.incentives)
            FROM `tabSales Invoice` si
            INNER JOIN `tabSales Team` te ON si.name = te.parent
            WHERE si.docstatus = 1
            AND si.posting_date BETWEEN %s AND %s
            AND te.sales_person = %s
            """,
                (self.start_date, self.end_date, sales_person),
            )[0][0]
            or 0
        )

        return flt(total_incentives)

    def calculate_net_pay(self, skip_tax_breakup_computation: bool = False):
        """
        Override the net pay calculation to include total incentives.
        """
        # Call the original method to calculate net pay
        super().calculate_net_pay(skip_tax_breakup_computation)

        # Add total incentives to net pay
        total_incentives = self.calculate_total_incentives()
        self.net_pay += total_incentives
        print(f"Net Pay after adding incentives: {self.net_pay}")

        # Recalculate gross_pay and related fields
        self.gross_pay = (self.gross_pay or 0) + total_incentives
        self.gross_year_to_date = (self.gross_year_to_date or 0) + total_incentives
        self.rounded_total = round(self.net_pay)
        self.total_in_words = money_in_words(self.net_pay, self.currency)
