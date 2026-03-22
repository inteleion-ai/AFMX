        _static_dir = os.path.join(os.path.dirname(__file__), "static")
        if os.path.isdir(_static_dir):
            # Mount /assets, /afmx/assets etc. for Vite-built JS/CSS chunks
            _assets_dir = os.path.join(_static_dir, "assets")
            if os.path.isdir(_assets_dir):
                app.mount(
                    "/assets",
                    StaticFiles(directory=_assets_dir),
                    name="assets",
                )

            # Mount the whole static dir for any other top-level files (favicon, etc.)
            app.mount(
                "/afmx/static",
                StaticFiles(directory=_static_dir),
                name="static",
            )

        # ── SPA shell: every /afmx/ui/* route returns index.html ─────────────
        # This lets React Router handle client-side navigation correctly.
        # The built Vite SPA outputs index.html to afmx/static/.
        @app.get("/afmx/ui", include_in_schema=False)
        @app.get("/afmx/ui/{rest:path}", include_in_schema=False)
        async def ui_spa(rest: str = ""):
            from fastapi.responses import FileResponse
            # Vite build outputs to static/; index.html is the SPA shell.
            spa_index = os.path.join(os.path.dirname(__file__), "static", "index.html")
            if os.path.exists(spa_index):
                return FileResponse(spa_index, media_type="text/html")
            # Fallback: legacy single-file dashboard while SPA is not yet built
            legacy = os.path.join(os.path.dirname(__file__), "static", "dashboard.html")
            if os.path.exists(legacy):
                return FileResponse(legacy, media_type="text/html")
            return JSONResponse(
                status_code=404,
                content={
                    "error": "UI not found",
                    "hint":  "Run: cd afmx/dashboard && npm install && npm run build",
                },
            )