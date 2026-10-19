# Recipe or document gap — tell us what a page is missing, or has wrong

**For:** an iVendNext Partner, a licensed customer's IT team or the CitiXsys Consulting Team who found a guide chapter, recipe, sample read-me or the API description missing, wrong, out of date, unclear or broken. These forms are for onboarded members ([who can file](README.md)). **Reference:** the guide ([`../guide/README.md`](../guide/README.md)) and the recipes ([`../recipes/`](../recipes/)).

The guide and recipes are written to be followed without asking us anything. When a step does not work as written, or a question the page should answer is not answered, that is a gap in the page.

## When to use it

- A step in a recipe fails and **the page is what is wrong**: a wrong command, a missing step, a name that no longer exists.
- A chapter does not say something you needed: what is refused, what happens when your service is down, a limit.
- Two pages disagree, a link is broken, an example does not run, or a word is not explained.

**Use another form if:** the page is right and the kit does not do what it says → [kit defect](kit_defect.md); you need a new way in → [extension-point request](point_request.md); you want a worked example → [sample request](sample_request.md).

## The form

```markdown
# Document gap: <one-line title>

## 1. The page
<The guide chapter or recipe file, and the heading or step number.>

## 2. What is wrong
<Missing, wrong, out of date, unclear, a broken link, or two pages that disagree. Quote the line, then say what you saw instead. Remove any secret.>

## 3. What would have helped (optional)
<The sentence, step, table or example you would have wanted.>
```

## What we may ask you next, in the issue

The task you were doing · the kit version or the date of the page you read · what you did instead · where you were (your sandbox, a customer's staging site, or reading only).

## What happens after you send it

- It is given an **id**, which comes back to you in the issue.
- It is answered in the issue with one of: **answered** (the page already says it, and the answer points to the line), **needs more**, **planned** (the page will change, and its change note says which gap it closed) or **declined** (with the reason).
- If the gap shows that a step does not work on the kit, the issue is passed on as a kit defect and keeps its id.
