# Deploy NOKK on Render (free)

The repository includes a Render Blueprint in `render.yaml`. It deploys the
Python app as a web service and starts it through `render_start.py`. The normal
desktop command remains `python app.py`; it still listens on `127.0.0.1` by
default and does not require Render or Docker.

## Deploy

1. In Render, choose **New → Blueprint** and connect this GitHub repository.
2. Select the `main` branch and apply the Blueprint from `render.yaml`.
3. When prompted for `APP_PASSWORD`, enter a unique password of at least 16
   characters. Keep it private. The configured username is `nokk`.
4. Wait for the service to finish deploying, then open its `onrender.com` URL.
   The browser will ask for the username and password. Render provides HTTPS.

The startup wrapper binds to `0.0.0.0` and the `PORT` supplied by Render. It
requires HTTP Basic Authentication for both the website and its API; do not
remove the password or expose the service without another authentication layer.

## Important: free plan storage

Render's free web service does not provide a persistent disk. NOKK saves its
provider configuration (including the API key), planner, workflows, and Telegram
settings as local JSON files. Those files may be erased when the free service
restarts, sleeps, or is redeployed, so you may need to configure the app again.

Do not treat this free deployment as durable storage. If you need to keep data,
export/back it up before deployments, or use an external database/storage service
and adapt the app to use it. A Render environment variable cannot make the
instance filesystem persistent.
