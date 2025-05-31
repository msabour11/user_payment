import frappe
import copy
import json
import re
import math


from frappe import _, throw
from frappe.model.document import Document
from frappe.utils import cint, flt
from erpnext.accounts.doctype.pricing_rule.pricing_rule import (
    remove_pricing_rule_for_item,
    update_args_for_pricing_rule,
    update_pricing_rule_uom,
    get_pricing_rule_details,
    apply_pricing_rule,
    apply_price_discount_rule,
)

from erpnext.accounts.doctype.pricing_rule.utils import (
    get_conversion_factor,
)

from frappe.utils import cint, flt, fmt_money, get_link_to_form, getdate, today


# override pricing rule function
def get_pricing_rule_for_item(args, doc=None, for_validate=False):
    from erpnext.accounts.doctype.pricing_rule.utils import (
        get_applied_pricing_rules,
        get_pricing_rule_items,
        get_pricing_rules,
        get_product_discount_rule,
    )

    if isinstance(doc, str):
        doc = json.loads(doc)

    if doc:
        doc = frappe.get_doc(doc)

    if args.get("is_free_item") or args.get("parenttype") == "Material Request":
        return {}

    item_details = frappe._dict(
        {
            "doctype": args.doctype,
            "has_margin": False,
            "name": args.name,
            "free_item_data": [],
            "parent": args.parent,
            "parenttype": args.parenttype,
            "child_docname": args.get("child_docname"),
            "discount_percentage": 0.0,
            "discount_amount": 0,
        }
    )

    if args.ignore_pricing_rule or not args.item_code:
        if frappe.db.exists(args.doctype, args.name) and args.get("pricing_rules"):
            item_details = remove_pricing_rule_for_item(
                args.get("pricing_rules"),
                item_details,
                item_code=args.get("item_code"),
                rate=args.get("price_list_rate"),
            )
        return item_details

    update_args_for_pricing_rule(args)

    pricing_rules = (
        get_applied_pricing_rules(args.get("pricing_rules"))
        if for_validate and args.get("pricing_rules")
        else get_pricing_rules(args, doc)
    )

    if pricing_rules:
        rules = []

        for pricing_rule in pricing_rules:
            if not pricing_rule:
                continue

            if isinstance(pricing_rule, str):
                pricing_rule = frappe.get_cached_doc("Pricing Rule", pricing_rule)
                update_pricing_rule_uom(pricing_rule, args)
                fetch_other_item = True if pricing_rule.apply_rule_on_other else False
                pricing_rule.apply_rule_on_other_items = (
                    get_pricing_rule_items(pricing_rule, other_items=fetch_other_item)
                    or []
                )

            if pricing_rule.coupon_code_based == 1:
                if not args.coupon_code:
                    return item_details

                coupon_code = frappe.db.get_value(
                    doctype="Coupon Code",
                    filters={"pricing_rule": pricing_rule.name},
                    fieldname="name",
                )
                if args.coupon_code != coupon_code:
                    continue

            if pricing_rule.get("suggestion"):
                continue

            item_details.validate_applied_rule = pricing_rule.get(
                "validate_applied_rule", 0
            )
            item_details.price_or_product_discount = pricing_rule.get(
                "price_or_product_discount"
            )

            rules.append(get_pricing_rule_details(args, pricing_rule))

            if pricing_rule.mixed_conditions or pricing_rule.apply_rule_on_other:
                item_details.update(
                    {
                        "price_or_product_discount": pricing_rule.price_or_product_discount,
                        "apply_rule_on": (
                            frappe.scrub(pricing_rule.apply_rule_on_other)
                            if pricing_rule.apply_rule_on_other
                            else frappe.scrub(pricing_rule.get("apply_on"))
                        ),
                    }
                )

                if pricing_rule.apply_rule_on_other_items:
                    item_details["apply_rule_on_other_items"] = json.dumps(
                        pricing_rule.apply_rule_on_other_items
                    )

            if (
                pricing_rule.mixed_conditions
                and pricing_rule.price_or_product_discount == "Product"
            ):
                # Calculate free_qty dynamically as percentage of total quantity
                free_qty_percentage = flt(
                    getattr(pricing_rule, "free_qty_percentage", 0)
                )
                total_qty = flt(
                    args.get("total_qty", 0)
                )  # You must pass total_qty in args from invoice
                if free_qty_percentage > 0 and total_qty > 0:
                    item_details.free_qty = total_qty * (free_qty_percentage / 100)
                else:
                    item_details.free_qty = 0

            if not pricing_rule.validate_applied_rule:
                if pricing_rule.price_or_product_discount == "Price":
                    apply_price_discount_rule(pricing_rule, item_details, args)
                else:
                    get_product_discount_rule(pricing_rule, item_details, args, doc)

        if not item_details.get("has_margin"):
            item_details.margin_type = None
            item_details.margin_rate_or_amount = 0.0

        item_details.has_pricing_rule = 1

        item_details.pricing_rules = frappe.as_json([d.pricing_rule for d in rules])

        if not doc:
            return item_details

    elif args.get("pricing_rules"):
        item_details = remove_pricing_rule_for_item(
            args.get("pricing_rules"),
            item_details,
            item_code=args.get("item_code"),
            rate=args.get("price_list_rate"),
        )

    return item_details


