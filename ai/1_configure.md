# Configure what iVendNext already has (way in 1)

**Goal.** Meet the need with settings iVendNext already offers, so no code or data of yours is installed at all.

**Read.** [guide/04_configure_first.md](../guide/04_configure_first.md) · the needs catalogue ([needs/README.md](../needs/README.md)) · [recipes/configure_no_code.md](../recipes/configure_no_code.md).

**Sample to copy.** [samples/s5_config_pack/](../samples/s5_config_pack/) — a configuration file and a short script that applies it (reasons, a phone's IMEI, a line detail, member pricing). For many stores from one file: [samples/s8_estate_rollout/](../samples/s8_estate_rollout/).

**Steps.**
1. Write the need as one sentence in the customer's words. Look it up with `python3 tools/needs/needs.py search <those words>`: a card whose door is `configure` names the setting and its limits. Check chapter 4 and the settings table of the recipe too. If a setting does it, stop here: this is the answer.
2. Put the settings in a file in the person's project, shaped like `samples/s5_config_pack/config.json`. Use the person's own names; keep the sample's `pp_` out of them.
3. Read `apply_config.py` and copy its shape. It changes shop settings, so **it writes**: do not run it. Give the person the exact command and the file, and let them run it, or run it only on their own sandbox after their yes.
4. Write down, for the person, each setting you changed and what the cashier or the back office will now see.

**Check.** There is no checker for settings. Instead, read the settings back from the sandbox (a read call, `api/collection/` shows the form) and compare them with your file; say which you compared. Run `python3 tools/check/check.py <project folder>`: it must find nothing that breaks a rule (a configuration-only project prints `NOTHING FOUND` and exits 2: that is not a verdict. Say so, and say which settings you read back instead).

**Done looks like.** The need is met by settings alone; the person has the file and the command; every setting is listed with its effect; nothing was written to any shop without a yes; and you said why no higher-numbered way in was needed.

**Never.** Add a script or code to "complete" a setting that does not exist. If the setting is missing, go to way 2, 3 or 4, or combine ways (an outside app with a document check, a Desk button, a capture); request an extension point only when no combination meets the need.
