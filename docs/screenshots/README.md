# Screenshots

These are the captured proofs referenced by the main README. Each one was taken
in a **private/incognito** window (except the chat platforms, where the message
is shown inside the channel it was delivered to).

| File | What it shows |
|---|---|
| `01-telegram.png` | `https://t.me/sp_autopost_test/5` open in incognito: channel `testingChannel` with the posted message and CTA link |
| `02-discord.png` | Discord `#general` in the `Autopost Test` server with the delivered message from the `Autopost Test` webhook |
| `03-bluesky.png` | `https://bsky.app/profile/sujalpahwa30.bsky.social/post/3n2ikimutav2j` in incognito: author, message and CTA link |
| `04-slack.png` | Slack `TestingWorkspace → #posting-test` with four messages delivered by the `posting-api` app |
| `05-tumblr.png` | `https://sujalpahwa30.tumblr.com/post/833514825848143872` in incognito: the post rendered on the blog |

All five were produced by a single `POST /posting` request
(`PLATFORMS=telegram,discord,slack,bluesky,tumblr`). The matching request,
response, verification commands and logs are in
[`../sample-run.txt`](../sample-run.txt).

Screenshots must not contain credentials. If a shot includes a webhook URL or an
access token, blur or crop it before committing.