# override utilize method


def get_product_discount_rule(pricing_rule, item_details, args=None, doc=None):
    free_item = pricing_rule.free_item
    if pricing_rule.same_item and pricing_rule.get("apply_on") != "Transaction":
        free_item = item_details.item_code or args.item_code

    if not free_item:
        frappe.throw(
            _("Free item not set in the pricing rule {0}").format(
                get_link_to_form("Pricing Rule", pricing_rule.name)
            )
        )

    # Calculate qty based on free_qty_percentage if mixed_conditions is enabled
    if (
        pricing_rule.mixed_conditions
        and pricing_rule.price_or_product_discount == "Product"
    ):
        if pricing_rule.free_qty_percentage:
            # Get total quantity from the document, handling None values
            total_qty = (
                sum([flt(row.qty) for row in doc.items if not row.is_free_item])
                if doc
                else 0
            )

            # Calculate free quantity based on percentage
            qty = flt(total_qty * (pricing_rule.free_qty_percentage / 100))
        else:
            qty = pricing_rule.free_qty or 1
    else:
        qty = pricing_rule.free_qty or 1

    if pricing_rule.is_recursive:
        transaction_qty = sum(
            [
                flt(row.qty)
                for row in doc.items
                if not row.is_free_item
                and row.item_code == args.item_code
                and row.pricing_rules == args.pricing_rules
            ]
        )
        transaction_qty = transaction_qty - pricing_rule.apply_recursion_over
        if transaction_qty and transaction_qty > 0:
            qty = flt(transaction_qty) * qty / pricing_rule.recurse_for
            if pricing_rule.round_free_qty:
                qty = (flt(transaction_qty) // pricing_rule.recurse_for) * (
                    pricing_rule.free_qty or 1
                )

    if not qty:
        return

    free_item_data_args = {
        "item_code": free_item,
        "qty": qty,
        "pricing_rules": pricing_rule.name,
        "rate": pricing_rule.free_item_rate or 0,
        "price_list_rate": pricing_rule.free_item_rate or 0,
        "is_free_item": 1,
    }

    item_data = frappe.get_cached_value(
        "Item", free_item, ["item_name", "description", "stock_uom"], as_dict=1
    )

    free_item_data_args.update(item_data)
    free_item_data_args["uom"] = pricing_rule.free_item_uom or item_data.stock_uom
    free_item_data_args["conversion_factor"] = get_conversion_factor(
        free_item, free_item_data_args["uom"]
    ).get("conversion_factor", 1)

    if item_details.get("parenttype") == "Purchase Order":
        free_item_data_args["schedule_date"] = doc.schedule_date if doc else today()

    if item_details.get("parenttype") == "Sales Order":
        free_item_data_args["delivery_date"] = doc.delivery_date if doc else today()

    item_details.free_item_data.append(free_item_data_args)







# def calculate_tiered_free_quantity(total_qty):
#     """Calculate the free quantity based on tiered thresholds and rates."""
#     if total_qty < 10:
#         return 0
#     remaining = total_qty
#     free_qty = 0
#     tiers = [
#         {"threshold": 100, "rate": 0.35},
#         {"threshold": 50, "rate": 0.34},
#         {"threshold": 10, "rate": 0.30}
#     ]
#     for tier in tiers:
#         if remaining >= tier["threshold"]:
#             blocks = remaining // tier["threshold"]
#             free_qty += math.floor(blocks * tier["threshold"] * tier["rate"])
#             remaining = remaining % tier["threshold"]
#     return free_qty

