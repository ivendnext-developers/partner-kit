# Kit defect — tell us a piece of the kit does not do what its recipe says

**For:** an iVendNext Partner, a licensed customer's IT team or the CitiXsys Consulting Team who followed a kit recipe and got a wrong answer, an error or nothing. These forms are for onboarded members ([who can file](README.md)). **Reference:** the recipes ([`../recipes/`](../recipes/)) and the tools they name ([`../tools/`](../tools/)).

A defect is a gap between what a kit piece **says it does** and what it **does**. Two short answers and the piece with its version let us repeat it.

## When to use it

- A kit piece gives a wrong answer, refuses valid input, accepts invalid input, crashes, or does nothing.
- The kit's result differs from what the recipe, or the kit's own output, says it should be.

**The kit pieces** (name one in the first line of the form): event feed client · manifest · Wasm kit · MCP server · design kit · sign-in recipe · scale-profile kit · money kit · self-check.

**Use another form if:** the page is wrong and the kit is right → [recipe or document gap](recipe_or_document_gap.md); you want the kit to do something new → [extension-point request](point_request.md) or [sample request](sample_request.md).

## The form

```markdown
# Kit defect: <one-line title>

Kit piece and version: <The kit piece, and the version it prints or the date you downloaded it.>

## 1. What you did
<The steps from a clean start, as you typed them.>

## 2. What you expected, and what happened
<What you expected, and where it says so (the recipe step, or the kit's own output). Then what you saw. Paste the output, with secrets removed.>

- [ ] It touches a sale, a price or a payment
```

## What we may ask you next, in the issue

How often it happens · the smallest input that still shows it (we may ask you to attach it) · your language, runtime and sandbox or staging site, and the date you made it · what it costs you (blocks the build, wrong answer, passes something it should refuse, refuses something it should pass) · any workaround.

## What happens after you send it

- It is given an **id**, which comes back to you in the issue.
- It is answered in the issue with one of: **answered**, **needs more** (a question back to you), **planned** (a fix, and the kit version that carries it) or **declined** (with the reason).
- A defect that touches money or the till, or lets bad work pass intake, is looked at first.
