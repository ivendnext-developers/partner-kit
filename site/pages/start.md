# Get started in five steps

From nothing to your first working call against an iVendNext site. You need git, curl, jq and Python 3; your own editor and language do the rest. Everything here is a first look: the guide's [chapter 2](../../guide/02_getting_started.md) and its [recipes](../../recipes/hosted_sandbox.md) go further.

## 1. Request a sandbox site

A sandbox site is your own iVendNext shop, hosted by us and full of made-up demo data, where you build and test before you touch a customer's site. You receive an address in your name, an administrator login, and logins for the shop's people. You never receive the software or a server.

[Request a sandbox](sandbox.md) and read what is on your site and what its limits are.

## 2. Get the kit

The guide, the recipes, the API description, the request collection, the tools and the samples are one repository:

```bash
git clone https://github.com/ivendnext-developers/partner-kit.git
cd partner-kit
```

The commands in step 3 and the samples are run from that folder.

## 3. Sign in, make your keys, and make the first call

Your first hour on the sandbox, from the recipe:

{{include recipes/hosted_sandbox.md#Your first hour}}

Then make the first call with the integration user's key. It starts with one right, reading items:

```bash
curl -s "https://<your-sandbox>/api/resource/Item?limit_page_length=5" \
  -H "Authorization: token <api key>:<api secret>"
```

You get back the first five items as JSON. A missing key answers `403`; a wrong one `401`. [Chapter 2](../../guide/02_getting_started.md) goes on to widen the role to what your app needs, and the request collection in `api/collection/` holds every call the samples make. Its first files run on any sandbox; the later ones book stock on test items a sandbox does not carry, so read them as examples.

## 4. Run a sample

Each [sample](../../samples/) is a small working example of one way in, with its tests. Its page says what it needs and how to run it. Pick the one nearest your project. On your sandbox you install a manifest yourself with `tools/deploy`; if your sandbox does not have the install screen yet, ask us and we update it.

## 5. Choose your way in and build

[Chapter 3](../../guide/03_ladder_and_never_list.md) is the order in which to try the ways in: configure first, then an outside app, a till key, a manifest, a sandboxed function, and last a request for a new extension point. Most needs stop at the first two. The [recipes](../../recipes/) are one per way in. Before you quote a customer, place every need on the ladder with the [project blueprint](../../kit/blueprint.md).

Before your app talks to a shop, read [Security and the handshake](security.md): consent, your app's own user, the signed call and its check. Every record call the samples make is in the [API reference](api.md). When your service is ready to leave your laptop: [Host with CitiXsys or run your own](hosting.md).

When something is missing or broken, [tell us](feedback.md).
