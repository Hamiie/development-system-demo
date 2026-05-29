# Development System Release Hub v6

This repository is the Streamlit Community Cloud release hub for Development System.

It does not run the real local-file app. It provides:

- a polished landing page
- a download for the latest local Windows app package
- separate flows for new users and existing users updating the app
- clear safety wording that the app folder is replaceable, but the Development folder is not

Deploy with Streamlit Community Cloud using:

```text
app/main.py
```

## Updating the local package

Replace the zip inside `downloads/` and update `latest_version.json`.

The local app package should not include user data, backups, Markdown folders, exports, tasklists, or a live database.
