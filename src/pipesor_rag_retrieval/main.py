import uvicorn

from .configuration import Settings


def main() -> None:
    settings = Settings.from_environment()
    uvicorn.run(
        "pipesor_rag_retrieval.api:app",
        host=settings.host,
        port=settings.port,
        access_log=False,
    )


if __name__ == "__main__":
    main()