# def add_free_items(doc, method):
#     """Validate and add free items to the Sales Invoice before saving."""
#     # Clear existing free items from the items table
#     frappe.msgprint("Adding free items based on discount_item entries...")
#     doc.items = [item for item in doc.items  ]

#     # Calculate total quantity of non-free items
#     total_qty = sum(item.qty for item in doc.items)

#     # Calculate expected free quantity based on tiers
#     expected_free = calculate_tiered_free_quantity(total_qty)

#     # Sum the quantities of free items entered by the user in the discount_item table
#     user_free_total = sum(d.quantity for d in doc.get("discount_item") or [])

#     # Validate that user-entered free quantity matches the calculated free quantity
#     if user_free_total != expected_free:
#         frappe.throw(f"Free items quantity ({user_free_total}) must match calculated tier quantity ({expected_free})")

#     # Add free items to the items table based on discount_item entries
#     for discount in doc.get("discount_item") or []:
#         item_uom = frappe.get_value("Item", discount.item_code, "stock_uom")
#         doc.append("items", {
#             "item_code": discount.item_code,
#             "item_name":f"{discount.item_code} Free Item",
#             "income_account":frappe.db.get_value("Company", doc.company, "default_income_account"),
#             "expense_account": frappe.db.get_value("Company", doc.company, "default_expense_account"),
#             "cost_center": frappe.db.get_value("Company", doc.company, "cost_center"),
#             "qty": discount.quantity,
#             "uom": item_uom,
#             "warehouse": doc.set_warehouse,
#             "discount_percentage": 100,
#             # "discount_amount": 10,
#             # "is_free_item": 1,
#             # "is_free_discount": 1,
#             "rate": 0,
#             "amount": 0,
#             "conversion_factor": get_conversion_factor(discount.item_code, item_uom).get("conversion_factor", 1),
#         })

# work version 2

# def add_free_items(doc, method):
#     """Manage free items in the Sales Invoice to avoid duplicates and update stock."""
#     # Step 1: Identify existing free items in the items table
#     # Free items are identified by rate = 0 and discount_percentage = 100


#     total_qty = sum(item.qty for item in doc.items if item.is_free_descount == 0 )
#     expected_free = calculate_tiered_free_quantity(total_qty)  # Your custom function
#     user_free_total = sum(d.quantity for d in doc.get("discount_item") or [])
#     if user_free_total != expected_free:
#         frappe.throw(f"Free items total ({user_free_total}) must match expected ({expected_free})")
#     existing_free_items = {item.item_code: item for item in doc.items if item.rate == 0 and item.discount_percentage == 100}
    
#     # Step 2: Get the free items to add from the discount_item table
#     free_items_to_add = {d.item_code: d.quantity for d in doc.get("discount_item") or []}
    
#     # Step 3: Update existing free items or add new ones
#     for item_code, quantity in free_items_to_add.items():
#         if item_code in existing_free_items:
#             # Update the quantity of the existing free item
#             existing_free_items[item_code].qty = quantity
#         else:
#             # Add a new free item
#             item_uom = frappe.get_value("Item", item_code, "stock_uom")
#             doc.append("items", {
#                 "item_code": item_code,
#                 "item_name": f"{item_code} Free {quantity} Item",
#                 "conversion_factor": get_conversion_factor(item_code, item_uom).get("conversion_factor", 1),
#                 "income_account":frappe.db.get_value("Company", doc.company, "default_income_account"),
#                 "expense_account": frappe.db.get_value("Company", doc.company, "default_expense_account"),
#                 "cost_center": frappe.db.get_value("Company", doc.company, "cost_center"),
#                 "qty": quantity,
#                 "uom": item_uom,
#                 "warehouse": doc.set_warehouse,  
#                 "rate": 0,
#                 "amount": 0,
#                 "base_rate": 0,
#                 "base_amount": 0,
#                 "is_free_descount": 1,
#             })
    
#     # Step 4: Remove free items that are no longer in discount_item
#     for item_code, item in list(existing_free_items.items()):
#         if item_code not in free_items_to_add:
#             doc.items.remove(item)





