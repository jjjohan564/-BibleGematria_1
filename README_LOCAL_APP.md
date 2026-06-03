# Bible Gematria Local App

## MacBook

Use `BibleGematria.command` for the full local app.

1. Double-click `BibleGematria.command`.
2. If macOS blocks it the first time, right-click it and choose `Open`.
3. The launcher starts MAMP MySQL, starts a local PHP server, and opens Bible Gematria in your browser.

The private Bible database stays on your Mac. This launcher does not upload SQL dumps or local data.

You can also open `macos/Bible Gematria.app`, but the `.command` file is easier to troubleshoot because it shows status text.

## iPhone

An iPhone cannot directly run this PHP/MySQL app like the Mac can. You have two practical options:

1. For the hosted version, open the website in Safari and use `Share > Add to Home Screen`.
2. For the full local version from your iPhone, double-click `BibleGematria-iPhone-Share.command` on the Mac and then open one of the printed local network URLs in Safari on your iPhone.

The iPhone-share launcher only works while the Mac is awake and connected to the same hotspot/Wi-Fi. It intentionally opens the local server to your own local network, so use it only on a network you trust.

## Stopping It

If you started the app with the launcher, the PHP server process id is written to `logs/php_server_8888.pid`.

Run this from the project folder if you want to stop the PHP server:

```sh
kill $(cat logs/php_server_8888.pid)
```

For the iPhone-share launcher, use `logs/php_server_8887.pid` instead.

MAMP MySQL may keep running in the background. You can stop it from the MAMP app if needed.
