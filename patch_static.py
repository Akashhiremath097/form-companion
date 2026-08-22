import io

p = "backend/main.py"
c = io.open(p, encoding="utf-8").read()

if "StaticFiles" in c:
    print("Already patched")
    raise SystemExit

c = c.replace(
    "from fastapi import FastAPI",
    "from fastapi import FastAPI\nfrom fastapi.responses import FileResponse\nfrom fastapi.staticfiles import StaticFiles",
)

old = '@app.get("/")\ndef root() -> dict:\n    return {"service": "Accessible Form Assistant", "docs": "/docs"}'

new = """STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")

if os.path.isdir(STATIC_DIR):
    app.mount("/assets", StaticFiles(directory=os.path.join(STATIC_DIR, "assets")), name="assets")

    @app.get("/")
    def serve_index() -> FileResponse:
        return FileResponse(os.path.join(STATIC_DIR, "index.html"))

    @app.get("/{path:path}")
    def serve_spa(path: str) -> FileResponse:
        candidate = os.path.join(STATIC_DIR, path)
        if path and os.path.isfile(candidate):
            return FileResponse(candidate)
        return FileResponse(os.path.join(STATIC_DIR, "index.html"))

else:

    @app.get("/")
    def root() -> dict:
        return {"service": "Accessible Form Assistant", "docs": "/docs"}"""

if old not in c:
    print("ANCHOR NOT FOUND")
    raise SystemExit(1)

io.open(p, "w", encoding="utf-8", newline="\n").write(c.replace(old, new))
print("PATCHED main.py")
