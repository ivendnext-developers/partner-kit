# Plan a project

From a customer's list of needs to a release, one step at a time. Each step links the page that does it. It is for the scoper and the builder together, before a quote.

{{plan: shortlist}}

## The steps

1. **Write the wish list** in the customer's own words, one need per line: *"no more than 50 of one item on a line"*, not *"a quantity validator"*.
2. **Find each need's card** in the [needs catalogue](../../needs/README.md) (its [A to Z list](../../needs/README.md#a-to-z) is in the customer's words), or at a terminal with `python3 tools/needs/needs.py search <words>`. A need with no card: place it on [the ladder](../../guide/03_ladder_and_never_list.md) yourself, or [ask for an extension point](../../feedback/point_request.md).
3. **Fill the blueprint**: copy [its template](../../kit/blueprint_template.md) or print [the form](https://developer.ivendnext.com/downloads/blueprint_form.pdf) ([how to fill it](../../kit/blueprint.md)); `python3 tools/needs/needs.py blueprint <id> <id> …` prints its section (b), one row per card, with the verdict, the door and the limits.
4. **Quote**: read every limit to the customer and write it into the proposal; each card's *Tell the customer* line is written for that. Group the needs into as few apps as you can.
5. **Build** each need from its card's recipe and sample, on [your sandbox](sandbox.md) ([build](build.md)).
6. **Test**: the samples' tests, the kit's checks and the money kit ([chapter 14](../../guide/14_testing_and_release.md)).
7. **Release** through the customer's own release gate ([chapter 14](../../guide/14_testing_and_release.md)) and, for an app others install, the [App library](publish.md).

## What is refused

Anything that breaks one of [the four rules](../../guide/03_ladder_and_never_list.md). The catalogue's [What is not possible](site:needs/not-possible.html) page lists the needs iVendNext cannot meet today, *Not yet* and *Not possible*, and what to do instead.
