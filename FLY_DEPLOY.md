# Deploy NOKK on Fly.io

Fly.io can run this repository as a Dockerized Python web service. The regular
desktop launch (`python app.py`) is unchanged; Fly uses `fly_start.py`, which
listens on the container interface and requires HTTP Basic Authentication.

## Before you start

Fly.io is not a guaranteed free hosting provider. Check the current pricing in
your Fly.io account before creating the app or volume; the persistent volume and
running machine may incur charges. This setup uses a 1 GB volume and a small
shared-CPU machine, but that does not guarantee a free bill.

## Deploy

1. Install the Fly.io CLI (`flyctl`) and sign in with `fly auth login`.
2. In `fly.toml`, replace `nokk-ai-change-this-name` with a globally unique Fly
   app name. If desired, change `primary_region = "ams"` to a nearby region.
3. Create the app and its persistent volume in the same region:

   ```sh
   fly apps create YOUR-UNIQUE-APP-NAME
   fly volumes create nokk_data --region ams --size 1
   ```

   If you changed the region in `fly.toml`, use that region in the volume command.
4. Set a private login. Use a unique password with at least 16 characters; do
   not put it in `fly.toml` or commit it to GitHub:

   ```sh
   fly secrets set APP_USERNAME=nokk APP_PASSWORD='choose-a-long-unique-password'
   ```

5. Deploy from the repository root:

   ```sh
   fly deploy
   fly open
   ```

   The browser will ask for the username and password. HTTPS is enforced by
   `fly.toml`.

The volume is mounted at `/data`; `AI_CONFIG_FILE=/data/config.json` puts the
configuration, planner, workflows, and Telegram JSON files on that persistent
volume. Keep the volume: deleting it deletes those files. The app stores the AI
provider key in its config file, so keep the Fly app private to your account and
use a strong Basic Auth password.

## Desktop use

For local desktop use, continue starting the app with:

```sh
python app.py
```

This does not require Fly CLI, Docker, credentials, or internet access to start.
The Fly-only authentication wrapper is used only by the container's start
command. Locally, the app continues to listen on `127.0.0.1` by default.
