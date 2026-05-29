# Development System Release Hub

This is the Streamlit Community Cloud landing/update hub for the Development System local app.

The hosted app does not write to the viewer's local folders. It provides a polished front door and download page for the local Windows package.

## Deploy to Streamlit Community Cloud

Upload this folder's contents to a GitHub repository.

Use this main file path:

```text
app/main.py
```

## Updating the downloadable local app

Replace the zip in:

```text
downloads/Development_System_Local_App_v0_5_15.zip
```

Then update:

```text
latest_version.json
```

Commit the changes to GitHub and reboot the Streamlit app.


## Launcher update

This release hub now downloads the local app package with a friendlier launcher. The launcher shows a progress bar and status updates instead of exposing the command/script output to ordinary users. Technical output is available through a Show details button if troubleshooting is needed.


## v3 package note

This release hub includes `downloads/Development_System_Local_App_v0_5_15_launcher_v3_with_exe.zip`, which contains the compiled `Start Development System.exe` launcher and the `.cmd` fallback.
