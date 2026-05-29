# Pathmark Release Hub

This repository deploys the Streamlit release hub for Pathmark.

Deploy with Streamlit Community Cloud using:

```text
app/main.py
```

## Repository contents

```text
app/
downloads/
.streamlit/
README.md
latest_version.json
requirements.txt
.gitignore
```

## Downloads

The `downloads/` folder contains the Windows and Mac local app packages shown on the release hub.

The Windows package intentionally does not include a prebuilt `.exe`. After downloading and extracting the Windows package, run:

```text
build_launcher_exe.bat
```

This creates:

```text
Start Pathmark.exe
```

The fallback launcher is:

```text
Start Pathmark.cmd
```

The Mac package includes `Start Pathmark.command` and an optional `Build Pathmark Launcher App.command` for building a local `.app` launcher on macOS.
