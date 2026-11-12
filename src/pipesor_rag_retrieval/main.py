import os

import uvicorn


def main() -> None:
    uvicorn.run(
        "pipesor_rag_retrieval.api:app",
        host=os.getenv("PIPESOR_RAG_HOST", "0.0.0.0"),
        port=int(os.getenv("PIPESOR_RAG_PORT", "8080")),
        access_log=False,
    )


if __name__ == "__main__":
    main()

