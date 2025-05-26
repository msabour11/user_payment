__version__ = "0.0.1"

# import frappe
# import erpnext




# from user_payment.overrides.product_discount import (
#     get_pricing_rule_for_item as custom_pricing_rule,
#     get_product_discount_rule as custom_product_discount,
# )
# from erpnext.accounts.doctype.pricing_rule.pricing_rule import get_pricing_rule_for_item as original_get_pricing_rule_for_item
# from erpnext.accounts.doctype.pricing_rule.utils import get_product_discount_rule as original_get_product_discount_rule

# def site_specific_pricing_rule(*args, **kwargs):
#     if frappe.local.site == "digital2":
#         return custom_pricing_rule(*args, **kwargs)
#     else:
#         return original_get_pricing_rule_for_item(*args, **kwargs)

# def site_specific_product_discount_rule(*args, **kwargs):
#     if frappe.local.site == "digital2":
#         return custom_product_discount(*args, **kwargs)
#     else:
#         return original_get_product_discount_rule(*args, **kwargs)

# erpnext.accounts.doctype.pricing_rule.pricing_rule.get_pricing_rule_for_item = site_specific_pricing_rule
# erpnext.accounts.doctype.pricing_rule.utils.get_product_discount_rule = site_specific_product_discount_rule