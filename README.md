# Pathmark Release Hub

This repository is the Streamlit release hub for Pathmark.

## Current release

Version: v0.5.40  
Platform: Windows only for now

## Repository structure

```text
.gitignore
README.md
requirements.txt
latest_version.json
REPOSITORY_STRUCTURE.txt
app/
  main.py
  assets/
    pathmark.png
downloads/
  Pathmark_Local_App_Windows_v0_5_40.zip
.streamlit/
  config.toml
```

## Updating the release

1. Replace the Windows zip in `downloads/`.
2. Update `latest_version.json` with the new version, release date, and package filename.
3. Update this README and `REPOSITORY_STRUCTURE.txt` if the structure changes.
4. Deploy or allow Streamlit Community Cloud to redeploy from GitHub.

## Notes

Mac support has deliberately been removed from this hub for now so the Windows workflow can be stabilised first.
