# Screenshots

Evidence for the headline run: one `POST /posting` with
`PLATFORMS=telegram,discord,slack,bluesky,tumblr`, `5/5 success` in 1812 ms
(2026-11-17 07:48 UTC / 13:18 local).

| File | What it shows | Logged out? |
|---|---|---|
| `01-telegram.png` | `https://t.me/sp_autopost_test/5` — channel `testingChannel`, message with the CTA link, 17 Nov 13:18 | yes, Chrome Incognito |
| `02-discord.png` | Discord `#general` on `Royal King's server`; the 13:18 message from the `Autopost Test` app is this run's post | no, Discord app |
| `03-bluesky.png` | `https://bsky.app/profile/sujalpahwa30.bsky.social/post/3n2ikimutav2j` — author, text, link, 13:18 · 17 Nov 2026 | yes, Chrome Incognito |
| `04-slack.png` | Slack `TestingWorkspace → #posting-test`, messages from the `posting-api` app; the 1:18 PM one is this run | no, Slack web app |
| `05-tumblr.png` | `https://sujalpahwa30.tumblr.com/post/833514825848143872` — the post rendered on the blog | yes, Chrome Incognito |

The matching request, response, public-URL verification commands and server logs
are in [`../sample-run.txt`](../sample-run.txt).

Screenshots must not contain credentials. If a shot includes a webhook URL or an
access token, blur or crop it before committing. These five contain none: the
Slack shot shows workspace/channel ids only, and the Discord shot shows channel
content only.
