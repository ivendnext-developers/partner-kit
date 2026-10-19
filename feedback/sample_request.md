# Sample request — ask for a worked example, or a manifest installed

**For:** an iVendNext Partner, a licensed customer's IT team or the CitiXsys Consulting Team who has placed a need on the ladder but cannot find a sample close enough to start from, or who has a manifest to be installed on a sandbox. These forms are for onboarded members ([who can file](README.md)). **Reference:** the samples ([`../samples/`](../samples/)), the customer archetypes in guide chapter 15 ([Customer archetypes](../guide/15_customer_archetypes.md)) and the blueprint ([`../kit/blueprint.md`](../kit/blueprint.md)).

A sample is a small, complete, working example of one pattern, with its recipe and tests, run on our own bench. A request that names the pattern is the one that moves a sample up the order.

## When to use it

- The door exists and works, and you want to see it used end to end in a situation like yours.
- A sample exists but differs from your case in a way that matters: another language, another door, a bigger size, money close by.
- You have a manifest and `deploy` stops at the check with *Failed to get method*: your sandbox needs its update; ask here and we update it (guide chapter 2).

**Use another form if:** no door exists for the need → [extension-point request](point_request.md); a sample does not run or does not match its read-me → [kit defect](kit_defect.md) or [recipe or document gap](recipe_or_document_gap.md).

## The form

```markdown
# Sample request: <one-line title>

What you need: <A worked example | An installed manifest>

## 1. The pattern or the manifest
<What the sample should show, in one or two lines. For a manifest: the manifest to install on your sandbox (attach it).>

## 2. The closest sample today (optional)
<Which sample you looked at, and why it does not do.>
```

## What we may ask you next, in the issue

The doors the sample would use · the nearest customer archetype in guide chapter 15 and how yours differs · your blueprint and the rows it would serve · your language and stack · whether money is nearby · the size (stores, tills, the busiest hour) · the test you would want it to ship with · where you will use it.

## What happens after you send it

- It is given an **id**, which comes back to you in the issue.
- It is answered in the issue with one of: **answered** (an existing sample already shows it, and the answer says where), **needs more**, **planned** (the sample joins the list, and its place in the order is shown) or **declined** (with the reason, for example that it needs a door that is not offered).
- A planned sample is built with its recipe, run on our bench and, near money, checked with the money kit before it is published.
