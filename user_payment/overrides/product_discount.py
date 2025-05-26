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

# version2
import frappe

def add_free_items(doc, method):
    """Manage free items in the Sales Invoice to avoid duplicates and update stock."""
    # Step 1: Identify existing free items in the items table
    # Free items are identified by rate = 0 and discount_percentage = 100


    total_qty = sum(item.qty for item in doc.items if item.rate != 0 or item.discount_percentage != 100)
    expected_free = calculate_tiered_free_quantity(total_qty)  # Your custom function
    user_free_total = sum(d.quantity for d in doc.get("discount_item") or [])
    if user_free_total != expected_free:
        frappe.throw(f"Free items total ({user_free_total}) must match expected ({expected_free})")
    existing_free_items = {item.item_code: item for item in doc.items if item.rate == 0 and item.discount_percentage == 100}
    
    # Step 2: Get the free items to add from the discount_item table
    free_items_to_add = {d.item_code: d.quantity for d in doc.get("discount_item") or []}
    
    # Step 3: Update existing free items or add new ones
    for item_code, quantity in free_items_to_add.items():
        if item_code in existing_free_items:
            # Update the quantity of the existing free item
            existing_free_items[item_code].qty = quantity
        else:
            # Add a new free item
            item_uom = frappe.get_value("Item", item_code, "stock_uom")
            doc.append("items", {
                "item_code": item_code,
                "item_name": f"{item_code} Free {quantity} Item",
                "conversion_factor": get_conversion_factor(item_code, item_uom).get("conversion_factor", 1),
                "income_account":frappe.db.get_value("Company", doc.company, "default_income_account"),
                "expense_account": frappe.db.get_value("Company", doc.company, "default_expense_account"),
                "cost_center": frappe.db.get_value("Company", doc.company, "cost_center"),
                "qty": quantity,
                "uom": item_uom,
                "warehouse": doc.set_warehouse,  
                "discount_percentage": 100,
                "rate": 0,
                "amount": 0,
                "base_rate": 0,
                "base_amount": 0,
            })
    
    # Step 4: Remove free items that are no longer in discount_item
    for item_code, item in list(existing_free_items.items()):
        if item_code not in free_items_to_add:
            doc.items.remove(item)