# add free items to sales invoice
# import frappe
# import math

# def calculate_tiered_free_quantity(total_qty):
#     """Calculate the free quantity based on tiered thresholds and rates."""
#     if total_qty < 10:
#         return 0
#     remaining = total_qty
#     free_qty = 0
#     tiers = [
#         {"threshold": 100, "rate": 0.35},
#         {"threshold": 50, "rate": 0.34},
#         {"threshold": 10, "rate": 0.30}
#     ]
#     for tier in tiers:
#         if remaining >= tier["threshold"]:
#             blocks = remaining // tier["threshold"]
#             free_qty += math.floor(blocks * tier["threshold"] * tier["rate"])
#             remaining = remaining % tier["threshold"]
#     return free_qty

# def get_item_rate(item_code, price_list):
#     """Fetch the rate of the item from the price list or standard rate."""
#     rate = frappe.get_value("Item Price", {"item_code": item_code, "price_list": price_list}, "price_list_rate")
#     if not rate:
#         rate = frappe.get_value("Item", item_code, "standard_rate")
#     return rate or 0

# def add_free_items(doc, method):
#     """Add or update free items in the Sales Invoice and set discount_amount."""
#     # Calculate total quantity of non-free items
#     total_qty = sum(item.qty for item in doc.items if not item.get("is_free_discount"))

#     # Calculate expected free quantity based on tiers
#     expected_free = calculate_tiered_free_quantity(total_qty)

#     # Sum the quantities of free items entered by the user in the discount_item table
#     user_free_total = sum(d.quantity for d in doc.get("discount_item") or [])

#     # Validate that user-entered free quantity matches the calculated free quantity
#     if user_free_total != expected_free:
#         frappe.throw(f"Free items quantity ({user_free_total}) must match calculated tier quantity ({expected_free})")

#     # Get the list of free items to add or update
#     free_items_to_add = {d.item_code: d.quantity for d in doc.get("discount_item") or []}

#     # Initialize total free items value
#     total_free_items_value = 0

#     # Update or add free items
#     for item_code, quantity in free_items_to_add.items():
#         rate = get_item_rate(item_code, doc.selling_price_list)
#         if not rate:
#             frappe.throw(f"No rate found for item {item_code}")
#         item_uom = frappe.get_value("Item", item_code, "stock_uom")
#         amount = quantity * rate
#         if doc.currency == doc.company_currency:
#             base_rate = rate
#             base_amount = amount
#         else:
#             base_rate = rate * doc.conversion_rate
#             base_amount = amount * doc.conversion_rate
#         income_account = frappe.db.get_value("Company", doc.company, "default_income_account")
#         expense_account = frappe.db.get_value("Company", doc.company, "default_expense_account")
#         if not income_account:
#             frappe.throw(f"Default Income Account not set for company {doc.company}")
#         cost_center = frappe.db.get_value("Company", doc.company, "cost_center")
#         if not income_account:
#             frappe.throw(f"Default Income Account not set for company {doc.company}")
#         if not cost_center:
#             frappe.throw(f"Default Cost Center not set for company {doc.company}")

#         # Check if there is an existing free item with the same item_code
#         existing_item = next((item for item in doc.items if item.get("is_free_discount") and item.item_code == item_code), None)
#         if existing_item:
#             # Update existing item
#             existing_item.qty = quantity
#             existing_item.rate = rate
#             existing_item.amount = amount
#             existing_item.base_rate = base_rate
#             existing_item.base_amount = base_amount
#         else:
#             # Add new item
#             doc.append("items", {
#                 "item_code": item_code,
#                 "item_name": f"{item_code} Free Item",
#                 "qty": quantity,
#                 "rate": rate,
#                 "amount": amount,
#                 "base_rate": base_rate,
#                 "base_amount": base_amount,
#                 "uom": item_uom,
#                 "warehouse": doc.set_warehouse,
#                 "income_account": income_account,
#                 "expense_account": expense_account,
#                 "cost_center": cost_center,
#                 "is_free_discount": True,
#                 "conversion_factor": 1  # since uom is stock_uom
#             })
#         total_free_items_value += amount

#     # Remove free items that are no longer in discount_item
#     doc.items = [item for item in doc.items if not item.get("is_free_discount") or item.item_code in free_items_to_add]

