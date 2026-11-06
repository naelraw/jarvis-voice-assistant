# JARVIS — a hands-free voice assistant for Windows

[Version française](README.md)

JARVIS is a **hands-free voice assistant for Windows** with a **phone web app** (tested on iPhone). You say
"OK Jarvis", it answers out loud and **acts on your PC**: open apps, launch a game, read and send mail, play
music, search the web, set reminders, take notes.

It is **French-first** (voice commands, UI and docs are in French) and built to stay **free**: it runs on a free
Gemini key (Google AI Studio), speech recognition runs locally (`faster-whisper`, NVIDIA GPU or CPU), and every other
service is optional.

> **Status: personal project, actively developed by one person.** It runs daily on the author's PC but has been
> tried on very few machines. Bug reports and hardware feedback are very welcome.

## Features

- **Voice**: live conversation with Gemini Live (PC and phone), "OK Jarvis" wake phrase, double hand-clap
  detection, local Whisper transcription.
- **On the PC**: apps and websites, games (JARVIS goes to sleep during a match), game clips through OBS, mail (IMAP),
  Google Calendar, reminders, timers, notes, music and YouTube, weather, news, Wikipedia, currency, VirusTotal
  (only a file's hash is sent, never the file).
- **Phone**: a web app (PWA) served by your PC over [Tailscale](https://tailscale.com) (free), with Pause / Mic /
  Keyboard buttons and **offline notes** that sync when the PC is reachable again.
- **Wake-on-LAN** for a desktop PC, through an always-on relay.
- **API connectors**: a page to plug in your own APIs (encrypted keys, protection against requests to the local network).
- **Camera window**: hand tracking (MediaPipe, downloaded on first use) to draw 3D shapes in the air.
- **Optional**: 3D model viewer and 3D printing, Android tablet as a second screen, a bridge to a Roblox Copilot,
  and a personal-site integration (`pcradar`, example only).

See [`docs/fonctions.md`](docs/fonctions.md) (French) for the full list.

## Install (Windows 10 / 11)

1. Get the repository (**Code → Download ZIP**, or `git clone`).
2. Open the `installation` folder and double-click **`INSTALLER JARVIS.bat`**. If Windows warns you, choose
   *More info → Run anyway* (the script is readable in `installation/installer.ps1`).
3. Wait 5–15 minutes: Python 3.13 if needed, the modules, shortcuts, start with Windows.
4. Paste your **Gemini key** when asked (free: <https://aistudio.google.com/apikey>). Everything else is optional.
5. The first launch downloads the speech model (~500 MB).
6. In **Settings**, set your first name ("Ton prénom"), then say **"OK Jarvis"** (in French), clap twice, or press
   `Ctrl+Alt+J`.

Manual install (developers):

```powershell
py -3.13 -m venv .venv
.venv\Scripts\pip install -r requirements.txt
# NVIDIA GPU only: .venv\Scripts\pip install -r requirements-nvidia.txt
.venv\Scripts\python jarvis_voice.py
```

## Good to know

- **Windows only** (DPAPI, UI Automation, native windows).
- **French commands and UI.** Code comments and docs are in French; English translations are a welcome contribution.
- **Privacy**: during a live conversation, **audio is sent to Google (Gemini API)**. Mail, calendar and other
  services are only used if you configure them. API keys are encrypted by Windows (DPAPI) under
  `%USERPROFILE%\.openjarvis\`, never in the repository.
- **Sensitive actions** (sending mail, shutting down, deleting) require spoken confirmation.
- The local server listens on `127.0.0.1:8765`. Phone access goes through Tailscale plus a pairing key; do not
  expose it to the internet any other way.

## Contributing

Contributions are welcome, even small ones (docs, translations, tests, reproduced bugs). See
[`CONTRIBUTING.md`](CONTRIBUTING.md). For security issues: [`SECURITY.md`](SECURITY.md).

## License

[MIT](LICENSE). Third-party services (Google Gemini, Groq, ElevenLabs, YouTube, …) have their own terms.
