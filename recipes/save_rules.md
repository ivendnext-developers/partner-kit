# Save rules: one tax id per customer group, and a submit kept for a role — the recipe

A **save rule** is the shop's own rule on a record type, held on every save from every door (Desk, an import, the API), with no service and no code: the shop's site checks it. Your manifest can carry save rules, installed switched off; the shop switches each on. This recipe shows the two kinds the POS app added with train T11 (2026-10-16), in one manifest that installs on a sandbox as it is. It is for an iVendNext Partner, or the CitiXsys Consulting Team.

**Reference implementation:** the manifest below, installed on our sandbox (see *What was proven where*). The product's [save rules page](../contracts/pages/save_rules.md) lists all nine kinds, the keys each takes and every refusal in the product's words; chapter 7 says how a manifest carries them.

**When to use it.** The rule reads only the record itself (its header fields, never its rows) and needs nothing from outside the shop. For a rule that needs your system's data before a document is submitted, use a document check ([recipe](document_check.md)); for the till's sale, a check before payment ([recipe](rule_guard.md)).

## Steps

1. **Write the rules in your manifest.** `scope_fields` and `bypass_roles` are lists. `rule_name` starts with your prefix.

   ```json
   {
    "manifest_version": 2,
    "app": "pp_svr",
    "prefix": "PP SVR",
    "title": "Two save rules: one tax id per customer group, purchase requests by a purchase manager",
    "version": "0.1.0",
    "publisher": "Partner Programme sample",
    "description": "Two save rules, installed switched off; the shop switches each on. One: a customer's tax id is on no other active customer of the same customer group (a second one is refused when it is saved). Two: a Material Request of type Purchase is submitted only by a person holding Purchase Manager, from Desk, an import or the API; any other submit is refused. Nothing leaves the shop and no service is called.",
    "save_rules": [
     {"rule_name": "PP SVR One tax id per group", "record_type": "Customer", "kind": "unique_across", "field": "tax_id",
      "scope_fields": ["customer_group"], "mode": "refuse"},
     {"rule_name": "PP SVR Purchase requests by a purchase manager", "record_type": "Material Request", "kind": "role_for_action",
      "action": "submit", "bypass_roles": ["Purchase Manager"], "mode": "refuse",
      "conditions": [{"field": "material_request_type", "operator": "=", "value": "Purchase"}]}
    ]
   }
   ```

   - **`unique_across`**: the value of `field` is on no other active record of the type with the same values in up to three `scope_fields`. Without `scope_fields` the value is unique across every record of the type.
   - **`role_for_action`**: the `action` (`submit` or `cancel`) is taken only by a person holding one of `bypass_roles` when every condition holds (0 to 3 conditions; none means every record). A second rule with `"action": "cancel"` keeps the cancel too.
2. **Check it on your machine:** `python3 tools/manifest/validate.py manifest.json` takes it. A checker copy from before train T11 refuses `scope_fields` and `action`; take the kit's current copy.
3. **Install it** on your sandbox (`tools/deploy/deploy.py manifest.json`, then `--consent`). Each rule arrives switched off: the shop opens *Retail Save Rule* and switches it on.
4. **Test it** as the shop will meet it: a second customer with the same tax id in the same group is refused, in another group it is saved; a submit by someone without the role is refused, and by someone with it goes through.

## What the user sees

- *"Tax ID PP-T11-TAX-0001 is already on another Customer."* when the second customer is saved.
- *"Only Purchase Manager can submit this Material Request."* when someone without the role submits.

## What is refused, and why

- **A `unique_across` or `role_for_action` rule on a table's rows** (*"A … rule checks the record itself, not a table."*): the rule reads the record's own fields.
- **A `role_for_action` rule on a till's own record** (a till sale, the POS day's opening and close): the till's booking is never held by role. On a till sale a save rule only flags.
- **A `role_for_action` rule with no role:** *"Name at least one role that may submit."*

## When your service is down, and when the till is offline

- **No service is called:** the shop's site holds the rule.
- **Offline:** a write inside a till's offline sync is never refused by a save rule, only flagged for review. A submit or cancel the till's own work makes (a sale, the day close, a layaway's forfeit, the quote edit and cancel) is flagged, never refused, by a `role_for_action` rule.

## Technical notes

### Bounds

- **`unique_across` is a rule, not a database constraint:** two saves at the same moment can both pass. A cancelled record holds no value; a disabled one still does (add `disabled` as a scope field to let it repeat there). An empty value passes. The comparison follows the database's case rules.
- **On a table above 10,000 records** the field must be indexed when the rule is saved; the product refuses the rule otherwise and says so.
- **`role_for_action` reads the person's own roles,** so the site's Administrator passes every role. Its conditions read the header: a Stock Entry's rows keep the store each names, so add a `required_when` rule that makes the header name the store.
- **Duplicates already there** when the rule is switched on never block an unrelated edit: the value is judged when a record is new or the value or a scope field changes.

### What was proven where

- **Laptop:** the kit's checker takes this manifest (`tools/manifest/tests/test_validate_t11.py` holds the two kinds), and the checker copy from before train T11 refused both keys.
- **The sandbox `demo-1`** (2026-10-21, POS app 2.0.0.656): this manifest installed with both rules switched off; switched on, a second customer with the same tax id in the same group was refused in the words above and a third in another group was saved; a Material Request of type Purchase was refused at submit for a user holding *Stock User* only, and submitted by the same user once given *Purchase Manager*. Every record made for the test was removed after.
