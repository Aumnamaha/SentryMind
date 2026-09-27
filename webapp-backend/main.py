from fastapi import FastAPI

app = FastAPI(title="Micor Hack API")


@app.get("/")
def read_root():
    return {"status": "ok", "message": "Backend API is running!"}


@app.get("/health")
def health_check():
    return {"status": "healthy"}
