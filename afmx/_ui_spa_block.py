    # ── UI Dashboard (React SPA) ───────────────────────────────────────────────
    if settings.UI_ENABLED:
        _static_dir = os.path.join(os.path.dirname(__file__), "static")
        if os.path.isdir(_static_dir):
            # Vite outputs JS/CSS chunks to static/assets/
            _assets_dir = os.path.join(_static_dir, "assets")
            if os.path.isdir(_assets_dir):
                app.mount(
                    "/assets",
                    StaticFiles(directory=_assets_dir),
                    name="assets",
                )
            # Serve all other static files (favicon, etc.)
            app.mount(
                "/afmx/static",
                StaticFiles(directory=_static_dir),
                name="static",
            )

        # SPA shell — every /afmx/ui/* deep-link returns index.html
        # so React Router can take over client-side navigation.
        @app.get("/afmx/ui",           include_in_schema=False)
        @app.get("/afmx/ui/{rest:path}", include_in_schema=False)
        async def ui_spa(rest: str = ""):
            from fastapi.responses import FileResponse
            _dir = os.path.join(os.path.dirname(__file__), "static")
            # Vite SPA build → index.html
            spa = os.path.join(_dir, "index.html")
            if os.path.exists(spa):
                return FileResponse(spa, media_type="text/html")
            # Fallback: legacy single-file dashboard (old HTML file)
            legacy = os.path.join(_dir, "dashboard.html")
            if os.path.exists(legacy):
                return FileResponse(legacy, media_type="text/html")
            return JSONResponse(
                status_code=404,
                content={
                    "error": "UI not found",
                    "hint":  "cd afmx/dashboard && npm install && npm run build",
                },
            )