#     # Set discount_amount to the total value of free items
#     doc.discount_amount = total_free_items_value



# update quantity

# import frappe
# import math

# def calculate_tiered_free_quantity(total_qty):
#     """Calculate the free quantity based on tiered thresholds and rates."""
#     if total_qty < 10:
#         return 0
#     remaining = total_qty
#     free_qty = 0
#     tiers = [
#         {"threshold": 100, "rate": 0.35},
#         {"threshold": 50, "rate": 0.34},
#         {"threshold": 10, "rate": 0.30}
#     ]
#     for tier in tiers:
#         if remaining >= tier["threshold"]:
#             blocks = remaining // tier["threshold"]
#             free_qty += math.floor(blocks * tier["threshold"] * tier["rate"])
#             remaining = remaining % tier["threshold"]
#     return free_qty

# def get_item_rate(item_code, price_list):
#     """Fetch the rate of the item from the price list or standard rate."""
#     rate = frappe.get_value("Item Price", {"item_code": item_code, "price_list": price_list}, "price_list_rate")
#     if not rate:
#         rate = frappe.get_value("Item", item_code, "standard_rate")
#     return rate or 0

# def add_free_items(doc, method):
#     """Update item quantities with free items from discount_item and set discount_amount."""
#     # Step 1: Calculate total paid quantity (excluding free quantities)
#     total_paid_qty = sum(item.qty for item in doc.items if not item.get("is_free_discount"))

#     # Step 2: Calculate expected free quantity
#     expected_free = calculate_tiered_free_quantity(total_paid_qty)

#     # Step 3: Sum user-entered free quantities from discount_item
#     user_free_total = sum(d.quantity for d in doc.get("discount_item") or [])

#     # Step 4: Validate free quantity
#     if user_free_total != expected_free:
#         frappe.throw(f"Free items quantity ({user_free_total}) must match calculated tier quantity ({expected_free})")

#     # Step 5: Initialize total free items value for discount_amount
#     total_free_items_value = 0

#     # Step 6: Process free items from discount_item
#     free_items_to_add = {d.item_code: d.quantity for d in doc.get("discount_item") or []}
#     for item_code, free_qty in free_items_to_add.items():
#         # Fetch item details
#         rate = get_item_rate(item_code, doc.selling_price_list)
#         if not rate:
#             frappe.throw(f"No rate found for item {item_code}")
#         item_uom = frappe.get_value("Item", item_code, "stock_uom")
#         income_account = frappe.db.get_value("Company", doc.company, "default_income_account")
#         expense_account = frappe.db.get_value("Company", doc.company, "default_expense_account")
#         cost_center = frappe.db.get_value("Company", doc.company, "cost_center")
#         if not income_account:
#             frappe.throw(f"Default Income Account not set for company {doc.company}")
#         if not expense_account:
#             frappe.throw(f"Default Expense Account not set for company {doc.company}")
#         if not cost_center:
#             frappe.throw(f"Default Cost Center not set for company {doc.company}")

#         # Calculate amounts
#         amount = free_qty * rate
#         base_rate = rate if doc.currency == doc.company_currency else rate * doc.conversion_rate
#         base_amount = amount if doc.currency == doc.company_currency else amount * doc.conversion_rate

#         # Check for existing item (non-free)
#         existing_item = next((item for item in doc.items if item.item_code == item_code and not item.get("is_free_discount")), None)
#         if existing_item:
#             # Update existing item's quantity and discount
#             existing_item.qty += free_qty
#             existing_item.amount = existing_item.qty * existing_item.rate
#             existing_item.base_amount = existing_item.amount if doc.currency == doc.company_currency else existing_item.amount * doc.conversion_rate
#             existing_item.discount_amount = (existing_item.discount_amount or 0) + amount
#             existing_item.base_discount_amount = existing_item.discount_amount if doc.currency == doc.company_currency else existing_item.discount_amount * doc.conversion_rate
#         else:
#             # Add new item for free quantity
#             doc.append("items", {
#                 "item_code": item_code,
#                 "item_name": f"{item_code} Free Item",
#                 "qty": free_qty,
#                 "rate": rate,
#                 "amount": amount,
#                 "base_rate": base_rate,
#                 "base_amount": base_amount,
#                 "discount_amount": amount,  # Full discount for free item
#                 "base_discount_amount": base_amount,
#                 "uom": item_uom,
#                 "warehouse": doc.set_warehouse,
#                 "income_account": income_account,
#                 "expense_account": expense_account,
#                 "cost_center": cost_center,
#                 "is_free_discount": True,
#                 "conversion_factor": 1  # Using stock UOM
#             })
#         total_free_items_value += amount

