import uvicorn
import logging

from .configuration import Settings


def main() -> None:
    settings = Settings.from_environment()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    uvicorn.run(
        "pipesor_rag_retrieval.api:app",
        host=settings.host,
        port=settings.port,
        access_log=False,
    )


if __name__ == "__main__":
    main()

