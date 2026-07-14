from fastapi import FastAPI

app = FastAPI(
    title="PCB Design Review Platform",
    description="Automated engineering design review for KiCad PCB projects.",
    version="0.1.0",
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
