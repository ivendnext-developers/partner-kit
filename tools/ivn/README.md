# ivn — make, try, publish and keep your app going from a terminal

The same steps as *My apps* in your browser (`https://developer.ivendnext.com/apps`), over the same server: the page and the command change one copy of your app. Put this folder on your `PATH`, or run `python3 tools/ivn/ivn.py`. Standard library only (Python 3.10+). It needs your copy of the kit to stay where it is, and acts on the app in the current folder (any folder holding an `app.json`), or `--app <folder>`.

```bash
ivn login
ivn new acme_member_till --from s23 --from s22
ivn try
ivn publish --to retailer.ivendnext.com
ivn publish --public
```

| Command | What it does |
|---|---|
| `ivn login` | Signs this computer in, by a code in your browser. The token is in `~/.ivendnext/token`, readable by you alone. |
| `ivn token new <name> [--app <app>]` | A token for a build server, shown once; on the server it goes in `IVN_TOKEN`. |
| `ivn new <app> --from <sample> …` | Makes one app from one sample or several, in `apps/<app>/` of the current repository. |
| `ivn download <app>` | Writes the server's copy into `apps/<app>/`. |
| `ivn check` | The kit's check and the app's own tests, one verdict line. |
| `ivn push` | Checks the folder and uploads it as the next draft. A folder made with `start.py` becomes an app of your company's at its first push. `.env` files never leave your computer. |
| `ivn pull` | Brings the server's latest draft in and keeps your changes, marking a conflict as git marks one (needs git). |
| `ivn add <sample>` · `ivn take <sample>` | Adds a sample · takes a sample's newer version, keeping what you changed. |
| `ivn sandbox <address>` | Connects your sandbox, once. |
| `ivn secret <NAME>` | Sets one of the app's own settings. |
| `ivn secrets` | Prints each connection point's secret on your own sandbox. |
| `ivn try` | Uploads a changed folder, shows what installing it changes, asks you to agree, installs it on your sandbox and tests each connection point. |
| `ivn test` · `ivn test --local` | Tests each connection point again · on this laptop, with the test secret in `.env.local`. |
| `ivn publish --to <site>` | Sends it to a customer's sites, and prints the message for their administrator. With no `--to`, to every site it is on. `--own`: the sites are your own company's. |
| `ivn publish --public` | Lists it for every retailer. The card's fields go in `app.json`'s `card`: you are asked once. |
| `ivn status` · `ivn logs` | Where it stands, and any newer sample version · what its service logged. |
| `ivn rollback <version>` | Publishes an earlier version's content as a new, higher version. |
| `ivn remove-site <site>` · `ivn cancel` · `ivn handover <word>` | Stops new versions reaching a site · stops the service at the month's end · hands the app to another company. Each asks for the app's name first. |
| `ivn key <site>` | A paid listed app's key for one retailer's site. |
| `ivn package` | Writes `package.zip` for your own function host. |

Exit code: 0 done · 1 refused · 2 usage. To reach a test server, set `IVN_HOSTING_URL`.

**The one `app.json`:** the app's name and version, the service's fields, its settings, `card` (the App library's card: `title`, `summary`, `what`, `pictures`, `industries`, `price`, `setup`, `guide`), `base` (the version this folder is), `address` (the service's address, written when you publish) and `samples` (the record *Add a sample* reads). Leave `base`, `address` and `samples` to the tools.