#     # Step 7: Remove free items no longer in discount_item
#     doc.items = [item for item in doc.items if not item.get("is_free_discount") or item.item_code in free_items_to_add]

#     # Step 8: Set discount_amount to the total value of free items
#     doc.discount_amount = total_free_items_value
#     # doc.calculate_taxes_and_totals()


# advanced so

import frappe
import math

def calculate_tiered_free_quantity(total_qty):
    """Calculate the free quantity based on tiered thresholds and rates."""
    if total_qty < 10:
        return 0
    remaining = total_qty
    free_qty = 0
    tiers = [
        {"threshold": 100, "rate": 0.35},
        {"threshold": 50, "rate": 0.34},
        {"threshold": 10, "rate": 0.30}
    ]
    for tier in tiers:
        if remaining >= tier["threshold"]:
            blocks = remaining // tier["threshold"]
            free_qty += math.floor(blocks * tier["threshold"] * tier["rate"])
            remaining = remaining % tier["threshold"]
    return free_qty

def get_item_rate(item_code, price_list):
    """Fetch the rate of the item from the price list or standard rate."""
    rate = frappe.get_value("Item Price", {"item_code": item_code, "price_list": price_list}, "price_list_rate")
    if not rate:
        rate = frappe.get_value("Item", item_code, "standard_rate")
    return rate or 0

def add_free_items(doc, method):
    """Update existing items with free quantities from discount_item table."""
    # Calculate total quantity of non-free items (items without free quantities)
    total_qty = sum(item.qty - (item.get("free_qty") or 0) for item in doc.items)

    # Calculate expected free quantity based on tiers
    expected_free = calculate_tiered_free_quantity(total_qty)

    # Sum the quantities of free items entered by the user in the discount_item table
    user_free_total = sum(d.quantity for d in doc.get("discount_item") or [])

    # Validate that user-entered free quantity matches the calculated free quantity
    if user_free_total != expected_free:
        frappe.throw(f"Free items quantity ({user_free_total}) must match calculated tier quantity ({expected_free})")

    # Get the list of free items from discount_item table
    free_items_dict = {d.item_code: d.quantity for d in doc.get("discount_item") or []}

    # Initialize total free items value for discount calculation
    total_free_items_value = 0

    # Reset all free quantities first
    for item in doc.items:
        if hasattr(item, 'free_qty'):
            item.free_qty = 0

    # Process each free item from discount_item table
    for item_code, free_quantity in free_items_dict.items():
        # Find existing item in items table
        existing_item = next((item for item in doc.items if item.item_code == item_code), None)
        
        if existing_item:
            # Update existing item with free quantity
            existing_item.free_qty = free_quantity
            
            # Calculate the value of free items for discount
            rate = get_item_rate(item_code, doc.selling_price_list)
            if not rate:
                frappe.throw(f"No rate found for item {item_code}")
            
            free_amount = free_quantity * rate
            total_free_items_value += free_amount
            
            # Update the item's total quantity to include free quantity
            # This assumes you want to show total qty including free items
            # If you want to keep them separate, you can skip this line
            existing_item.qty = (existing_item.qty or 0) + free_quantity
            
            # Recalculate amount based on paid quantity only (excluding free qty)
            paid_qty = existing_item.qty - free_quantity
            existing_item.amount = paid_qty * existing_item.rate
            
            # Update base amounts for multi-currency
            if doc.currency == doc.company_currency:
                existing_item.base_amount = existing_item.amount
            else:
                existing_item.base_amount = existing_item.amount * doc.conversion_rate
                
        else:
            # If item doesn't exist in items table, you might want to add it
            # or throw an error - depending on your business logic
            frappe.msgprint(f"Item {item_code} not found in items table. Free quantity will be ignored.")

    # Set discount_amount to the total value of free items
    doc.discount_amount = total_free_items_value

    # Optional: Add a custom field to track free items value
    if hasattr(doc, 'free_items_value'):
        doc.free_items_value = total_free_items_value