# Pathmark Release Hub

This repository is the Streamlit release hub for Pathmark.

It should contain only:

- `app/`
- `downloads/`
- `.streamlit/`
- `README.md`
- `latest_version.json`
- `requirements.txt`
- `.gitignore`

The Windows package is build-first: users or maintainers run `build_launcher_exe.bat` inside the extracted Pathmark app package to create `Pathmark.exe`. The fallback launcher is `Start Pathmark.cmd`.
