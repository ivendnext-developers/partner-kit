# Reporting a security problem

**Never in an issue, a proposal, a discussion or a commit message.** Those are visible to everyone who can read this repository.

## How to report

- **Use GitHub's private vulnerability reporting.** On this repository's **Security** tab, choose **Report a vulnerability** and fill in the form. Only the kit's maintainers (`@ivendnext-developers/kit-maintainers`) see the report, and nobody else can read it. It needs a free GitHub account.
- **No GitHub account?** Use the contact page at <https://www.ivendnext.com/contact/> and say only that you have a security report for the iVendNext partner kit. Do not put details in that message: we reply with a private way to send them.

Say, in the report:
- the file, tool or sample, and the version or the commit you used;
- what an attacker could do, and the steps to show it on a sandbox site — never on a customer's live site;
- whether money, a sale, a payment, a credential or personal data is reachable.

We acknowledge a report, keep it private until a fix is released, and credit you unless you ask us not to.

**What counts:** a way for a kit tool, a sample or a recipe to leak a secret or personal data, to let a check pass that should fail (the manifest checker, the self-check, the money kit, the Wasm kit's admission), to reach a customer's site with more rights than were granted, or to change money unseen.

**Not here:** a problem in iVendNext itself, seen through the kit, is reported the same private way, and we route it to the owning product team.
