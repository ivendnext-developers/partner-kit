# ivn — make, try, publish and keep your app going from a terminal

New to it? [Build your first app](../../site/pages/first_app.md).

The same steps as *My apps* in your browser (`https://developer.ivendnext.com/apps`), over the same server: the page and the command change one copy of your app. Nothing of iVendNext goes on your computer: `ivn` talks to our server and to your sites in the cloud. One line gets it ready, on macOS and Linux `curl -fsSL https://developer.ivendnext.com/install.sh | sh`, on Windows `irm https://developer.ivendnext.com/install.ps1 | iex`: it puts the kit in `~/.ivendnext/kit`, a launcher in your own bin folder (`~/.local/bin`, or `%USERPROFILE%\.ivendnext\bin`) that is on your PATH for good, and runs `ivn doctor`. By hand: put this folder on your `PATH` in your shell's start file, or run `python3 tools/ivn/ivn.py` (on Windows, `py tools\ivn\ivn.py`, or `ivn.cmd` from this folder). Standard library only: Python 3.9 or newer (a Mac's own `python3` is enough), and git for `ivn pull` and to update a clone. It needs your copy of the kit to stay where it is (moved it? run the install line again), and acts on the app in the current folder (any folder holding an `app.json`), or `--app <folder>`.

```bash
ivn doctor
ivn login
ivn new acme_store_rules
ivn new acme_member_till --from s23 --from s22
ivn sites add test.acme.example
ivn sites label test.acme.example "Acme test"
ivn try --site "Acme test"
ivn sites add live.acme.example --label "Acme live"
ivn publish --to "Acme live" --install
ivn publish --public
```

| Command | What it does |
|---|---|
| `ivn doctor` | One screen: the Python and git it found and whether each is new enough, whether this computer is signed in and as whom, the sites you can try on (or *none yet*, with the sandbox link), and the one command to run next. |
| `ivn update` | Brings the kit and `ivn` up to date: `git pull` in a clone, else GitHub's latest kit written over the folder in place. It says which version it moved from and to. |
| `ivn login` | Signs this computer in, by a code in your browser. The token is in `~/.ivendnext/token`, readable by you alone. |
| `ivn token new <name> [--app <app>]` | A token for a build server, shown once; on the server it goes in `IVN_TOKEN`. |
| `ivn new <app>` | Makes a blank app in `apps/<app>/` of the current repository: a `manifest.json` with your app's name and nothing else, one test, and a `README.md` listing everything you can add, each with a line to copy or the sample that brings it. `ivn add <sample>` adds a sample into it later. |
| `ivn new <app> --from <sample> …` | Makes one app from one sample or several, in `apps/<app>/` of the current repository. |
| `ivn download <app>` | Writes the server's copy into `apps/<app>/`. |
| `ivn check` | The kit's check and the app's own tests, one verdict line. |
| `ivn push` | Checks the folder and uploads it as the next draft. `.env` files never leave your computer. |
| `ivn pull` | Brings the server's latest draft in and keeps your changes, marking a conflict as git marks one (needs git). |
| `ivn add <sample>` · `ivn take <sample>` | Adds a sample · takes a sample's newer version, keeping what you changed. |
| `ivn secret <NAME>` | Sets one of the app's own settings. |
| `ivn secrets` | Prints each connection point's secret on the site you last tried on, or `--site <address>`. On a site we did not hand you, it points you to **Copy secret** on that site. |
| `ivn sites` | Lists your company's sites (*My sites* on My apps): each one's label, address and how Try installs there. |
| `ivn sites add <address>` | Adds a site you administer. It asks for an API key and secret you make there on your own user (your *User* record, its *Settings* tab, *API Access*, *Generate Keys*; never on Administrator), without echo; a build server sets `IVN_SITE_KEY` and `IVN_SITE_SECRET`. With the key, Try installs there in one press; press Enter for none, and its administrator installs from the shelf key. `--label "Acme live"` labels it at once: a customer's live site never joins Try's list. |
| `ivn sites use <address or label>` | Makes it your default: `ivn try` goes there. |
| `ivn sites label <address> "<label>"` | Names it, such as `"Acme test"` or `"Acme live"`. A label with *live*, *prod* or *production* makes it a customer's live site: Publish sends it the production copy, and Try does not go there. `""` takes the label off. |
| `ivn sites remove <address>` | Takes it off your list, and deletes the key you added for it. (`ivn remove-site` is different: it stops an app's new versions reaching a site.) |
| `ivn try` | Names the site first (`--site <address or label>`, else your default), uploads a changed folder, shows what installing it changes, installs it there and tests each connection point. On a site added without a key, it prints the shelf key that site's administrator pastes in **App library**. It asks nothing, and it is free. |
| `ivn test` · `ivn test --local` | Tests each connection point again · on this laptop, with the test secret in `.env.local`. |
| `ivn publish --to <site or label>` | Sends it to a customer's sites, and prints the message for their administrator. With no `--to`, to every site it is on. `--own`: the sites are your own company's. `--install`: on a customer's site where you added its key, it prints what installing it changes and installs it there now. |
| `ivn publish --public` | Lists it for every retailer. The card's fields go in `app.json`'s `card`: you are asked once. |
| `ivn status` · `ivn logs` | Where it stands, and any newer sample version · what its service logged. |
| `ivn rollback <version>` | Publishes an earlier version's content as a new, higher version. |
| `ivn remove-site <site>` · `ivn cancel` · `ivn handover <word>` | Stops new versions reaching a site · stops the service at the month's end · hands the app to another company. Each asks for the app's name first. |
| `ivn key <site>` | A paid listed app's key for one retailer's site. |
| `ivn package` | Writes `package.zip` for your own function host. |

Exit code: 0 done · 1 refused · 2 usage. To reach a test server, set `IVN_HOSTING_URL`.

**The one `app.json`:** the app's name and version, the service's fields, its settings, `card` (the App library's card: `title`, `summary`, `what`, `pictures`, `industries`, `price`, `guide`), `base` (the version this folder is), `address` (the service's address, written when you publish) and `samples` (the record *Add a sample* reads; a blank app's is `blank` until its first sample). Leave `base`, `address`, `samples` and `blank` to the tools.
